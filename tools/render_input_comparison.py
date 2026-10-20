"""Export actual CPU pose-session inputs for the same video frames."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import av
import cv2
import numpy as np


def save_png(path, bgr):
    ok, encoded = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("PNG encode failed")
    path.write_bytes(encoded.tobytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    upstream = args.upstream.resolve()
    sys.path.insert(0, str(upstream / "src"))
    from extraction.yolo_onnx_runner import YOLO, letterbox

    weights = upstream / "models/rallyclip_v0.5.0/yolov8n-pose-960-dynamic.onnx"
    runner = YOLO(str(weights), providers=["CPUExecutionProvider"], intra_op_threads=2)
    session = runner._session
    captured = []

    class Observer:
        def run(self, names, feed):
            captured.append(next(iter(feed.values())).copy())
            return session.run(names, feed)

    runner._session = Observer()
    assert runner._static_hw is None
    cv2.setNumThreads(2)
    wanted = [10.0, 20.0, 30.0]
    frames = []
    with av.open(str(args.video.resolve())) as container:
        container.streams.video[0].codec_context.thread_count = 2
        for frame in container.decode(video=0):
            if not wanted:
                break
            timestamp = float(frame.time)
            if timestamp + 1e-7 < wanted[0]:
                continue
            requested = wanted.pop(0)
            bgr = frame.to_ndarray(format="bgr24")
            stem = f"frame_{int(requested):02d}"
            save_png(output / (stem + "_source.png"), bgr)
            item = {
                "requested_seconds": requested, "timestamp_seconds": timestamp,
                "source_width": bgr.shape[1], "source_height": bgr.shape[0],
                "source_png": stem + "_source.png", "inputs": {},
            }
            for size in (416, 960):
                result = runner.predict(source=[bgr], conf=0.25, imgsz=size, device="cpu")[0]
                tensor = captured.pop()
                expected, ratio, pad = letterbox(bgr, size)
                assert np.array_equal(tensor, expected)
                rgb = np.rint(tensor[0].transpose(1, 2, 0) * 255).astype(np.uint8)
                png = stem + f"_input_{size}.png"
                save_png(output / png, rgb[..., ::-1])
                recovered = cv2.imdecode(np.fromfile(output / png, np.uint8), cv2.IMREAD_COLOR)
                assert np.array_equal(
                    recovered[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255,
                    tensor,
                )
                np.save(output / (stem + f"_tensor_{size}.npy"), tensor)
                boxes = result.boxes.xyxy.numpy()
                if size == 960 and len(boxes):
                    box = max(boxes, key=lambda b: b[3])
                    item["near_focus"] = [float((box[0] + box[2]) / 2),
                                          float((box[1] + box[3]) / 2)]
                item["inputs"][str(size)] = {
                    "png": png, "tensor_shape": list(tensor.shape),
                    "width": tensor.shape[3], "height": tensor.shape[2],
                    "ratio": ratio, "pad_left": pad[0], "pad_top": pad[1],
                    "tensor_sha256": hashlib.sha256(tensor.tobytes()).hexdigest(),
                    "png_roundtrip_exact": True,
                    "raw_person_detections": len(boxes),
                }
            frames.append(item)
    if wanted:
        raise RuntimeError("Input video did not include all requested times")
    audit = {
        "video": str(args.video.resolve()), "frames": frames,
        "model_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "providers": session.get_providers(), "same_source_frame_per_pair": True,
        "captured_at": "actual ONNX InferenceSession.run feed, pose model only",
        "upstream_modified": False, "model_retrained": False,
        "temporal_model_run": False,
        "note": "Input-size visualization only; single-frame detections do not explain temporal segmentation.",
    }
    (output / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    template = (Path(__file__).parent / "templates/input_comparison.html").read_text(encoding="utf-8")
    page = template.replace("__INPUT_COMPARISON_DATA__", json.dumps(audit, ensure_ascii=False).replace("<", "\\u003c"))
    (output / "review.html").write_text(page, encoding="utf-8")
    print(json.dumps({"page": str(output / "review.html"),
                      "frames": [{key: row[key] for key in ("timestamp_seconds", "inputs")} for row in frames]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
