import json
from types import SimpleNamespace

import pytest

from rallycut import optional_gpu


def test_unfinished_install_is_not_selected(tmp_path, monkeypatch):
    monkeypatch.delenv("RALLYCUT_DEVICE", raising=False)
    target = optional_gpu.gpu_directory(tmp_path)
    target.mkdir(parents=True)
    (target / "onnxruntime").mkdir()
    assert optional_gpu.select_gpu_directory(tmp_path) is None
    (target / "rallycut-ready.json").write_text(json.dumps({"versions": {}}))
    assert optional_gpu.select_gpu_directory(tmp_path) == target
    monkeypatch.setenv("RALLYCUT_DEVICE", "cpu")
    assert optional_gpu.select_gpu_directory(tmp_path) is None


def test_activation_refuses_missing_or_incomplete_dependencies(tmp_path, monkeypatch):
    (tmp_path / "requirements-gpu.txt").write_text("onnxruntime-gpu==1.22.0\n")
    target = optional_gpu.gpu_directory(tmp_path)
    target.mkdir(parents=True)
    monkeypatch.setattr(optional_gpu.importlib.metadata, "distributions", lambda **kw: [])
    with pytest.raises(RuntimeError, match="版本不符"):
        optional_gpu.verify_install(tmp_path)
    dist = SimpleNamespace(metadata={"Name": "onnxruntime-gpu"}, version="1.22.0",
                           files=["onnxruntime/capi/native.dll"])
    monkeypatch.setattr(optional_gpu.importlib.metadata, "distributions", lambda **kw: [dist])
    with pytest.raises(RuntimeError, match="不完整"):
        optional_gpu.verify_install(tmp_path)
    file = target / "onnxruntime/capi/native.dll"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"fixture")
    directory, versions = optional_gpu.verify_install(tmp_path)
    assert directory == target
    assert versions == {"onnxruntime-gpu": "1.22.0"}


def test_activation_refuses_cpu_gpu_mixed_install(tmp_path, monkeypatch):
    (tmp_path / "requirements-gpu.txt").write_text("onnxruntime-gpu==1.22.0\n")
    dist = SimpleNamespace(metadata={"Name": "onnxruntime"}, version="1.31.0", files=[])
    monkeypatch.setattr(optional_gpu.importlib.metadata, "distributions", lambda **kw: [dist])
    with pytest.raises(RuntimeError, match="冲突"):
        optional_gpu.verify_install(tmp_path)
