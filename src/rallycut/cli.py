from pathlib import Path
import argparse
import csv
import json
import os
import platform
import subprocess
import time

from .audio import detect_onsets
from .ball_activity import extract_ball_activity, segment_ball_activity
from .evaluate import evaluate, evaluate_end_events
from .fusion import fuse_predictions
from .llm import call_prepared, prepare
from .media import executable, export_clips, probe
from .report import write_report
from .segment import segment
from .vision import extract_visual, install_model


def save(result, output, labels=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if labels:
        evaluator = evaluate_end_events if labels.get("annotation_type")=="rally_end_events" else evaluate
        target = labels if evaluator is evaluate_end_events else labels["rallies"]
        result["evaluation"] = evaluator(result["rallies"], target, result["video"]["duration_seconds"])
        result["manual_label_source"] = labels.get("source")
    (output / "rallies.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "rallies.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["rally", "start_seconds", "end_seconds", "needs_review"])
        writer.writeheader()
        for index, row in enumerate(result["rallies"], 1):
            writer.writerow({"rally": index, **{k:row.get(k, True) for k in writer.fieldnames if k != "rally"}})
    if result.get("method") == "boundary_union_cpu":
        with (output / "boundaries.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["seconds", "sources", "agreement", "needs_review"])
            writer.writeheader()
            for point in result["boundaries"]:
                writer.writerow({k: "+".join(point[k]) if k == "sources" else point[k] for k in writer.fieldnames})
        with (output / "timeline_segments.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            fields = ["start_seconds", "end_seconds", "activity_state", "start_sources", "end_sources", "short_fragment", "needs_review"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in result["timeline_segments"]:
                writer.writerow({k: "+".join(row[k]) if k.endswith("_sources") else row[k] for k in fields})
    write_report(result, output / "review.html", labels)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independent tennis rally segmentation, CPU by default")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="CPU sampled CV/audio baselines")
    analyze.add_argument("video", type=Path)
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--mode", choices=["edited", "scene", "visual", "audio", "hybrid", "ball-motion"], default="hybrid")
    analyze.add_argument("--fps", type=float, help="Default 6 for ball-motion, 4 otherwise")
    analyze.add_argument("--width", type=int, help="Default 960 for ball-motion, 320 otherwise")
    analyze.add_argument("--threads", type=int, default=2)
    analyze.add_argument("--person-model", type=Path, help="Optional CPU YOLOX-Nano evidence; no pose")
    analyze.add_argument("--roi", type=Path, help='JSON {"points":[[x,y],...]} normalized court polygon')
    analyze.add_argument("--labels", type=Path, help="Evaluation only; never passed to detector")
    analyze.add_argument("--export-clips", action="store_true")
    analyze.add_argument("--preview", action="store_true", help="Also transcode a browser-playable review copy")
    vlm = commands.add_parser("vlm-prepare", help="Prepare sampled images and prompts without calling a service")
    vlm.add_argument("video", type=Path)
    vlm.add_argument("--output", type=Path, required=True)
    vlm.add_argument("--fps", type=float, default=1)
    vlm.add_argument("--threads", type=int, default=2)
    call = commands.add_parser("vlm-call", help="Call the explicitly configured external/local VLM endpoint")
    call.add_argument("directory", type=Path)
    call.add_argument("--labels", type=Path)
    gemini = commands.add_parser("gemini-call", help="Call native Gemini/Vertex AI with a prepared image sequence")
    gemini.add_argument("directory", type=Path)
    gemini.add_argument("--model", help="Available Gemini model ID, or RALLYCUT_GEMINI_MODEL")
    gemini.add_argument("--labels", type=Path)
    native = commands.add_parser("gemini-video-prepare", help="CPU encode a compact native-video request")
    native.add_argument("video",type=Path)
    native.add_argument("--output",type=Path,required=True)
    native.add_argument("--fps",type=float,default=2)
    native.add_argument("--threads",type=int,default=2)
    native.add_argument("--no-audio",action="store_true")
    model = commands.add_parser("install-person-model", help="Download and checksum the official optional model")
    model.add_argument("destination", type=Path)
    score = commands.add_parser("evaluate")
    score.add_argument("prediction", type=Path)
    score.add_argument("labels", type=Path)
    score.add_argument("--tolerance", type=float, default=1)
    fuse = commands.add_parser("fuse", help="Experimental union of saved RallyClip and scene boundary candidates")
    fuse.add_argument("rallyclip", type=Path)
    fuse.add_argument("scenes", type=Path)
    fuse.add_argument("--output", type=Path, required=True)
    fuse.add_argument("--merge-tolerance", type=float, default=1.0)
    fuse.add_argument("--short-seconds", type=float, default=1.0)
    fuse.add_argument("--labels", type=Path, help="Evaluation only, loaded after fusion")
    args = parser.parse_args(argv)
    if args.command == "fuse":
        rallyclip = json.loads(args.rallyclip.read_text(encoding="utf-8"))
        scenes = json.loads(args.scenes.read_text(encoding="utf-8"))
        result = fuse_predictions(rallyclip, scenes, args.merge_tolerance, args.short_seconds)
        result["source_result_paths"] = {"RallyClip": str(args.rallyclip.resolve()), "PySceneDetect": str(args.scenes.resolve())}
        labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else None
        save(result, args.output, labels)
        print(json.dumps({"statistics": result["fusion"]["statistics"],
                          "result": str((args.output / "rallies.json").resolve())}, ensure_ascii=False, indent=2))
        return
    if args.command == "install-person-model":
        install_model(args.destination)
        print(str(args.destination.resolve()))
        return
    if args.command == "evaluate":
        prediction = json.loads(args.prediction.read_text(encoding="utf-8"))
        labels = json.loads(args.labels.read_text(encoding="utf-8"))
        evaluator = evaluate_end_events if labels.get('annotation_type')=='rally_end_events' else evaluate
        target = labels if evaluator is evaluate_end_events else labels['rallies']
        print(json.dumps(evaluator(prediction["rallies"], target,
                                  prediction["video"]["duration_seconds"], args.tolerance), indent=2))
        return
    if args.command == "vlm-call":
        result = call_prepared(args.directory)
        labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else None
        save(result, args.directory / "result", labels)
        print(str((args.directory / "result" / "rallies.json").resolve()))
        return
    if args.command == "gemini-call":
        from .gemini import call_gemini_prepared
        result = call_gemini_prepared(args.directory, args.model)
        labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else None
        save(result, args.directory / "gemini_result", labels)
        print(str((args.directory / "gemini_result" / "rallies.json").resolve()))
        return
    before = time.perf_counter()
    meta = probe(args.video)
    if args.command == 'gemini-video-prepare':
        from .gemini import prepare_native_video
        bundle = prepare_native_video(meta,args.output,args.threads,args.fps,not args.no_audio)
        print(json.dumps({'status':bundle['status'],'proxy_bytes':bundle['proxy_bytes'],
                          'preparation_seconds':bundle['preparation_seconds']}))
        return
    if args.command == "vlm-prepare":
        bundle = prepare(meta, args.output, args.fps, args.threads)
        print(json.dumps({"status": bundle["status"], "windows": len(bundle["windows"]),
                          "output": str(args.output.resolve())}))
        return
    if args.threads < 1:
        parser.error("--threads must be >=1")
    args.output.mkdir(parents=True, exist_ok=True)
    args.fps = args.fps if args.fps is not None else (6 if args.mode=='ball-motion' else 4)
    args.width = args.width if args.width is not None else (960 if args.mode=='ball-motion' else 320)
    timings = {"probe_seconds": time.perf_counter()-before}
    rows, cuts, stats = [], [], {"device": "CPU", "sampled_frames": 0}
    tick = time.perf_counter()
    if args.mode == 'ball-motion':
        if args.person_model or args.roi:
            parser.error('ball-motion uses automatic ROI; person-model/roi options apply to other visual baselines')
        rows,stats=extract_ball_activity(meta,args.fps,args.width,args.threads)
    elif args.mode != "audio":
        roi = json.loads(args.roi.read_text(encoding="utf-8"))["points"] if args.roi else None
        rows, cuts, stats = extract_visual(meta, args.fps, args.width, args.threads,
                                           args.person_model, roi, edited=args.mode=="edited")
    timings["visual_with_decode_seconds"] = time.perf_counter()-tick
    tick = time.perf_counter()
    onsets, audio = [], {"available": meta["audio_stream_index"] is not None, "analyzed": False}
    if args.mode in ("audio", "hybrid"):
        onsets, audio = detect_onsets(meta, args.threads)
    timings["audio_with_decode_seconds"] = time.perf_counter()-tick
    tick = time.perf_counter()
    if args.mode=='ball-motion':
        rallies,uncertain=segment_ball_activity(meta,rows)
    else:
        rallies, uncertain = segment(meta, rows, cuts, onsets, args.mode)
    timings["segmentation_seconds"] = time.perf_counter()-tick
    wall = time.perf_counter()-before
    result = {"schema_version": 1, "status": "candidate_predictions", "method": args.mode,
              "task_kind": "edit_boundary_diagnostic" if args.mode in ("scene", "edited") else "untrimmed_rally_candidates",
              "validated_for_untrimmed_training": False,
              "video": meta, "rallies": rallies, "uncertain_candidates": uncertain,
              "scene_cut_candidates_seconds": cuts, "audio_onsets_seconds": onsets,
              "visual_stats": stats, "audio_stats": audio, "timings": timings,
              "wall_seconds": wall, "video_seconds_per_wall_second": meta["duration_seconds"]/wall,
              "machine": {"system": platform.platform(), "processor": platform.processor(),
                          "logical_cpu_count": os.cpu_count(), "thread_limit": args.threads},
              "limitations": ["Development baselines; no held-out accuracy claim",
                              "Scene changes do not certify tennis rally boundaries",
                              "Sampling reduces analysis; codec decoding may still visit all frames",
                              "Audio transients are not guaranteed racket contacts"]}
    (args.output / "visual_features.json").write_text(json.dumps(rows), encoding="utf-8")
    if args.preview:
        tick = time.perf_counter()
        preview = args.output.resolve() / "preview.mp4"
        subprocess.run([executable("ffmpeg", encoder="libx264"), "-v", "error", "-nostdin", "-y", "-threads", str(args.threads),
            "-i", meta["path"], "-map", f"0:{meta['video_stream_index']}", "-map", "0:a:0?",
            "-vf", "scale=854:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
            "-threads", str(args.threads), "-c:a", "aac", "-movflags", "+faststart", str(preview)],
            capture_output=True, check=True)
        result["review_video"] = str(preview)
        timings["optional_preview_seconds"] = time.perf_counter()-tick
    if args.export_clips:
        tick = time.perf_counter()
        export_clips(meta, rallies, args.output / "clips", args.threads)
        timings["optional_clip_export_seconds"] = time.perf_counter()-tick
    # Labels are deliberately loaded only after prediction and optional exports.
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else None
    save(result, args.output, labels)
    print(json.dumps({"rallies": len(rallies), "wall_seconds": wall,
                      "result": str((args.output / "rallies.json").resolve()),
                      "review": str((args.output / "review.html").resolve())}, indent=2))


if __name__ == "__main__":
    main()
