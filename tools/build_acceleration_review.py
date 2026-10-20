"""Create a local, synchronized video comparison against a frozen teacher."""
import argparse
import json
from pathlib import Path
from rallycut.teacher_comparison import compare_intervals

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
parser.add_argument("--pair", nargs=3, action="append",
                    metavar=("LABEL", "TEACHER_DIR", "FAST_DIR"),
                    help="Compare a custom pair; repeat for multiple videos")
args = parser.parse_args()
out = args.directory.resolve()
pairs = args.pair or [("开发 · 71 秒", "dev_teacher", "dev_fast_v2"),
         ("开发 · 5 分钟", "dev_long_teacher", "dev_long_fast_v2"),
         ("未调参 · deemo1", "held_deemo1_teacher", "held_deemo1_fast_v2"),
         ("未调参 · 同录制另一段", "held_clip2_teacher", "held_clip2_fast_v2")]
data = []
for label, teacher_name, fast_name in pairs:
    teacher=json.loads((out/teacher_name/"rallies.json").read_text(encoding="utf8"))
    fast=json.loads((out/fast_name/"rallies.json").read_text(encoding="utf8"))
    duration=teacher["video"]["duration_seconds"]
    data.append({"label":label,"src":Path(teacher["video"]["path"]).as_uri(),
                 "duration":duration,"teacher":teacher["rallies"],"fast":fast["rallies"],
                 "teacherSeconds":teacher["wall_seconds"],"fastSeconds":fast["wall_seconds"],
                 "metrics":compare_intervals(fast["rallies"],teacher["rallies"],duration)})
template = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RallyCut · 纯视觉加速对照</title>
<style>
:root{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#163b33;background:#f3f5ef}
*{box-sizing:border-box}body{margin:0 auto;padding:24px;max-width:1180px}header{display:flex;gap:20px;justify-content:space-between;align-items:center}
h1{font-size:27px;margin:0 0 8px}p{line-height:1.6;color:#5d7068}select,button{font:inherit;border:1px solid #ccd7cd;border-radius:9px;background:white;padding:9px;cursor:pointer}
.stage{position:relative;background:#102b24;border-radius:15px;overflow:hidden}video{display:block;width:100%;max-height:62vh}
.overlay{position:absolute;top:12px;left:12px;display:flex;gap:8px;pointer-events:none;flex-wrap:wrap}
.badge{padding:8px 13px;border-radius:7px;background:#072b24df;color:white;font-weight:600}.fast{background:#7d420cdf}.diff{background:#b52f32ed}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.card{background:white;padding:15px;border:1px solid #dfe6dd;border-radius:11px}.card b{display:block;font-size:24px;margin-top:6px}.card small{color:#61766b}
.tracks{margin:16px 0;padding:14px;background:white;border-radius:12px}canvas{width:100%;height:100px;display:block;cursor:pointer}
.controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}input{flex:1;min-width:180px}
table{width:100%;border-collapse:collapse;background:white}td,th{text-align:left;padding:10px;border-bottom:1px solid #e0e6df;font-size:14px}th{background:#e5ede2}
.note{padding:12px;border-left:4px solid #c6ce73;background:#eef1df}.row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:700px){body{padding:12px}header{display:block}select{width:100%;margin-bottom:12px}.cards{grid-template-columns:1fr 1fr}.row{grid-template-columns:1fr}.badge{font-size:12px}h1{font-size:22px}}
</style>
<header><div><h1>纯画面，能快多少？</h1><p>绿色：当前完整版 teacher　橙色：加速候选</p></div><select id="case"></select></header>
<div class="stage"><video id="video" controls muted playsinline preload="metadata"></video>
<div class="overlay"><span id="teacherState" class="badge"></span><span id="fastState" class="badge fast"></span><span id="difference" class="badge diff" hidden>当前判断不同</span></div></div>
<div class="controls"><button id="back">−5 秒</button><button id="next">下一处差异</button><input id="seek" type="range" min="0" step=".05"><span id="time"></span></div>
<div class="tracks"><canvas id="timeline"></canvas><small>点击时间轴跳转；下方两行共用同一时间。</small></div>
<div id="cards" class="cards"></div>
<p class="note">这是对 teacher 的一致性检查，不是人工准确率。回合内时间重合高，也可能漏切或多切边界。耗时为本机 CPU 两线程单次分析，不含视频导出；未在业务服务器测速。</p>
<p id="summary"></p><div class="row"><div><h3>完整版 teacher</h3><table id="teacherTable"></table></div><div><h3>加速候选</h3><table id="fastTable"></table></div></div>
<script>
const cases=__DATA__;
const $=id=>document.getElementById(id), video=$('video');let current=0;
function stamp(t){return `${Math.floor(t/60)}:${(t%60).toFixed(2).padStart(5,'0')}`}
function active(rows,t){return rows.findIndex(r=>t>=r.start_seconds&&t<r.end_seconds)}
function table(rows){return '<tr><th>回合</th><th>开始</th><th>结束</th></tr>'+rows.map((r,i)=>`<tr><td>${i+1}</td><td>${stamp(r.start_seconds)}</td><td>${stamp(r.end_seconds)}</td></tr>`).join('')}
function load(i){current=i;const d=cases[i],m=d.metrics;video.src=d.src;$('seek').max=d.duration;
$('teacherTable').innerHTML=table(d.teacher);$('fastTable').innerHTML=table(d.fast);
$('cards').innerHTML=[['完整版耗时',d.teacherSeconds.toFixed(1)+' 秒'],['加速版耗时',d.fastSeconds.toFixed(1)+' 秒'],['加速倍数',(d.teacherSeconds/d.fastSeconds).toFixed(2)+'×'],['耗时 / 视频长',(d.fastSeconds/d.duration).toFixed(3)+'×']].map(([k,v])=>`<div class="card"><small>${k}</small><b>${v}</b></div>`).join('');
$('summary').textContent=`回合数 ${d.teacher.length} → ${d.fast.length}；回合内时间交并比 ${(m.active_time_iou*100).toFixed(1)}%。按 ±1 秒一对一匹配，teacher 结束点漏 ${m.ends.missing} 个、候选新增 ${m.ends.extra} 个；开始点漏 ${m.starts.missing} 个、新增 ${m.starts.extra} 个。`;
if(!d.teacher.length)$('summary').textContent=`teacher 在这段视频中没有检出回合，加速版检出 ${d.fast.length} 个。两版都是零不能证明识别正确，本段不能验证回合召回能力。`;
update()}
function update(){const d=cases[current],t=video.currentTime||0,a=active(d.teacher,t),b=active(d.fast,t);
$('teacherState').textContent='teacher · '+(a<0?'回合外':`回合 ${a+1}`);$('fastState').textContent='加速版 · '+(b<0?'回合外':`回合 ${b+1}`);
$('difference').hidden=(a<0)===(b<0);$('time').textContent=stamp(t)+' / '+stamp(d.duration);$('seek').value=t;draw(t)}
function draw(t){const c=$('timeline'),ratio=devicePixelRatio||1,w=c.clientWidth;c.width=w*ratio;c.height=100*ratio;const x=c.getContext('2d');x.scale(ratio,ratio);x.font='13px system-ui';
const d=cases[current],left=70,span=w-left-6;[['teacher',d.teacher,'#16836c'],['加速版',d.fast,'#b36525']].forEach(([label,rows,color],i)=>{let y=12+i*37;x.fillStyle='#476052';x.fillText(label,0,y+14);x.fillStyle='#e6ece5';x.fillRect(left,y,span,23);x.fillStyle=color;for(const r of rows)x.fillRect(left+r.start_seconds/d.duration*span,y,Math.max(1,(r.end_seconds-r.start_seconds)/d.duration*span),23)});
x.strokeStyle='#ce3045';x.beginPath();x.moveTo(left+t/d.duration*span,5);x.lineTo(left+t/d.duration*span,81);x.stroke()}
$('case').innerHTML=cases.map((d,i)=>`<option value="${i}">${d.label}</option>`).join('');$('case').onchange=e=>load(+e.target.value);
$('seek').oninput=e=>{video.currentTime=+e.target.value;update()};$('back').onclick=()=>video.currentTime=Math.max(0,video.currentTime-5);
$('next').onclick=()=>{const d=cases[current],t=video.currentTime;
const events=[...d.teacher,...d.fast].flatMap(r=>[r.start_seconds,r.end_seconds]).sort((a,b)=>a-b);
const next=events.find(s=>s>t+.3&&((active(d.teacher,s+.08)<0)!==(active(d.fast,s+.08)<0)||(active(d.teacher,s-.08)<0)!==(active(d.fast,s-.08)<0)));
if(next!==undefined)video.currentTime=Math.max(0,next-.1);update()};
$('timeline').onclick=e=>{const rect=e.currentTarget.getBoundingClientRect();video.currentTime=Math.max(0,Math.min(cases[current].duration,(e.clientX-rect.left-70)/(rect.width-76)*cases[current].duration));update()};
video.addEventListener('timeupdate',update);window.addEventListener('resize',update);load(0);
</script></html>"""
(out/"review.html").write_text(template.replace("__DATA__",json.dumps(data,ensure_ascii=False).replace("<","\\u003c")),encoding="utf8")
(out/"review_data.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
print(out/"review.html")
