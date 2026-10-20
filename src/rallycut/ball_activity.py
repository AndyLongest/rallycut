"""CPU experiment: OpenCV colour/motion blobs and short coherent trajectories.

References: OpenCV KNN/connected components and minvamos's published HSV+KNN
tennis experiment. No upstream project source or reported accuracy is copied.
These are ball-like motion candidates, never certified ball observations.
"""

from collections import deque
import time

import cv2
import numpy as np

from .media import sampled_frames
from .segment import group_times, validate_rallies


class MotionBallProposals:
    def __init__(self, fps, width, height):
        self.fps, self.width, self.height = fps, width, height
        self.background = cv2.createBackgroundSubtractorKNN(history=max(20, round(4*fps)),
            dist2Threshold=100, detectShadows=False)
        self.tracks = []
        self.next_id = 0
        self.roi = None
        self.roi_status = None
        self.contrast_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11,11))

    def _court_roi(self, frame):
        # Calibrate geometry from appearance only, never from manual event times.
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        blue = cv2.inRange(hsv, (85, 25, 40), (135, 220, 250))
        contours, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        roi = np.zeros(frame.shape[:2], np.uint8)
        best = max(contours, key=cv2.contourArea, default=None)
        if best is not None and cv2.contourArea(best) > .12*self.width*self.height:
            cv2.fillConvexPoly(roi, cv2.convexHull(best), 255)
            radius = max(3, round(self.width*.10))
            roi = cv2.dilate(roi, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1)))
            self.roi_status = "automatic blue-surface hull plus 10%-width flight margin; not a calibrated court"
        else:
            roi.fill(255)
            self.roi_status = "blue-surface ROI unavailable; full image fallback, increased false-positive risk"
        return roi

    def update(self, stamp, frame):
        if self.roi is None:
            self.roi = self._court_roi(frame)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # Bright local contrast preserves small/low-saturation far balls while
        # rejecting the green floor that broke the initial HSV-only experiment.
        colour = cv2.inRange(hsv, (18, 40, 130), (55, 255, 255))
        contrast = cv2.morphologyEx(hsv[:,:,2],cv2.MORPH_TOPHAT,self.contrast_kernel)
        yellow = cv2.bitwise_and(colour,cv2.inRange(contrast,22,255))
        foreground = self.background.apply(yellow, learningRate=.04)
        mask = cv2.bitwise_and(cv2.bitwise_and(yellow, foreground), self.roi)
        count, _, stats, centers = cv2.connectedComponentsWithStats(mask, connectivity=8)
        proposals = []
        scale = self.width/960
        for index in range(1, count):
            x, y, w, h, area = stats[index]
            if 1 <= area <= max(12, 120*scale*scale) and max(w,h) <= max(7, 28*scale) and min(w,h)/max(w,h) >= .15:
                proposals.append((float(centers[index,0]), float(centers[index,1]), int(area)))
        # An overloaded mask is unknown evidence, not a rally end or scene cut.
        if len(proposals) > 40:
            self.tracks = []
            return {"t": stamp, "active": False, "unknown": True, "proposals": [], "tracks": []}
        self.tracks = [tr for tr in self.tracks if stamp-tr["history"][-1][0] <= .5]
        available = set(range(len(self.tracks)))
        active_tracks = []
        for x, y, area in sorted(proposals, key=lambda p: p[2], reverse=True):
            distances = [(np.hypot(x-self.tracks[i]["history"][-1][1], y-self.tracks[i]["history"][-1][2]), i)
                         for i in available]
            distance, best = min(distances, default=(float("inf"), None))
            if best is not None and distance <= self.width*.20:
                track = self.tracks[best]
                available.remove(best)
                track["history"].append((stamp,x,y))
            else:
                track = {"id": self.next_id, "history": deque([(stamp,x,y)])}
                self.next_id += 1
                self.tracks.append(track)
            history = track["history"]
            while history and stamp-history[0][0] > 1:
                history.popleft()
            if len(history) >= 3:
                points = np.asarray(history)
                dt = np.diff(points[:,0])
                steps = np.linalg.norm(np.diff(points[:,1:3],axis=0),axis=1)
                speeds = steps/np.maximum(dt,1e-6)
                span = np.linalg.norm(np.ptp(points[:,1:3],axis=0))
                # Reject stationary centre/net balls and slow collection motion.
                moving_now = steps[-1] >= max(1.5, 2*scale)
                straightness=np.linalg.norm(points[-1,1:3]-points[0,1:3])/max(float(np.sum(steps)),1e-6)
                if moving_now and straightness>=.65 and span >= max(8, self.height*.02) and np.median(speeds) >= self.width*.04:
                    active_tracks.append({"id": track["id"], "x": x, "y": y,
                                          "speed_pixels_per_second": float(np.median(speeds)),
                                          "span_pixels": float(span), "observations": len(history)})
        return {"t": round(stamp,4), "active": bool(active_tracks), "unknown": False,
                "proposals": proposals, "tracks": active_tracks}


def extract_ball_activity(meta, fps=6, width=960, threads=2):
    cv2.setNumThreads(threads)
    rows = []
    detector = None
    started = time.perf_counter()
    with sampled_frames(meta, fps, width, threads) as frames:
        for stamp, frame in frames:
            if stamp >= meta["duration_seconds"]:
                continue
            if detector is None:
                detector = MotionBallProposals(fps, frame.shape[1], frame.shape[0])
            rows.append(detector.update(stamp, frame))
    return rows, {"device": "CPU", "sample_fps": fps, "analysis_width": detector.width,
                  "analysis_height": detector.height, "threads": threads,
                  "sampled_frames": len(rows), "roi": detector.roi_status,
                  "detector": "OpenCV top-hat local contrast + HSV + KNN + connected components + short motion links",
                  "certified_ball_tracking": False, "scene_cuts_used": False,
                  "elapsed_seconds": time.perf_counter()-started}


def segment_ball_activity(meta, rows, gap_seconds=2, end_buffer_seconds=.5):
    active = [row["t"] for row in rows if row["active"]]
    rallies = []
    uncertain = []
    for group in group_times(active, gap_seconds):
        a, b = max(0,group[0]-.4), min(meta["duration_seconds"], group[-1]+end_buffer_seconds)
        row = {"start_seconds": round(a,4), "end_seconds": min(meta["duration_seconds"],round(b,4)),
               "evidence": f"{len(group)} samples of ball-like coherent motion; not certified hits",
               "needs_review": True, "active_samples": len(group)}
        # Retain short attempts separately; never discard possible serve faults.
        (rallies if len(group)>=3 else uncertain).append(row)
    for left,right in zip(rallies,rallies[1:]):
        if left["end_seconds"]>right["start_seconds"]:
            mid=(left["end_seconds"]+right["start_seconds"])/2
            left["end_seconds"]=right["start_seconds"]=mid
    return validate_rallies(rallies,meta["duration_seconds"]), uncertain
