# RallyCut: independent project

This directory is the complete project boundary. Do not import Tennis_Vision or
netcastApp or change their behavior. Existing service credentials may be reused
only with explicit owner authorization (Gemini reuse authorized 2026-10-19);
read them in memory for the authorized call, never copy them into this project,
tool output or documentation. A user-specified
video may be anywhere on disk. Sampled analysis is explicitly authorized here;
it does not change Tennis_Vision's native-frame ball-tracking contract.

Maintain two comparable paths: sampled VLM temporal grounding and CPU sampled
visual recognition, with audio-only and audio/visual baselines. Record upstream
sources, model provenance, limitations and real measurements. Human labels are
the evaluation ground truth; predictions must never become ground truth.

No paid GPU provisioning is necessary. If later requested, the workspace's
Tennis_Vision/docs/ALIBABA_GPU_RUNBOOK.md remains mandatory before any paid run.
Never put credentials, weights, video or generated output in source control.

Run pytest for code changes. Demo predictions are candidates until independently
labelled. Do not claim server capacity from laptop timings or from a proposal's
estimated CPU specifications. No autonomous deployment to the business server.

## Owner correction: actual untrimmed training footage (2026-10-19)

The deliverable is actual rally/idle segmentation of a complete, unedited training
recording. Edit seams, camera cuts, scene transitions and artificial concatenation
are not rally evidence and must never create boundaries in the training-video
paths. `edited`/`scene` are retired diagnostics only; their demo alignment scores
cannot be reported as rally accuracy or used to rank against Gemini semantics.
Do not restore the old edited demo as the main launcher or silently apply its
contiguous annotations to other videos. CPU-only, no required pose inference,
open-source comparison and independent-project requirements remain in force.
Use independent human labels of real play/idle. No route is currently accepted
for untrimmed training footage.

## Raw-video development sample (2026-10-19)

Owner supplied E:\Built\TennisVision\demo3_clip1.mp4 (about 299.6s, 1080p)
and end events 35,51,64,83,~110,132,169,186,222,238,297 seconds.
The durable annotation is tests/fixtures/demo3_clip1.manual_ends.v1.json.
These are END-ONLY labels. Never fill starts from preceding ends or claim
segment-IoU/start accuracy. Include net/out serves as short attempts. Only ~110s
was explicitly approximate. This is development evidence, not an independent
test set. Preserve unsuccessful baselines and unmatched predictions.

The owner proposed court-centre ball presence and requested light CPU methods.
Test motion/coherence rather than stationary presence; stationary net balls must
not prolong play. Do not assume small weights imply low compute: the experimental
0.9MB two-frame model consumes full 1080p pairs and has an upstream AGPL license.
Weights and license for that model stay together under ignored models/. Do not
deploy it to the business server without a separately reviewed accepted result.

## Owner clarification: faults and occasional edits (2026-10-19)

The owner accepts merging a failed serve with the following serve attempt.
Preserve the original attempt-level manual labels and historical 11-end scores;
any relaxed point-level evaluation must be reported separately with an explicit
optional-fault policy. This does not excuse merging two completed rallies.

Mostly continuous uploads may contain occasional edits. An edit may be recorded
as a discontinuity and used to reset temporal tracking, but is insufficient on
its own to assert a rally boundary. Distinguish removed waiting, a viewpoint
change within a rally, and replay/duplicate footage. The current raw-video
benchmarks do not validate mixed-edit handling; do not claim it is implemented
or accepted without a separate labelled mixed-edit test.

Owner-requested revisit of the old edited demo with the same CPU416 model is
recorded in docs/EDITED_DEMO_REVISIT_20261019.md: one interval 0.44–57.35s,
all four internal manual ends missed at ±2s. Preserve this failure separately
from old seam-detection results; it does not replace the raw-video benchmark.

## Owner-authorized boundary union experiment (2026-10-20)

The owner explicitly requested implementing the union of PySceneDetect and
RallyClip boundary candidates, merging nearby duplicate points, preserving
source attribution, and flagging short fragments without deleting them.
This authorizes a new experimental fusion path where scene candidates can
split RallyClip intervals. Preserve the previous standalone baselines and
their no-scene-splitting behavior. Retain every union boundary in the output,
including those outside predicted play; do not relabel waiting as play or
claim that a scene cut proves a rally end. Report unlabelled random-demo tests
as qualitative reviews, never as measured rally accuracy.

Implementation and random test are recorded in docs/UNION_EXPERIMENT_20261020.md.
The genuine random draw selected demo_forrating2.mp4 (70.97s); keep its saved
selection seed/pool and the poor result. Five union boundaries form six full
partitions; only two intervals have RallyClip support, first ~35s hitting is
missed by that route, and a 0.899s activity fragment remains. This is not accepted
for unattended clipping. Existing edited-demo regression recovers four internal
ends, which is development evidence only. Final 48 tests passed.

Same-day follow-up restored the official 960 input on that exact random video:
first-35s activity coverage improved from 0 to 33.429s, not a measured accuracy
or recall score. Separate two-thread CPU control runs took 11.499s (416) and
33.790s (960); weights, 5fps and thresholds unchanged. Short fragments and the
need for scene supplementation remain. Preserve both results; do not generalize
960 superiority to every video (older raw-video end scores were equal).
tools/run_union.py now accepts --imgsz 416|640|960, default remains 416. The
960 option uses the official artifact default without an input-size override.

Actual pose inspection is recorded in docs/POSE_DIAGNOSTIC_20261020.md. On that
same random video, official960 captured 355 actual 5fps samples: near assigned
355 times, far only once. Raw detections contain just one person in 350 samples.
Do not describe this run as reliably extracting both players. Feature capture
preserves exact previous predictions; display threshold changes no inference.
Keep pose_samples.jsonl, actual_features.npz and rendered evidence under ignored
outputs/pose_diagnostic_20261020/, not in source control.

## Score diagnosis and replay correction (2026-10-20)

docs/SCORE_DIAGNOSTIC_20261020.md records an owner-authorized exact960 rerun on
demo3_clip1 with actual three score tracks and poses. All12 original intervals
reproduce exactly;8/11 ends match at2s. Missed35/64/132 are crossed by continuous
high pointness, not the0.5s merge rule (no merges occurred). Near missing268/1499,
far missing1492/1499; pose absence is evidence, not established causality.
Sequential source decode now verifies a37s transition and visible「精彩回放」at
38/40/45/49s. Correct earlier claims of wholly unedited footage: this sample
contains replay. Preserve original owner labels and historical scores; do not
silently remove replay events or invent a new replay ground-truth policy.
Use outputs/demo3_score_diagnostic_20261020/review.html for the synchronized
video/pose/score/end-label diagnosis. Feature/score captures never train on labels.

## Owner-authorized portable application (2026-10-20)

The owner requested a standalone ZIP with its runtime and models inside the
project, one-click frontend launch after extraction, and Netcast Tennis styling.
The application is now `src/rallycut/local_app.py`, `local_worker.py`, and `web/`.
It uses the official960 CPU RallyClip path displayed in the score diagnosis,
not the416 shortcut, Gemini, or the optional scene-union experiment.

Keep runtime and generated content under ignored `dist/`, `runtime/`, `vendor/`
and `data/`. `tools/build_portable.py` builds an offline Windows x64 package
from explicit allowlists, official embedded Python, app-local VC runtime,
FFmpeg and the unmodified upstream snapshot/model files. Do not package
development virtualenvs, credentials, private videos or populated data folders.
Upstream `src/preprocessing/default_court_mask.png` is a required runtime asset.
Unicode directories require the worker's scoped image-read adapter; it preserves
identical mask pixels and restores OpenCV after use. Do not alter model weights,
score thresholds or sample timing to fix packaging failures.

The app uses a single CPU job queue and loopback HTTP, records real phases,
and exports H264 previews/clips plus real pose/scores. A compatible original
video remains the inference source; unsupported playback codecs get a separate
preview conversion. Rotation or large timestamp normalization is explicitly
recorded. Cancelling stops the worker and descendants; deleting a job deletes
only its application-owned directory, never the user's external original.

See docs/PORTABLE_APP.md and docs/PORTABLE_ACCEPTANCE_20261020.md for evidence.
Software packaging tests do not constitute new segmentation accuracy evidence.
The upstream snapshot still has no root LICENSE; preserve the third-party
notices and do not claim external redistribution rights have been obtained.

## Owner-authorized automatic GPU fallback (2026-10-20)

The owner now requests GPU when available and CPU otherwise. This supersedes
CPU-only execution for the portable app; CPU support remains mandatory. Use
NVIDIA CUDA with the unchanged official960/5fps weights; no paid instance or
business-server deployment is authorized by this request. The local RTX3050Ti
can be used for verification. Keep the historical CPU ZIP and results.
The AutoGPU package must contain its GPU runtime libraries as well as CPU
fallback, without requiring user installation of CUDA or an online download.
Record actual provider execution and fallback reasons; a GPU-capable wheel or
the presence of a GPU is not proof that CUDA inference ran. Retry the same input
on CPU once after a GPU failure, and propagate CPU failures. Do not hide backend
fallback, change thresholds, or weaken interval comparisons to claim success.

Implementation and actual ZIP acceptance: docs/GPU_AUTO_FALLBACK_20261020.md.
AutoGPU ZIP includes ORT1.22.0 CUDA12 plus pinned NVIDIA libraries; CPU/GPU ORT
wheels must never overlap. A first cuFFT-missing probe correctly fell back to CPU;
preserve that evidence and keep cuFFT in the package allowlist. Real CUDA kernel
profiling and a full extracted-package upload passed on the local3050Ti.
CUDA_VISIBLE_DEVICES=-1 verifies the same package's automatic CPU fallback.
All three intervals remain within0.001s of the historic reference, not bit equal.
90 source tests passed; no new accuracy or business-server capacity claim.

## Owner correction: GPU dependencies outside the default ZIP (2026-10-20)

The owner explicitly rejected bundling the large GPU runtime in the default ZIP,
and asked for clear requirements instead. This supersedes the earlier mandatory
GPU-library-bundling instruction. Deliver a Light CPU-ready portable package with
requirements-gpu.txt and GPU_SETUP.md. Optional GPU packages install into the
project's separate runtime/gpu-site-packages, verified and enabled before loading.
Never overlay GPU wheels onto the base CPU runtime directory. The base package
remains usable without optional installation; keep automatic GPU/CPU fallback.
Retain the previous large AutoGPU ZIP as historical output, not the new download.

Light release acceptance is recorded in docs/OPTIONAL_GPU_PACKAGE_20261020.md:
263,122,848-byte ZIP, 93 tests passed, real extracted CPU and separately installed
GPU inference both reproduce the three reference intervals within0.001s. All3593
base file hashes survive the optional pip install; frontend startup also passes.
The requirements are an extension to the portable CPU environment, not a complete
standalone virtualenv manifest. GPU install uses Python3.12 x64 as an installation
tool; application execution still uses its embedded Python.

## Owner-authorized visual-only acceleration (2026-10-20)

The owner rejects any audio involvement in the new accelerated route. Use only
video pixels; the current official960/5fps output may serve as a frozen teacher
optimization target. Teacher agreement is NOT human accuracy. Keep the current
portable release and teacher weights intact; experimental changes must have a
separate entry point. Record speed, missed/extra teacher intervals and boundary
drift, with separate development and held-out videos. No teacher predictions,
cached teacher poses, or labels may be read by the accelerated inference path.
CPU-only benchmark results remain local, not business-server measurements.

First visual-only acceleration is documented in docs/VISUAL_ACCELERATION_20261020.md.
Entry: run_fast_visual.ps1 / tools/run_fast_visual.py. v2 uses256 person crops,
full960 rediscovery every10 samples, one court-search attempt and empty recheck
every5 samples with motion-triggered early checks. Keep native decode and5fps.
No audio, no teacher files read at inference, no new student training claim.
Do not silently replace the portable full-quality default.

CPU2-thread tests: demo3_clip1 233.52→78.15s; separately held-out clip2
224.33→75.76s (~3x,0.25x video duration), teacher12→student11. Clip2's missed
teacher interval is90.72–91.87s;11/12 ends match within1s (mean error0.120s).
Clip2 is another part of the same recording, not an independent camera.
Short development clip has one extra split; deemo1 gives0→0 and cannot establish
rally recall. flat_deemo was rejected by teacher's720p minimum, not scored.
98tests and four-video browser review passed. Preserve failed sparse/interpolation,
tiny-crop, INT8, OpenVINO and NONREF experiments. Teacher agreement is not accuracy.

Owner-requested additional frozen-v2 video check: deemo2.mp4 (133.639s,
2880x1620), selected before inference and not used for acceleration tuning.
Results: outputs/visual_acceleration_deemo2_20261020/review_data.json.
CPU2-thread teacher68.586s vs fast27.105s (2.53x,0.203x video duration).
Teacher7 intervals vs fast5; active-time IoU only0.40155; starts1/7 and ends2/7
match within1s. This is a material generalization failure relative to teacher.
Do not summarize v2 as broadly accurate based only on the earlier clip2 result.
No retuning occurred; full default remains unchanged. Teacher is not human truth.

Owner subsequently excluded deemo2 from future testing and scheme evaluation
("deemo2不太行的，别测它"); preserve its existing output as history only.
The owner selected demo3_clip1.mp4 again. Its existing frozen-v2 run is available;
the dedicated review is outputs/visual_acceleration_demo3_clip1_review_20261020/.
This is reused development evidence, not a new held-out test or a new timing run.

## Owner-authorized GitHub team handoff (2026-10-20)

The owner requested GitHub delivery to the technical director using AndyLongest.
Keep this project an independent repository; default to a private team handoff.
Do not upload sibling projects, private footage, populated job directories or
credentials. GCM holds the owner's existing GitHub login; do not persist tokens.
README now routes to docs/HANDOFF.md and docs/RESULT_CONTRACT.md; the previous
README is preserved as docs/LEGACY_EXPERIMENTS.md.
upstream-lock.json pins source commit ebf1a82b9853ae62d03f4da2c2b8a0d647a48261
and v0.5.0 artifacts; tools/bootstrap_upstream.py verifies 90 files and never
overwrites modified existing assets. Runtime files remain ignored.
The released Light ZIP is the previously verified full application, byte-for-byte
unchanged. Fast v2 is delivered as source CLI, not silently inserted into its UI.
See docs/DELIVERY_ACCEPTANCE.md for clean-environment and package evidence.

## demo_cut diagnostic correction (2026-10-20)

demo_cut.mp4 is720x404, rejected by the unmodified720p minimum. A separately
labelled1284x720 upscale experiment produced0 final intervals in both full/fast.
Do NOT infer pose failure or low pointness from those empty results: actual
decode replay shows867/869 samples above0.5, one refined172.64s candidate,
discarded by max_duration_sec=60 before merging. Full pose capture confirms
raw people in836/869 samples, near selected802/869, far1/869; score arrays
exactly reproduce the prior run. Far-player absence is real, but not established
as the cause of continuous pointness. Raising the cap alone would retain one
long interval, not recover internal rally boundaries. Evidence and actual
pose/score review: outputs/demo_cut_visual_20261020/teacher_pose/.

## Owner-authorized current visual union (2026-10-20)

Owner confirms continuous hitting in demo_cut and explicitly requests union with
edit detection again. New run_visual_union.ps1 / tools/run_visual_union.py uses
current fast v2 or official full CPU, no audio. Restore only score runs dropped
for exceeding the original60s limit after exact decoder replay verification,
then fuse scene boundaries. Retain final fragments still over60s with review
flags. Preserve standalone behavior and the already published Light ZIP.
See docs/VISUAL_UNION_V2.md. demo_cut explicit720p upscale now yields4 candidates
at0.299–30,30–96.5,96.5–140.5,140.5–172.940. All three edit candidates show
position discontinuities in neighboring sampled frames; this is qualitative,
not labelled accuracy. No threshold retuning.108 tests passed; separate42.57s
fresh CPU2-thread smoke completed in29.951s. Keep cached phase sums distinct
from new end-to-end timings and disclose the original404p limitation.

Owner subsequently identified a missed rally/edit boundary around51s. Native
frames confirm a position discontinuity at51.64s; do not present the previous4
segments as complete. At sampled51.75s global adaptive_ratio2.81524 missed3.0
(content3.92863 passed floor.5). Same-threshold left/lower70% regional detector
ratio3.19515 recovers it; global+left+right yields4cuts/5segments. Global threshold
2.8 also recovers it on this sample, so regional superiority is unproven.
This is a separate diagnostic only, not a changed default or held-out evaluation.
See docs/VISUAL_UNION_V2.md and outputs/demo_cut_seam_diagnostic_20261020/.

Owner requested repository update after that diagnostic. Regional detection is
now an opt-in source CLI profile: run_visual_union.ps1 -SceneProfile regional
or --scene-profile regional. Keep global default and the published ZIP unchanged.
Reuse one sampled decode for upstream full/left/right detectors, preserve regional
provenance, reject cached profile mismatches. No fresh human accuracy claim.
