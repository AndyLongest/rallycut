"""Protect bootstrap extraction and existing assets from silent replacement."""
import importlib.util
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location(
    "bootstrap_upstream", Path(__file__).resolve().parents[1] / "tools/bootstrap_upstream.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/escape", "..\\escape"])
def test_rejects_unsafe_archive_before_writing(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("innocent.txt", "first")
        package.writestr(name, "bad")
    target = tmp_path / "target"
    with pytest.raises(ValueError):
        bootstrap.safe_extract(archive, target)
    assert not (target / "innocent.txt").exists()


def test_existing_assets_not_overwritten_or_redownloaded(tmp_path, monkeypatch):
    destination = tmp_path / "upstream"
    destination.mkdir()
    asset = destination / "model.onnx"
    asset.write_bytes(b"original")
    lock = {"files": {"model.onnx": bootstrap.sha256(asset)}}
    monkeypatch.setattr(bootstrap, "fetch", lambda *_: pytest.fail("No download allowed"))
    assert bootstrap.install(destination, tmp_path / "cache", lock) == 1
    asset.write_bytes(b"modified")
    with pytest.raises(ValueError, match="changed"):
        bootstrap.install(destination, tmp_path / "cache", lock)
    assert asset.read_bytes() == b"modified"
