"""Offline worker with automatic CUDA selection and CPU fallback.

The upstream model and decoder are used unchanged. Observers write the actual
pose assignments and three probability tracks without changing yielded values.
"""

from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback
import zipfile


THREADS = 2
MAX_DISPLAY_POSES = 12000
MODEL_HASHES = {
    "manifest.json": "b14c2c85445f3a3ba10e99c459b2df3231f5b9a92f377fc7d7cf62fd6429a2e7",
    "model.onnx": "45f27d19a712ac1c53cd993046ba33645b1bd91a7a774be19f44b6201376b481",
    "yolov8n-pose-960-dynamic.onnx":
        "4a3fe0de63042b3a48a458d4f4358615417b58c56471a6e1da53b249f5ec0011",
    "scaler.json": "2d4f86ebf7bca27fd1cf37854a7a4b4edd8b130f6a045b33fe73f98d1f3fe9f2",
}


def atomic_json(path: Path, value) -> None:
    """Readers see either the previous complete document or the new one."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False,
                  separators=(",", ":"))
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.02 * (attempt + 1))


class Progress:
    def __init__(self, job: Path):
        self.path = job / "progress.json"
        self.total = 0.0
        self.value = 0.0
        self.last_write = 0.0
        self.device = "正在检测计算设备"
        self.device_message = None

    def update(self, phase, progress, message, processed=0.0, *, force=False):
        now = time.monotonic()
        if not force and now - self.last_write < 0.5:
            return
        self.value = max(self.value, min(1.0, float(progress)))
        atomic_json(self.path, {
            "phase": phase, "progress": self.value, "message": message,
            "processed_seconds": min(self.total, max(0.0, float(processed))),
            "total_seconds": self.total,
            "device": self.device, "device_message": self.device_message,
        })
        self.last_write = now


def find_assets(root: Path):
    development = root / "outputs" / "upstream_rallyclip" / "RallyClip-main"
    source = root / "vendor" / "RallyClip" / "src"
    if not source.is_dir():
        source = development / "src"
    artifact = root / "models" / "rallyclip_v0.5.0"
    if not artifact.is_dir():
        artifact = root / "vendor" / "RallyClip" / "models" / "rallyclip_v0.5.0"
    if not artifact.is_dir():
        artifact = development / "models" / "rallyclip_v0.5.0"
    if not (source / "rallyclip_engine" / "runner.py").is_file():
        raise RuntimeError("缺少项目内的 RallyClip 运行代码，请重新解压完整安装包。")
    for name, expected in MODEL_HASHES.items():
        path = artifact / name
        if not path.is_file():
            raise RuntimeError(f"缺少离线模型文件 {name}，请重新解压完整安装包。")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != expected:
            raise RuntimeError(f"模型文件 {name} 校验失败，请重新解压完整安装包。")
    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
    feature = manifest["feature_pipeline"]
    inference = manifest["inference"]
    params = manifest["postprocess"]["params"]
    if (feature["imgsz"] != 960 or feature["target_fps"] != 5
            or inference["seq_len_frames"] != 100
            or inference["overlap_frames"] != 50
            or feature["conf"] != 0.25
            or feature["yolo_model"] != "yolov8n-pose-960-dynamic.onnx"
            or params.get("threshold") != 0.5
            or manifest["pipeline"]["id"] != "frame_startend_heatmap"):
        raise RuntimeError("模型清单不符合完整 960 版本，未启动推理。")
    return source, artifact, manifest


def find_media_tool(root: Path, name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    for directory in (
        root / "runtime" / "ffmpeg" / "bin", root / "runtime" / "ffmpeg",
        root / "bin", root / "runtime" / "bin",
    ):
        candidate = directory / (name + suffix)
        if candidate.is_file():
            return str(candidate)
    # Source checkout development only. Packaged builds carry both executables.
    if (root / "outputs" / "upstream_rallyclip" / "RallyClip-main").is_dir():
        from rallycut.media import executable
        return executable(name, encoder="libx264" if name == "ffmpeg" else None)
    raise RuntimeError(f"安装包中缺少 {name}，请重新解压完整安装包。")


def inspect_video(ffprobe: str, video: Path) -> dict:
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json",
         str(video)], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        raise ValueError("无法读取视频，请确认文件完整且未加密。")
    data = json.loads(completed.stdout)
    video_stream = next((stream for stream in data.get("streams", [])
                         if stream.get("codec_type") == "video"
                         and not stream.get("disposition", {}).get("attached_pic")), None)
    if video_stream is None:
        raise ValueError("文件中没有可读取的视频画面。")
    duration = float(video_stream.get("duration")
                     or data.get("format", {}).get("duration") or 0)
    rate = video_stream.get("avg_frame_rate", "0/1").split("/")
    fps = float(rate[0]) / max(float(rate[1]), 1)
    audio_stream = next((stream for stream in data.get("streams", [])
                         if stream.get("codec_type") == "audio"), None)
    rotation = next((side.get("rotation", 0)
                     for side in video_stream.get("side_data_list", [])
                     if "rotation" in side), 0)
    result = {
        "duration_seconds": duration, "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)), "fps": fps,
        "video_stream_index": int(video_stream["index"]),
        "codec": video_stream.get("codec_name"), "pixel_format": video_stream.get("pix_fmt"),
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "start_seconds": float(video_stream.get("start_time") or 0),
        "rotation": rotation,
    }
    if not math.isfinite(duration) or duration <= 0 or fps <= 0:
        raise ValueError("视频时长或帧率无效，请先重新导出完整视频。")
    if result["height"] < 720:
        raise ValueError("当前模型需要至少 720p 视频，请选择更高清的原始视频。")
    if duration < 20:
        raise ValueError("当前模型需要至少 20 秒视频，请选择更长的视频。")
    return result


def run_ffmpeg(ffmpeg: str, arguments: list[str], job: Path, on_progress=None):
    """Keep stderr on disk and reap the child on cooperative cancellation."""
    with (job / "ffmpeg.log").open("ab") as errors:
        process = subprocess.Popen(
            [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
             "-progress", "pipe:1", "-nostats", *arguments],
            stdout=subprocess.PIPE, stderr=errors, text=True, encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            assert process.stdout is not None
            for line in process.stdout:
                key, _, value = line.strip().partition("=")
                if key == "out_time_us" and on_progress:
                    try:
                        on_progress(max(0.0, float(value) / 1_000_000))
                    except ValueError:
                        pass
            code = process.wait()
            if code:
                raise RuntimeError(f"视频转换失败（退出码 {code}），详情见任务日志 ffmpeg.log。")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()


def prepare_media(ffmpeg: str, video: Path, meta: dict, job: Path,
                  progress: Progress) -> tuple[Path, bool]:
    media = job / "media.mp4"
    compatible = (
        video.suffix.lower() in {".mp4", ".m4v", ".mov"}
        and meta["codec"] == "h264"
        and meta["pixel_format"] in {"yuv420p", "yuvj420p"}
        and meta["audio_codec"] in {None, "aac"}
        and not meta["rotation"]
        and abs(meta["start_seconds"]) < 0.5
    )
    if compatible:
        if video != media and not (media.exists() and os.path.samefile(video, media)):
            try:
                os.link(video, media)
            except OSError:
                shutil.copyfile(video, media)
        progress.update("preparing", 0.12, "视频已就绪，正在加载模型。", force=True)
        return media, False
    progress.update("preparing", 0.02, "正在转换为浏览器可播放的视频（CPU）。", force=True)
    run_ffmpeg(ffmpeg, [
        "-threads", str(THREADS), "-i", str(video), "-map", f"0:{meta['video_stream_index']}",
        "-map", "0:a:0?", "-vf", "setpts=PTS-STARTPTS,scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-af", f"asetpts=PTS-{meta['start_seconds']}/TB",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-fps_mode", "passthrough",
        "-threads", str(THREADS), "-filter_threads", str(THREADS),
        "-c:a", "aac", "-movflags", "+faststart", str(media),
    ], job, lambda seconds: progress.update(
        "preparing", 0.02 + 0.1 * min(1, seconds / progress.total),
        "正在转换为浏览器可播放的视频（CPU）。", seconds))
    return media, True


@contextmanager
def unicode_image_reads():
    """Preserve OpenCV decoding while supporting Windows Unicode filenames."""
    import cv2
    import numpy as np

    original_imread = cv2.imread

    def imread(filename, flags=cv2.IMREAD_COLOR):
        decoded = original_imread(filename, flags)
        if decoded is not None:
            return decoded
        try:
            path = Path(filename)
            if path.is_file():
                return cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), flags)
        except OSError:
            pass
        return decoded

    cv2.imread = imread
    try:
        yield
    finally:
        cv2.imread = original_imread


@contextmanager
def inference_runtime(progress=None, root=None):
    from rallycut.device_runtime import AutoRuntime
    from rallycut.optional_gpu import select_gpu_directory

    optional_path = select_gpu_directory(root) if root is not None else None
    if optional_path is not None:
        sys.path.insert(0, str(optional_path))

    keys = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
            "POSE_DEVICE", "POSE_BATCH_SIZE", "PIPELINE_PROFILE", "RALLYCLIP_NO_TQDM")
    previous_env = {key: os.environ.get(key) for key in keys}
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = str(THREADS)
    os.environ["POSE_BATCH_SIZE"] = "1"
    os.environ["PIPELINE_PROFILE"] = "main"
    os.environ["RALLYCLIP_NO_TQDM"] = "1"
    import av
    import cv2
    import onnxruntime as ort

    original_session = ort.InferenceSession
    original_open = av.open
    original_threads = cv2.getNumThreads()
    def device_changed(device, reason):
        if progress:
            progress.device, progress.device_message = device, reason
            progress.update("analyzing", progress.value,
                            f"正在识别回合 · {device}", force=True)

    runtime = AutoRuntime(ort, THREADS, mode=os.environ.get("RALLYCUT_DEVICE", "auto"),
                          on_change=device_changed)
    os.environ["POSE_DEVICE"] = runtime.requested_device

    def open_video(*args, **kwargs):
        container = original_open(*args, **kwargs)
        if kwargs.get("mode", "r") == "r":
            for stream in container.streams.video:
                stream.codec_context.thread_count = THREADS
        return container

    ort.InferenceSession = runtime.session
    av.open = open_video
    cv2.setNumThreads(THREADS)
    try:
        with unicode_image_reads():
            yield runtime
    finally:
        ort.InferenceSession = original_session
        av.open = original_open
        cv2.setNumThreads(original_threads)
        if optional_path is not None:
            sys.path.remove(str(optional_path))
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def display_player(player):
    """Keep the actual reference-space coordinates and confidence values."""
    if player is None:
        return None
    return {
        "bbox": [float(value) for value in player["box"]],
        "keypoints": [[float(point[0]), float(point[1]), float(confidence)]
                      for point, confidence in zip(player["keypoints"], player["conf"])],
    }


class Capture:
    def __init__(self, job: Path, progress: Progress):
        self.job = job
        self.progress = progress
        self.count = 0
        self.tracks = None
        self.times = None
        self.decode_config = None
        self.reference_size = [1280, 720]
        self.missing_near = 0
        self.missing_far = 0
        self.pending_timestamp = None
        self.last_timestamp = None

    @contextmanager
    def installed(self):
        import numpy as np
        from extraction.pose_extractor import PoseExtractor
        from preprocessing.data_preprocessor import DataPreprocessor
        from rallyclip_engine.models import HeatmapHybridModel

        original_iterator = PoseExtractor.frame_iterator_pyav
        original_pose = PoseExtractor.iter_pose_frames
        original_preprocess = DataPreprocessor.iter_preprocess_frames
        original_postprocess = HeatmapHybridModel.postprocess
        capture = self
        stream = (self.job / "poses.jsonl").open("w", encoding="utf-8")

        def iterator(extractor, *args, **kwargs):
            for frame, timestamp in original_iterator(extractor, *args, **kwargs):
                if hasattr(extractor, "_rallycut_times"):
                    start, end = extractor._rallycut_range
                    if start <= timestamp <= end:
                        extractor._rallycut_times.append(float(timestamp))
                yield frame, timestamp

        def pose(extractor, *args, **kwargs):
            extractor._rallycut_times = deque()
            start = kwargs.get("start_time_seconds", args[2] if len(args) > 2 else 0)
            duration = kwargs.get("duration_seconds", args[3] if len(args) > 3 else 60)
            extractor._rallycut_range = (start, start + duration)
            try:
                for record in original_pose(extractor, *args, **kwargs):
                    timestamp = extractor._rallycut_times.popleft()
                    if record.get("annotation_status", 0) >= 0:
                        capture.pending_timestamp = timestamp
                    yield record
            finally:
                del extractor._rallycut_times

        def preprocess(preprocessor, *args, **kwargs):
            for record in original_preprocess(preprocessor, *args, **kwargs):
                _, target, near, far = record
                if target >= 0:
                    if capture.pending_timestamp is None:
                        raise RuntimeError("人体姿态时间戳未对齐。")
                    sample = {"timestamp_seconds": capture.pending_timestamp,
                              "near": display_player(near), "far": display_player(far)}
                    capture.reference_size = [preprocessor.screen_width, preprocessor.screen_height]
                    stream.write(json.dumps(sample, ensure_ascii=False, allow_nan=False,
                                            separators=(",", ":")) + "\n")
                    capture.count += 1
                    capture.missing_near += near is None
                    capture.missing_far += far is None
                    seconds = capture.pending_timestamp
                    capture.last_timestamp = seconds
                    capture.pending_timestamp = None
                    capture.progress.update(
                        "analyzing", 0.12 + 0.66 * min(1, seconds / capture.progress.total),
                        f"正在识别回合 · 已分析 {seconds:.0f} / {capture.progress.total:.0f} 秒",
                        seconds)
                yield record

        def postprocess(model, model_output):
            tracks = np.asarray(model_output)
            if tracks.ndim != 2 or tracks.shape[0] != 3 or tracks.shape[1] != capture.count:
                raise RuntimeError("模型分数与实际人体姿态样本未对齐。")
            if not np.isfinite(tracks).all() or tracks.min() < 0 or tracks.max() > 1:
                raise RuntimeError("模型返回了无效概率。")
            capture.tracks = tracks.copy()
            capture.times = model.request.start_time + np.arange(tracks.shape[1]) / model.request.fps
            capture.decode_config = asdict(model._decode_config())
            return original_postprocess(model, model_output)

        PoseExtractor.frame_iterator_pyav = iterator
        PoseExtractor.iter_pose_frames = pose
        DataPreprocessor.iter_preprocess_frames = preprocess
        HeatmapHybridModel.postprocess = postprocess
        try:
            yield self
        finally:
            PoseExtractor.frame_iterator_pyav = original_iterator
            PoseExtractor.iter_pose_frames = original_pose
            DataPreprocessor.iter_preprocess_frames = original_preprocess
            HeatmapHybridModel.postprocess = original_postprocess
            stream.close()

    def display_samples(self, playback_offset=0.0):
        stride = max(1, math.ceil(self.count / MAX_DISPLAY_POSES))
        with (self.job / "poses.jsonl").open(encoding="utf-8") as stream:
            samples = [json.loads(line) for index, line in enumerate(stream)
                       if index % stride == 0]
        if playback_offset:
            for sample in samples:
                sample["source_timestamp_seconds"] = sample["timestamp_seconds"]
                sample["timestamp_seconds"] = max(0.0, sample["timestamp_seconds"] - playback_offset)
        return samples, stride


def build_request(artifact: Path, manifest: dict, video: Path, job: Path, duration: float,
                  device="cpu"):
    from rallyclip_core.contracts import RunRequest
    from runtime.assets import manifest_values

    values = manifest_values(artifact / "model.onnx", artifact / "manifest.json")
    return RunRequest(
        video_path=video, output_dir=job, output_name=None, csv_output_dir=job,
        write_csv=False, segment_video=False,
        yolo_weights=str(artifact / manifest["feature_pipeline"]["yolo_model"]),
        yolo_device=device, model_path=artifact / "model.onnx", scaler_path=artifact / "scaler.json",
        manifest_path=artifact / "manifest.json", models_dir=artifact,
        pipeline_id=values["pipeline_id"],
        fps=values["fps"], seq_len=values["seq_len"], imgsz=values["imgsz"],
        conf=values["conf"], feature_set=values["feature_set"],
        screen_width=values["screen_width"], screen_height=values["screen_height"],
        overlap=values["overlap"], sigma=values["sigma"], low=values["low"],
        high=values["high"], min_dur_sec=values["min_dur_sec"],
        start_time=0, duration=max(999999, math.ceil(duration) + 1),
        estimated_duration_s=duration,
    )


def export_rallies(ffmpeg: str, media: Path, rallies: list[dict], job: Path,
                   progress: Progress):
    directory = job / "clips"
    directory.mkdir(exist_ok=True)
    total_duration = sum(rally["duration_seconds"] for rally in rallies)
    completed_duration = 0.0
    for rally in rallies:
        index = rally["id"]
        label = f"正在导出回合 {index} / {len(rallies)}（CPU 精确切分）"
        progress.update("exporting", 0.8 + 0.18 * completed_duration / max(total_duration, 1),
                        label, progress.total, force=True)
        # Input seeking is accurate with transcoding: FFmpeg decodes from the
        # preceding keyframe and discards pre-roll; output is never stream-copy.
        run_ffmpeg(ffmpeg, [
            "-threads", str(THREADS), "-ss", str(rally["start_seconds"]),
            "-i", str(media), "-t", str(rally["duration_seconds"]),
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-threads", str(THREADS), "-filter_threads", str(THREADS),
            "-c:a", "aac", "-movflags", "+faststart",
            str(directory / f"rally_{index:03d}.mp4"),
        ], job, lambda seconds: progress.update(
            "exporting", 0.8 + 0.18 * (completed_duration + min(
                seconds, rally["duration_seconds"])) / max(total_duration, 1),
            label, progress.total))
        completed_duration += rally["duration_seconds"]
    progress.update("exporting", 0.99, "正在整理回合下载文件。", progress.total, force=True)
    with zipfile.ZipFile(job / "clips.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for rally in rallies:
            name = f"rally_{rally['id']:03d}.mp4"
            archive.write(directory / name, name)
        archive.writestr("rallies.json", json.dumps(rallies, ensure_ascii=False, indent=2))


def run(root: Path, job: Path, video: Path, filename: str, progress: Progress) -> dict:
    started = time.perf_counter()
    progress.update("preparing", 0.01, "正在检查视频和本地模型。", force=True)
    source, artifact, manifest = find_assets(root)
    ffmpeg = find_media_tool(root, "ffmpeg")
    ffprobe = find_media_tool(root, "ffprobe")
    meta = inspect_video(ffprobe, video)
    source_meta = dict(meta)
    progress.total = meta["duration_seconds"]
    media, converted = prepare_media(ffmpeg, video, meta, job, progress)
    normalization_reasons = []
    if meta["rotation"]:
        normalization_reasons.append("旋转元数据需要转为实际画面方向")
    if abs(meta["start_seconds"]) >= 0.5:
        normalization_reasons.append("视频起始时间戳需要归零")
    normalized = bool(normalization_reasons)
    analysis_video = media if normalized else video
    playback_offset = meta["start_seconds"] if converted and not normalized else 0.0
    if normalized:
        meta = inspect_video(ffprobe, media)
        progress.total = meta["duration_seconds"]
    sys.path.insert(0, str(source))
    progress.update("analyzing", 0.12, "正在初始化完整 960 模型，优先使用 GPU。", force=True)
    capture = Capture(job, progress)
    analysis_started = time.perf_counter()
    with inference_runtime(progress, root) as runtime:
        from rallyclip_engine import run_analysis
        request = build_request(artifact, manifest, analysis_video, job, progress.total,
                                device=runtime.requested_device)
        with capture.installed():
            inference_result = run_analysis(request)
    analysis_seconds = time.perf_counter() - analysis_started
    if capture.tracks is None or capture.count == 0:
        raise RuntimeError("没有生成有效分析结果。")
    if capture.last_timestamp is None or capture.last_timestamp < progress.total - 1:
        raise RuntimeError("视频解码提前结束，未覆盖完整视频，请检查文件或重新导出后再试。")
    rallies = []
    for index, (start, end) in enumerate(inference_result.intervals_sec, 1):
        if not (math.isfinite(start) and math.isfinite(end)
                and 0 <= start < end <= progress.total + 0.25):
            raise RuntimeError("模型返回了超出视频时长的回合，请检查视频时间戳。")
        end = min(float(end), progress.total)
        rallies.append({"id": index, "start_seconds": float(start), "end_seconds": end,
                        "duration_seconds": end - float(start), "needs_review": True})
    import numpy as np
    np.savez_compressed(job / "model_scores.npz", timestamps=capture.times,
                        pointness=capture.tracks[0], start=capture.tracks[1],
                        end=capture.tracks[2])
    export_started = time.perf_counter()
    export_rallies(ffmpeg, media, rallies, job, progress)
    poses, stride = capture.display_samples(playback_offset)
    result = {
        "schema_version": 1, "filename": filename, "duration_seconds": progress.total,
        "analysis_seconds": analysis_seconds,
        "export_seconds": time.perf_counter() - export_started,
        "total_seconds": time.perf_counter() - started,
        "video": {key: meta[key] for key in ("width", "height", "fps")},
        "source_video": {key: source_meta[key] for key in
                         ("width", "height", "fps", "codec", "start_seconds", "rotation")},
        "rallies": rallies,
        "scores": {"timestamps": capture.times.tolist(),
                   "pointness": capture.tracks[0].tolist(),
                   "start": capture.tracks[1].tolist(), "end": capture.tracks[2].tolist()},
        "poses": poses, "pose_reference_size": capture.reference_size,
        "pose_total_samples": capture.count, "pose_display_stride": stride,
        "pose_missing": {"near": capture.missing_near, "far": capture.missing_far},
        "model": {
            "name": "RallyClip v0.5.0 · 完整 960",
            "device": runtime.device, "device_policy": runtime.mode,
            "fallback_reason": runtime.fallback_reason,
            "threads": THREADS, "sample_fps": 5, "input_size": 960,
            "threshold": 0.5, "decode_config": capture.decode_config,
            "sessions": runtime.sessions, "weights_sha256": MODEL_HASHES,
            "scene_splitting": False,
            "torch_imported": "torch" in sys.modules,
            "ultralytics_imported": "ultralytics" in sys.modules,
        },
        "needs_review": True, "media_converted": converted,
        "input_normalized": normalized, "input_normalization_reasons": normalization_reasons,
        "inference_source": "normalized_video" if normalized else "original_video",
        "pose_playback_offset_seconds": playback_offset,
        "notes": [
            "回合为模型候选结果，可播放复核；没有输入人工标注或在当前视频上训练。",
            "骨架为实际模型输入使用的近端/远端分配结果；缺失时不补造骨架。",
            "分数时间轴为模型的 5fps 名义网格；骨架时间戳来自实际视频帧。",
            "回合视频按源视频帧精确重编码，边界有一个视频帧以内的量化误差。",
        ] + (["本视频先经过方向/时间戳规范化再推理；转换使用 CPU 编码，输入像素可能与原文件有差异。"]
             if normalized else [])
          + ([f"长视频骨架预览每 {stride} 个真实样本显示一个；全量保留在 poses.jsonl，推理未降采样。"]
             if stride > 1 else []),
    }
    atomic_json(job / "result.json", result)
    progress.update("completed", 1, f"分析完成，识别到 {len(rallies)} 个候选回合。",
                    progress.total, force=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--filename", required=True)
    args = parser.parse_args(argv)
    job = args.job.resolve()
    job.mkdir(parents=True, exist_ok=True)
    progress = Progress(job)

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        run(args.root.resolve(), job, args.video.resolve(strict=True),
            args.filename, progress)
        return 0
    except KeyboardInterrupt:
        progress.update("cancelled", progress.value, "任务已取消。", force=True)
        return 130
    except Exception as exc:
        traceback.print_exc()
        progress.update("error", progress.value, str(exc), force=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
