"""FFmpeg decoding. Sampling reduces inference, not inter-frame codec decoding."""

from contextlib import contextmanager
from pathlib import Path
from functools import lru_cache
import json
import os
import shutil
import subprocess
import tempfile

import numpy as np


@lru_cache(maxsize=8)
def executable(name, encoder=None):
    candidates = []
    for directory in os.get_exec_path():
        found = shutil.which(name, path=directory)
        if found and found not in candidates:
            candidates.append(found)
    for candidate in candidates:
        if encoder:
            capabilities = subprocess.run([candidate, "-hide_banner", "-encoders"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            if encoder not in capabilities.stdout:
                continue
        return candidate
    raise RuntimeError(f"{name}" + (f" with software encoder {encoder}" if encoder else "") + " is required on PATH")


def probe(video):
    video = Path(video).resolve(strict=True)
    result = subprocess.run(
        [executable("ffprobe"), "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(video)], capture_output=True, check=True, text=True,
        encoding="utf-8", timeout=60,
    )
    data = json.loads(result.stdout)
    streams = data["streams"]
    stream = next((s for s in streams if s["codec_type"] == "video"
                   and not s.get("disposition", {}).get("attached_pic")), None)
    if stream is None:
        raise ValueError("Input has no video stream")
    duration = float(stream.get("duration", data["format"].get("duration", 0)))
    if duration <= 0:
        raise ValueError("Input must be a finite video with a known duration")
    rate = stream.get("avg_frame_rate", "0/1").split("/")
    audio = next((s for s in streams if s["codec_type"] == "audio"), None)
    start = float(stream.get("start_time", 0))
    return {"path": str(video), "duration_seconds": duration,
            "width": int(stream["width"]), "height": int(stream["height"]),
            "native_fps": float(rate[0]) / max(float(rate[1]), 1),
            "video_stream_index": stream["index"], "video_start_seconds": start,
            "audio_stream_index": audio["index"] if audio else None,
            "audio_offset_seconds": float(audio.get("start_time", start)) - start if audio else 0}


@contextmanager
def sampled_frames(meta, fps=4.0, width=640, threads=2):
    """Yield an iterator over a normalized, uniform sampling grid (VFR safe)."""
    if not 0 < fps <= 30 or width < 64 or threads < 1:
        raise ValueError("fps must be in (0,30], width >=64 and threads >=1")
    width = min(width, meta["width"])
    height = max(2, round(meta["height"] * width / meta["width"] / 2) * 2)
    cmd = [executable("ffmpeg"), "-v", "error", "-nostdin", "-threads", str(threads),
           "-i", meta["path"], "-map", f"0:{meta['video_stream_index']}", "-an",
           "-vf", f"setpts=PTS-STARTPTS,fps={fps}:start_time=0,scale={width}:{height}",
           "-filter_threads", str(threads), "-threads", str(threads),
           "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors)
        def frames():
            index = 0
            size = width * height * 3
            while True:
                raw = process.stdout.read(size)
                if not raw:
                    break
                if len(raw) != size:
                    raise RuntimeError("Truncated FFmpeg frame")
                yield index / fps, np.frombuffer(raw, np.uint8).reshape(height, width, 3)
                index += 1
            code = process.wait(timeout=60)
            if code:
                errors.seek(0)
                raise RuntimeError("FFmpeg failed: " + errors.read(4096).decode(errors="replace"))
            if index == 0:
                raise RuntimeError("FFmpeg decoded no frames")
        try:
            yield frames()
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=30)


def export_clips(meta, rallies, output, threads=2):
    """Re-encode for accurate seeking; stream copy cannot promise cut boundaries."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for index, rally in enumerate(rallies, 1):
        start, end = rally["start_seconds"], rally["end_seconds"]
        subprocess.run(
            [executable("ffmpeg", encoder="libx264"), "-v", "error", "-nostdin", "-y", "-i", meta["path"],
             "-ss", str(start), "-t", str(end - start),
             "-map", f"0:{meta['video_stream_index']}", "-map", "0:a:0?",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", str(threads),
             "-c:a", "aac", "-movflags", "+faststart", str(output / f"rally_{index:03d}.mp4")],
            check=True, capture_output=True,
        )
