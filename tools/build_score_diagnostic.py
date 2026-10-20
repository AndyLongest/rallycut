"""Build a self-contained local review page for captured RallyClip diagnostics."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from urllib.parse import urlparse


def build_page(diagnostic_path: Path, output_path: Path) -> Path:
    data = json.loads(diagnostic_path.read_text(encoding="utf-8-sig"))
    video = data.get("video", {})
    if not video.get("path"):
        raise ValueError("diagnostic.video.path is required")
    duration = float(video.get("duration_seconds", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("diagnostic.video.duration_seconds must be positive")
    source_path = str(video["path"])
    # Windows drive letters must not be mistaken for URL schemes.
    if urlparse(source_path).scheme.lower() in {"file", "http", "https"}:
        video["url"] = source_path
    else:
        source = Path(source_path)
        if not source.is_absolute():
            source = diagnostic_path.resolve().parent / source
        video["url"] = source.resolve().as_uri()
    data["video"] = video
    template_path = Path(__file__).with_name("templates") / "score_diagnostic.html"
    template = template_path.read_text(encoding="utf-8")
    if template.count("__DIAGNOSTIC_DATA__") != 1:
        raise RuntimeError("The HTML template must contain exactly one data placeholder")
    # Embedding arbitrary descriptions in a script element must not allow </script>.
    embedded = (
        json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        template.replace("__DIAGNOSTIC_DATA__", embedded), encoding="utf-8"
    )
    return output_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = build_page(args.diagnostic, args.output)
    print(json.dumps({"review_html": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
