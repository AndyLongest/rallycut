"""Self-contained video overlay review for visual union candidates."""
import json
import os
from pathlib import Path
from urllib.parse import quote


def write_union_review(result, destination):
    destination = Path(destination)
    source = Path(result["video"]["path"])
    url = quote(os.path.relpath(source, destination.parent).replace(os.sep, "/"), safe="/:")
    data = json.dumps({
        "video": url, "duration": result["video"]["duration_seconds"],
        "rallies": result["rallies"], "boundaries": result["boundaries"],
        "recovery": result["activity_recovery"],
    }, ensure_ascii=False).replace("<", "\\u003c")
    template = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>画面识别 + 剪辑候选 · 并集复核</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#101d24;color:#edf4f4;font:16px system-ui}
main{max-width:1200px;margin:auto;padding:24px}h1{font-size:26px}
p{color:#adbdc6;line-height:1.7}.player{position:relative;background:#000}
video{width:100%;display:block;max-height:70vh}
#badge{position:absolute;left:12px;top:12px;background:#10252be8;padding:10px 14px;
border-left:4px solid #71d4bc;pointer-events:none;max-width:90%;font-size:18px}
#flash{position:absolute;right:12px;top:72px;background:#f4ae48;color:#172329;padding:8px;display:none;pointer-events:none}
canvas{width:100%;height:110px;display:block;cursor:pointer}
.row{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
button{border:1px solid #49616c;background:#213842;color:#edf4f4;padding:10px 14px;border-radius:8px;cursor:pointer}
button:hover{border-color:#71d4bc}table{width:100%;border-collapse:collapse}
td,th{padding:12px 8px;text-align:left;border-bottom:1px solid #30444e}
a{color:#71d4bc}.note{border-left:3px solid #f4ae48;padding-left:14px}
@media(max-width:600px){main{padding:12px}h1{font-size:21px}td,th{padding:10px 3px;font-size:13px}#badge{font-size:14px}}
</style><main>
<h1>画面识别 + 剪辑候选 · 并集复核</h1>
<p id="summary"></p>
<div class="player"><video controls preload="metadata"></video><div id="badge"></div><div id="flash"></div></div>
<canvas id="timeline"></canvas>
<p>青色：动作支持的候选段；橙线：剪辑候选。点击时间轴跳转，下面的按钮从切点前 2 秒播放。</p>
<div class="row" id="cuts"></div>
<table><thead><tr><th>候选段</th><th>起止</th><th>时长</th><th>复核</th></tr></thead><tbody id="rows"></tbody></table>
<p class="note">剪辑候选不等于回合结束。持续活动先保留，再按并集边界切开；超过原 60 秒上限的片段也保留待复核。纯画面分析，没有使用音频。</p>
<p><a href="rallies.json">下载完整 JSON 与边界来源</a></p>
</main><script>
const D=__DATA__,v=document.querySelector('video'),c=document.querySelector('canvas'),ctx=c.getContext('2d');
v.src=D.video;const cuts=D.boundaries.filter(b=>b.sources.includes('PySceneDetect'));
const fmt=t=>`${Math.floor(t/60)}:${(t%60).toFixed(2).padStart(5,'0')}`;
document.querySelector('#summary').textContent=`原始最终结果 ${D.recovery.original_final_candidates} 段；保留 ${D.recovery.restored_candidates.length} 段被时长规则过滤的活动；加入 ${cuts.length} 个剪辑候选后，得到 ${D.rallies.length} 个动作候选段。`;
for(const b of cuts){const el=document.createElement('button');el.textContent=`看切点 ${fmt(b.seconds)}`;el.onclick=()=>{v.currentTime=Math.max(0,b.seconds-2);v.play().catch(()=>{});};document.querySelector('#cuts').append(el);}
for(const [i,r] of D.rallies.entries()){
 const tr=document.createElement('tr');
 for(const text of [i+1,`${fmt(r.start_seconds)} — ${fmt(r.end_seconds)}`,`${(r.end_seconds-r.start_seconds).toFixed(2)} 秒`,r.exceeds_original_duration_limit?'超过 60 秒，已保留':'待复核']){
  const td=document.createElement('td');td.textContent=text;tr.append(td);
 }document.querySelector('#rows').append(tr);
}
function draw(){
 const w=c.clientWidth,h=110,dpr=devicePixelRatio||1;
 if(c.width!==Math.round(w*dpr)){c.width=Math.round(w*dpr);c.height=h*dpr;}
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 const x=t=>12+t/D.duration*(w-24);
 ctx.fillStyle='#213842';ctx.fillRect(12,35,w-24,30);
 for(const [i,r] of D.rallies.entries()){
  ctx.fillStyle=i%2?'#419a92':'#71d4bc';ctx.fillRect(x(r.start_seconds),35,x(r.end_seconds)-x(r.start_seconds),30);
 }ctx.fillStyle='#f4ae48';for(const b of cuts)ctx.fillRect(x(b.seconds)-1,20,2,58);
 ctx.fillStyle='#edf4f4';ctx.fillRect(x(v.currentTime)-1,14,2,70);
 ctx.font='13px system-ui';ctx.fillText(`${fmt(v.currentTime)} / ${fmt(D.duration)}`,12,101);
 const index=D.rallies.findIndex(r=>r.start_seconds<=v.currentTime&&v.currentTime<r.end_seconds);
 document.querySelector('#badge').textContent=index<0?'当前无动作候选支持':`候选段 ${index+1} / ${D.rallies.length} · 动作模型支持`;
 const near=cuts.find(b=>Math.abs(b.seconds-v.currentTime)<.7),flash=document.querySelector('#flash');
 flash.style.display=near?'block':'none';if(near)flash.textContent=`剪辑候选 ${fmt(near.seconds)}`;
 requestAnimationFrame(draw);
}c.onclick=e=>{const r=c.getBoundingClientRect();v.currentTime=Math.max(0,Math.min(D.duration,(e.clientX-r.left-12)/(r.width-24)*D.duration));};
draw();
</script></html>'''
    destination.write_text(template.replace("__DATA__", data), encoding="utf8")
