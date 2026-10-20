"""Experimental union of boundary candidates, separate from play classification."""
import math
from pathlib import Path
import time

from .segment import validate_rallies


def fuse_predictions(rallyclip, scenes, merge_tolerance=1.0, short_seconds=1.0):
    """Keep both routes' boundaries; split predicted play without inventing play.

    A scene point within tolerance snaps to the nearest existing RallyClip
    boundary. Distinct RallyClip starts/ends are never collapsed, so short
    attempts survive. Every other scene point is retained, even outside play.
    """
    started = time.perf_counter()
    if not math.isfinite(merge_tolerance) or merge_tolerance < 0:
        raise ValueError("merge_tolerance must be finite and nonnegative")
    if not math.isfinite(short_seconds) or short_seconds <= 0:
        raise ValueError("short_seconds must be finite and positive")
    video, other = rallyclip["video"], scenes["video"]
    if Path(video["path"]).resolve() != Path(other["path"]).resolve():
        raise ValueError("Fusion requires exactly the same source video")
    duration = float(video["duration_seconds"])
    other_duration = float(other["duration_seconds"])
    if not math.isfinite(duration) or not math.isfinite(other_duration) or duration <= 0 or abs(duration-other_duration) > 1e-4:
        raise ValueError("Fusion source durations differ or are invalid")
    if scenes.get("task_kind") != "edit_boundary_diagnostic":
        raise ValueError("The scene input must be a scene/edit diagnostic")
    if "scene_cut_candidates_seconds" not in scenes:
        raise ValueError("The scene input is missing explicit cut candidates")
    rallies = validate_rallies(rallyclip["rallies"], duration)
    cuts = sorted(set(float(t) for t in scenes["scene_cut_candidates_seconds"]))
    if any(not math.isfinite(t) or not 0 < t < duration for t in cuts):
        raise ValueError("Scene points must be finite and strictly inside the video")
    points = {}
    for i, interval in enumerate(rallies):
        for kind in ("start", "end"):
            t = interval[f"{kind}_seconds"]
            point = points.setdefault(t, {"seconds": t, "sources": ["RallyClip"], "events": []})
            point["events"].append({"source": "RallyClip", "kind": kind,
                                    "original_seconds": t, "rally_index": i})
    anchors = sorted(points)
    snapped = 0
    for t in cuts:
        nearest = min(anchors, key=lambda x: (abs(x-t), x)) if anchors else None
        if nearest is not None and abs(nearest-t) <= merge_tolerance + 1e-9:
            snapped += 1
            point = points[nearest]
        else:
            point = points.setdefault(t, {"seconds": t, "sources": [], "events": []})
        if "PySceneDetect" not in point["sources"]:
            point["sources"].append("PySceneDetect")
        point["events"].append({"source": "PySceneDetect", "kind": "cut", "original_seconds": t})
    boundaries = [points[t] for t in sorted(points)]
    for point in boundaries:
        point["agreement"] = "both" if len(point["sources"]) == 2 else "single_source"
        point["needs_review"] = True
    edges = sorted({0.0, duration, *points})
    timeline = []
    for start, end in zip(edges, edges[1:]):
        if end <= start:
            continue
        middle = (start+end)/2
        parent = next((i for i, row in enumerate(rallies)
                       if row["start_seconds"] <= middle < row["end_seconds"]), None)
        left = points.get(start, {}).get("sources", ["video_edge"])
        right = points.get(end, {}).get("sources", ["video_edge"])
        timeline.append({"start_seconds": start, "end_seconds": end,
                         "parent_rally_index": parent,
                         "activity_state": "rallyclip_candidate" if parent is not None else "outside_rallyclip_candidate",
                         "start_sources": list(left), "end_sources": list(right),
                         "short_fragment": end-start < short_seconds,
                         "needs_review": True,
                         "evidence": f"boundary union; start={'+'.join(left)}; end={'+'.join(right)}; "
                                     + (f"RallyClip candidate {parent+1}" if parent is not None else "no RallyClip play evidence")})
    play = [row for row in timeline if row["parent_rally_index"] is not None]
    outside = [row for row in timeline if row["parent_rally_index"] is None]
    elapsed = time.perf_counter()-started
    source_seconds = sum(float(r.get("wall_seconds", 0)) for r in (rallyclip, scenes))
    return {"schema_version": 1, "status": "candidate_predictions", "method": "boundary_union_cpu",
            "task_kind": "experimental_boundary_union", "validated_for_untrimmed_training": False,
            "video": dict(video), "rallies": validate_rallies(play, duration),
            "timeline_segments": timeline,
            "outside_activity_segments": outside,
            "boundaries": boundaries,
            "wall_seconds": source_seconds+elapsed,
            "timings": {"fusion_seconds": elapsed, "recorded_source_processing_seconds": source_seconds,
                        "timing_basis": "Sum of source-run measurements plus fusion; not measured end-to-end."},
            "fusion": {"merge_tolerance_seconds": merge_tolerance, "short_threshold_seconds": short_seconds,
                       "merge_rule": "Scene points snap to nearest RallyClip boundary; distinct RallyClip boundaries preserved.",
                       "raw_scene_points": cuts, "snapped_scene_points": snapped,
                       "source_methods": [rallyclip["method"], scenes["method"]],
                       "statistics": {"original_rallyclip_candidates": len(rallies), "fused_play_candidates": len(play),
                                      "added_play_splits": len(play)-len(rallies), "union_boundaries": len(boundaries),
                                      "both_source_boundaries": sum(p["agreement"] == "both" for p in boundaries),
                                      "scene_only_boundaries": sum(p["sources"] == ["PySceneDetect"] for p in boundaries),
                                      "short_play_fragments": sum(r["short_fragment"] for r in play),
                                      "all_partition_segments": len(timeline),
                                      "short_partition_fragments": sum(r["short_fragment"] for r in timeline),
                                      "outside_activity_segments": len(outside)}},
            "limitations": ["Experimental candidate-boundary union; scene cuts do not prove rally endings.",
                            "All union points are retained in boundaries/timeline_segments, including outside predicted play.",
                            "rallies contains only the split RallyClip activity candidates; outside intervals are not relabelled as play.",
                            "Single-source and short fragments require review; short attempts are not deleted.",
                            "Source agreement is not a calibrated probability. CPU RallyClip still uses pose features."]}
