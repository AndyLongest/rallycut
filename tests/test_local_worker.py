import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from rallycut import local_worker as worker


def test_progress_is_complete_json_and_never_moves_backwards(tmp_path):
    progress = worker.Progress(tmp_path)
    progress.total = 100
    progress.update("analyzing", 0.5, "识别中", 50, force=True)
    progress.update("analyzing", 0.4, "旧进度", 40, force=True)
    saved = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))
    assert saved["progress"] == 0.5
    assert saved["message"] == "旧进度"
    assert not (tmp_path / "progress.json.tmp").exists()


def test_display_pose_keeps_actual_coordinates_and_confidence():
    import numpy as np
    player = {"box": np.array([1, 2, 3, 4]), "keypoints": np.array([[10, 20], [30, 40]]),
              "conf": np.array([0.1, 0.9])}
    before = player["keypoints"].copy()
    actual = worker.display_player(player)
    assert actual == {"bbox": [1, 2, 3, 4], "keypoints": [[10, 20, 0.1], [30, 40, 0.9]]}
    np.testing.assert_array_equal(before, player["keypoints"])
    assert worker.display_player(None) is None


def test_long_video_display_is_bounded_but_full_pose_file_retained(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "MAX_DISPLAY_POSES", 3)
    path = tmp_path / "poses.jsonl"
    path.write_text("".join(json.dumps({"timestamp_seconds": index / 5})
                            + "\n" for index in range(8)), encoding="utf-8")
    capture = worker.Capture(tmp_path, worker.Progress(tmp_path))
    capture.count = 8
    samples, stride = capture.display_samples()
    assert stride == 3
    assert [record["timestamp_seconds"] for record in samples] == [0, 0.6, 1.2]
    assert len(path.read_text().splitlines()) == 8


@pytest.mark.parametrize(("height", "duration", "message"),
                         [(360, 30, "720p"), (720, 10, "20 秒")])
def test_preflight_rejects_unsupported_input_before_inference(monkeypatch, height, duration, message):
    payload = {"streams": [{"index": 0, "codec_type": "video", "width": 1280,
                           "height": height, "duration": str(duration),
                           "avg_frame_rate": "30/1"}]}
    monkeypatch.setattr(worker.subprocess, "run",
                        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(payload)))
    with pytest.raises(ValueError, match=message):
        worker.inspect_video("ffprobe", Path("video.mp4"))


def test_exports_reencode_exact_interval_and_archive_all_candidates(tmp_path, monkeypatch):
    calls = []

    def fake_ffmpeg(tool, arguments, job, callback=None):
        calls.append(arguments)
        Path(arguments[-1]).write_bytes(b"test video")

    monkeypatch.setattr(worker, "run_ffmpeg", fake_ffmpeg)
    rallies = [
        {"id": 1, "start_seconds": 3.25, "end_seconds": 5.45, "duration_seconds": 2.2},
        {"id": 2, "start_seconds": 10, "end_seconds": 10.4, "duration_seconds": 0.4},
    ]
    progress = worker.Progress(tmp_path)
    progress.total = 20
    worker.export_rallies("ffmpeg", Path("media.mp4"), rallies, tmp_path, progress)
    assert len(calls) == 2
    assert calls[0][calls[0].index("-ss") + 1] == "3.25"
    assert calls[0][calls[0].index("-t") + 1] == "2.2"
    assert all(command[command.index("-c:v") + 1] == "libx264" for command in calls)
    with zipfile.ZipFile(tmp_path / "clips.zip") as archive:
        assert set(archive.namelist()) == {"rally_001.mp4", "rally_002.mp4", "rallies.json"}
        assert json.loads(archive.read("rallies.json")) == rallies


def test_missing_bundled_code_fails_without_network_or_model_fallback(tmp_path):
    with pytest.raises(RuntimeError, match="RallyClip"):
        worker.find_assets(tmp_path)


def test_vendor_model_layout_resolves_without_development_checkout(tmp_path, monkeypatch):
    import hashlib
    source = tmp_path / "vendor" / "RallyClip" / "src" / "rallyclip_engine"
    source.mkdir(parents=True)
    (source / "runner.py").write_text("# test engine", encoding="utf-8")
    artifact = tmp_path / "vendor" / "RallyClip" / "models" / "rallyclip_v0.5.0"
    artifact.mkdir(parents=True)
    manifest = {
        "feature_pipeline": {"imgsz": 960, "target_fps": 5, "conf": 0.25,
                             "yolo_model": "yolov8n-pose-960-dynamic.onnx"},
        "inference": {"seq_len_frames": 100, "overlap_frames": 50},
        "postprocess": {"params": {"threshold": 0.5}},
        "pipeline": {"id": "frame_startend_heatmap"},
    }
    content = json.dumps(manifest).encode()
    (artifact / "manifest.json").write_bytes(content)
    monkeypatch.setattr(worker, "MODEL_HASHES", {"manifest.json": hashlib.sha256(content).hexdigest()})
    actual_source, actual_artifact, actual_manifest = worker.find_assets(tmp_path)
    assert actual_source == source.parent
    assert actual_artifact == artifact
    assert actual_manifest == manifest


def test_preview_timestamp_adjustment_preserves_source_pts_evidence(tmp_path):
    (tmp_path / "poses.jsonl").write_text(
        '{"timestamp_seconds":0.1,"near":null,"far":null}\n', encoding="utf-8")
    capture = worker.Capture(tmp_path, worker.Progress(tmp_path))
    capture.count = 1
    samples, _ = capture.display_samples(playback_offset=0.1)
    assert samples[0]["timestamp_seconds"] == 0
    assert samples[0]["source_timestamp_seconds"] == 0.1
    original = json.loads((tmp_path / "poses.jsonl").read_text())
    assert original["timestamp_seconds"] == 0.1


def test_unicode_mask_fallback_preserves_pixels_flags_and_restores_imread(tmp_path, monkeypatch):
    import cv2
    import numpy as np
    mask = (np.arange(17 * 13, dtype=np.uint8).reshape(13, 17) > 75).astype(np.uint8) * 255
    directory = tmp_path / "中文 路径"
    directory.mkdir()
    path = directory / "球场遮罩.png"
    success, encoded = cv2.imencode(".png", mask)
    assert success
    path.write_bytes(encoded.tobytes())
    calls = []

    def unreadable(filename, flags):
        calls.append((filename, flags))
        return None

    monkeypatch.setattr(cv2, "imread", unreadable)
    with worker.unicode_image_reads():
        decoded = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        np.testing.assert_array_equal(decoded, mask)
        assert calls == [(str(path), cv2.IMREAD_GRAYSCALE)]
        assert cv2.imread(str(directory / "不存在.png"), cv2.IMREAD_GRAYSCALE) is None
    assert cv2.imread is unreadable


def test_unicode_imread_prefers_successful_native_decoder(monkeypatch):
    import cv2
    import numpy as np
    original_image = np.zeros((2, 2), np.uint8)
    monkeypatch.setattr(cv2, "imread", lambda name, flags: original_image)
    with worker.unicode_image_reads():
        assert cv2.imread("not-read-from-disk.png", cv2.IMREAD_GRAYSCALE) is original_image
