"""A local review artifact, with human labels visually separate from predictions."""

from pathlib import Path
import html
import json


def write_report(result, destination, labels=None):
    destination = Path(destination)
    fused = result.get("method") == "boundary_union_cpu"
    displayed = {**result, "rallies": result["timeline_segments"]} if fused else result
    data = {"result": displayed, "labels": labels}
    encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    video = html.escape(Path(result.get("review_video", result["video"]["path"])).as_uri(), quote=True)
    diagnostic = result.get("method") in ("edited", "scene")
    notice = ("历史剪辑接缝诊断：本页结果不计入完整训练视频的回合切分验收。此前切点对齐分数不代表回合识别准确率。"
              if diagnostic else "完整训练视频的回合识别尚未验收。候选需逐段复核，并与同一口径的人工标注比较。")
    if fused:
        notice = ("双路并集实验：本页展示完整并集分区，含没有RallyClip动作支持的待确认区间。"
                  "灰色区间不能当作已识别回合；短碎段保留并提示复核。无人工标注时不报告准确率。")
    template = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RallyCut 回合切分对照</title>
<style>body{margin:0;background:#111a20;color:#e8f0f2;font:16px system-ui}main{max-width:1080px;margin:auto;padding:28px}h1{font-size:26px}p{color:#a9bec8;line-height:1.7}video{width:100%;max-height:60vh;background:black;border-radius:12px}button,input{background:#23343e;color:white;border:1px solid #49606c;border-radius:6px;padding:8px;margin:4px}button{cursor:pointer}section{padding:16px;background:#192832;margin:16px 0;border-radius:12px}.bar{position:relative;height:30px;background:#0a1218;margin:8px 0}.part{position:absolute;top:0;height:30px;border:1px solid #111;box-sizing:border-box;background:#39a7b3;color:#07151a;font-size:12px;overflow:hidden}.manual{background:#c4ad73}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:10px;border-bottom:1px solid #344852}.bad{color:#f6be8f}pre{white-space:pre-wrap}label{display:block;margin:8px 0}</style>
<main><h1>RallyCut · 回合切分对照</h1><p class="bad">TASK_NOTICE</p><p id="summary"></p>
<video id="video" controls src="VIDEO_URL"></video>
<p>若浏览器不支持原视频的 HEVC 编码，请选择浏览器可播放的视频副本，或用外部播放器核对时间。标注和预测使用同一条从 0 开始的时间轴。</p>
<input id="source" type="file" accept="video/*"><span id="clock"></span>
<section><strong>算法候选 · 青色</strong><div class="bar" id="pred"></div><strong>人工标注 · 金色</strong><div class="bar" id="truth"></div><p class="bad">输出需要人工复核；剪辑接缝与实际击球回合采用不同定义，不能混用评测。</p></section>
<section><h2>算法输出</h2><table><thead><tr><th>回合</th><th>起止（秒）</th><th>证据</th><th>复核</th></tr></thead><tbody id="rows"></tbody></table></section>
<section><h2>人工标注</h2><p>定位到视频时间，记录起止；支持逐帧近似跳转。导出 JSON 后可直接用于评测。</p>
<button id="back">−0.1 秒</button><button id="forward">+0.1 秒</button><button id="startNow">记为开始</button><button id="endNow">记为结束</button>
<label>开始 <input id="start" type="number" min="0" step="0.01" value="0"> 结束 <input id="end" type="number" min="0" step="0.01" value="0"></label>
<button id="add">添加人工回合</button><button id="undo">撤销最后一条</button><button id="download">导出人工标注 JSON</button><pre id="manual"></pre></section>
<section><h2>评测与耗时</h2><pre id="metrics"></pre></section></main>
<script>const data=DATA_JSON;const r=data.result;let manual=data.labels?.rallies?.map(x=>({...x}))||[];const manualEnds=data.labels?.events||[];const v=document.getElementById('video');let stopAt=null;
function show(id,text){document.getElementById(id).textContent=text}function jump(a,b){v.currentTime=a;stopAt=b;v.play().catch(()=>{})}
function bar(id,segments,cls){const node=document.getElementById(id);node.replaceChildren();segments.forEach((s,i)=>{const b=document.createElement('button');b.className='part '+cls;b.style.left=(100*s.start_seconds/r.video.duration_seconds)+'%';b.style.width=(100*(Math.min(s.end_seconds,r.video.duration_seconds)-s.start_seconds)/r.video.duration_seconds)+'%';b.style.margin=0;b.style.padding='4px';b.textContent=i+1;b.title=s.start_seconds.toFixed(2)+'–'+s.end_seconds.toFixed(2)+'s';b.onclick=()=>jump(s.start_seconds,s.end_seconds);node.append(b)})}
bar('pred',r.rallies,'');function refresh(){bar('truth',manual,'manual');if(!manual.length&&manualEnds.length){const node=document.getElementById('truth');manualEnds.forEach(e=>{const b=document.createElement('button');b.className='part manual';b.style.left=(100*e.end_seconds/r.video.duration_seconds)+'%';b.style.width='3px';b.style.padding=0;b.style.margin=0;b.title=e.end_seconds+'s '+(e.description||'人工结束标注');b.onclick=()=>jump(Math.max(0,e.end_seconds-3),Math.min(r.video.duration_seconds,e.end_seconds+2));node.append(b)})}show('manual',JSON.stringify(manualEnds.length?{rallies:manual,end_events:manualEnds}:manual,null,2))}refresh();
show('summary',`${r.method} · ${r.rallies.length} 个候选回合 · 视频 ${r.video.duration_seconds.toFixed(2)} 秒 · 分析耗时 ${r.wall_seconds?.toFixed(2)??'未记录'} 秒`);
r.rallies.forEach((s,i)=>{const tr=document.createElement('tr');[i+1,`${s.start_seconds.toFixed(2)}–${s.end_seconds.toFixed(2)}`,s.evidence||'模型输出'].forEach(x=>{const td=document.createElement('td');td.textContent=x;tr.append(td)});const td=document.createElement('td');const b=document.createElement('button');b.textContent='播放';b.onclick=()=>jump(s.start_seconds,s.end_seconds);td.append(b);tr.append(td);document.getElementById('rows').append(tr)});
show('metrics',JSON.stringify({evaluation:r.evaluation,timing:r.timings,model:r.model,usage:r.usage,api_seconds_per_window:r.api_seconds_per_window,visual:r.visual_stats,audio:r.audio_stats},null,2));
v.ontimeupdate=()=>{show('clock',v.currentTime.toFixed(2)+' 秒');if(stopAt!==null&&v.currentTime>=stopAt){v.pause();stopAt=null}};
let objectUrl=null;document.getElementById('source').onchange=e=>{const f=e.target.files[0];if(f){if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=URL.createObjectURL(f);v.src=objectUrl}};
document.getElementById('back').onclick=()=>{v.pause();v.currentTime=Math.max(0,v.currentTime-.1)};document.getElementById('forward').onclick=()=>{v.pause();v.currentTime+=.1};
document.getElementById('startNow').onclick=()=>document.getElementById('start').value=v.currentTime.toFixed(2);document.getElementById('endNow').onclick=()=>document.getElementById('end').value=v.currentTime.toFixed(2);
document.getElementById('add').onclick=()=>{const a=Number(document.getElementById('start').value),b=Number(document.getElementById('end').value);if(!(Number.isFinite(a)&&Number.isFinite(b)&&0<=a&&a<b&&b<=r.video.duration_seconds+1&&(!manual.length||a>=manual.at(-1).end_seconds)))return alert('起止需有效、按序、不重叠，结束不能超出视频。');manual.push({start_seconds:a,end_seconds:b});refresh()};
document.getElementById('undo').onclick=()=>{manual.pop();refresh()};document.getElementById('download').onclick=()=>{const blob=new Blob([JSON.stringify({schema_version:1,source:'human review',video_name:r.video.path.split(/[\\\\/]/).pop(),rallies:manual},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='manual_rallies.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
</script></html>'''
    if fused:
        template = template.replace("个候选回合", "个并集分区（含待确认）")
        template = template.replace("<strong>算法候选 · 青色</strong>", "<strong>完整并集分区 · 青色有动作支持，灰色待确认</strong>")
        template = template.replace("<h2>算法输出</h2>", "<h2>完整并集分区</h2>").replace("<th>回合</th>", "<th>区间</th>")
        template = template.replace("b.className='part '+cls;", "b.className='part '+cls;if(s.activity_state==='outside_rallyclip_candidate')b.style.background='#586a74';")
    destination.write_text(template.replace("TASK_NOTICE", html.escape(notice)).replace("VIDEO_URL", video).replace("DATA_JSON", encoded), encoding="utf-8")
