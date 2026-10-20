"""Agreement with a frozen model, explicitly not human ground-truth accuracy."""
import numpy as np
from scipy.optimize import linear_sum_assignment


def compare_intervals(student, teacher, duration, tolerance=1.0):
    def events(rows, key):
        return np.array([x[key] for x in rows], dtype=float)
    result = {"reference_kind": "frozen_model_teacher_not_human_truth",
              "teacher_count": len(teacher), "student_count": len(student),
              "positive_reference_available": bool(teacher)}
    for key, label in (("start_seconds", "starts"), ("end_seconds", "ends")):
        a, b = events(student,key), events(teacher,key)
        matches = []
        if len(a) and len(b):
            cost = abs(a[:,None]-b[None,:])
            ri, ci = linear_sum_assignment(np.where(cost <= tolerance,cost,(len(a)+len(b)+1)*(duration+1)))
            matches = [float(cost[i,j]) for i,j in zip(ri,ci) if cost[i,j] <= tolerance]
        result[label] = {"matched": len(matches), "missing": len(b)-len(matches),
                         "extra": len(a)-len(matches),
                         "mean_error_seconds": float(np.mean(matches)) if matches else None,
                         "max_error_seconds": max(matches) if matches else None}
    times = np.arange(0,duration,.05)
    def mask(rows):
        values = np.zeros(len(times), bool)
        for row in rows:
            values |= (times >= row["start_seconds"]) & (times < row["end_seconds"])
        return values
    a,b = mask(student),mask(teacher)
    union = np.sum(a|b)
    result["active_time_iou"] = float(np.sum(a&b)/union) if union else 1.0
    result["missed_teacher_active_seconds"] = float(np.sum(b&~a)*.05)
    result["extra_active_seconds"] = float(np.sum(a&~b)*.05)
    result["boundary_tolerance_seconds"] = tolerance
    return result
