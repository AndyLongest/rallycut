"""Render captured upstream poses, not a second detector or interpolated tracking."""

import argparse
import bisect
import html
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np

from rallycut.media import executable, probe, sampled_frames

EDGES = [(0,1),(0,2),(1,3),(2,4),(5,6),(5,7),(7,9),(6,8),(8,10),
         (5,11),(6,12),(11,12),(11,13),(13,15),(12,14),(14,16)]
NEAR = (220, 225, 35)
FAR = (45, 160, 255)
GREY = (140, 140, 140)
THRESHOLD = .35  # Display only; every original confidence remains in the feature vector.


def text(image, message, xy, color=(235,235,235), scale=.57):
    cv2.putText(image, message, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, (0,0,0), 4, cv2.LINE_AA)
    cv2.putText(image, message, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def draw_player(image, player, label, color, scale):
    if player is None:
        return
    box = np.asarray(player['box']) * np.tile(scale, 2)
    points = np.asarray(player['keypoints']) * scale
    confidence = np.asarray(player['conf'])
    cv2.rectangle(image, tuple(box[:2].astype(int)), tuple(box[2:].astype(int)), color, 2)
    text(image, label, (int(box[0]), max(48, int(box[1])-6)), color, .52)
    valid = (confidence >= THRESHOLD) & (points[:,0] > 0) & (points[:,1] > 0)
    for a, b in EDGES:
        if valid[a] and valid[b]:
            cv2.line(image, tuple(points[a].astype(int)), tuple(points[b].astype(int)), color, 2, cv2.LINE_AA)
    for point, visible in zip(points, valid):
        if visible:
            cv2.circle(image, tuple(point.astype(int)), 3, color, -1, cv2.LINE_AA)


def crop_player(canvas, source, player, scale, left, color, name):
    text(canvas, name + ' / magnified', (left+10, 750), color)
    if player is None:
        text(canvas, 'NOT DETECTED / no feature', (left+10, 835), color, .5)
        return
    box = np.asarray(player['box']) * np.tile(scale, 2)
    x1,y1,x2,y2 = box
    pad = max(15, (y2-y1)*.18)
    x1,y1 = max(0,int(x1-pad)),max(0,int(y1-pad))
    x2,y2 = min(source.shape[1],int(x2+pad)),min(source.shape[0],int(y2+pad))
    if x2 <= x1 or y2 <= y1:
        return
    crop = source[y1:y2,x1:x2]
    factor = min(280/crop.shape[1], 185/crop.shape[0])
    crop = cv2.resize(crop, (max(1,round(crop.shape[1]*factor)), max(1,round(crop.shape[0]*factor))))
    x,y = left+(300-crop.shape[1])//2, 760
    canvas[y:y+crop.shape[0],x:x+crop.shape[1]] = crop


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('capture', type=Path)
    parser.add_argument('--threads', type=int, default=2)
    args=parser.parse_args()
    output=args.capture.resolve()
    prediction=json.loads((output/'rallies.json').read_text(encoding='utf-8'))
    meta=prediction['video']
    samples=[json.loads(line) for line in (output/'pose_samples.jsonl').read_text().splitlines()]
    times=[s['timestamp_seconds']-meta['video_start_seconds'] for s in samples]
    if times != sorted(times) or len(set(times)) != len(times):
        raise ValueError('Capture timestamps must increase strictly')
    movie=output/'pose_features_960.mp4'
    duration=meta['duration_seconds']
    width,height=1280,1000
    cv2.setNumThreads(args.threads)
    command=[executable('ffmpeg',encoder='libx264'),'-y','-v','error',
             '-f','rawvideo','-pix_fmt','bgr24','-s',f'{width}x{height}','-r','30','-i','pipe:0',
             '-threads',str(args.threads),'-i',meta['path'], '-map','0:v:0','-map','1:a?',
             '-c:v','libx264','-preset','veryfast','-crf','22','-threads',str(args.threads),
             '-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart','-t',str(duration),str(movie)]
    with (output/'pose_render.log').open('w') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log)
        try:
            with sampled_frames(meta,fps=30,width=1280,threads=args.threads) as frames:
                for timestamp, frame in frames:
                    canvas=np.full((height,width,3), (23,20,17), dtype=np.uint8)
                    view=cv2.resize(frame,(1280,720))
                    index=bisect.bisect_right(times,timestamp+1e-7)-1
                    sample=samples[index] if index >= 0 else None
                    active=any(r['start_seconds'] <= timestamp < r['end_seconds'] for r in prediction['rallies'])
                    if sample:
                        native_scale=np.array([1280/meta['width'],720/meta['height']])
                        for box in sample['raw']['boxes']:
                            coords=(np.asarray(box)*np.tile(native_scale,2)).astype(int)
                            cv2.rectangle(view,tuple(coords[:2]),tuple(coords[2:]),GREY,1)
                        ref_scale=np.array([1280/sample['reference_size'][0],720/sample['reference_size'][1]])
                        for name,color in [('near',NEAR),('far',FAR)]:
                            draw_player(view,sample[name], name.upper()+' (selected)',color,ref_scale)
                        # The inset enlarges the same held 5fps overlay; no extra inference.
                        canvas[:720]=view
                        for name,color,left in [('near',NEAR,0),('far',FAR,310)]:
                            crop_player(canvas,view,sample[name],ref_scale,left,color,name.upper())
                        text(canvas,f'VIDEO {timestamp:05.2f}s  |  POSE {times[index]:05.2f}s  |  age {timestamp-times[index]:.2f}s', (640,751))
                        text(canvas,'Actual ONNX CPU / input 960 / 5 pose samples per second',(640,780),scale=.49)
                        text(canvas,f'Raw people: {len(sample["raw"]["boxes"])}  |  after court filter: {len(sample["filtered"]["boxes"])}',(640,810),scale=.53)
                        for name,color,y in [('near',NEAR,840),('far',FAR,870)]:
                            player=sample[name]
                            desc='MISSING' if player is None else f'box {player["box_conf"]:.2f} / visible joints {sum(c>=THRESHOLD for c in player["conf"])}/17 / mean {np.mean(player["conf"]):.2f}'
                            text(canvas,name.upper()+': '+desc,(640,y),color,.49)
                        text(canvas,'362D actual feature vector saved / no ball tracking',(640,903),scale=.51)
                        text(canvas,'Joints >=0.35 shown; low confidence hidden, not corrected',(640,932),scale=.46)
                    else:
                        canvas[:720]=view
                    cv2.rectangle(canvas,(0,0),(1280,36),(23,20,17),-1)
                    text(canvas,'RallyClip pose diagnostic | '+('RALLY CANDIDATE' if active else 'OUTSIDE CANDIDATE')+' | not ground truth', (16,25), NEAR if active else GREY,.63)
                    for r in prediction['rallies']:
                        a,b=(round(r[k]/duration*1240)+20 for k in ['start_seconds','end_seconds'])
                        cv2.rectangle(canvas,(a,970),(b,983),NEAR,-1)
                    cursor=round(timestamp/duration*1240)+20
                    cv2.line(canvas,(cursor,962),(cursor,991),(255,255,255),2)
                    process.stdin.write(canvas.tobytes())
        finally:
            process.stdin.close()
        if process.wait(timeout=60):
            raise RuntimeError('Render failed: see pose_render.log')
    rendered=probe(movie)
    if abs(rendered['duration_seconds']-duration)>.2:
        raise RuntimeError('Rendered duration mismatch')
    summary={'samples':len(samples),'pose_fps':5,'display_joint_threshold':THRESHOLD,
             'sample_times':'actual source PTS; latest sample held until next; no interpolation',
             'near_missing':sum(s['near'] is None for s in samples),
             'far_missing':sum(s['far'] is None for s in samples),
             'rendered':rendered}
    (output/'pose_render_audit.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>RallyClip 人体特征检查</title>
<style>body{background:#10171d;color:#e4edf4;font:16px system-ui;margin:24px auto;max-width:1280px;padding:0 20px}h1{font-size:25px}p{line-height:1.7;color:#bdcbd8}video{width:100%;max-height:80vh;background:black}button,a{color:#e4edf4;background:#273847;border:0;border-radius:6px;padding:9px 14px;margin:5px;cursor:pointer}strong{color:#fff}.near{color:#23e1dc}.far{color:#ffa02d}</style>
<h1>模型实际提取的人体特征 · CPU 960</h1><p>同一段 demo_forrating2 视频，使用原版 RallyClip 的姿态提取、场地过滤和球员分配结果。<strong>上方主画面看位置，下方两个放大窗看关键点。</strong></p>
<video id="v" controls preload="metadata" src="pose_features_960.mp4"></video>
<div><button onclick="v.currentTime=0">开头</button><button onclick="v.currentTime=5.4">5.4 秒：模型状态变化附近</button><button onclick="v.currentTime=34.5">34.5 秒：画面变化附近</button><button onclick="v.currentTime=67">67 秒：末段</button><button onclick="v.playbackRate=.5">0.5 倍速</button><button onclick="v.playbackRate=1">正常速度</button></div>
<p><span class="near">青色 NEAR：模型分配的近端球员</span>；<span class="far">橙色 FAR：模型分配的远端球员</span>；灰框：姿态模型原始人体检测。彩色框是经过场地过滤、合并与分配后真正进入特征计算的对象，并非人工确认身份。</p>
<p>每秒实际提取 5 次姿态，叠加保持到下一次抽帧，未插值或额外跟踪；POSE 是原始样本时间，age 是距当前画面的时间差。只绘制置信度 ≥0.35 的关键点和连线，阈值只影响显示，原始低置信度数值仍输入原模型。右下 box 为人体框置信度，visible joints 为显示关键点数，mean 为17点平均置信度；这些都不是动作分类概率。</p>
<p>顶部及底部时间轴沿用本次 RallyClip 的回合候选状态，不含剪辑检测并集，也不是人工真值。骨架画得正确并不代表回合边界正确。底部放大窗只放大原画面，不生成细节。</p>
<p id="summary">SUMMARY</p><p><a href="pose_features_960.mp4">打开视频</a><a href="pose_samples.jsonl">原始人体与球员分配</a><a href="actual_features.npz">实际 362 维特征</a><a href="pose_render_audit.json">渲染记录</a></p></html>'''
    page=page.replace('SUMMARY',html.escape(f'共 {len(samples)} 次姿态采样；近端未分配 {summary["near_missing"]} 次，远端未分配 {summary["far_missing"]} 次。未分配只统计对象缺失，不统计认错人。'))
    (output/'pose_review.html').write_text(page,encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
