"""Evidence baselines, intentionally separate from manual labels."""

import math
import numpy as np


def validate_rallies(rallies, duration, clip_last=False):
    validated = []
    for row in rallies:
        start, end = float(row["start_seconds"]), float(row["end_seconds"])
        if clip_last and duration < end <= duration + 1:
            end = duration
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration + 1e-5:
            raise ValueError(f"Invalid interval: {start}, {end}; duration={duration}")
        if validated and start < validated[-1]["end_seconds"] - 1e-5:
            raise ValueError("Rallies must be ordered and non-overlapping")
        validated.append({**row, "start_seconds": start, "end_seconds": min(duration, end)})
    return validated


def group_times(times, gap):
    groups = []
    for stamp in times:
        if not groups or stamp - groups[-1][-1] > gap:
            groups.append([stamp])
        else:
            groups[-1].append(stamp)
    return groups


def _interval(start, end, duration, reason, review=False):
    return {"start_seconds": round(max(0, start), 4),
            "end_seconds": min(duration, round(end, 4)),
            "evidence": reason, "needs_review": review}


def segment(meta, rows, cuts, onsets, mode="hybrid", gap=3.2):
    duration = meta["duration_seconds"]
    if mode in ("scene", "edited"):
        bounds = [0, *[c for c in cuts if 0 < c < duration], duration]
        return [_interval(a, b, duration, "scene interval; scene != certified rally", True)
                for a, b in zip(bounds, bounds[1:])], []
    values = np.asarray([r["motion"] for r in rows])
    if len(values):
        floor = float(np.percentile(values, 25))
        spread = float(np.median(np.abs(values - np.median(values))))
        threshold = max(.0015, floor + 2 * spread)
        active = [r["t"] for r in rows if r["motion"] > threshold]
    else:
        threshold, active = 0, []
    if mode == "visual":
        groups = group_times(active, 1.5)
        intervals = [_interval(g[0]-.75, g[-1]+.75, duration,
                               "sampled OpenCV motion; play semantics unverified", True)
                     for g in groups if g[-1]-g[0] >= 1]
    else:
        intervals = []
        uncertain = []
        for g in group_times(onsets, gap):
            a, b = max(0, g[0]-.75), min(duration, g[-1]+.75)
            support = [r for r in rows if a <= r["t"] <= b]
            moving = sum(r["motion"] > threshold for r in support)
            # No model -> no person gating. No audio is never silently replaced.
            visual_support = moving >= min(2, len(support)) and len(support) > 0
            accepted = len(g) >= 2 and (mode == "audio" or visual_support)
            item = _interval(a, b, duration, f"{len(g)} audio transients" +
                             (" + sampled motion" if visual_support and mode == "hybrid" else ""),
                             review=True)
            (intervals if accepted else uncertain).append(item)
        if mode == "hybrid" and not onsets:
            return [], [_interval(0, duration, duration,
                "no audio onset support; use visual mode explicitly", True)]
        # User's task is untrimmed training footage. Editing/scene discontinuities
        # must not create tennis rally boundaries, including in the hybrid path.
        return _make_disjoint(intervals, duration), uncertain
    return _make_disjoint(intervals, duration), []


def _make_disjoint(intervals, duration):
    for left, right in zip(intervals, intervals[1:]):
        if left["end_seconds"] > right["start_seconds"]:
            middle = (left["end_seconds"] + right["start_seconds"]) / 2
            left["end_seconds"] = right["start_seconds"] = middle
    return validate_rallies(intervals, duration)
