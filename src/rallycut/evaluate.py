"""One-to-one matching, with internal boundaries and segment overlap separate."""

import numpy as np
from scipy.optimize import linear_sum_assignment

from .segment import validate_rallies


def _scores(matches, predictions, truth):
    precision = matches / predictions if predictions else float(truth == 0)
    recall = matches / truth if truth else float(predictions == 0)
    return {"precision": precision, "recall": recall,
            "f1": 2*precision*recall/(precision+recall) if precision+recall else 0,
            "matched": matches, "predicted_count": predictions, "manual_count": truth,
            "false_positives": predictions-matches, "false_negatives": truth-matches}


def boundaries(rallies, duration):
    # Include starts as well as ends, exclude trivial video edges, deduplicate.
    return sorted({round(r[k], 4) for r in rallies for k in ("start_seconds", "end_seconds")
                   if .05 < r[k] < duration-.05})


def evaluate(predicted, labelled, duration, tolerance=1.0, min_iou=.5):
    if tolerance < 0 or not 0 < min_iou <= 1:
        raise ValueError("Invalid evaluation tolerance or IoU")
    predicted = validate_rallies(predicted, duration)
    labelled = validate_rallies(labelled, duration, clip_last=True)
    p, g = boundaries(predicted, duration), boundaries(labelled, duration)
    errors = []
    if p and g:
        costs = np.abs(np.asarray(p)[:, None] - np.asarray(g)[None, :])
        # Large penalty maximizes match count before minimizing timing error.
        penalty = (len(p)+len(g)+1) * (max(duration, 1)+1)
        a, b = linear_sum_assignment(np.where(costs <= tolerance, costs, penalty))
        errors = [float(costs[i,j]) for i,j in zip(a,b) if costs[i,j] <= tolerance]
    boundary = {**_scores(len(errors), len(p), len(g)),
                "tolerance_seconds": tolerance,
                "mean_abs_error_seconds": float(np.mean(errors)) if errors else None,
                "predicted_seconds": p, "manual_seconds": g}
    matched = []
    if predicted and labelled:
        ious = np.zeros((len(predicted), len(labelled)))
        for i, pr in enumerate(predicted):
            for j, gt in enumerate(labelled):
                intersection = max(0, min(pr["end_seconds"], gt["end_seconds"]) -
                                   max(pr["start_seconds"], gt["start_seconds"]))
                union = pr["end_seconds"]-pr["start_seconds"] + gt["end_seconds"]-gt["start_seconds"]-intersection
                ious[i,j] = intersection / union
        a, b = linear_sum_assignment(np.where(ious >= min_iou, -1000-ious, 0))
        matched = [float(ious[i,j]) for i,j in zip(a,b) if ious[i,j] >= min_iou]
    return {"internal_boundaries": boundary,
            "segments": {**_scores(len(matched), len(predicted), len(labelled)),
                         "minimum_temporal_iou": min_iou,
                         "mean_matched_iou": float(np.mean(matched)) if matched else None},
            "qualification": "Development clip only; no held-out accuracy claim"}


def evaluate_end_events(predicted, annotation, duration, tolerance=1.0):
    """End-only labels cannot justify invented starts or segment-IoU claims."""
    if tolerance < 0:
        raise ValueError("Tolerance must be nonnegative")
    predicted = validate_rallies(predicted,duration)
    truth = [float(e["end_seconds"]) for e in annotation["events"]]
    if any(not np.isfinite(t) or not 0<=t<=duration for t in truth) or truth!=sorted(set(truth)):
        raise ValueError("Manual ends must be unique, finite, in range and chronological")
    ends = [r["end_seconds"] for r in predicted]
    pairs = []
    if ends and truth:
        costs = np.abs(np.asarray(ends)[:,None]-np.asarray(truth)[None,:])
        penalty=(len(ends)+len(truth)+1)*(max(duration,1)+1)
        a,b=linear_sum_assignment(np.where(costs<=tolerance,costs,penalty))
        pairs=[{"prediction_index": int(i), "manual_index": int(j),
                "predicted_end_seconds": ends[i], "manual_end_seconds": truth[j],
                "absolute_error_seconds": float(costs[i,j])}
               for i,j in zip(a,b) if costs[i,j]<=tolerance]
    matched_p={p["prediction_index"] for p in pairs}
    matched_g={p["manual_index"] for p in pairs}
    return {"annotation_type": "rally_end_events", "ends": {
        **_scores(len(pairs),len(ends),len(truth)), "tolerance_seconds": tolerance,
        "mean_absolute_error_seconds": float(np.mean([p["absolute_error_seconds"] for p in pairs])) if pairs else None,
        "matches": pairs, "missed_manual_ends_seconds": [t for j,t in enumerate(truth) if j not in matched_g],
        "unmatched_predicted_ends_seconds": [t for i,t in enumerate(ends) if i not in matched_p]},
        "start_accuracy": None, "segment_iou": None,
        "qualification": "Development labels; end-only evaluation; completeness unverified; approximate annotations retained"}
