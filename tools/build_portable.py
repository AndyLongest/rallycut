"""Build an application-local Windows x64 distribution without copying a venv.

Run with the project's CPython 3.12 environment. Build-time downloads are cached;
the result never installs packages or fetches models when the end user starts it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
PYTHON_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
# Published on https://www.python.org/downloads/release/python-31210/ .
PYTHON_MD5 = "fe8ef205f2e9c3ba44d0cf9954e1abd3"
DISTRIBUTIONS = (
    "numpy", "scipy", "opencv-python-headless", "av", "onnxruntime",
    "tqdm", "tomli", "flatbuffers", "packaging", "protobuf", "colorama",
    "scenedetect", "click", "platformdirs",
)
GPU_DISTRIBUTIONS = {
    "onnxruntime-gpu": "1.22.0",
    "nvidia-cuda-runtime-cu12": "12.4.127",
    "nvidia-cublas-cu12": "12.4.5.8",
    "nvidia-cudnn-cu12": "9.1.0.70",
    "nvidia-cuda-nvrtc-cu12": "12.4.127",
    "nvidia-cufft-cu12": "11.2.1.3",
}
TOOLS = ("pose_capture.py", "score_capture.py", "build_portable.py")
UPSTREAM_RESOURCES = ("src/preprocessing/default_court_mask.png",)
MODEL_FILES = (
    "manifest.json", "model.onnx", "scaler.json", "SHA256SUMS",
    "yolov8n-pose-544x960-static.onnx", "yolov8n-pose-960-dynamic.onnx",
)
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv"}


def digest(path: Path, algorithm: str = "sha256") -> str:
    result = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    return resolved


def copy_file(source: Path, target: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"Refusing symbolic link: {source.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_code_tree(source: Path, target: Path) -> None:
    """Copy explicit code/assets only; never samples, caches, secrets or binaries."""
    suffixes = {".py", ".html", ".js", ".css", ".svg", ".json", ".toml", ".woff2"}
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if any(part in SKIP_PARTS or part.startswith(".env") for part in relative.parts):
            continue
        if item.is_file() and item.suffix.lower() in suffixes:
            inside(item, source)
            copy_file(item, target / relative)


def copy_distributions(destination: Path, gpu_dependencies: Path | None = None) -> list[dict]:
    """RECORD is an allowlist, but its ../Scripts entries are never copied."""
    result = []
    for name in DISTRIBUTIONS:
        if name == "onnxruntime" and gpu_dependencies is not None:
            continue  # CPU and GPU wheels cannot share this import namespace.
        distribution = importlib.metadata.distribution(name)
        origin = Path(distribution.locate_file("")).resolve()
        copied = 0
        for record in distribution.files or ():
            relative = Path(str(record))
            if relative.is_absolute() or ".." in relative.parts:
                continue
            if "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pth", ".whl"}:
                continue
            source = inside(origin / relative, origin)
            if not source.is_file():
                raise FileNotFoundError(f"Missing distribution file: {name}/{relative}")
            copy_file(source, destination / relative)
            copied += 1
        if not copied:
            raise RuntimeError(f"No distribution files found for {name}")
        result.append({"name": name, "version": distribution.version, "files": copied})
    if gpu_dependencies is not None:
        available = {d.metadata["Name"].lower().replace("_", "-"): d
                     for d in importlib.metadata.distributions(path=[str(gpu_dependencies)])}
        for name, version in GPU_DISTRIBUTIONS.items():
            distribution = available[name]
            if distribution.version != version:
                raise RuntimeError(f"Unexpected GPU runtime version: {name}")
            copied = 0
            for record in distribution.files or ():
                relative = Path(str(record))
                if (relative.is_absolute() or ".." in relative.parts
                        or "__pycache__" in relative.parts
                        or relative.suffix in {".pyc", ".pth", ".whl"}):
                    continue
                source = inside(gpu_dependencies / relative, gpu_dependencies)
                copy_file(source, destination / relative)
                copied += 1
            result.append({"name": name, "version": version, "files": copied})
    return result


def copy_upstream_resources(source: Path, target: Path) -> None:
    for relative in UPSTREAM_RESOURCES:
        copy_file(source / relative, target / relative)


def python_archive(cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / PYTHON_URL.rsplit("/", 1)[1]
    if not archive.exists():
        temporary = archive.with_suffix(".download")
        with urllib.request.urlopen(PYTHON_URL, timeout=60) as response, temporary.open("wb") as target:
            shutil.copyfileobj(response, target)
        temporary.replace(archive)
    if digest(archive, "md5") != PYTHON_MD5:
        raise RuntimeError("Official Python archive checksum does not match")
    return archive


def extract_python(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            inside(destination / member.filename, destination)
        package.extractall(destination)
    # No import site: .pth hooks, user packages and system registry are excluded.
    (destination / "python312._pth").write_text(
        "python312.zip\n.\n../site-packages\n../../src\n../../tools\n",
        encoding="ascii",
    )


def find_ffmpeg() -> Path:
    base = Path(os.environ["LOCALAPPDATA"]) / "Microsoft/WinGet/Packages"
    candidates = sorted(base.glob("Gyan.FFmpeg.Shared_*/ffmpeg-*-full_build-shared/bin"))
    if not candidates:
        raise FileNotFoundError("Provide --ffmpeg-bin for a complete FFmpeg shared build")
    return candidates[-1]


def find_vc_redist() -> Path:
    candidates = []
    for name in ("ProgramFiles(x86)", "ProgramFiles"):
        base = Path(os.environ.get(name, "C:/Program Files")) / "Microsoft Visual Studio/2022"
        candidates.extend(base.glob("*/VC/Redist/MSVC/*/x64/Microsoft.VC143.CRT"))
    if not candidates:
        raise FileNotFoundError("Provide --vc-redist pointing to official x64 Microsoft.VC143.CRT")
    return sorted(candidates)[-1]


def copy_runtime_binaries(ffmpeg: Path, vc_redist: Path, target: Path) -> dict:
    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        copy_file(ffmpeg / executable, target / "runtime/ffmpeg/bin" / executable)
    for library in ffmpeg.glob("*.dll"):
        copy_file(library, target / "runtime/ffmpeg/bin" / library.name)
    for filename in ("LICENSE", "README.txt"):
        copy_file(ffmpeg.parent / filename, target / "runtime/ffmpeg" / filename)
    required_crt = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
    for name in required_crt:
        if not (vc_redist / name).is_file():
            raise FileNotFoundError(f"Official C++ runtime missing {name}")
    for library in vc_redist.glob("*.dll"):
        copy_file(library, target / "runtime/python" / library.name)
    version = subprocess.run(
        [str(target / "runtime/ffmpeg/bin/ffmpeg.exe"), "-version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    ).stdout
    (target / "runtime/ffmpeg/build-configuration.txt").write_text(version, encoding="utf-8")
    return {"ffmpeg": version.splitlines()[0], "vc_runtime": vc_redist.parent.parent.name}


def isolated_environment(target: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX"):
        env.pop(key, None)
    system_root = env.get("SystemRoot", "C:\\Windows")
    env["PATH"] = str(target / "runtime/ffmpeg/bin") + os.pathsep + system_root + "\\System32"
    env["TEMP"] = env["TMP"] = str(target / "data/temp")
    env["PYTHONNOUSERSITE"] = "1"
    return env


def self_check(target: Path) -> dict:
    """Check imports and CPU model loads from outside the package with a clean PATH."""
    script = r'''
import json, sys
from pathlib import Path
import numpy, scipy, scipy.ndimage, scipy.signal, cv2, av, onnxruntime, scenedetect
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "vendor/RallyClip/src"))
import rallyclip_api, cli.main, pose_capture, score_capture
from preprocessing.data_preprocessor import DataPreprocessor
from rallycut.local_worker import unicode_image_reads
with unicode_image_reads():
    mask = DataPreprocessor()._load_default_court_mask((720, 1280, 3))
if mask.shape != (720, 1280) or mask.dtype != numpy.uint8:
    raise RuntimeError("Default court mask failed to load with the upstream contract")
options = onnxruntime.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
models = []
for name in ("model.onnx", "yolov8n-pose-960-dynamic.onnx"):
    model = root / "vendor/RallyClip/models/rallyclip_v0.5.0" / name
    session = onnxruntime.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
    models.append({"model": name, "providers": session.get_providers()})
outside = sorted({str(Path(m.__file__).resolve()) for m in tuple(sys.modules.values())
                  if getattr(m, "__file__", None) and not str(Path(m.__file__).resolve()).startswith(str(root))
                  and not str(m.__file__).startswith("<")})
if outside:
    raise RuntimeError("Imports escaped portable directory: " + repr(outside))
import ctypes
from ctypes import wintypes
import os
modules = (wintypes.HMODULE * 2048)()
needed = wintypes.DWORD()
ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
ctypes.windll.psapi.EnumProcessModules.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
ctypes.windll.kernel32.GetModuleFileNameW.argtypes = (wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD)
process = ctypes.windll.kernel32.GetCurrentProcess()
if not ctypes.windll.psapi.EnumProcessModules(process, modules, ctypes.sizeof(modules), ctypes.byref(needed)):
    raise ctypes.WinError()
native = {}
external_native = []
host_security = []
defender_root = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft/Windows Defender"
for handle in modules[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
    filename = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetModuleFileNameW(wintypes.HMODULE(handle), filename, len(filename))
    path = Path(filename.value)
    if not path.resolve().is_relative_to(root) and not path.resolve().is_relative_to(Path(os.environ["SystemRoot"])):
        if path.resolve().is_relative_to(defender_root):
            host_security.append(path.name)
        else:
            external_native.append(str(path))
    if path.name.lower().startswith(("msvcp140", "vcruntime140")):
        path.resolve().relative_to(root)
        native[path.name] = str(path.resolve().relative_to(root))
if "msvcp140.dll" not in {name.lower() for name in native}:
    raise RuntimeError("MSVC runtime was not observed after loading ONNX Runtime")
if external_native:
    raise RuntimeError("Native modules escaped package and Windows: " + repr(external_native))
print(json.dumps({"python": sys.version.split()[0], "models": models,
                  "default_court_mask_shape": list(mask.shape),
                  "external_imports": outside, "app_local_vc_runtime": native,
                  "external_native_modules": external_native,
                  "host_security_modules": host_security,
                  "gpu_framework_loaded": "torch" in sys.modules or "ultralytics" in sys.modules}))
'''
    process = subprocess.run(
        [str(target / "runtime/python/python.exe"), "-B", "-c", script, str(target)],
        cwd=os.environ.get("SystemRoot", "C:\\Windows"), env=isolated_environment(target),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
    )
    if process.returncode:
        raise RuntimeError("Portable runtime check failed:\n" + process.stdout + process.stderr)
    return json.loads(process.stdout)


def write_manifest(target: Path, metadata: dict) -> None:
    metadata["files"] = [
        {"path": str(path.relative_to(target)).replace("\\", "/"),
         "size": path.stat().st_size, "sha256": digest(path)}
        for path in sorted(target.rglob("*")) if path.is_file()
        and path.name != "distribution-manifest.json"
        and "__pycache__" not in path.parts
    ]
    (target / "distribution-manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def archive_distribution(target: Path) -> Path:
    archive = Path(str(target) + ".zip")
    if archive.exists():
        raise FileExistsError(f"Refusing to replace existing archive: {archive}")
    # User jobs and self-test scratch must never enter a distributable ZIP.
    unexpected = [p for p in (target / "data").rglob("*") if p.is_file()]
    if unexpected:
        raise RuntimeError("Distribution data directory is not empty")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(target.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                package.write(path, str(Path(target.name) / path.relative_to(target)))
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="RallyCut-Windows-x64")
    parser.add_argument("--upstream", type=Path, default=PROJECT / "outputs/upstream_rallyclip/RallyClip-main")
    parser.add_argument("--ffmpeg-bin", type=Path)
    parser.add_argument("--vc-redist", type=Path)
    parser.add_argument("--no-zip", action="store_true")
    parser.add_argument("--gpu-dependencies", type=Path,
                        help="Isolated directory containing pinned GPU wheels; replaces CPU ORT")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8 or os.name != "nt":
        raise RuntimeError("Build using Windows x64 CPython 3.12")
    if Path(args.name).name != args.name or not args.name or args.name in {".", ".."}:
        parser.error("--name must be a plain directory name")
    destination = inside(PROJECT / "dist" / args.name, PROJECT / "dist")
    if destination.exists():
        raise FileExistsError(f"Choose a new --name; distribution already exists: {destination}")
    for file in MODEL_FILES:
        if not (args.upstream / "models/rallyclip_v0.5.0" / file).is_file():
            raise FileNotFoundError(f"Missing upstream artifact: {file}")
    archive = python_archive(PROJECT / "outputs/portable_build/cache")
    ffmpeg = args.ffmpeg_bin or find_ffmpeg()
    vc_redist = args.vc_redist or find_vc_redist()
    destination.mkdir(parents=True)
    print(f"Building {destination}", flush=True)
    extract_python(archive, destination / "runtime/python")
    packages = copy_distributions(destination / "runtime/site-packages", args.gpu_dependencies)
    binary_info = copy_runtime_binaries(ffmpeg, vc_redist, destination)
    copy_code_tree(PROJECT / "src", destination / "src")
    copy_file(PROJECT / "pyproject.toml", destination / "pyproject.toml")
    copy_file(PROJECT / "requirements-gpu.txt", destination / "requirements-gpu.txt")
    for file in TOOLS:
        copy_file(PROJECT / "tools" / file, destination / "tools" / file)
    copy_code_tree(args.upstream / "src", destination / "vendor/RallyClip/src")
    copy_upstream_resources(args.upstream, destination / "vendor/RallyClip")
    for file in MODEL_FILES:
        copy_file(args.upstream / "models/rallyclip_v0.5.0" / file,
                  destination / "vendor/RallyClip/models/rallyclip_v0.5.0" / file)
    for file in ("README.md", "pyproject.toml"):
        copy_file(args.upstream / file, destination / "vendor/RallyClip" / file)
    for file in args.upstream.glob("*"):
        if file.is_file() and any(word in file.name.upper() for word in ("LICENSE", "NOTICE", "COPYING")):
            copy_file(file, destination / "vendor/RallyClip" / file.name)
    for file in (PROJECT / "packaging").iterdir():
        if file.is_file() and file.suffix.lower() in {".cmd", ".txt", ".md"}:
            copy_file(file, destination / file.name)
            copy_file(file, destination / "packaging" / file.name)
    if (PROJECT / "docs/PORTABLE_APP.md").is_file():
        copy_file(PROJECT / "docs/PORTABLE_APP.md", destination / "docs/PORTABLE_APP.md")
    for folder in ("jobs", "logs", "temp", "cache"):
        (destination / "data" / folder).mkdir(parents=True, exist_ok=True)
    check = self_check(destination)
    print(json.dumps(check), flush=True)
    write_manifest(destination, {
        "schema_version": 1, "platform": "windows-x64", "application": "RallyCut",
        "python_source": PYTHON_URL, "python_archive_sha256": digest(archive),
        "upstream": "https://github.com/iroblesrazzaq/RallyClip",
        "artifact": "rallyclip_v0.5.0", "dependencies": packages,
        "binaries": binary_info, "isolated_runtime_check": check,
    })
    if not args.no_zip:
        output = archive_distribution(destination)
        print(json.dumps({"zip": str(output), "bytes": output.stat().st_size, "sha256": digest(output)}), flush=True)


if __name__ == "__main__":
    main()
