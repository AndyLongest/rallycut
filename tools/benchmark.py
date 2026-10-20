"""Repeatable, sequential CPU sampling ablation. Labels are evaluation-only."""
from pathlib import Path
import argparse
import json

from rallycut.cli import main


parser = argparse.ArgumentParser()
parser.add_argument("video", type=Path)
parser.add_argument("--labels", type=Path)
parser.add_argument("--output", type=Path, default=Path("outputs/benchmark"))
args = parser.parse_args()
results = []
for fps, width in [(1, 320), (2, 320), (4, 160), (4, 320), (4, 480), (8, 320)]:
    directory = args.output / f"fps{fps}_width{width}"
    command = ["analyze", str(args.video), "--mode", "edited", "--fps", str(fps),
               "--width", str(width), "--threads", "2", "--output", str(directory)]
    if args.labels:
        command.extend(["--labels", str(args.labels)])
    main(command)
    result = json.loads((directory / "rallies.json").read_text(encoding="utf-8"))
    results.append({"fps": fps, "width": width, "wall_seconds": result["wall_seconds"],
                    "rallies": len(result["rallies"]),
                    "cut_seconds": result["scene_cut_candidates_seconds"],
                    "evaluation": result.get("evaluation")})
(args.output / "comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
