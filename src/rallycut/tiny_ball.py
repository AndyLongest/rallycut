"""Optional CPU-only probe of leonbeier/tennis_demo's two-frame ONNX model.

Upstream model and project carry AGPL-3.0; not bundled or deployed by RallyCut.
This adapter is an experiment, not an accepted detector or production fallback.
"""

from pathlib import Path
import hashlib
import time

import cv2
import numpy as np

from .media import sampled_frames
from .segment import group_times,validate_rallies

MODEL_SHA256='49f561dfc0f36d889a2bf6703f0aba58e2321e1d14264023f906e687c3e5e33f'


def extract_tiny_ball(meta,model,threads=2,inference_fps=2):
    import onnxruntime as ort
    if hashlib.sha256(Path(model).read_bytes()).hexdigest()!=MODEL_SHA256:
        raise ValueError('Unexpected experimental two-frame model checksum')
    if not 0<inference_fps<=4:
        raise ValueError('Experimental inference fps must be in (0,4]')
    cv2.setNumThreads(threads)
    options=ort.SessionOptions();options.intra_op_num_threads=threads;options.inter_op_num_threads=1
    session=ort.InferenceSession(str(model),sess_options=options,providers=['CPUExecutionProvider'])
    if session.get_providers()!=['CPUExecutionProvider']:
        raise RuntimeError('This experiment requires CPU-only ONNX Runtime')
    rows=[];previous=None;last_inference=-100;inference_seconds=0;calls=0
    started=time.perf_counter()
    with sampled_frames(meta,fps=4,width=1920,threads=threads) as frames:
        for stamp,frame in frames:
            frame=cv2.resize(frame,(1920,1080))
            clean=frame.copy()
            # Static normalized overlay exclusion is an explicit camera-specific
            # preprocessing limitation; no OCR/score updates enter segmentation.
            clean[:216,1440:]=0;clean[:162,:480]=0;clean[864:,:576]=0
            current=cv2.cvtColor(clean,cv2.COLOR_BGR2RGB).astype(np.float32)/255
            if previous is not None and stamp-last_inference>=1/inference_fps-1e-5 and stamp<meta['duration_seconds']:
                pair=np.ascontiguousarray(np.stack([previous,current],axis=-1).transpose(2,0,1,3)[None])
                tick=time.perf_counter();output=session.run(None,{session.get_inputs()[0].name:pair})[0][0]
                inference_seconds+=time.perf_counter()-tick;calls+=1;last_inference=stamp
                proposals=[{'x':float(d[0]),'y':float(d[1]),'confidence':float(d[4])} for d in output
                           if d[4]>=.95 and 0<=d[0]<1920 and 0<=d[1]<1080]
                rows.append({'t':stamp,'active':bool(proposals),'proposals':proposals})
            previous=current
    return rows,{'device':'CPU','runtime':'onnxruntime CPUExecutionProvider',
        'model':'leonbeier/tennis_demo one_ai/model.onnx','model_sha256':MODEL_SHA256,
        'model_bytes':Path(model).stat().st_size,'model_license':'upstream AGPL-3.0; experimental, not deployed',
        'pair_shape':[1,3,1080,1920,2],'pair_delay_seconds':.25,'sampler_fps':4,
        'inference_fps':inference_fps,'inference_calls':calls,'inference_seconds':inference_seconds,
        'wall_seconds':time.perf_counter()-started,'threads':threads,
        'scene_cuts_used':False,'pose_used':False,'manual_labels_used':False,
        'overlay_mask':'fixed broadcast rectangles; may hide real balls near these areas'}


def segment_tiny_ball(meta,rows,gap_seconds=2.5):
    groups=group_times([r['t'] for r in rows if r['active']],gap_seconds)
    rallies=[]
    for group in groups:
        rallies.append({'start_seconds':max(0,group[0]-.4),
            'end_seconds':min(meta['duration_seconds'],group[-1]+.5),
            'evidence':f'{len(group)} two-frame model ball proposals, not certified contacts',
            'needs_review':True,'active_samples':len(group)})
    return validate_rallies(rallies,meta['duration_seconds'])
