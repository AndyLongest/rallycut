"""Visual-only union which preserves activity rejected solely for excessive length."""
from copy import deepcopy
import math

import numpy as np

from .fusion import fuse_predictions
from .segment import validate_rallies


def recover_long_candidates(prediction, scores, capture, decoder):
    """Replay the frozen decoder, then recover only its too-long threshold runs.

    Keep original accepted intervals and their boundaries unchanged. Never infer
    activity from a scene cut. The original cap still applies in standalone mode;
    this new union policy retains long activity with explicit review flags.
    """
    config = decoder.HeatmapDecodeConfig(**capture["config"])
    if config.mode != "hybrid":
        raise ValueError("Visual union requires the shipped hybrid score decoder")
    times = np.asarray(scores["timestamps"], dtype=np.float64)
    tracks = [np.asarray(scores[k], dtype=np.float64) for k in ("pointness", "start", "end")]
    if (times.ndim != 1 or not times.size or not np.isfinite(times).all()
            or np.any(np.diff(times) <= 0)
            or any(t.shape != times.shape or not np.isfinite(t).all()
                   or np.any((t < 0) | (t > 1)) for t in tracks)):
        raise ValueError("Invalid captured score tracks or timestamps")
    if capture.get("sample_count") != times.size:
        raise ValueError("Score capture sample count differs")
    duration = float(prediction["video"]["duration_seconds"])
    if times[0] < 0 or times[-1] > duration + 1e-4:
        raise ValueError("Score timestamps outside video")
    original = validate_rallies(prediction["rallies"], duration)
    replay = decoder.decode_heatmap_segments(*tracks, times, config)
    expected = [(r["start_seconds"], r["end_seconds"]) for r in original]
    if len(replay) != len(expected) or not np.allclose(
            np.asarray(replay), np.asarray(expected), rtol=0, atol=1e-6):
        raise ValueError("Captured scores do not reproduce the saved RallyClip result")
    if capture.get("decoded_intervals") is None or len(capture["decoded_intervals"]) != len(replay) or not np.allclose(
            np.asarray(capture["decoded_intervals"]), np.asarray(replay), rtol=0, atol=1e-6):
        raise ValueError("Capture metadata disagrees with replay")
    point, start, end = tracks
    detected = point if config.smooth_sigma_frames is None else decoder._gaussian_smooth(point, config.smooth_sigma_frames)
    restored = []
    for first, last in decoder._runs_above(detected, config.threshold):
        left = decoder._soft_argmax_time(start, times, first, config._refine_window())
        right = decoder._soft_argmax_time(end, times, last, config._refine_window())
        if right <= left:
            left, right = float(times[first]), float(times[last])
        length = right - left
        if length <= 0 or length < config.min_duration_sec or length <= config.max_duration_sec:
            continue
        restored.append({"start_seconds": float(left), "end_seconds": float(right),
                         "restored_from_duration_filter": True, "needs_review": True,
                         "evidence": "RallyClip score run rejected only by max_duration_sec; retained for visual union"})
    activity = deepcopy(prediction)
    activity["method"] = prediction["method"] + "_long_activity_retained"
    activity["rallies"] = validate_rallies(
        sorted(original + restored, key=lambda r: r["start_seconds"]), duration)
    activity["activity_recovery"] = {
        "original_final_candidates": len(original),
        "restored_candidates": restored,
        "original_duration_limit_seconds": config.max_duration_sec,
        "decoder_replay_verified": True,
        "policy": "Keep original results plus only score-supported too-long runs; do not delete long union fragments.",
    }
    return activity


def fuse_visual_activity(activity, scenes, merge_tolerance=1.0, short_seconds=1.0):
    result = fuse_predictions(activity, scenes, merge_tolerance, short_seconds)
    recovery = activity["activity_recovery"]
    limit = recovery["original_duration_limit_seconds"]
    if not math.isfinite(limit) or limit <= 0:
        raise ValueError("Invalid original duration cap")
    for collection in ("rallies", "timeline_segments", "outside_activity_segments"):
        for row in result[collection]:
            parent = row.get("parent_rally_index")
            row["restored_long_activity"] = bool(
                parent is not None and activity["rallies"][parent].get("restored_from_duration_filter"))
            row["exceeds_original_duration_limit"] = row["end_seconds"] - row["start_seconds"] > limit
    result["pipeline_version"] = "visual_union_v2"
    result["activity_recovery"] = deepcopy(recovery)
    result["audio_used"] = False
    result["fusion"]["statistics"]["original_final_candidates"] = recovery["original_final_candidates"]
    result["fusion"]["statistics"]["restored_long_candidates"] = len(recovery["restored_candidates"])
    result["limitations"].append(
        "This union explicitly restores overlong score-supported activity; final fragments above the original cap are kept for review.")
    return result
