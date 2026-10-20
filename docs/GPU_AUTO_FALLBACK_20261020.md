# Automatic CUDA with CPU fallback — 2026-10-20

The owner requested GPU when available, CPU otherwise. This changes the
portable application's execution backend, keeping official RallyClip v0.5.0
weights, 960 pose input, 5fps, confidence/decoder thresholds and batch size 1.
CPU threads remain 2. No paid machine, server access or model retraining.

## Implementation

`device_runtime.py` checks both the ORT CUDA provider and the actual CUDA driver
device count, then loads application-local NVIDIA libraries. A successful CUDA
session must finish a run before the UI calls it GPU. The session wrapper owns
fallback: initialization errors, ORT silently returning CPU, and GPU run
exceptions disable further GPU attempts for that job. The failed input is retried
once on CPU; a failing CPU retry propagates. Other existing CUDA sessions move
to CPU before their next call. No failed sample is skipped.

Progress and results expose the actual device, first fallback reason, per-session
providers and successful CUDA-backed/CPU run counts. `GPU → CPU` records a job
that executed CUDA before fallback. CUDA-backed sessions may still execute
unsupported/small graph operators on CPU; the GPU label is not a claim that
every operator ran on the GPU.

CUDA uses FP32 with TF32 disabled and heuristic, bounded-workspace convolution
selection. This avoids precision reduction and large exhaustive-search scratch
allocations. It does not guarantee identical floating-point bits across backends.
FFmpeg media preparation/export remains CPU-based.

The application-local GPU wheel is ONNX Runtime 1.22.0 (CUDA12), replacing rather
than overlapping the CPU-only wheel. NVIDIA CUDA Runtime12.4.127,
cuBLAS12.4.5.8, cuFFT11.2.1.3, NVRTC12.4.127 and cuDNN9.1.0.70 are bundled.
The Windows driver is external; the application does not install/update it.
AMD/Intel GPUs currently use CPU. `RALLYCUT_DEVICE=cpu` is a maintenance override.

## Evidence

Local GPU: RTX3050Ti Laptop, 4GiB, driver551.61; local CPU Ryzen7 6800H.
The video is the same 70.966667s `demo_forrating2.mp4`.

- `outputs/gpu_auto_20261020/direct_gpu/result.json`: the first dependency
  probe lacked cuFFT. It correctly completed on CPU with an explicit
  initialization-fallback reason. Analysis42.695s, total50.100s; three intervals,
  maximum boundary deviation from the historical CPU reference3.54e-8s.
  This unsuccessful GPU attempt is preserved, not presented as GPU execution.
- `outputs/gpu_auto_20261020/gpu_complete_runtime/result.json`: after including
  the missing cuFFT wheel, all three model sessions used CUDA. Court pose11
  calls, main pose355 calls, temporal model7 calls. Analysis21.822s,
  total31.287s; three intervals, maximum endpoint difference2.995e-7s.
- `outputs/gpu_auto_20261020/kernel_profile/verified.json`: independent real
  pose-input profiling verifies272 CUDA kernel events and49 CPU events.
  This confirms actual CUDA execution, rather than only a provider registration.
- Unit tests exercise no CUDA wheel, no visible driver/device, runtime-load
  failure, CUDA initialization exception, silent CPU fallback, GPU run failure
  with same-input CPU retry, sticky fallback across sessions, CPU failure
  propagation, and the explicit CPU override. Source suite:90 passing tests.

These are implementation/regression checks on a development sample, not new
accuracy measurements or server capacity claims. Timings include initialization
and ordinary desktop load; they are not controlled multi-repeat GPU benchmarks.
The older CPU ZIP and all earlier benchmark results remain available.

## Final distribution acceptance

Release: `dist/RallyCut-Windows-x64-AutoGPU.zip`,1,771,224,460 bytes.
SHA256: `9adb34311306116d5a8645a5c353152c9eeb838cd75311739f271bdab4b96289`.
ZIP CRC passed;3777 manifest file hashes and current application source parity
were checked after extracting the release into a Chinese-and-space directory.
The ZIP contains no user jobs or QA footage. GPU libraries are bundled rather
than copied from a system CUDA installation.

`outputs/gpu_auto_20261020/package_acceptance.json` records tests from the exact
extracted release, launched from `C:\Windows` with Python environment paths
removed and PATH limited to package FFmpeg and Windows:

- With `CUDA_VISIBLE_DEVICES=-1`, default automatic selection correctly reports
  CPU and no available NVIDIA device/driver. All sessions run on CPU.
  Analysis35.502s; total including video exports42.192s. This hides the local
  GPU for the test; it is not a separate physical CPU-only host test.
- Restoring normal device visibility, an actual browser upload selects CUDA.
  Analysis14.935s; total21.162s. The page shows the actual GPU device.
  Three intervals remain, maximum boundary deviation2.995e-7s from the
  historical CPU reference. This is numerical tolerance, not bit equality.
- `browser_gpu/acceptance.json` records successful playback, actual bone pixels,
  12.2s sample stepping, video/JSON/ZIP downloads, mobile layout, real worker
  cancellation, deletion of test jobs and corrupt-video rejection. No browser
  JavaScript errors or external requests.

The GPU UI service is left running from the extracted QA package on127.0.0.1:8766.
The original CPU application and historical results are not replaced.
These single package acceptance timings are informative, not a guaranteed
throughput ratio. No paid GPU resource was created.
