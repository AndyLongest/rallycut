"""Distribution boundaries are important: never ship development data by accident."""

import importlib.util
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location(
    "build_portable", Path(__file__).resolve().parents[1] / "tools/build_portable.py"
)
portable = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portable)


def test_code_copy_excludes_private_and_generated_files(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    for name in ("app.py", "web/index.html", ".env.private.json", "sample.mp4",
                 "__pycache__/secret.py", ".git/config.json", "node_modules/p.js"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test")
    portable.copy_code_tree(source, target)
    assert sorted(str(p.relative_to(target)).replace("\\", "/")
                  for p in target.rglob("*") if p.is_file()) == ["app.py", "web/index.html"]


def test_python_extract_rejects_traversal(tmp_path):
    package = tmp_path / "python.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("../outside.txt", "bad")
    with pytest.raises(ValueError):
        portable.extract_python(package, tmp_path / "runtime")
    assert not (tmp_path / "outside.txt").exists()


def test_archive_refuses_user_job_data(tmp_path):
    target = tmp_path / "RallyCut"
    data = target / "data/jobs"
    data.mkdir(parents=True)
    (data / "private-video.mp4").write_bytes(b"video")
    with pytest.raises(RuntimeError, match="not empty"):
        portable.archive_distribution(target)
    assert not target.with_suffix(".zip").exists()


def test_runtime_path_configuration_does_not_use_system_packages(tmp_path):
    package = tmp_path / "python.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("python312._pth", "bad\nimport site\n")
    target = tmp_path / "runtime/python"
    portable.extract_python(package, target)
    paths = (target / "python312._pth").read_text()
    assert "import site" not in paths
    assert "../../src" in paths and "../site-packages" in paths


def test_required_inference_resource_is_copied_and_missing_is_fatal(tmp_path):
    source, target = tmp_path / "upstream", tmp_path / "vendor"
    path = source / "src/preprocessing/default_court_mask.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"required mask")
    portable.copy_upstream_resources(source, target)
    assert (target / path.relative_to(source)).read_bytes() == b"required mask"
    path.unlink()
    with pytest.raises(FileNotFoundError):
        portable.copy_upstream_resources(source, target)


def test_distribution_copy_keeps_runtime_and_license_but_not_wheel_cache(tmp_path, monkeypatch):
    source, target = tmp_path / "installed", tmp_path / "packaged"
    filenames = ["library/core.py", "library/lib.dll", "library.dist-info/LICENSE",
                 "cached.whl", "library/__pycache__/core.pyc", "../../Scripts/tool.exe"]
    for name in filenames[:-1]:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")

    class Distribution:
        version = "1.0"
        files = filenames

        def locate_file(self, name):
            return source / name

    monkeypatch.setattr(portable, "DISTRIBUTIONS", ("fixture",))
    monkeypatch.setattr(portable.importlib.metadata, "distribution", lambda name: Distribution())
    portable.copy_distributions(target)
    assert (target / "library/lib.dll").is_file()
    assert (target / "library.dist-info/LICENSE").is_file()
    assert not (target / "cached.whl").exists()
    assert not (target / "library/__pycache__").exists()
