import shutil
import subprocess

import cv2
import numpy as np
import pytest

from rallycut.audio import detect_onsets
from rallycut.media import export_clips, probe, sampled_frames
from rallycut.vision import extract_visual


@pytest.fixture
def two_shot_video(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required for media integration")
    video = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20, (160, 96))
    if not writer.isOpened():
        pytest.skip("OpenCV video encoder unavailable")
    try:
        for index in range(200):
            writer.write(np.full((96, 160, 3), 20 if index < 100 else 220, np.uint8))
    finally:
        writer.release()
    return video


def test_sample_grid_and_upstream_scene_detector(two_shot_video):
    meta = probe(two_shot_video)
    rows, cuts, stats = extract_visual(meta, fps=4, width=160, threads=1, edited=True)
    assert len(rows) == 40  # 200 input frames, only 40 analyzed
    assert cuts == [5.0]
    assert stats["device"] == "CPU"
    assert stats["person_detector_calls"] == 0
    onsets, audio = detect_onsets(meta)
    assert not onsets and not audio["available"]


def test_decoder_failure_is_visible(two_shot_video):
    meta = probe(two_shot_video)
    meta["path"] += ".missing"
    with pytest.raises(RuntimeError, match="FFmpeg"):
        with sampled_frames(meta) as frames:
            list(frames)


def test_exported_clip_has_expected_duration(two_shot_video, tmp_path):
    meta = probe(two_shot_video)
    try:
        export_clips(meta, [{"start_seconds": 2, "end_seconds": 4}], tmp_path / "clips", threads=1)
    except RuntimeError as exc:
        if "libx264" in str(exc):
            pytest.skip("Full FFmpeg software encoder required for clip export")
        raise
    clip = probe(tmp_path / "clips" / "rally_001.mp4")
    assert clip["duration_seconds"] == pytest.approx(2, abs=.06)
