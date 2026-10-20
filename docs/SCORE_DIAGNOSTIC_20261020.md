# Frozen-model score diagnosis, 2026-10-20

Owner authorized checking existing `demo3_clip1` end annotations against the
actual RallyClip score tracks and pose input. No new labels, tuning, training,
GPU, service calls or upstream source/weight changes were used.

## Reproduction and outputs

```powershell
.\.venv\Scripts\python.exe tools/benchmark_rallyclip.py outputs/upstream_rallyclip/RallyClip-main E:/Built/TennisVision/demo3_clip1.mp4 --output outputs/demo3_score_diagnostic_20261020 --threads 2 --capture-features --capture-scores --labels tests/fixtures/demo3_clip1.manual_ends.v1.json
.\.venv\Scripts\python.exe tools/diagnose_scores.py outputs/demo3_score_diagnostic_20261020 tests/fixtures/demo3_clip1.manual_ends.v1.json --upstream outputs/upstream_rallyclip/RallyClip-main --historical outputs/demo3_clip1_rallyclip_cpu/rallies.json --observations outputs/demo3_score_diagnostic_20261020/visual_observations.json
.\.venv\Scripts\python.exe tools/build_score_diagnostic.py outputs/demo3_score_diagnostic_20261020/diagnostic.json --output outputs/demo3_score_diagnostic_20261020/review.html
```

Primary artifact: `outputs/demo3_score_diagnostic_20261020/review.html`.
It loads the original local video with synchronized canvas pose overlay,
pointness/start/end score tracks, threshold, original candidate intervals,
end-only human marks, per-end evidence and unmatched predictions. It uses no
network/CDN/server. Original media remains necessary at its recorded path.

Captured `model_scores.npz` contains the actual post-sigmoid, overlapping-window
averaged outputs immediately before `HeatmapHybridModel.postprocess`.
`score_capture.json` records the actual effective decoder config. Poses/features
are `pose_samples.jsonl` and `actual_features.npz`. `diagnostic.json` and
`diagnostic_summary.json` contain stage trace and evidence; visual observations
are separate, never inference input or new ground truth.

Official v0.5.0 defaults: pose input960, 5fps, 20s/100-frame windows, CPU ORT two
threads. 1499 samples. Capture run 197.555s with some concurrent QA work, not a
new controlled capacity benchmark. All twelve output intervals, including every
floating-point endpoint, exactly match the earlier saved official960 run.

## End-only results and exact decode path

Strict, one-to-one ±2s: 8/11 human ends matched. Starts and interval-IoU are
unknown because no start labels were supplied. Fault endpoints64/132 remain in
the historical evaluation, with the owner's accepted fault-merging policy shown
separately. The labels' completeness is unverified, so unmatched predictions are
not automatically confirmed false positives.

| Manual end | Saved model end | Diagnostic evidence |
|---|---|---|
|35|None|Raw high-pointness run6.2–50.0s. In33–37s pointness0.823–0.953; end head peak0.557 at33.6s. Internal end peaks do not independently split this decoder.|
|51|49.947|Matched, early1.053s.|
|64, serve fault|None|High-pointness run59.6–83.0s; nearby pointness0.877–0.958. Fault merging is acceptable to owner.|
|83|82.957|Matched.|
|~110|109.541|Matched, original approximation preserved.|
|132, serve fault|None within2s|High-pointness run128.4–135.4s; end peak0.635 at131.8s. Refined end135.086 is3.086s late; refinement actually moves the raw end earlier.|
|169|167.330|Matched, early1.670s.|
|186|184.130|Matched, early1.870s.|
|222|221.727|Matched.|
|238|237.900|Matched.|
|297|296.526|Matched.|

Unmatched predicted ends135.086,139.031,140.4,171.890s. The last three correspond
to short score islands; final durations1.258s,0.400s,0.352s. Their short lengths
are demonstrated by output data, not sufficient on their own to prove false
positives. Around138–141s inspected frames show near-player serve preparation.

Trace reconstructed15 raw >=0.5 runs. Three were rejected by the0.3s duration
floor; none by the60s maximum. Twelve remain and **none are merged**. Exact
replay with `merge_gap_sec=0` produces the same twelve intervals. Therefore
the short-gap merge rule did not cause the missed35/64/132 endpoints in this run.

Do not describe an internal end-score peak as a confirmed correct boundary.
It is evidence of a response on that output channel; the main score and hybrid
decoding policy still govern whether a split occurs. This localizes the
computation but does not explain why network weights produced high pointness.

## Pose evidence and newly verified replay content

Near player unassigned268/1499 samples; far player unassigned1492/1499.
Among near-missing samples233 have no raw person detections;35 had one raw
detection removed by the court filter. At35±2s,18/21 near samples are missing;
all18 have zero raw detections. Far is missing in all21 samples in that window.
This local absence begins before court filtering or player assignment. Missing
input co-occurring with a wrong boundary does not prove the causal explanation.

**Correction to earlier descriptions of demo3_clip1 as wholly unedited footage:**
visual review now verifies a transition at37s and clearly visible
「精彩回放」text at38,40,45 and49s. This is mixed footage containing replay,
not an independently established unedited-training benchmark. Preserve original
labels and all historical scores; do not retrospectively relabel or remove
events without owner-defined policy. First35s endpoint crosses into this replay
material within a single high-pointness run. Skeletal motion alone does not
encode the replay label visible in the image.

Initial OpenCV random-seek thumbnails emitted H264 reference-frame warnings;
they are not the authoritative timestamp evidence. Key observations were
rechecked through sequential PyAV decode without seeking, saved as
`sequential_35.jpg`, `sequential_37.jpg`, `sequential_38.jpg`, etc. Their actual
PTS equals the requested timestamp. Keep this limitation and the verification.

## Verification

- Original prediction exact parity and exact upstream decoder replay parity.
- Independent second read confirmed tracks, run count, matching and missing
  input counts; no tuning used to obtain the reported result.
- Source PTS and model time kept separate. Decoder uses `i/5`; actual sample
  PTS differs by up to0.1s in this clip. This does not account for multi-second
  boundary errors. The viewer uses each respective time axis.
- 52 pytest tests passed, including non-mutating score-capture and distinct
  stage-attribution cases.
- Edge `file://` playback, pause, seek, sample step, pose toggle, all11 manual
  and4 unmatched rows, and390px mobile layout passed without JavaScript errors
  or page overflow. Screenshots at32/35/132s inspected for overlay/score alignment.

Next experiments, not implemented here: measure better person coverage and
correct player assignments; evaluate treatment of internal end signals while
guarding against peaks inside real rallies; define replay inclusion policy.
Keep development tuning and future video-level validation separate. Existing
evidence does not yet warrant a claim that retraining or a specific rule fixes
these errors.
