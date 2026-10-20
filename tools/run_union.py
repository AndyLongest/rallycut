"""One-video CPU runner for RallyClip + PySceneDetect boundary union."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from rallycut.cli import save
from rallycut.fusion import fuse_predictions


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, default=project/"outputs/upstream_rallyclip/RallyClip-main")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--imgsz", type=int, choices=[416,640,960], default=416,
                        help="Pose input size; 960 restores the official artifact default, 416 is the speed experiment")
    parser.add_argument("--merge-tolerance", type=float, default=1)
    parser.add_argument("--short-seconds", type=float, default=1)
    parser.add_argument("--labels", type=Path, help="Optional independent annotations, read after inference")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("threads must be positive")
    video = args.video.resolve(strict=True)
    upstream = args.upstream.resolve(strict=True)
    if not (upstream/"models/rallyclip_v0.5.0/model.onnx").is_file():
        parser.error("RallyClip v0.5.0 official artifacts are required; see docs/RAW_VIDEO_20261019.md")
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    started = time.perf_counter()
    environment = {**os.environ, "OMP_NUM_THREADS": str(args.threads), "MKL_NUM_THREADS": str(args.threads),
                   "OPENBLAS_NUM_THREADS": str(args.threads)}

    def run(stage, command):
        print(stage, flush=True)
        result = subprocess.run(command, cwd=project, env=environment, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        (out/f"{stage}.log").write_text(result.stdout+result.stderr,encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"{stage} failed; inspect {out / (stage+'.log')}")

    rallyclip_command = [sys.executable,str(project/"tools/benchmark_rallyclip.py"),str(upstream),str(video),
                         "--output",str(out/"rallyclip"),"--threads",str(args.threads)]
    if args.imgsz != 960:
        rallyclip_command += ["--imgsz",str(args.imgsz)]
    run("rallyclip_cpu",rallyclip_command)
    run("scene_cpu", [sys.executable,"-m","rallycut.cli","analyze",str(video),"--mode","edited",
                      "--fps","4","--width","320","--threads",str(args.threads),"--output",str(out/"scenes")])
    rallyclip = json.loads((out/"rallyclip/rallies.json").read_text(encoding="utf-8"))
    scenes = json.loads((out/"scenes/rallies.json").read_text(encoding="utf-8"))
    result = fuse_predictions(rallyclip,scenes,args.merge_tolerance,args.short_seconds)
    result["timings"]["end_to_end_analysis_seconds"] = time.perf_counter()-started
    result["timings"]["timing_basis"] = "Measured sequential CPU inference plus fusion, excluding video rendering."
    result["wall_seconds"] = result["timings"]["end_to_end_analysis_seconds"]
    result["source_result_paths"] = {"RallyClip": str(out/"rallyclip/rallies.json"),"PySceneDetect": str(out/"scenes/rallies.json")}
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else None
    save(result,out/"fused",labels)
    if args.render:
        command = [sys.executable,str(project/"tools/render_prediction_video.py"),str(out/"fused/rallies.json")]
        if args.labels:
            command.append(str(args.labels.resolve()))
        command += ["--output",str(out/"rendered/prediction_union.mp4"),"--threads",str(args.threads)]
        run("render_cpu",command)
    (out/"pipeline_audit.json").write_text(json.dumps({"video": str(video),"cpu_only": True,
        "threads": args.threads,"pose_input_size": args.imgsz,"analysis_seconds": result["wall_seconds"],
        "total_seconds_including_render_and_reports": time.perf_counter()-started,
        "shared_decode": False,"statistics": result["fusion"]["statistics"],
        "labels_loaded_after_inference": True,"rendered": args.render},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"output": str(out),"analysis_seconds": result["wall_seconds"],
                      "statistics": result["fusion"]["statistics"]},ensure_ascii=False,indent=2),flush=True)


if __name__ == "__main__":
    main()
