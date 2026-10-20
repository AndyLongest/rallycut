"""Upstream PySceneDetect/OpenCV, optionally upstream YOLOX-Nano on CPU."""

from pathlib import Path
import hashlib
import time
import urllib.request

import cv2
import numpy as np
from scenedetect.detectors import AdaptiveDetector

from .media import sampled_frames

MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx"
MODEL_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"


def install_model(destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response, temporary.open("wb") as target:
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("YOLOX model checksum mismatch")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


class PersonDetector:
    """416px COCO person detector, BGR 0..255, upstream YOLOX grid decode."""

    def __init__(self, path):
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("Expected the checksummed YOLOX-Nano ONNX model")
        self.net = cv2.dnn.readNetFromONNX(str(path))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        grids, strides = [], []
        for stride in (8, 16, 32):
            y, x = np.meshgrid(np.arange(416 // stride), np.arange(416 // stride), indexing="ij")
            grids.append(np.stack((x, y), axis=-1).reshape(-1, 2))
            strides.append(np.full((x.size, 1), stride))
        self.grid, self.strides = np.concatenate(grids), np.concatenate(strides)

    def detect(self, frame):
        h, w = frame.shape[:2]
        ratio = min(416 / h, 416 / w)
        resized = cv2.resize(frame, (int(w * ratio), int(h * ratio)))
        padded = np.full((416, 416, 3), 114, dtype=np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        blob = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=np.float32)
        self.net.setInput(blob)
        raw = self.net.forward()[0]
        if raw.shape != (3549, 85):
            raise ValueError(f"Unexpected YOLOX output: {raw.shape}")
        scores = raw[:, 4] * raw[:, 5]  # COCO class 0 = person
        keep = scores >= .20
        prediction = raw[keep]
        centers = (prediction[:, :2] + self.grid[keep]) * self.strides[keep]
        sizes = np.exp(prediction[:, 2:4]) * self.strides[keep]
        xywh = np.concatenate((centers - sizes / 2, sizes), axis=1) / ratio
        indices = cv2.dnn.NMSBoxes(xywh.tolist(), scores[keep].tolist(), .20, .45)
        result = []
        for index in np.asarray(indices).flatten():
            x, y, bw, bh = xywh[index]
            result.append([max(0, float(x)), max(0, float(y)),
                           min(w, float(x+bw)), min(h, float(y+bh)), float(scores[keep][index])])
        return result


def extract_visual(meta, fps=4, width=320, threads=2, model=None, roi=None, edited=False):
    """Sampling is independent of native FPS. No pose or GPU dependency."""
    cv2.setNumThreads(threads)
    detector = PersonDetector(model) if model else None
    # Edited same-camera reels change few pixels: upstream default floor 15 misses
    # them. This profile was selected on the labelled development demo, not held out.
    scene = (AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=max(1, round(2*fps)),
                              window_width=max(1, round(.75*fps)),
                              min_content_val=.5, luma_only=True) if edited else
             AdaptiveDetector(adaptive_threshold=3.0, min_scene_len=max(1, round(fps)),
                              min_content_val=15.0))
    background = cv2.createBackgroundSubtractorMOG2(history=max(20, round(10*fps)),
                                                  varThreshold=25, detectShadows=False)
    previous = None
    mask = None
    rows, cuts = [], []
    boxes = []
    detector_seconds, detector_calls = 0.0, 0
    with sampled_frames(meta, fps, width, threads) as frames:
        for index, (stamp, frame) in enumerate(frames):
            h, w = frame.shape[:2]
            if mask is None:
                mask = np.ones((h, w), np.uint8)
                if roi:
                    points = np.asarray(roi, dtype=float)
                    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or np.any((points < 0) | (points > 1)):
                        raise ValueError("ROI needs >=3 normalized [x,y] points in [0,1]")
                    mask.fill(0)
                    cv2.fillPoly(mask, [np.rint(points * [w-1, h-1]).astype(np.int32)], 1)
                    if not mask.any():
                        raise ValueError("ROI has no area")
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            foreground = background.apply(gray, learningRate=min(.25, 1 / (fps * 8)))
            cuts.extend(float(cut / fps) for cut in scene.process_frame(index, frame))
            if detector and (index == 0 or stamp - last_detection >= .5 - 1e-6):
                before = time.perf_counter()
                boxes = detector.detect(frame)
                detector_seconds += time.perf_counter() - before
                detector_calls += 1
                last_detection = stamp
            diff = cv2.absdiff(gray, previous) if previous is not None else np.zeros_like(gray)
            # Global illumination changes are subtracted before foreground scoring.
            signed = gray.astype(np.int16) - previous.astype(np.int16) if previous is not None else np.zeros_like(gray, np.int16)
            changed = np.abs(signed - np.median(signed[mask > 0])) > 18
            motion = float(np.mean(changed[mask > 0])) if previous is not None else 0
            fg = float(np.mean((foreground > 0)[mask > 0])) if index > fps else 0
            player_motion = 0.0
            valid_boxes = []
            for x1, y1, x2, y2, confidence in boxes:
                x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
                if x2 > x1 and y2 > y1 and mask[min(h-1, y2-1), min(w-1, (x1+x2)//2)]:
                    player_motion = max(player_motion, float(np.mean(diff[y1:y2, x1:x2])) / 255)
                    valid_boxes.append([x1, y1, x2, y2, confidence])
            rows.append({"t": round(stamp, 4), "motion": motion, "foreground": fg,
                         "player_motion": player_motion, "people": len(valid_boxes),
                         "boxes": valid_boxes})
            previous = gray
    return rows, sorted(set(cuts)), {"sample_fps": fps, "sampled_frames": len(rows),
        "analysis_width": w, "analysis_height": h, "device": "CPU", "threads": threads,
        "person_detector": "YOLOX-Nano" if detector else None,
        "person_detector_calls": detector_calls, "person_detector_seconds": detector_seconds,
        "scene_detector": ("PySceneDetect AdaptiveDetector ratio=3 floor=.5 luma window=.75s min=2s; development-tuned"
                           if edited else "PySceneDetect AdaptiveDetector 3.0/15.0 (upstream defaults)"),
        "roi": roi, "sampling_time_uncertainty_seconds": 1 / fps}
