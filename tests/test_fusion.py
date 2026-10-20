from copy import deepcopy
import csv
import json

import pytest

from rallycut.fusion import fuse_predictions


def sources(intervals, cuts, duration=20):
    video = {"path": "same-video.mp4", "duration_seconds": duration}
    return ({"method": "rallyclip", "video": video,
             "rallies": [{"start_seconds": a, "end_seconds": b} for a,b in intervals]},
            {"method": "edited", "task_kind": "edit_boundary_diagnostic", "video": video,
             "scene_cut_candidates_seconds": cuts})


def test_complementary_cut_splits_play_and_preserves_outside_boundary():
    r, s = sources([(2, 10), (14, 18)], [6, 12])
    original = deepcopy((r,s))
    result = fuse_predictions(r, s)
    assert [(x["start_seconds"], x["end_seconds"]) for x in result["rallies"]] == [(2,6),(6,10),(14,18)]
    assert any(p["seconds"] == 12 and p["sources"] == ["PySceneDetect"] for p in result["boundaries"])
    assert all(not (x["start_seconds"] <= 12 < x["end_seconds"]) for x in result["rallies"])
    assert (r,s) == original
    assert sum(x["end_seconds"]-x["start_seconds"] for x in result["timeline_segments"]) == 20


def test_nearby_cut_has_both_sources_but_short_rally_survives():
    r,s = sources([(2,2.4),(5,12)], [2.3,12.5])
    result = fuse_predictions(r,s,merge_tolerance=1)
    assert len(result["rallies"]) == 2
    assert result["rallies"][0]["short_fragment"]
    assert {p["seconds"] for p in result["boundaries"]} == {2,2.4,5,12}
    assert next(p for p in result["boundaries"] if p["seconds"] == 2.4)["agreement"] == "both"
    assert result["fusion"]["snapped_scene_points"] == 2


def test_no_transitive_deduplication_and_no_short_fragment_deletion():
    r,s = sources([(1,10)], [4,4.8,5.6])
    result = fuse_predictions(r,s)
    assert len(result["rallies"]) == 4
    assert result["fusion"]["statistics"]["short_play_fragments"] == 2
    assert len([p for p in result["boundaries"] if p["sources"] == ["PySceneDetect"]]) == 3


def test_empty_activity_keeps_scene_timeline_without_inventing_play():
    r,s = sources([], [8])
    result = fuse_predictions(r,s)
    assert result["rallies"] == []
    assert len(result["timeline_segments"]) == 2
    assert result["boundaries"][0]["seconds"] == 8


@pytest.mark.parametrize("cut", [float("nan"),float("inf"),-1,0,20,21])
def test_invalid_scene_point_is_rejected(cut):
    with pytest.raises(ValueError):
        fuse_predictions(*sources([(2,10)], [cut]))


def test_cross_video_and_cross_duration_results_are_rejected():
    r,s = sources([(2,10)], [5])
    s=deepcopy(s);s["video"]["path"]="other-video.mp4"
    with pytest.raises(ValueError,match="same source"):
        fuse_predictions(r,s)
    r,s = sources([(2,10)], [5])
    s=deepcopy(s);s["video"]["duration_seconds"] = 21
    with pytest.raises(ValueError,match="durations"):
        fuse_predictions(r,s)


def test_cli_preserves_full_partition_and_source_exports_without_fake_accuracy(tmp_path):
    from rallycut.cli import main
    r,s = sources([(2,10)], [6,12])
    r["video"]["path"] = str(tmp_path/"input.mp4")
    for name, value in (("rallyclip",r),("scene",s)):
        (tmp_path/f"{name}.json").write_text(json.dumps(value),encoding="utf-8")
    out=tmp_path/"output"
    main(["fuse",str(tmp_path/"rallyclip.json"),str(tmp_path/"scene.json"),"--output",str(out)])
    result=json.loads((out/"rallies.json").read_text(encoding="utf-8"))
    assert "evaluation" not in result
    assert len(result["rallies"]) == 2 and len(result["timeline_segments"]) == 5
    with (out/"boundaries.csv").open(encoding="utf-8-sig",newline="") as stream:
        exported=list(csv.DictReader(stream))
    assert len(exported) == 4
    assert any(row["seconds"] == "12.0" and row["sources"] == "PySceneDetect" for row in exported)
    with (out/"timeline_segments.csv").open(encoding="utf-8-sig",newline="") as stream:
        exported=list(csv.DictReader(stream))
    assert len(exported) == 5 and sum(row["activity_state"] == "outside_rallyclip_candidate" for row in exported) == 3
