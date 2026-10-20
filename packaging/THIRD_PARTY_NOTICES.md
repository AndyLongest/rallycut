# Third-party components

This distribution contains unmodified third-party runtime files and model assets.
Their original terms apply. This notice does not grant a new license for any of
them. Versions and per-file SHA-256 values are in `distribution-manifest.json`.

## RallyClip and models

Source: https://github.com/iroblesrazzaq/RallyClip

The bundled snapshot and `rallyclip_v0.5.0` model artifact are preserved under
`vendor/RallyClip`. Source and manifests are included; inference uses ONNX Runtime
on CPU or CUDA. At the time of packaging, the downloaded upstream root did not contain
a LICENSE/COPYING file. Public source availability alone does not establish
permission to redistribute or commercially sublicense that source or its weights.
The distributor should resolve this with the upstream author before external
distribution. This package does not assert that permission has been obtained.

The pose artifact is a YOLOv8n-pose export, attributed in its upstream manifest.
Ultralytics licensing information: https://www.ultralytics.com/license .
No blanket license assertion for the upstream exported weights is made here.

## CPython

Official CPython 3.12.10 Windows x64 embeddable package:
https://www.python.org/downloads/release/python-31210/

Original license: `runtime/python/LICENSE.txt`.
This application-local runtime is independent of a system Python installation.

## Python distributions

NumPy, SciPy, OpenCV, PyAV, ONNX Runtime, tqdm, tomli, FlatBuffers, packaging,
protobuf, colorama, PySceneDetect, click and platformdirs are included. Their
wheel-provided license and metadata files are retained in
`runtime/site-packages/*dist-info/` and the corresponding package directories.
PyAV's bundled FFmpeg libraries retain the wheel's notices and license files.
Package versions are listed in `distribution-manifest.json`.

## NVIDIA runtime libraries (AutoGPU edition)

The AutoGPU edition includes the official NVIDIA CUDA Runtime, cuBLAS, cuFFT,
NVRTC and cuDNN wheel distributions. Their original license files are retained
in `runtime/site-packages/nvidia_*dist-info/` and package directories.
Sources: https://pypi.org/user/nvidia/ and https://developer.nvidia.com/cuda-toolkit .
NVIDIA terms apply to these binaries. The NVIDIA display/compute driver is
provided by the host operating system; this application never installs a driver.

## FFmpeg

The bundled FFmpeg build is the Gyan shared Windows build, licensed GPL v3
according to its distributor's README. Original LICENSE, README/source reference
and exact binary build configuration are in `runtime/ffmpeg/`.

- Distributor: https://www.gyan.dev/ffmpeg/builds/
- Project and source: https://ffmpeg.org/ and the commit link in that README.

## Microsoft Visual C++ runtime

Unmodified x64 Microsoft.VC143.CRT binaries are included next to `python.exe`.
They are taken from Visual Studio's official `VC/Redist/MSVC` directory, not
debug runtime or arbitrary system DLLs. Microsoft terms apply:

- https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution
- https://visualstudio.microsoft.com/license-terms/

Operating-system DLLs and the installed GPU driver may be loaded from Windows.
CUDA user-space libraries are application-local. No global installer is executed.
