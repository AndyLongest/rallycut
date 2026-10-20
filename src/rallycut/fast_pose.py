"""Experimental visual-only pose reuse. Never reads teacher results at inference."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import time

import numpy as np
from scipy.optimize import linear_sum_assignment


def interpolate_pose(left, right, fraction):
    """Interpolate matched people; never blend unrelated identities across a cut."""
    a, b = left["boxes"], right["boxes"]
    if not len(a) or len(a) != len(b):
        return deepcopy(left if fraction < .5 else right)
    lo = np.maximum(a[:, None, :2], b[None, :, :2])
    hi = np.minimum(a[:, None, 2:], b[None, :, 2:])
    intersection = np.prod(np.maximum(0, hi - lo), axis=2)
    area_a = np.prod(np.maximum(0, a[:, 2:] - a[:, :2]), axis=1)
    area_b = np.prod(np.maximum(0, b[:, 2:] - b[:, :2]), axis=1)
    iou = intersection / np.maximum(area_a[:, None] + area_b[None, :] - intersection, 1e-6)
    rows, cols = linear_sum_assignment(-iou)
    if np.any(iou[rows, cols] < .1):
        return deepcopy(left if fraction < .5 else right)
    order = cols[np.argsort(rows)]
    out = deepcopy(left)
    for key in ("boxes", "box_conf", "keypoints", "conf"):
        out[key] = ((1 - fraction) * left[key] + fraction * right[key][order]).astype(np.float32)
    return out


@contextmanager
def sparse_pose(stride=1, mode="interpolate"):
    """Keep the temporal model's 5fps contract, evaluate expensive poses less often."""
    if stride < 1 or mode not in {"interpolate", "hold"}:
        raise ValueError("Invalid sparse pose configuration")
    from extraction.pose_extractor import PoseExtractor

    original = PoseExtractor.iter_pose_frames
    audit = {"stride": stride, "mode": mode, "selected_frames": 0,
             "pose_calls": 0, "pose_seconds": 0.0, "teacher_input_at_inference": False}

    def iterator(self, *args, **kwargs):
        model, batch_size = self.model, self.batch_size
        self.batch_size = 1

        class Proxy:
            count = 0
            cached = None

            def predict(proxy, *a, **kw):
                if proxy.count % stride == 0:
                    start = time.perf_counter()
                    proxy.cached = model.predict(*a, **kw)
                    audit["pose_seconds"] += time.perf_counter() - start
                    audit["pose_calls"] += 1
                proxy.count += 1
                return proxy.cached

        proxy = Proxy()
        self.model = proxy
        pending = []
        try:
            for record in original(self, *args, **kwargs):
                if record["annotation_status"] < 0:
                    continue
                index = proxy.count - 1
                audit["selected_frames"] += 1
                if mode == "hold" or stride == 1:
                    yield record
                elif index % stride == 0 and pending:
                    for offset, prior in enumerate(pending):
                        yield interpolate_pose(pending[0], record, offset / len(pending))
                    pending = [record]
                else:
                    pending.append(record)
            yield from pending
        finally:
            self.model, self.batch_size = model, batch_size

    PoseExtractor.iter_pose_frames = iterator
    try:
        yield audit
    finally:
        PoseExtractor.iter_pose_frames = original


@contextmanager
def cropped_pose(refresh=5, crop_size=256, empty_recheck=1):
    """Track detections with small crops, with periodic full-frame rediscovery."""
    if refresh < 1 or crop_size < 96 or crop_size % 32 or not 1 <= empty_recheck <= refresh:
        raise ValueError("Invalid crop configuration")
    import cv2
    from extraction.pose_extractor import PoseExtractor
    from extraction.yolo_onnx_runner import Result
    original = PoseExtractor.iter_pose_frames
    audit = {"mode": "crop", "refresh": refresh, "crop_size": crop_size,
             "full_calls": 0, "crop_calls": 0, "scene_resets": 0,
             "empty_recheck": empty_recheck, "empty_reuses": 0,
             "pose_seconds": 0.0, "selected_frames": 0, "teacher_input_at_inference": False}

    def iterator(self, *args, **kwargs):
        model, batch_size = self.model, self.batch_size
        self.batch_size = 1

        class Proxy:
            count = 0
            previous = None
            small = None
            last_full = -refresh

            def predict(proxy, *a, **kw):
                image = kw["source"][0]
                h, w = image.shape[:2]
                small = cv2.resize(image, (32, 18)).astype(np.float32)
                motion = float(np.mean(abs(small-proxy.small))) if proxy.small is not None else 255.
                cut = proxy.small is not None and motion > 35
                proxy.small = small
                empty = proxy.previous is not None and len(proxy.previous.boxes) == 0
                force = (proxy.count % refresh == 0 or proxy.previous is None or
                         len(proxy.previous.boxes) > 4 or cut or
                         (empty and (proxy.count-proxy.last_full >= empty_recheck or motion > 2.0)))
                if cut:
                    audit["scene_resets"] += 1
                start = time.perf_counter()
                result = None
                if not force and empty:
                    result = proxy.previous
                    audit["empty_reuses"] += 1
                elif not force:
                    rows = []
                    for box in proxy.previous.boxes.xyxy.numpy():
                        # Same person pixel scale as the full-resolution teacher,
                        # but remove background before constructing the tensor.
                        side = max(max(h,w) * crop_size / kw["imgsz"],
                                   1.5*max(box[2]-box[0], box[3]-box[1]))
                        cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
                        x0, y0 = int(max(0, min(w-side, cx-side/2))), int(max(0, min(h-side, cy-side/2)))
                        x1, y1 = min(w, int(x0+side)), min(h, int(y0+side))
                        options = dict(kw, source=[image[y0:y1,x0:x1]], imgsz=crop_size)
                        candidate = model.predict(*a, **options)[0]
                        audit["crop_calls"] += 1
                        if not len(candidate.boxes):
                            force = True
                            break
                        boxes = candidate.boxes.xyxy.numpy().copy()
                        boxes += [x0,y0,x0,y0]
                        centers = (boxes[:,:2]+boxes[:,2:])/2
                        best = int(np.argmin(np.linalg.norm(centers-[cx,cy],axis=1)))
                        points = candidate.keypoints.xy.numpy()[best].copy()
                        points += [x0,y0]
                        rows.append((boxes[best], candidate.boxes.conf.numpy()[best],
                                     points, candidate.keypoints.conf.numpy()[best]))
                    if not force:
                        result = Result(*(np.asarray([row[i] for row in rows], dtype=np.float32)
                                          for i in range(4)))
                if force:
                    result = model.predict(*a, **kw)[0]
                    proxy.last_full = proxy.count
                    audit["full_calls"] += 1
                audit["pose_seconds"] += time.perf_counter()-start
                audit["selected_frames"] += 1
                proxy.previous = result
                proxy.count += 1
                return [result]

        self.model = Proxy()
        try:
            yield from original(self, *args, **kwargs)
        finally:
            self.model, self.batch_size = model, batch_size

    PoseExtractor.iter_pose_frames = iterator
    try:
        yield audit
    finally:
        PoseExtractor.iter_pose_frames = original


@contextmanager
def bounded_court(attempts=1):
    """Bound front-loaded court searches; retain upstream empirical fallback."""
    if attempts < 1:
        raise ValueError("Court attempts must be positive")
    from preprocessing.data_preprocessor import DataPreprocessor
    original_times = DataPreprocessor._court_sample_times
    original_compute = DataPreprocessor.compute_court_mask
    audit = {"attempt_limit": attempts, "seconds": 0.0}
    def times(self, *a, **kw):
        return original_times(self, *a, **kw)[:attempts]
    def compute(self, *a, **kw):
        start = time.perf_counter()
        result = original_compute(self, *a, **kw)
        audit.update(seconds=time.perf_counter()-start, metadata=result[1])
        return result
    DataPreprocessor._court_sample_times = times
    DataPreprocessor.compute_court_mask = compute
    try:
        yield audit
    finally:
        DataPreprocessor._court_sample_times = original_times
        DataPreprocessor.compute_court_mask = original_compute
