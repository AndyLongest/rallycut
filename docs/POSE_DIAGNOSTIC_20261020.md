# Actual pose feature overlay, 2026-10-20

Owner requested visualizing the human features actually entering RallyClip on
the current random sample, `E:\Built\TennisVision\demo_forrating2.mp4`.

Run: `tools/benchmark_rallyclip.py` with official artifact defaults, CPU ORT,
two threads, and `--capture-features`; output `outputs/pose_diagnostic_20261020/`.
The optional observer in `tools/pose_capture.py` captures native PyAV PTS,
raw detections, court-filtered detections, reference-coordinate near/far player
assignments, and the actual 362-dimensional feature vectors. It forwards original
objects/results unchanged. The upstream snapshot and model weights were not edited.

Evidence:

- 355 samples, feature matrix `(355, 362)`; existence flags at offsets 0 and 181
  match every captured near/far assignment. Every predicted interval is exactly
  equal to the saved official-960 control run, including floating-point endpoints.
- Near player assigned in all 355 samples. Far player absent in 354 samples;
  only assigned at source PTS 6.233333333333333s. Assignment is a heuristic label,
  not verified identity tracking.
- Raw person counts: 350 samples have one detection, four have two, one has three.
  Thus the missing far-player signal often originates before court filtering,
  rather than solely from the subsequent player assignment. This does not prove
  that all rally boundary errors have this cause.
- Capture run took 54.453s including observation; not a new clean speed benchmark.
  Preserve earlier separate 33.790s official-960 and 11.499s 416 control timings.

`tools/render_pose_features.py` renders `pose_features_960.mp4` and
`pose_review.html`. Main video plus near/far magnified insets, raw grey boxes,
selected cyan/orange boxes, 17-point skeletons, confidence diagnostics, actual
sample timestamps/age, and original RallyClip candidate status. Display confidence
threshold 0.35 only hides uncertain joints/edges in the rendering; it does not
change model input or predictions. A 5fps sample is held until the next actual
sample, without interpolation or additional inference. Candidate state excludes
scene-boundary fusion, and is never labelled ground truth.

Validation: 48 pytest tests passed; exact prediction parity and all feature
existence flags checked against saved data; 10s/40s/60s rendered frames inspected;
complete output video/audio decoded without errors. Output 1280x1000, 30fps,
70.966667s with audio. Source 1280x720 picture preserved above diagnostic insets.
Visible far-side people lack a selected far-player overlay in inspected frames;
near-player skeleton can lag moving limbs because the underlying sample rate is
5fps. This artifact exposes those limitations rather than correcting them.
