#!/usr/bin/env python3
"""Download the public 2026 Global Fire Atlas ignition archive privately."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path

from environmental_sources import ROOT


URL = "https://zenodo.org/records/17669692/files/SHP_ignitions.zip"
EXPECTED_BYTES = 851_919_355
EXPECTED_MD5 = "f80b45adbfd8ee1737d2a16cee8bc7ea"
OUT_DIR = ROOT / "training/data/environmental/private/global-fire-atlas-2026-04"
ARCHIVE = OUT_DIR / "SHP_ignitions.zip"
MANIFEST = OUT_DIR / "download-manifest.json"


def digest_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not ARCHIVE.exists():
        partial = ARCHIVE.with_suffix(".zip.part")
        request = urllib.request.Request(
            URL,
            headers={"User-Agent": "MiSenderoResearch/1.0", "Accept": "application/octet-stream"},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response, partial.open("wb") as output:
                while True:
                    block = response.read(4 * 1024 * 1024)
                    if not block:
                        break
                    output.write(block)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        if partial.stat().st_size != EXPECTED_BYTES:
            partial.unlink(missing_ok=True)
            raise RuntimeError("Downloaded Global Fire Atlas archive has an unexpected size.")
        if digest_file(partial, "md5") != EXPECTED_MD5:
            partial.unlink(missing_ok=True)
            raise RuntimeError("Downloaded Global Fire Atlas archive failed the Zenodo MD5 check.")
        partial.replace(ARCHIVE)

    if ARCHIVE.stat().st_size != EXPECTED_BYTES or digest_file(ARCHIVE, "md5") != EXPECTED_MD5:
        raise RuntimeError("Local Global Fire Atlas archive failed its published size/MD5 check.")
    report = {
        "source": "Zenodo record 17669692, updated 2026-04-08",
        "url": URL,
        "archive": ARCHIVE.relative_to(ROOT).as_posix(),
        "bytes": ARCHIVE.stat().st_size,
        "md5": EXPECTED_MD5,
        "sha256": digest_file(ARCHIVE, "sha256"),
        "synthetic_observations": 0,
        "deployment_approved": False,
    }
    temporary = MANIFEST.with_suffix(".json.part")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, MANIFEST)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
