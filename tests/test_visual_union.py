"""Policy regressions: rejected long activity must survive scene-boundary union."""
from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from rallycut.visual_union import recover_long_candidates, fuse_visual_activity


@dataclass
class Config:
    mode: str = "hybrid"
    threshold: float = .5
    min_duration_sec: float = .3
    max_duration_sec: float = 60
    smooth_sigma_frames: object = None
    def _refine_window(self):
        return 1


def fixture(runs=((0, 172),), accepted=()):
    # Mock only the upstream decoder interface; assertions target fusion policy.
    decoder = SimpleNamespace(
        HeatmapDecodeConfig=Config,
        _runs_above=lambda *_: runs,
        _soft_argmax_time=lambda _, times, i, window: float(times[i]),
        decode_heatmap_segments=lambda *args: list(accepted))
    scores = {"timestamps": np.arange(174, dtype=float),
              **{k: np.ones(174) for k in ("pointness", "start", "end")}}
    video = {"path": "same.mp4", "duration_seconds": 174}
    prediction = {"video": video, "method": "rallyclip",
                  "rallies": [{"start_seconds": a, "end_seconds": b} for a, b in accepted]}
    capture = {"config": {}, "sample_count": 174, "decoded_intervals": list(accepted)}
    scene = {"video": video, "method": "edited", "task_kind": "edit_boundary_diagnostic",
             "scene_cut_candidates_seconds": [90]}
    return prediction, scores, capture, decoder, scene


def test_zero_final_results_recover_two_segments_even_if_both_exceed_old_cap():
    prediction, scores, capture, decoder, scene = fixture()
    original = deepcopy(prediction)
    activity = recover_long_candidates(prediction, scores, capture, decoder)
    result = fuse_visual_activity(activity, scene)
    assert [(r["start_seconds"], r["end_seconds"]) for r in result["rallies"]] == [(0,90),(90,172)]
    assert all(r["exceeds_original_duration_limit"] and r["restored_long_activity"] for r in result["rallies"])
    assert result["activity_recovery"]["original_final_candidates"] == 0
    assert result["boundaries"][1]["sources"] == ["PySceneDetect"]
    assert prediction == original


def test_scene_cut_without_score_activity_does_not_invent_a_rally():
    prediction, scores, capture, decoder, scene = fixture(runs=())
    scores["pointness"][:] = 0
    result = fuse_visual_activity(recover_long_candidates(prediction,scores,capture,decoder),scene)
    assert result["rallies"] == []
    assert len(result["timeline_segments"]) == 2


def test_original_short_rally_boundaries_and_overlong_activity_are_both_kept():
    prediction, scores, capture, decoder, scene = fixture(runs=((1,2),(5,172)),accepted=((1,2),))
    result = fuse_visual_activity(recover_long_candidates(prediction,scores,capture,decoder),scene)
    assert [(r["start_seconds"], r["end_seconds"]) for r in result["rallies"]] == [(1,2),(5,90),(90,172)]
    assert not result["rallies"][0]["restored_long_activity"]


def test_no_scene_cut_keeps_long_activity_for_review_without_arbitrary_sixty_second_chunks():
    prediction,scores,capture,decoder,scene=fixture()
    scene["scene_cut_candidates_seconds"]=[]
    result=fuse_visual_activity(recover_long_candidates(prediction,scores,capture,decoder),scene)
    assert len(result["rallies"]) == 1
    assert result["rallies"][0]["end_seconds"] == 172
    assert result["rallies"][0]["needs_review"]


def test_replay_mismatch_and_invalid_scores_fail_explicitly():
    prediction,scores,capture,decoder,_=fixture()
    prediction["rallies"]=[{"start_seconds":1,"end_seconds":2}]
    with pytest.raises(ValueError,match="reproduce"):
        recover_long_candidates(prediction,scores,capture,decoder)
    scores["pointness"][5]=np.nan
    with pytest.raises(ValueError,match="Invalid"):
        recover_long_candidates(prediction,scores,capture,decoder)
