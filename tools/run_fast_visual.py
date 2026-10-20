"""Pure-visual experimental fast CLI. No teacher files or audio analysis inputs."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, default=root/"outputs/upstream_rallyclip/RallyClip-main")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if not args.video.is_file():
        parser.error("Video file does not exist")
    if args.output.exists():
        parser.error("Choose a new output directory; existing results are preserved")
    if args.threads < 1:
        parser.error("threads must be positive")
    command = [sys.executable, str(root/"tools/benchmark_rallyclip.py"),
               str(args.upstream.resolve()), str(args.video.resolve()),
               "--output", str(args.output.resolve()), "--threads", str(args.threads),
               "--crop-refresh", "10", "--crop-size", "256",
               "--court-attempts", "1", "--empty-recheck", "5", "--capture-scores"]
    raise SystemExit(subprocess.call(command, cwd=root))


if __name__ == "__main__":
    main()
