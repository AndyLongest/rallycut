"""Build a separate CPU INT8 pose artifact from visual calibration frames only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--upstream", type=Path, required=True)
parser.add_argument("--video", type=Path, action="append", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--frames-per-video", type=int, default=24)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(args.upstream.resolve() / "src"))
import cv2
import av
import numpy as np
import onnx
import onnxruntime as ort
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from onnxruntime.quantization.shape_inference import quant_pre_process
from extraction.yolo_onnx_runner import letterbox

cv2.setNumThreads(2)
original_session = ort.InferenceSession
def session(path, sess_options=None, **kwargs):
    options = sess_options or ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    return original_session(path, sess_options=options, **kwargs)
ort.InferenceSession = session
source = args.upstream / "models/rallyclip_v0.5.0/yolov8n-pose-960-dynamic.onnx"
prepared = args.output / "prepared.onnx"
started = time.perf_counter()
quant_pre_process(str(source), str(prepared), skip_symbolic_shape=True)
model = onnx.load(str(prepared))
input_name = model.graph.input[0].name
excluded = [node.name for node in model.graph.node if "/model.22/" in node.name]
records = []
class Reader(CalibrationDataReader):
    def __init__(self):
        self.iterator = self.frames()

    def frames(self):
        for video in args.video:
            with av.open(str(video.resolve())) as container:
                stream = container.streams.video[0]
                stream.codec_context.thread_count = 2
                duration = float(stream.duration*stream.time_base)
                targets = iter(np.linspace(.2, max(.2,duration-.5), args.frames_per_video))
                target = next(targets, None)
                for frame in container.decode(stream):
                    if target is None:
                        break
                    stamp = float(frame.pts*stream.time_base)
                    if stamp < target:
                        continue
                    records.append({"video": str(video.resolve()), "pts": int(frame.pts),
                                    "seconds": stamp})
                    print(f"calibration {len(records)} @ {video.name} {stamp:.1f}s", flush=True)
                    yield {input_name: letterbox(frame.to_ndarray(format="bgr24"), 960)[0]}
                    target = next(targets, None)

    def get_next(self):
        return next(self.iterator, None)

quantize_static(str(prepared), str(args.output / "pose-int8.onnx"), Reader(),
                quant_format=QuantFormat.QDQ, activation_type=QuantType.QInt8,
                weight_type=QuantType.QInt8, per_channel=True,
                op_types_to_quantize=["Conv"], nodes_to_exclude=excluded,
                calibration_providers=["CPUExecutionProvider"])
audit = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
         "model_sha256": hashlib.sha256((args.output/"pose-int8.onnx").read_bytes()).hexdigest(),
         "calibration": records, "audio_used": False, "teacher_labels_used": False,
         "head_kept_fp32": True, "seconds": time.perf_counter()-started,
         "source": "https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html",
         "onnx": onnx.__version__, "onnxruntime": ort.__version__}
(args.output/"audit.json").write_text(json.dumps(audit, indent=2), encoding="utf8")
print(json.dumps({"seconds":audit["seconds"],"frames":len(records),"output":str(args.output)}))
