"""Trace frozen upstream scores against end-only labels; never tune on the labels."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

from rallycut.evaluate import evaluate_end_events


def trace_decode(module, scores, times, config):
    cfg = module.HeatmapDecodeConfig(**config)
    if cfg.mode != 'hybrid':
        raise ValueError('This diagnostic traces the shipped hybrid decoder only')
    point, start, end = (np.asarray(scores[k], dtype=np.float64) for k in ['pointness', 'start', 'end'])
    detected = point if cfg.smooth_sigma_frames is None else module._gaussian_smooth(point, cfg.smooth_sigma_frames)
    runs = []
    for i, j in module._runs_above(detected, cfg.threshold):
        left = module._soft_argmax_time(start, times, i, cfg._refine_window())
        right = module._soft_argmax_time(end, times, j, cfg._refine_window())
        fallback = right <= left
        if fallback:
            left, right = float(times[i]), float(times[j])
        duration = right - left
        reason = ('nonpositive' if duration <= 0 else 'too_short' if duration < cfg.min_duration_sec
                  else 'too_long' if duration > cfg.max_duration_sec else None)
        runs.append({'first_index': i, 'last_index': j, 'raw_start_seconds': float(times[i]),
                     'raw_end_seconds': float(times[j]), 'refined_start_seconds': left,
                     'refined_end_seconds': right, 'duration_seconds': duration,
                     'refine_fallback': fallback, 'discard_reason': reason})
    before = [(r['refined_start_seconds'], r['refined_end_seconds']) for r in runs if r['discard_reason'] is None]
    merged = module._merge_intervals(before, gap=cfg.merge_gap_sec)
    traced = [s for s in merged if s[1]-s[0] >= cfg.hybrid_min_duration_sec]
    actual = module.decode_heatmap_segments(point, start, end, times, cfg)
    if traced != actual:
        raise RuntimeError('Stage trace does not reproduce the upstream decoder')
    for r in runs:
        r['merged_group'] = next((i for i, (a,b) in enumerate(merged)
                                   if r['discard_reason'] is None and a <= r['refined_start_seconds']
                                   and b >= r['refined_end_seconds']), None)
    return {'runs': runs, 'before_merge': before, 'after_merge': merged, 'final': actual,
            'no_gap_merge_counterfactual': module.decode_heatmap_segments(
                point,start,end,times,replace(cfg,merge_gap_sec=0.0)),
            'trace_parity': True}


def local_evidence(t, scores, times, poses, radius=2):
    mask = (times >= t-radius) & (times <= t+radius)
    idx = int(np.argmin(abs(times-t)))
    near_poses = [p for p in poses if abs(p['timestamp_seconds']-t) <= radius]
    end_idx = np.flatnonzero(mask)[int(np.argmax(scores['end'][mask]))]
    return {'point_at_end': float(scores['pointness'][idx]),
            'point_min': float(np.min(scores['pointness'][mask])),
            'point_max': float(np.max(scores['pointness'][mask])),
            'end_peak': float(scores['end'][end_idx]), 'end_peak_time': float(times[end_idx]),
            'pose_count': len(near_poses),
            'near_missing': sum(p['near'] is None for p in near_poses),
            'far_missing': sum(p['far'] is None for p in near_poses)}


def explain_event(t, matched, trace, evidence, tolerance):
    if matched is not None:
        return '结束点已匹配', f'预测结束 {matched:.2f}s，与人工相差 {matched-t:+.2f}s。'
    raw_near = [r for r in trace['runs'] if abs(r['raw_end_seconds']-t) <= tolerance]
    refined_near = [r for r in trace['runs'] if abs(r['refined_end_seconds']-t) <= tolerance]
    discarded = [r for r in refined_near if r['discard_reason']]
    if discarded:
        r = min(discarded, key=lambda r: abs(r['refined_end_seconds']-t))
        return '候选被时长过滤', f'出现附近候选结束，但候选时长 {r["duration_seconds"]:.2f}s，过滤原因 {r["discard_reason"]}。'
    merged_away = [r for r in refined_near if r['discard_reason'] is None and r['merged_group'] is not None
                   and abs(trace['after_merge'][r['merged_group']][1]-t) > tolerance]
    if merged_away:
        r = merged_away[0]
        return '附近候选被合并', f'细化后结束 {r["refined_end_seconds"]:.2f}s，合并后延长到 {trace["after_merge"][r["merged_group"]][1]:.2f}s。'
    if raw_near:
        r = min(raw_near, key=lambda r: abs(r['raw_end_seconds']-t))
        return '边界细化后超出容差', f'阈值段结束 {r["raw_end_seconds"]:.2f}s，细化后 {r["refined_end_seconds"]:.2f}s；需结合人工时间精度检查。'
    crossing = [r for r in trace['runs'] if r['raw_start_seconds'] < t-tolerance and r['raw_end_seconds'] > t+tolerance]
    if crossing:
        r = crossing[0]
        return '回合中分数连续跨过人工结束', f'≥0.5 的连续段为 {r["raw_start_seconds"]:.2f}–{r["raw_end_seconds"]:.2f}s；该结束附近未产生阈值段末端，结束分数仅细化段的两头。'
    return '模型阈值段结束未对齐', f'人工结束 ±{tolerance:g}s 内没有可保留的阈值段末端；需检查分数变化与输入特征，不能仅凭曲线断言训练原因。'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('capture',type=Path)
    parser.add_argument('labels',type=Path)
    parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--historical',type=Path)
    parser.add_argument('--observations',type=Path,help='Optional separately recorded visual-review notes; never inference inputs')
    parser.add_argument('--tolerance',type=float,default=2)
    args=parser.parse_args()
    out=args.capture.resolve()
    pred=json.loads((out/'rallies.json').read_text(encoding='utf-8'))
    labels=json.loads(args.labels.read_text(encoding='utf-8'))
    if labels.get('annotation_type') != 'rally_end_events':
        raise ValueError('Expected end-only labels')
    capture=json.loads((out/'score_capture.json').read_text())
    poses=[json.loads(line) for line in (out/'pose_samples.jsonl').read_text().splitlines()]
    npz=np.load(out/'model_scores.npz')
    times=npz['timestamps']
    scores={key:npz[key] for key in ['pointness','start','end']}
    if len(poses) != len(times):
        raise RuntimeError('Score/pose row count mismatch')
    sys.path.insert(0,str(args.upstream.resolve()/'src'))
    from infer import heatmap_decode
    trace=trace_decode(heatmap_decode,scores,times,capture['config'])
    expected=[(r['start_seconds'],r['end_seconds']) for r in pred['rallies']]
    if trace['final'] != expected:
        raise RuntimeError('Replayed scores differ from saved inference intervals')
    historical_parity=None
    if args.historical:
        prior=json.loads(args.historical.read_text(encoding='utf-8'))
        historical_parity=expected == [(r['start_seconds'],r['end_seconds']) for r in prior['rallies']]
    evaluation=evaluate_end_events(pred['rallies'],labels,pred['video']['duration_seconds'],args.tolerance)
    matches=evaluation['ends']['matches']
    matched={m['manual_index']:m for m in matches}
    events=[]
    for i,event in enumerate(labels['events']):
        t=event['end_seconds']
        match=matched.get(i)
        end=match['predicted_end_seconds'] if match else None
        evidence=local_evidence(t,scores,times,poses,args.tolerance)
        diagnosis,details=explain_event(t,end,trace,evidence,args.tolerance)
        details+=f' 附近分数范围 {evidence["point_min"]:.3f}–{evidence["point_max"]:.3f}，结束分数峰值 {evidence["end_peak"]:.3f}@{evidence["end_peak_time"]:.1f}s；近端缺失 {evidence["near_missing"]}/{evidence["pose_count"]}、远端缺失 {evidence["far_missing"]}/{evidence["pose_count"]} 次。'
        if event.get('serve_fault'):
            details+=' 发球失误：按用户口径可接受与下一次尝试合并；严格匹配记录仍保留。'
        events.append({**event,'matched_end_seconds':end,'error_seconds':None if end is None else end-t,
                       'diagnosis':diagnosis,'details':details,'evidence':evidence})
    matched_indices={m['prediction_index'] for m in matches}
    unmatched=[]
    for i,r in enumerate(pred['rallies']):
        if i in matched_indices:
            continue
        t=r['end_seconds'];evidence=local_evidence(t,scores,times,poses,args.tolerance)
        closest=min(labels['events'],key=lambda x:abs(x['end_seconds']-t))
        near_run=min(trace['runs'],key=lambda x:abs(x['refined_end_seconds']-t))
        unmatched.append({**r,'diagnosis':'未匹配人工结束，需视频复核',
                          'details':f'候选 {r["start_seconds"]:.2f}–{t:.2f}s（{t-r["start_seconds"]:.2f}s）；最近人工结束 {closest["end_seconds"]:g}s，差 {t-closest["end_seconds"]:+.2f}s。对应附近阈值段 {near_run["raw_start_seconds"]:.2f}–{near_run["raw_end_seconds"]:.2f}s。结束标签未确认穷尽，不能直接认定为误报。',
                          'evidence':evidence})
    summary={'sample_count':len(poses),'near_missing':sum(p['near'] is None for p in poses),
             'far_missing':sum(p['far'] is None for p in poses),'matched_count':len(matches),
             'manual_count':len(events),'predicted_count':len(pred['rallies']),
             'tolerance_seconds':args.tolerance,'historical_exact_parity':historical_parity,
             'max_pose_vs_decoder_time_difference_seconds':float(np.max(abs(times-np.array([p['timestamp_seconds'] for p in poses])))),
             'notes':['人工仅标结束，未推断开始或空闲区间；匹配采用一对一 ±2s。',
                      '分数是窗口平均后的模型输出，不是校准过的准确率；输入缺失和错误的共现不能证明因果。',
                      '骨架用真实抽帧 PTS，分数与切分沿用上游 i/5 时间网格。',
                      '候选时长、阈值和合并规则保持原版；不调参、不训练。']}
    observations = json.loads(args.observations.read_text(encoding='utf-8')) if args.observations else {}
    summary['notes'].extend(observations.get('notes', []))
    for event in events:
        review = observations.get('event_notes', {}).get(str(event['end_seconds']))
        if review:
            event['visual_review'] = review
            event['details'] += ' 画面复核：' + review
    data={'video':pred['video'],'model':{'name':'RallyClip v0.5.0 · CPU 960','imgsz':960,'fps':5,'threshold':capture['config']['threshold']},
          'scores':{'times':times.tolist(),**{k:v.tolist() for k,v in scores.items()}},
          'pose_samples':[{k:p[k] for k in ['timestamp_seconds','reference_size','near','far']} for p in poses],
          'rallies':pred['rallies'],'events':events,'unmatched_predictions':unmatched,'summary':summary,
          'evaluation':evaluation,'decode_trace':trace,'decoder_config':capture['config'],
          'visual_review':observations}
    (out/'diagnostic.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    (out/'diagnostic_summary.json').write_text(json.dumps({k:data[k] for k in ['summary','events','unmatched_predictions','decode_trace']},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'summary':summary,'events':events,'unmatched_predictions':unmatched},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
