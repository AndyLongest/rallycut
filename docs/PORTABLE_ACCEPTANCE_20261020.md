# Portable application acceptance, 2026-10-20

Owner requested a standalone, self-contained ZIP with a one-click local
frontend, using Netcast Tennis colors. Target: Windows 10/11 x64.
This packages the existing official960 CPU experiment; no model training,
label changes, paid compute or business-server access occurred.

## Implementation

- `src/rallycut/local_app.py`: loopback HTTP, streaming uploads, serial worker
  queue, restart history, cancellation, safe app-owned deletion, byte-range
  playback and downloads. Origin/Host/token checks protect mutation endpoints.
- `src/rallycut/local_worker.py`: unchanged official960/5fps model and decoder,
  actual pose/score capture, CPU-only sessions, H264 preview, re-encoded clips,
  JSON and ZIP. Source/normalization provenance is explicit.
- `src/rallycut/web/`: offline Chinese UI, Netcast deep purple `#171020`,
  purple `#8b42ee`, lime `#c4f12c`, pale background `#f5f3f7`.
- `tools/build_portable.py`, `packaging/`: application-local Python 3.12.10,
  dependency allowlists, required model files and court mask, FFmpeg, Microsoft
  redistributable CRT DLLs, startup/shutdown scripts, per-file SHA256 manifest.

## Evidence already obtained

`outputs/portable_worker_smoke/smoke_verification.json`:
the70.97s H264 sample produced exactly the three historic official960 interval
endpoints, including every floating-point value. Analysis45.683s,
export7.193s, total55.275s. Clip duration differences below one30fps frame.

`outputs/portable_worker_hevc_smoke/smoke_verification.json`:
the57.9s HEVC sample was inferred from the original source, while its H264
preview retained1737frames and57.9s duration. Analysis30.478s,
export5.679s, total43.322s. Its original poor rally segmentation remains:
only one interval; no scene boundaries were silently added.

`outputs/portable_unicode_verification/verification.json`:
Chinese-and-space directories retain identical court-mask pixels, identical
TCN/pose outputs from CPU ONNX sessions, and identical PyAV video pixels.

The isolated package import/model check ran from `C:\Windows` after clearing
Python environment paths and limiting PATH. All imported modules and loaded
MSVC runtime DLLs resolved inside the package; both ONNX files loaded on CPU.
No PyTorch or Ultralytics inference framework was imported.

`outputs/portable_ui_qa/acceptance.json`:
actual package-browser upload, CPU inference, video playback/seeking, visible
pose pixels,12.0→12.2sample stepping, clip download,390px layout, history,
real-worker cancellation/deletion, and corrupt-video rejection all passed.
No JavaScript errors or external requests. Packaged analysis36.780s,
total43.571s on this laptop, not a server estimate or controlled speed comparison.

Final source test run: `python -m pytest -q`: **80 passed**.

## Final ZIP extraction acceptance

Release: `dist/RallyCut-Windows-x64.zip`,263,069,336bytes; unpacked
672,364,131bytes,3589files. SHA256:
`4d5abc10387f9f45f1334f0e576a7581bfc92290069f155d83504434f9a55ed3`.

`outputs/portable_build/build_audit.json` records passing ZIP CRC, mandatory
asset presence, current source consistency, no populated data, private video,
credentials, development venv or cache wheel. Runtime module and CRT loading
checks resolve inside the app, excluding normal Windows/security modules.

The actual final ZIP was extracted under
`outputs/portable_zip_qa/中文 解压验收/RallyCut-Windows-x64`.
Its unmodified `Start.cmd` was invoked from `C:\Windows` with no development
Python environment and a minimal system PATH. It opened the browser and
started the local service successfully.

`outputs/portable_zip_qa/browser/acceptance.json` records a new actual browser
upload and full CPU run in that extracted directory: analysis42.752s,
total50.742s, all three session providers CPU only; exact historic960 interval
parity. Actual skeleton pixels and12.2s sample step checked; no browser errors,
external page requests or390px horizontal overflow. MP4 downloaded, JSON and
whole-clips ZIP downloads matched source hashes. Cancellation of a second
real worker, deletion of its app-owned data and corrupt-video rejection passed.
The ZIP itself remains unchanged and contains no acceptance-test user data.

## Defects found and corrected during packaging

1. The first code-file allowlist omitted the author's default court-mask PNG.
   Actual inference failed clearly. The resource now has an explicit allowlist
   entry, packaging test and actual mask-load self-check.
2. OpenCV's Windows `imread` failed for that resource under Chinese directories.
   A scoped adapter reads the same bytes with `imdecode`; pixel identity is
   verified. The original upstream snapshot is not modified.
3. Headless Edge cancelled a test download when the harness passed a
   forward-slash Windows `downloadsPath`. Canonicalizing that harness path
   fixed the test; independent browser downloads of MP4/JSON/ZIP also matched
   the served source hashes. No unsupported frontend workaround was added.

## Limits

This validates software operation on the current Windows machine with isolated
package paths. It is not a clean-Windows-VM certification, Linux distribution,
business-server benchmark or new accuracy evaluation. The recognizer still has
the documented false merges/misses and short fragments.

The public upstream snapshot does not include a root LICENSE. Third-party
source/weight redistribution permission has not been asserted or obtained by
this packaging work. The package includes provenance and existing notices.
