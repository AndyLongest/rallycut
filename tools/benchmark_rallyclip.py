"""Read-only upstream benchmark. No source/weights/threshold changes, CPU only."""

from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
import argparse
import json
import os
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument('upstream',type=Path)
parser.add_argument('video',type=Path)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--threads',type=int,default=2)
parser.add_argument('--pose-engine',choices=['ort','openvino'],default='ort')
parser.add_argument('--imgsz',type=int,help='Explicit development override of pose input resolution; original temporal sampling unchanged')
parser.add_argument('--labels',type=Path,help='Optional human annotations, read only after inference')
parser.add_argument('--capture-features',action='store_true',help='Observe actual pose assignments and 362D feature vectors')
parser.add_argument('--capture-scores',action='store_true',help='Observe actual stitched point/start/end tracks before decoding')
parser.add_argument('--pose-stride',type=int,default=1,help='Experimental sparse pose calls; preserve 5fps temporal grid')
parser.add_argument('--pose-reuse',choices=['interpolate','hold'],default='interpolate')
parser.add_argument('--crop-refresh',type=int,default=0,help='Experimental crop tracking; full rediscovery every N samples')
parser.add_argument('--crop-size',type=int,default=256)
parser.add_argument('--empty-recheck',type=int,default=1,help='Recheck empty scenes every N samples; motion forces immediate check')
parser.add_argument('--pose-model',type=Path,help='Experimental separate pose artifact; original artifact untouched')
parser.add_argument('--decode-nonref',action='store_true',help='Experimental native decoder skips non-reference pictures')
parser.add_argument('--court-attempts',type=int,default=0,help='Bound court search attempts; 0 preserves upstream')
args=parser.parse_args()
root=args.upstream.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['OMP_NUM_THREADS']=str(args.threads)
os.environ['OPENBLAS_NUM_THREADS']=str(args.threads)
os.environ['MKL_NUM_THREADS']=str(args.threads)
os.environ['POSE_DEVICE']='cpu'
sys.path.insert(0,str(root/'src'))

import onnxruntime as ort
import cv2
import av

cv2.setNumThreads(args.threads)
original_session=ort.InferenceSession
sessions=[]
def cpu_session(path,sess_options=None,providers=None,**kwargs):
    if args.pose_model and 'yolov8' in str(path).lower():
        path = str(args.pose_model.resolve())
    options=sess_options or ort.SessionOptions()
    options.intra_op_num_threads=args.threads;options.inter_op_num_threads=1
    result=original_session(path,sess_options=options,providers=['CPUExecutionProvider'],**kwargs)
    if args.pose_engine=='openvino' and 'yolov8' in str(path).lower():
        import openvino as ov
        core=ov.Core()
        compiled=core.compile_model(core.read_model(str(path)),'CPU',{
            'INFERENCE_NUM_THREADS':args.threads,'NUM_STREAMS':1,
            'PERFORMANCE_HINT':'LATENCY','INFERENCE_PRECISION_HINT':'f32'})
        reference=result
        class OVSession:
            def get_inputs(self):return reference.get_inputs()
            def get_outputs(self):return reference.get_outputs()
            def get_providers(self):return ['OpenVINO:CPU']
            def run(self,names,feed):
                outputs=compiled(feed)
                return [outputs[compiled.output(i)].copy() for i in range(len(compiled.outputs))]
        result=OVSession()
    sessions.append({'model':str(path),'providers':result.get_providers(),'threads':args.threads})
    return result
ort.InferenceSession=cpu_session
original_open=av.open
def cpu_open(*a,**kw):
    container=original_open(*a,**kw)
    if kw.get('mode','r')=='r':
        for stream in container.streams.video:
            stream.codec_context.thread_count=args.threads
            if args.decode_nonref:
                stream.codec_context.skip_frame = "NONREF"
    return container
av.open=cpu_open

from rallyclip_api import RallyClipServices,run_result_payload
from cli.main import main

save_capture = None
if args.capture_features:
    from pose_capture import install_capture
    save_capture = install_capture()
save_scores = None
if args.capture_scores:
    from score_capture import install_score_capture
    save_scores = install_score_capture()

captured=[]
original_analysis=RallyClipServices.run_analysis
def capture(self,*a,**kw):
    result=original_analysis(self,*a,**kw);captured.append(result);return result
RallyClipServices.run_analysis=capture
config=out/'benchmark.toml'
config.write_text('[run]\nwrite_csv=true\nsegment_video=false\n',encoding='utf-8')
sys.argv=['rallyclip','--config',str(config),'--video',str(args.video.resolve()),
          '--artifact-dir',str(root/'models/rallyclip_v0.5.0'),
          '--output-dir',str(out),'--csv-output-dir',str(out),
          '--yolo-device','cpu','--no-segment-video','--write-csv','--json']
if args.imgsz is not None:
    sys.argv += ['--imgsz',str(args.imgsz)]
started=time.perf_counter()
print(json.dumps({'stage':'upstream_rallyclip_cpu','threads':args.threads,'video':str(args.video.resolve())}),flush=True)
from contextlib import nullcontext
from rallycut.fast_pose import sparse_pose, cropped_pose, bounded_court
if args.capture_features and args.pose_stride != 1:
    raise ValueError('Original feature observer requires unmodified pose iterator')
context = sparse_pose(args.pose_stride, args.pose_reuse) if args.pose_stride != 1 else nullcontext(None)
if args.crop_refresh:
    if args.pose_stride != 1:
        raise ValueError('Compare crop and sparse experiments independently')
    context = cropped_pose(args.crop_refresh,args.crop_size,args.empty_recheck)
court_context = bounded_court(args.court_attempts) if args.court_attempts else nullcontext(None)
with context as acceleration, court_context as court_audit, (out/'upstream.log').open('w',encoding='utf-8') as log,redirect_stdout(log),redirect_stderr(log):
    main()
elapsed=time.perf_counter()-started
if not captured:
    raise RuntimeError('Upstream returned no captured analysis result')
payload=run_result_payload(captured[-1])
capture_audit = save_capture(out) if save_capture else None
score_audit = save_scores(out) if save_scores else None
(out/'upstream_result.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
audit={'wall_seconds':elapsed,'threads':args.threads,'sessions':sessions,
       'pose_engine':args.pose_engine,
       'torch_imported':'torch' in sys.modules,'ultralytics_imported':'ultralytics' in sys.modules,
       'source_modified':False,'upstream_model_contract_overridden':args.imgsz is not None,
       'pose_imgsz_override':args.imgsz}
audit['decode_nonref'] = args.decode_nonref
audit['audio_used'] = False
audit['teacher_predictions_read_during_inference'] = False
if args.decode_nonref:
    audit['upstream_model_contract_overridden'] = True
if acceleration is not None:
    audit['acceleration'] = acceleration
    audit['upstream_model_contract_overridden'] = True
if court_audit is not None:
    audit['court_acceleration'] = court_audit
    audit['upstream_model_contract_overridden'] = True
if args.pose_model:
    import hashlib
    audit['pose_model_override'] = str(args.pose_model.resolve())
    audit['pose_model_sha256'] = hashlib.sha256(args.pose_model.read_bytes()).hexdigest()
    audit['upstream_model_contract_overridden'] = True
if capture_audit:
    audit['feature_capture'] = capture_audit
if score_audit:
    audit['score_capture'] = score_audit
(out/'benchmark_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
from rallycut.media import probe
from rallycut.cli import save
meta=probe(args.video)
result={'schema_version':1,'status':'candidate_predictions',
        'method':f'upstream_rallyclip_tcn_cpu_{args.imgsz}' if args.imgsz else 'upstream_rallyclip_tcn_cpu',
        'task_kind':'untrimmed_rally_candidates','validated_for_untrimmed_training':False,
        'video':meta,'wall_seconds':elapsed,'visual_stats':audit,
        'rallies':[{'start_seconds':x['start_s'],'end_seconds':x['end_s'],
                    'evidence':'upstream pretrained TCN from low-rate CPU pose features; no label input',
                    'needs_review':True} for x in payload['intervals']],
        'limitations':['Optional upstream reference contains pose features but no GPU execution',
                       'Not trained on the uploaded video; not an accepted production scheme',
                       'May merge serve faults with subsequent rallies']}
if args.crop_refresh or args.pose_stride != 1 or args.pose_model or args.court_attempts or args.decode_nonref:
    result['method'] = 'experimental_rallyclip_visual_accelerated'
    result['limitations'].append('Experimental acceleration changes visual inputs; teacher agreement is not human accuracy')
labels=json.loads(args.labels.read_text(encoding='utf-8')) if args.labels else None
save(result,out,labels)
print(json.dumps({'stage':'completed','audit':audit,'payload':payload},ensure_ascii=False,indent=2),flush=True)
