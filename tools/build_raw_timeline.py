"""Build the raw-video timeline page from saved predictions, without inference."""
from pathlib import Path
import html
import json

from rallycut.evaluate import evaluate_end_events


def build_timeline(project: Path) -> Path:
    annotation = json.loads((project / "tests/fixtures/demo3_clip1.manual_ends.v1.json").read_text(encoding="utf-8"))
    sources = [
        ("cpu416", "CPU 416", "RallyClip · 416", "outputs/demo3_clip1_rallyclip_416/rallies.json"),
        ("cpu640", "CPU 640", "RallyClip · 640", "outputs/demo3_clip1_rallyclip_640/rallies.json"),
        ("cpu960", "CPU 960", "RallyClip · 原始 960", "outputs/demo3_clip1_rallyclip_cpu/rallies.json"),
        ("gemini", "Gemini", "Gemini · 原生视频", "outputs/demo3_clip1_gemini_native/result/rallies.json"),
    ]
    models = []
    video = None
    for key, name, full, relative in sources:
        result = json.loads((project / relative).read_text(encoding="utf-8"))
        if Path(result["video"]["path"]).name.lower() != annotation["video_name"].lower():
            raise ValueError("Timeline mixes different source videos")
        if video is not None and result["video"]["path"] != video["path"]:
            raise ValueError("Timeline source video paths differ")
        video = result["video"]
        models.append({
            "id": key, "name": name, "full": full,
            "seconds": round(result["wall_seconds"], 2),
            "preparation": round(result.get("preparation_seconds", 0), 2),
            "intervals": [[r["start_seconds"], r["end_seconds"]] for r in result["rallies"]],
            "evaluation": evaluate_end_events(result["rallies"], annotation, video["duration_seconds"], 2)["ends"],
        })
    data = {"video": annotation["video_name"], "duration": video["duration_seconds"],
            "events": annotation["events"], "models": models}
    templates = project / "tools/templates"
    fragment = (templates / "raw_timeline_fragment.html").read_text(encoding="utf-8")
    fragment = fragment.replace("__TIMELINE_DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"))
    page = (templates / "raw_timeline_page.html").read_text(encoding="utf-8")
    page = page.replace("__TIMELINE_FRAGMENT__", fragment).replace("__VIDEO_URI__", html.escape(Path(video["path"]).as_uri(), quote=True))
    output = project / "outputs/demo3_clip1_comparison/timeline.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return output


if __name__ == "__main__":
    print(build_timeline(Path(__file__).resolve().parents[1]))
