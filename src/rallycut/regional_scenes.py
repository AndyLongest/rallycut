"""Opt-in same-camera edit candidates using upstream PySceneDetect on three regions."""
import time

import cv2
from scenedetect.detectors import AdaptiveDetector

from .media import sampled_frames


REGIONS = {
    "global": (0.0, 1.0, 0.0, 1.0),
    "left_lower": (0.0, .5, .3, 1.0),
    "right_lower": (.5, 1.0, .3, 1.0),
}


class RegionalSceneDetector:
    """All regions share thresholds; no labels, poses or audio are consumed."""
    def __init__(self, fps=4):
        if not 0 < fps <= 30:
            raise ValueError("fps must be in (0,30]")
        self.fps = fps
        self.detectors = {
            name: AdaptiveDetector(
                adaptive_threshold=3.0, min_scene_len=max(1, round(2*fps)),
                window_width=max(1, round(.75*fps)), min_content_val=.5, luma_only=True)
            for name in REGIONS
        }
        self.cuts = {name: [] for name in REGIONS}

    def process(self, index, frame):
        h, w = frame.shape[:2]
        for name, (x1, x2, y1, y2) in REGIONS.items():
            crop = frame[int(h*y1):int(h*y2), int(w*x1):int(w*x2)]
            self.cuts[name].extend(
                float(t/self.fps) for t in self.detectors[name].process_frame(index, crop))

    def candidates(self):
        return sorted({t for cuts in self.cuts.values() for t in cuts})


def analyze_regional_scenes(meta, fps=4, width=320, threads=2):
    started = time.perf_counter()
    cv2.setNumThreads(threads)
    detector = RegionalSceneDetector(fps)
    count = 0
    with sampled_frames(meta, fps, width, threads) as frames:
        for index, (_, frame) in enumerate(frames):
            detector.process(index, frame)
            count += 1
    cuts = detector.candidates()
    edges = [0.0, *cuts, meta["duration_seconds"]]
    elapsed = time.perf_counter()-started
    return {
        "schema_version": 1, "status": "candidate_predictions", "method": "edited_regional",
        "task_kind": "edit_boundary_diagnostic", "validated_for_untrimmed_training": False,
        "video": dict(meta),
        "rallies": [{"start_seconds": a, "end_seconds": b, "needs_review": True,
                    "evidence": "regional scene interval; scene != certified rally"}
                   for a, b in zip(edges, edges[1:])],
        "scene_cut_candidates_seconds": cuts, "audio_onsets_seconds": [],
        "audio_stats": {"available": meta.get("audio_stream_index") is not None, "analyzed": False},
        "visual_stats": {
            "scene_profile": "regional", "sample_fps": fps, "sampled_frames": count,
            "analysis_width": frame.shape[1], "analysis_height": frame.shape[0],
            "threads": threads, "device": "CPU", "audio_used": False,
            "scene_detector": "PySceneDetect AdaptiveDetector, full + left/right lower70%",
            "adaptive_threshold": 3.0, "min_content_val": .5, "luma_only": True,
            "window_seconds": .75, "min_scene_seconds": 2,
            "regions_normalized_xyxy": {k: [x1,y1,x2,y2] for k,(x1,x2,y1,y2) in REGIONS.items()},
            "region_cut_candidates_seconds": detector.cuts,
            "sampling_time_uncertainty_seconds": 1/fps,
        },
        "wall_seconds": elapsed,
        "timings": {"visual_with_decode_seconds": elapsed},
        "limitations": [
            "Experimental regional profile selected on a development video; no held-out accuracy claim.",
            "Fast movement, occlusion and entering/leaving the frame may trigger false edit candidates.",
            "Scene cuts alone do not prove rally endings; regions use fixed coordinates, not person tracking.",
        ],
    }


def validate_scene_profile(scenes, requested):
    """Reject cached full-frame results when the caller explicitly asks for regions."""
    actual = scenes.get("visual_stats", {}).get("scene_profile", "global")
    if actual != requested:
        raise ValueError(f"Saved scene profile {actual!r} differs from requested {requested!r}")
