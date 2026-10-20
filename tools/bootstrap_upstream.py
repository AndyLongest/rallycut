"""Fetch and verify the exact upstream used for this handoff; standard library only."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(spec, cache):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (spec["sha256"] + ".zip")
    if not target.is_file():
        temporary = target.with_suffix(".download")
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "RallyCut-handoff"})
        with urllib.request.urlopen(request, timeout=120) as source, temporary.open("wb") as out:
            shutil.copyfileobj(source, out)
        if sha256(temporary) != spec["sha256"]:
            raise ValueError("Downloaded archive checksum mismatch; installation stopped")
        temporary.replace(target)
    if sha256(target) != spec["sha256"]:
        raise ValueError("Cached archive checksum mismatch; use a fresh cache directory")
    return target


def safe_extract(archive, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        # Validate every entry before writing any of them.
        for item in package.infolist():
            name = PurePosixPath(item.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or any(":" in p for p in name.parts):
                raise ValueError("Unsafe archive path")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive symlinks are not supported")
            (destination / str(name)).resolve().relative_to(destination)
        package.extractall(destination)


def verify(destination, lock):
    for relative, expected in lock["files"].items():
        path = destination / relative
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Upstream missing or changed: {relative}")
    return len(lock["files"])


def install(destination, cache, lock):
    if destination.exists():
        return verify(destination, lock)  # Never overwrite an existing checkout.
    source = fetch(lock["source"], cache)
    artifact = fetch(lock["artifact"], cache)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rallycut-bootstrap-", dir=destination.parent) as temp:
        temporary = Path(temp)
        safe_extract(source, temporary)
        extracted = temporary / ("RallyClip-" + lock["commit"])
        safe_extract(artifact, extracted / "models/rallyclip_v0.5.0")
        count = verify(extracted, lock)
        extracted.rename(destination)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path,
                        default=ROOT / "outputs/upstream_rallyclip/RallyClip-main")
    parser.add_argument("--cache", type=Path, default=ROOT / "outputs/bootstrap_cache")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    lock = json.loads((ROOT / "upstream-lock.json").read_text(encoding="utf-8"))
    destination = args.destination.resolve()
    count = verify(destination, lock) if args.verify_only else install(destination, args.cache, lock)
    print(json.dumps({"upstream": str(destination), "commit": lock["commit"],
                      "verified_files": count, "model": "rallyclip_v0.5.0"}))


if __name__ == "__main__":
    main()
