"""Verify a release ZIP without extracting or executing it."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--sha256", required=True, help="Expected hash from trusted release notes")
    args = parser.parse_args()
    with args.archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest.lower() != args.sha256.lower():
        raise ValueError("Release SHA-256 mismatch")
    with zipfile.ZipFile(args.archive) as archive:
        if archive.testzip():
            raise ValueError("ZIP CRC failed")
        names = archive.namelist()
        manifest_name, = [n for n in names if n.endswith("/distribution-manifest.json")]
        prefix = manifest_name.removesuffix("distribution-manifest.json")
        if any(n.startswith(prefix + "data/") and not n.endswith("/") for n in names):
            raise ValueError("Release contains populated application data")
        manifest = json.loads(archive.read(manifest_name))
        for item in manifest["files"]:
            content = archive.read(prefix + item["path"])
            if len(content) != item["size"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ValueError(f"Manifest mismatch: {item['path']}")
    print(json.dumps({"archive": args.archive.name, "sha256": digest,
                      "bytes": args.archive.stat().st_size, "crc": "passed",
                      "verified_files": len(manifest["files"]), "no_job_data": True}))


if __name__ == "__main__":
    main()
