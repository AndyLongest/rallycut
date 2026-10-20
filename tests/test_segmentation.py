import copy
import math

import pytest

from rallycut.evaluate import evaluate, evaluate_end_events
from rallycut.segment import segment, validate_rallies


def interval(a, b):
    return {"start_seconds": a, "end_seconds": b}


def test_whole_video_does_not_get_credit_for_multiple_rallies():
    score = evaluate([interval(0, 20)], [interval(0, 5), interval(5, 10), interval(10, 20)], 20)
    assert score["internal_boundaries"]["recall"] == 0
    assert score["segments"]["recall"] == pytest.approx(1/3)


def test_boundaries_are_one_to_one_and_count_extra_predictions():
    score = evaluate([interval(0, 4.7), interval(4.7, 5.2), interval(5.2, 10)],
                     [interval(0, 5), interval(5, 10)], 10)
    assert score["internal_boundaries"]["matched"] == 1
    assert score["internal_boundaries"]["false_positives"] == 1


def test_human_end_rounding_is_clipped_without_modifying_labels():
    labels = [interval(0, 9), interval(9, 58)]
    original = copy.deepcopy(labels)
    score = evaluate([interval(0, 9), interval(9, 57.9)], labels, 57.9)
    assert score["internal_boundaries"]["f1"] == 1
    assert labels == original


@pytest.mark.parametrize("rallies", [[interval(-1, 2)], [interval(2, 1)],
    [interval(0, math.nan)], [interval(0, math.inf)], [interval(0, 3), interval(2, 4)]])
def test_invalid_intervals_rejected(rallies):
    with pytest.raises(ValueError):
        validate_rallies(rallies, 10)


def test_empty_prediction_is_a_miss():
    result = evaluate([], [interval(0, 5), interval(5, 10)], 10)
    assert result["internal_boundaries"]["false_negatives"] == 1
    assert result["segments"]["false_negatives"] == 2


def test_scene_mode_never_assumes_five_rallies():
    result, uncertain = segment({"duration_seconds": 30}, [], [4, 19], [], "edited")
    assert [(r["start_seconds"], r["end_seconds"]) for r in result] == [(0, 4), (4, 19), (19, 30)]
    assert all(r["needs_review"] for r in result)
    assert not uncertain


def test_no_audio_never_creates_confirmed_hybrid_rallies():
    result, uncertain = segment({"duration_seconds": 30}, [{"t": 2, "motion": .8}], [], [], "hybrid")
    assert not result
    assert "no audio" in uncertain[0]["evidence"]


def test_single_hit_is_retained_for_ace_review():
    result, uncertain = segment({"duration_seconds": 30}, [], [], [4], "audio")
    assert not result
    assert len(uncertain) == 1


def test_end_of_video_open_cluster_is_flushed():
    result, _ = segment({"duration_seconds": 10}, [], [], [8, 9.8], "audio")
    assert result[0]["end_seconds"] == 10


@pytest.mark.parametrize("mode", ["audio", "visual", "hybrid"])
def test_scene_cuts_cannot_create_boundaries_in_training_video_modes(mode):
    rows = [{"t": t, "motion": .01 if t in (1, 2, 3, 14, 15, 16) else 0}
            for t in range(20)]
    hits = [1, 2, 3, 14, 15, 16]
    expected = segment({"duration_seconds": 20}, rows, [], hits, mode)
    actual = segment({"duration_seconds": 20}, rows, [2.3, 8, 15.3], hits, mode)
    assert len(expected[0]) == 2
    assert actual == expected


def test_end_only_ground_truth_does_not_invent_starts_or_iou():
    labels={'events':[{'end_seconds':5},{'end_seconds':12}]}
    score=evaluate_end_events([interval(2,5.2),interval(9,12.5)],labels,20,1)
    assert score['ends']['matched']==2
    assert score['start_accuracy'] is None and score['segment_iou'] is None
    assert labels=={'events':[{'end_seconds':5},{'end_seconds':12}]}


def test_duplicate_end_predictions_cannot_inflate_recall():
    labels={'events':[{'end_seconds':5}]}
    score=evaluate_end_events([interval(0,4.8),interval(4.8,5.2)],labels,10,1)
    assert score['ends']['matched']==1
    assert score['ends']['false_positives']==1
