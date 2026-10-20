"""Burn saved rally predictions and separately labelled human ends into an MP4."""
import argparse
import html
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import quote

from rallycut.evaluate import evaluate_end_events
from rallycut.media import executable, probe
from rallycut.segment import validate_rallies


def timestamp(seconds):
    ticks = round(seconds * 100)
    return f"{ticks // 360000}:{ticks // 6000 % 60:02}:{ticks // 100 % 60:02}.{ticks % 100:02}"


def display_time(seconds):
    ticks = round(seconds * 100)
    return f"{ticks // 6000:02}:{ticks // 100 % 60:02}.{ticks % 100:02}"


def overlay_identity(result):
    if result.get("method") == "boundary_union_cpu":
        return False, "RallyClip + PySceneDetect · 边界并集", "并集"
    edits = result.get("task_kind") == "edit_boundary_diagnostic" or result["method"] in ("edited", "scene")
    name = "剪辑接缝检测（剪辑分段）" if edits else (
        "CPU 416 · 模型预测" if result["method"] == "upstream_rallyclip_tcn_cpu_416" else result["method"])
    return edits, name, "剪辑" if edits else "模型"


def build_overlay(result, annotation, width=1280):
    video = result["video"]
    duration = video["duration_seconds"]
    fused = result.get("method") == "boundary_union_cpu"
    rallies = validate_rallies(result["timeline_segments"] if fused else result["rallies"], duration)
    has_manual = bool(annotation and annotation.get("events"))
    evaluation = evaluate_end_events(result["rallies"], annotation, duration, 2)["ends"] if has_manual else None
    annotation = annotation or {"events": []}
    edits, name, noun = overlay_identity(result)
    height = round(width * video["height"] / video["width"] / 2) * 2
    # Keep the court fully visible: the two timeline rows occupy an added footer.
    canvas = height + 144
    teal, orange, white, muted = "&HC2C663&", "&H7BA6FF&", "&HF4F1EC&", "&HCABEAD&"
    rows = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}",
            f"PlayResY: {canvas}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
            "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Text,Microsoft YaHei,22,{white},{white},&H00221A10&,&H00221A10&,0,0,0,0,100,100,0,0,1,0.7,0,7,0,0,0,1", "",
            "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    def event(start, end, content, layer=3):
        if end > start:
            rows.append(f"Dialogue: {layer},{timestamp(max(0,start))},{timestamp(min(duration,end))},Text,,0,0,0,,{content}")

    def text(start, end, x, y, content, size=22, color=white, align=7):
        clean = str(content).replace("\\", "＼").replace("{", "（").replace("}", "）").replace("\n", " ")
        event(start, end, f"{{\\an{align}\\pos({x},{y})\\fs{size}\\c{color}}}{clean}")

    def box(start, end, x, y, w, h, color, alpha="00", layer=1):
        event(start, end, f"{{\\an7\\pos({x},{y})\\bord0\\shad0\\c{color}\\alpha&H{alpha}&\\p1}}m 0 0 l {w} 0 l {w} {h} l 0 {h}{{\\p0}}", layer)

    box(0, duration, 18, 18, 500, 90, "&H221A10&", "30")
    text(0, duration, 34, 86, name, 16, muted)
    cursor = 0
    for index, rally in enumerate(rallies, 1):
        start, end = rally["start_seconds"], rally["end_seconds"]
        if start > cursor:
            text(cursor, start, 34, 28, "剪辑区间外" if edits else "模型：回合外", 28, muted)
            text(cursor, start, 34, 59, "当前没有分段" if edits else "当前没有回合候选", 18, muted)
        unconfirmed = fused and rally.get("activity_state") == "outside_rallyclip_candidate"
        active_text = f"并集区间 {index:02} · {'待确认' if unconfirmed else '动作支持'}" if fused else (
            f"剪辑分段 · 第 {index:02} 段" if edits else f"模型：回合中 · 候选 {index:02}")
        text(start, end, 34, 28, active_text, 28, muted if unconfirmed else teal)
        text(start, end, 34, 59, f"{display_time(start)} — {display_time(end)}", 18)
        box(start, end, 18, 18, 4, 90, teal)
        if fused and rally.get("short_fragment"):
            text(start, end, 34, 112, "短碎段：保留，待复核", 21, orange)
        if edits and start > 0:
            stop = min(end, start + 1.5)
            box(start, stop, width-510, 226, 492, 42, "&H221A10&", "18")
            text(start, stop, width-496, 231, f"检测到剪辑点：{display_time(start)}", 23, teal)
        cursor = end
    if cursor < duration:
        text(cursor, duration, 34, 28, "模型：回合外", 28, muted)
        text(cursor, duration, 34, 59, "当前没有回合候选", 18, muted)

    # Human annotation callouts are evaluation overlays, never model input.
    matched_by_manual = {m["manual_index"]: m for m in evaluation["matches"]} if evaluation else {}
    panel_x = width - 510
    for i, manual in enumerate(annotation["events"]):
        end = manual["end_seconds"]
        start, stop = max(0, end - 1), min(duration, end + 3)
        box(start, stop, panel_x, 116, 492, 94, "&H221A10&", "18")
        text(start, stop, panel_x + 14, 124, f"人工结束：{display_time(end)}", 25, orange)
        if manual.get("serve_fault"):
            detail = "发球失误 · 允许与后续尝试合并"
        elif i in matched_by_manual:
            delta = matched_by_manual[i]["predicted_end_seconds"] - end
            detail = f"{'剪辑点' if edits else '模型结束'}{'晚' if delta >= 0 else '早'} {abs(delta):.2f} 秒（±2秒内）"
        else:
            detail = "±2 秒内未检测到剪辑点" if edits else "模型未在 ±2 秒内输出结束"
        text(start, stop, panel_x + 14, 158, detail, 21)
        text(start, stop, panel_x + 14, 186, manual["description"], 16, muted)

    # Two rows share a single time axis; manual annotations have no invented starts.
    x0, x1 = 140, width - 30
    time_x = lambda t: round(x0 + (x1 - x0) * t / duration)
    model_y, human_y = height + 51, height + 94
    text(0, duration, 24, height + 9, "整段视频对照", 18, muted)
    legend = "青：动作支持  灰：待确认  橙线：剪辑  紫线：双路" if fused else (
        "青色：剪辑分段    白线：人工结束    接缝不等同真实回合" if edits else "青色：模型区间    白线：人工结束    *：发球失误可合并")
    text(0, duration, 248, height + 9, legend, 18, muted)
    text(0, duration, 24, model_y - 6, noun, 20)
    text(0, duration, 24, human_y - 7, "人工" if has_manual else ("动作" if fused else "标注"), 20)
    box(0, duration, x0, model_y, x1 - x0, 12, "&H504634&")
    box(0, duration, x0, human_y, x1 - x0, 2, "&H504634&")
    matched_p = {m["prediction_index"] for m in evaluation["matches"]} if evaluation else set()
    for i, rally in enumerate(rallies):
        a, b = time_x(rally["start_seconds"]), time_x(rally["end_seconds"])
        color = "&H746A58&" if fused and rally.get("activity_state") == "outside_rallyclip_candidate" else teal
        box(0, duration, a, model_y, max(1, b-a), 12, color)
        if edits and i < len(rallies)-1:
            box(0, duration, b-1, model_y-6, 2, 24, orange, layer=2)
        if evaluation and not fused and i not in matched_p:
            text(0, duration, b, model_y - 6, "×", 21, orange, align=8)
    if fused:
        for point in result["boundaries"]:
            t = point["seconds"]
            color = "&HDF99C8&" if point["agreement"] == "both" else (
                orange if point["sources"] == ["PySceneDetect"] else teal)
            box(0, duration, time_x(t)-1, model_y-6, 2, 24, color, layer=2)
            if 0 < t < duration:
                stop = min(duration,t+1.1)
                box(t, stop, width-510, 226, 492, 42, "&H221A10&", "18")
                text(t, stop, width-496, 231, f"边界 {display_time(t)} · {'双路' if point['agreement']=='both' else ('剪辑' if 'PySceneDetect' in point['sources'] else '动作')}", 22, color)
        if not has_manual:
            for row in result["rallies"]:
                a,b = time_x(row["start_seconds"]),time_x(row["end_seconds"])
                box(0,duration,a,human_y-5,max(1,b-a),12,teal)
            text(0,duration,x0,human_y+11,"下行：RallyClip原始动作候选；无人工标注，不计算准确率",16,muted)
    elif not has_manual:
        text(0,duration,x0,human_y+11,"没有人工结束标注，不计算准确率",16,muted)
    for manual in annotation["events"]:
        x = time_x(manual["end_seconds"])
        box(0, duration, x-1, human_y - 6, 2, 15, orange if manual.get("serve_fault") else white)
        label = display_time(manual["end_seconds"])[:-3] + ("*" if manual.get("serve_fault") else "")
        if manual.get("approximate"):
            label = "≈" + label
        text(0, duration, min(x1-18, max(x0+20,x)), human_y + 10, label, 16, white, align=8)
    for second in range(0, int(duration) + 1, 60):
        x = time_x(second)
        text(0, duration, x, height + 127, display_time(second)[:-3], 15, muted, align=8)
    text(0, duration, x1, height + 127, display_time(duration), 15, muted, align=9)
    for second in range(int(duration) + 1):
        text(second, min(duration,second+1), width-28, height+9,
             f"{display_time(second)[:-3]} / {display_time(duration)}", 18, white, align=9)
    event(0, duration,
          f"{{\\an7\\move({x0},{model_y-6},{x1},{model_y-6})\\bord0\\shad0\\c{orange}\\p1}}m 0 0 l 2 0 l 2 57 l 0 57{{\\p0}}", 6)
    return "\n".join(rows) + "\n", height, canvas, evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("labels", type=Path, nargs="?", help="Optional independent human end-event labels")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("threads must be positive")
    result = json.loads(args.predictions.read_text(encoding="utf-8"))
    annotation = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else None
    meta = probe(result["video"]["path"])
    if annotation and Path(meta["path"]).name.lower() != annotation["video_name"].lower():
        raise ValueError("Manual annotations belong to a different video")
    if abs(meta["duration_seconds"] - result["video"]["duration_seconds"]) > .1:
        raise ValueError("Saved predictions do not match source duration")
    output = args.output.resolve()
    if output.suffix.lower() != ".mp4" or output == Path(meta["path"]):
        raise ValueError("Output must be a separate MP4")
    output.parent.mkdir(parents=True, exist_ok=True)
    subtitle, height, canvas, evaluation = build_overlay(result, annotation)
    ass_path = output.parent / "prediction_overlay.ass"
    ass_path.write_text(subtitle, encoding="utf-8-sig")
    # Relative ASS path avoids Windows drive-colon escaping in FFmpeg's filter parser.
    vf = f"setpts=PTS-STARTPTS,fps=30,scale=1280:{height},pad=1280:{canvas}:0:0:color=0x101A22,tpad=stop_mode=clone:stop_duration=0.1,ass=prediction_overlay.ass"
    command = [executable("ffmpeg", encoder="libx264"), "-hide_banner", "-nostdin", "-y",
               "-threads", str(args.threads), "-i", meta["path"], "-map", f"0:{meta['video_stream_index']}",
               "-map", "0:a:0?", "-vf", vf, "-af", "asetpts=PTS-STARTPTS",
               "-t", str(meta["duration_seconds"]), "-filter_threads", str(args.threads),
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
               "-threads", str(args.threads), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
               "-progress", "pipe:1", "-nostats", str(output)]
    started = time.perf_counter()
    with (output.parent / "render.log").open("w", encoding="utf-8") as errors:
        process = subprocess.Popen(command, cwd=output.parent, stdout=subprocess.PIPE,
                                   stderr=errors, text=True, encoding="utf-8")
        last = -30
        for line in process.stdout:
            if line.startswith("out_time_us="):
                try:
                    seconds = int(line.split("=",1)[1]) / 1_000_000
                except ValueError:
                    continue
                if seconds - last >= 30:
                    print(f"Rendered {seconds:.0f}/{meta['duration_seconds']:.0f} seconds", flush=True)
                    last = seconds
        if process.wait():
            raise RuntimeError(f"Video render failed; inspect {output.parent / 'render.log'}")
    rendered = probe(output)
    if abs(rendered["duration_seconds"] - meta["duration_seconds"]) > .2:
        raise RuntimeError("Rendered duration differs from source")
    audit = {"source_predictions": str(args.predictions.resolve()), "source_labels": str(args.labels.resolve()) if args.labels else None,
             "method": result["method"], "render_seconds": time.perf_counter()-started,
             "render_only_no_inference": True, "encoder": "libx264", "hardware_acceleration": False,
             "threads": args.threads, "output": rendered, "end_evaluation": evaluation,
             "annotation_notes": annotation.get("notes") if annotation else None,
             "note": "Human labels only draw separate evaluation overlays; no inferred human starts."}
    (output.parent / "render_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    report_url = quote(os.path.relpath(args.predictions.resolve().parent / "review.html", output.parent).replace(os.sep, "/"), safe="/")
    edits, name, noun = overlay_identity(result)
    heading = "剪辑接缝检测 · 叠加结果视频" if edits else "模型预测，直接叠加在视频上"
    legend = "青色显示剪辑分段，人工结束单独提示；接缝出现时闪现检测时间。剪辑接缝不等同于真实回合结束。" if edits else "青色显示模型候选，人工结束单独提示；底部两行时间轴随视频移动。发球失误以 * 标注。"
    if result.get("method") == "boundary_union_cpu":
        heading = "双路边界并集 · 随机demo测试"
        legend = "完整并集分区全部保留：青色有RallyClip动作支持，灰色待确认；橙线为剪辑边界，紫线为两路共识。下行显示原始动作候选。这段没有人工回合标注，不报告准确率。"
    elif not annotation:
        legend += " 本段无人工回合标注，不计算准确率。"
    review = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(name)} · 叠加结果视频</title>
<style>body{{background:#101a22;color:#ecf1f4;font:16px system-ui;margin:24px}}main{{max-width:1280px;margin:auto}}video{{width:100%;max-height:85vh}}a{{color:#63c6c2}}p{{color:#adbeca}}</style>
<main><h2>{heading}</h2><p>{legend}</p><video controls preload="metadata" src="{html.escape(output.name,quote=True)}"></video><p>{html.escape(name)} · 画面叠加来自已保存的识别结果 · <a href="{html.escape(report_url,quote=True)}">查看原始识别报告</a></p></main></html>'''
    (output.parent / "review.html").write_text(review, encoding="utf-8")
    print(output, flush=True)


if __name__ == "__main__":
    main()
