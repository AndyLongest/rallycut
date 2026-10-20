"""Enable an independently installed GPU runtime without replacing the CPU one."""

from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import sys


def gpu_directory(root: Path) -> Path:
    return root / "runtime" / "gpu-site-packages"


def select_gpu_directory(root: Path) -> Path | None:
    directory = gpu_directory(root)
    if os.environ.get("RALLYCUT_DEVICE") == "cpu":
        return None
    if (directory / "rallycut-ready.json").is_file():
        return directory
    return None


def verify_install(root: Path):
    directory = gpu_directory(root).resolve()
    requested = {}
    for line in (root / "requirements-gpu.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            name, version = line.strip().split("==")
            requested[name] = version
    found = {d.metadata["Name"].lower().replace("_", "-"): d
             for d in importlib.metadata.distributions(path=[str(directory)])}
    if "onnxruntime" in found:
        raise RuntimeError("GPU 目录中存在冲突的 CPU onnxruntime，请使用独立的空目录安装。")
    for name, version in requested.items():
        if name not in found or found[name].version != version:
            raise RuntimeError(f"GPU 依赖缺失或版本不符：{name}=={version}")
        for item in found[name].files or ():
            relative = Path(str(item))
            if ".." in relative.parts or relative.suffix == ".pyc":
                continue
            path = (directory / relative).resolve()
            path.relative_to(directory)
            if not path.is_file():
                raise RuntimeError(f"GPU 依赖安装不完整：{relative}")
    return directory, requested


def main():
    root = Path(__file__).resolve().parents[2]
    directory = gpu_directory(root)
    marker = directory / "rallycut-ready.json"
    # Revalidation never leaves an old success marker after a failed install.
    marker.unlink(missing_ok=True)
    directory, versions = verify_install(root)
    sys.path.insert(0, str(directory))
    import onnxruntime as ort
    from rallycut.local_worker import find_assets

    _, artifact, _ = find_assets(root)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    # This also proves that the optional GPU wheel still supports CPU fallback.
    ort.InferenceSession(str(artifact / "model.onnx"), sess_options=options,
                         providers=["CPUExecutionProvider"])
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("所安装的 ONNX Runtime 不支持 CUDA。")
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps({"versions": versions}), encoding="utf-8")
    temporary.replace(marker)
    print("GPU 依赖已启用。重新双击 Start.cmd；显卡或驱动不可用时仍自动使用 CPU。")


if __name__ == "__main__":
    main()
