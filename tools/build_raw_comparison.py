"""Create one end-event comparison artifact; all rows use the owner's raw video."""
from pathlib import Path
import html
import json

from rallycut.evaluate import evaluate_end_events
from build_raw_timeline import build_timeline

project=Path(__file__).resolve().parents[1]
labels=json.loads((project/'tests/fixtures/demo3_clip1.manual_ends.v1.json').read_text(encoding='utf-8'))
files=[
    'outputs/demo3_clip1_baseline/visual/rallies.json',
    'outputs/demo3_clip1_baseline/audio/rallies.json',
    'outputs/demo3_clip1_baseline/hybrid/rallies.json',
    'outputs/demo3_clip1_ball_cpu/rallies.json',
    'outputs/demo3_clip1_ball_contrast_cpu/rallies.json',
    'outputs/demo3_clip1_gemini_native/result/rallies.json',
    'outputs/demo3_clip1_tiny_cpu_full/rallies.json',
    'outputs/demo3_clip1_tiny_cpu_development/rallies.json',
    'outputs/demo3_clip1_rallyclip_cpu/rallies.json',
    'outputs/demo3_clip1_rallyclip_openvino/rallies.json',
    'outputs/demo3_clip1_rallyclip_640/rallies.json',
    'outputs/demo3_clip1_rallyclip_416/rallies.json',
]
records=[];table=[]
for relative in files:
    path=project/relative
    if not path.exists():continue
    r=json.loads(path.read_text(encoding='utf-8'))
    if Path(r['video']['path']).name.lower()!=labels['video_name'].lower():
        raise ValueError('Comparison mixes different source videos')
    scores={str(t):evaluate_end_events(r['rallies'],labels,r['video']['duration_seconds'],t)['ends'] for t in [1,2,3]}
    records.append({'method':r['method'],'analysis_seconds':r['wall_seconds'],
        'preparation_seconds':r.get('preparation_seconds',0),'candidate_count':len(r['rallies']),
        'scores':scores,'source':relative,'development_tuned':bool(r.get('postprocessing',{}).get('selected_on_development_labels'))})
    review=(path.parent/'review.html').as_uri()
    table.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in
        [r['method'],len(r['rallies']),f"{r['wall_seconds']:.2f}",
         scores['1']['matched'],scores['2']['matched'],scores['3']['matched'],scores['2']['false_positives']])+
         f'<td><a href="{html.escape(review,quote=True)}">逐段复核</a></td></tr>')
out=project/'outputs/demo3_clip1_comparison';out.mkdir(parents=True,exist_ok=True)
(out/'comparison.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>完整原片回合切分对照</title>
<style>body{font:16px system-ui;background:#12212a;color:#e8f1f5;margin:30px}main{max-width:1200px;margin:auto}p{line-height:1.7;color:#bdd0d9}table{border-collapse:collapse;width:100%;background:#1d303b}th,td{padding:12px;text-align:left;border-bottom:1px solid #41515b}a{color:#83d4d2}.notice{padding:14px;border:1px solid #cead73}</style>
<main><h1>完整原片 · 回合结束时间对照</h1><p>视频：demo3_clip1.mp4 · 约 299.6 秒 · 人工结束标注 11 个。开始时间未标注，因此不报告开始准确率或区间 IoU。</p>
<p><a href="timeline.html">打开交互时间轴：模型预测与人工标注 →</a></p>
<p><a href="../demo3_clip1_rendered/review.html">播放已渲染的视频：画面叠加模型识别结果 →</a></p>
<p class="notice">这是开发样本，没有任何路线通过验收。“匹配数”须同时看多余候选。1:50 为用户明确的近似时间；未匹配候选需人工核对标注完整性。开发调参结果不代表新视频效果。</p>
<table><thead><tr><th>方法</th><th>候选段数</th><th>分析秒数</th><th>±1s 匹配/11</th><th>±2s 匹配/11</th><th>±3s 匹配/11</th><th>±2s 未匹配候选</th><th>结果</th></tr></thead><tbody>ROWS</tbody></table>
<p>Gemini 另有约 25.46 秒视频代理准备成本，API 用时约 24.18 秒；已收到的响应复核没有再次调用服务。CPU 基线共享抽帧缓存的测量条件详见实验记录。tiny_cpu_development_temporal 在本视频标注上选过参数。</p>
<p>“球在场地中央”只是一项位置证据；静止的网前球不能维持活跃状态。当前对照不使用剪辑接缝、比分变化或广播时钟推断回合。</p></main></html>'''
(out/'index.html').write_text(page.replace('ROWS',''.join(table)),encoding='utf-8')
print(str(out/'index.html'))
print(str(build_timeline(project)))
