"""Current full/fast visual inference + edit-boundary union, preserving long activity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from rallycut.cli import save
from rallycut.media import probe
from rallycut.visual_union import recover_long_candidates, fuse_visual_activity
from rallycut.union_review import write_union_review


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["fast", "full"], default="fast")
    parser.add_argument("--upstream", type=Path, default=project/"outputs/upstream_rallyclip/RallyClip-main")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--reuse-rallyclip", type=Path, help="Explicitly reuse a same-video capture directory")
    parser.add_argument("--reuse-scenes", type=Path, help="Explicitly reuse a same-video scene result directory")
    parser.add_argument("--merge-tolerance", type=float, default=1.0)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output directory")
    if args.threads < 1:
        parser.error("threads must be positive")
    video = args.video.resolve(strict=True)
    upstream = args.upstream.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True)
    started = time.perf_counter()
    environment = {**os.environ, "OMP_NUM_THREADS": str(args.threads),
                   "MKL_NUM_THREADS": str(args.threads), "OPENBLAS_NUM_THREADS": str(args.threads)}
    media_bin = project/"runtime/ffmpeg/bin"
    if media_bin.is_dir():
        environment["PATH"] = str(media_bin) + os.pathsep + environment.get("PATH", "")
        os.environ["PATH"] = environment["PATH"]
    meta = probe(video)

    def run(name, command):
        print(name, flush=True)
        with (out/(name+".log")).open("w", encoding="utf8") as log:
            subprocess.run(command, cwd=project, env=environment, stdout=log,
                           stderr=subprocess.STDOUT, check=True)

    pose_dir = args.reuse_rallyclip.resolve() if args.reuse_rallyclip else out/"rallyclip"
    scene_dir = args.reuse_scenes.resolve() if args.reuse_scenes else out/"scenes"
    if not args.reuse_rallyclip:
        if args.mode == "fast":
            command = [sys.executable, str(project/"tools/run_fast_visual.py"), str(video),
                       "--upstream", str(upstream), "--output", str(pose_dir), "--threads", str(args.threads)]
        else:
            command = [sys.executable, str(project/"tools/benchmark_rallyclip.py"), str(upstream), str(video),
                       "--output", str(pose_dir), "--threads", str(args.threads), "--capture-scores"]
        run("rallyclip", command)
    prediction = json.loads((pose_dir/"rallies.json").read_text(encoding="utf8"))
    expected_method = "experimental_rallyclip_visual_accelerated" if args.mode == "fast" else "upstream_rallyclip_tcn_cpu"
    if prediction["method"] != expected_method:
        raise ValueError("Saved inference mode differs from --mode")
    if (Path(prediction["video"]["path"]).resolve() != video
            or abs(prediction["video"]["duration_seconds"]-meta["duration_seconds"]) > 1e-4):
        raise ValueError("Saved inference belongs to a different video")
    if not args.reuse_scenes:
        run("scenes", [sys.executable, "-m", "rallycut.cli", "analyze", str(video),
                      "--mode", "edited", "--fps", "4", "--width", "320",
                      "--threads", str(args.threads), "--output", str(scene_dir)])
    scenes = json.loads((scene_dir/"rallies.json").read_text(encoding="utf8"))
    capture = json.loads((pose_dir/"score_capture.json").read_text(encoding="utf8"))
    sys.path.insert(0, str(upstream/"src"))
    from infer import heatmap_decode
    with np.load(pose_dir/"model_scores.npz") as scores:
        activity = recover_long_candidates(prediction, scores, capture, heatmap_decode)
    result = fuse_visual_activity(activity, scenes, args.merge_tolerance)
    elapsed = time.perf_counter()-started
    save(activity, out/"activity")
    result["timings"]["current_invocation_analysis_seconds"] = elapsed
    result["timings"]["cached_rallyclip"] = bool(args.reuse_rallyclip)
    result["timings"]["cached_scenes"] = bool(args.reuse_scenes)
    result["timings"]["timing_basis"] = (
        "Recorded source-run measurements plus fusion; current invocation reuses explicit saved results."
        if args.reuse_rallyclip or args.reuse_scenes else
        "Measured sequential CPU analysis, excluding result page writing and media export.")
    if not args.reuse_rallyclip and not args.reuse_scenes:
        result["wall_seconds"] = elapsed
    result["source_result_paths"] = {"RallyClip": str(pose_dir/"rallies.json"),
                                     "PySceneDetect": str(scene_dir/"rallies.json")}
    result["score_capture_sha256"] = hashlib.sha256((pose_dir/"model_scores.npz").read_bytes()).hexdigest()
    save(result, out/"fused")
    write_union_review(result, out/"fused/review.html")
    print(json.dumps({"output": str(out/"fused"), "rallies": result["rallies"],
                      "statistics": result["fusion"]["statistics"],
                      "timings": result["timings"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
