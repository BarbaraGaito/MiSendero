"""Download a bounded public Borg dataset snapshot; never run downloaded code."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from public_sources import RAW, ROOT, digest

DESTINATION = ROOT / "training/data/raw/fatigue-research/worker-fatigue"
ARCHIVE_SHA256 = "5e542bae625f8e5d0a7d47f072c94059dc20d5ec9c177b8b13a773dd86590940"
ARCHIVE_BYTES = 105438964


def extract_sensor_csvs(archive):
    """Extract a whitelist of data members, excluding scripts and path escapes."""
    cache = DESTINATION / "processed"
    cache.mkdir(exist_ok=True)
    listing = subprocess.check_output(["tar", "-tf", str(archive)], text=True).splitlines()
    pattern = r"MxD_Data_User_Study/(?:composite|ziptie)/P\d+[CZ]\d+S\d+/(?:Rep[1-5]|Initial_Rest|Final_Rest)_P\d+[CZ]\d+S\d+\.csv"
    members = [name for name in listing if re.fullmatch(pattern, name)]
    for name in members:
        target = (cache / name).resolve()
        if not target.is_relative_to(cache.resolve()) or target.is_symlink():
            raise ValueError("Archive member escapes the audited sensor-data directory")
    for i in range(0, len(members), 40):
        batch = [name for name in members[i:i+40] if not (cache / name).exists()]
        if batch:
            subprocess.run(["tar", "-xf", str(archive), "-C", str(cache), "--", *batch], check=True, capture_output=True)
    (DESTINATION / "processed-members.json").write_text(json.dumps(members, indent=2) + "\n", encoding="utf-8")
    return members


def download(url, destination, *, maximum_bytes, sha256=None, expected_bytes=None):
    if destination.exists() and (sha256 is None or digest(destination) == sha256):
        return destination
    request = urllib.request.Request(url, headers={"User-Agent": "MiSendero-Borg-research/1.0"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
        for block in iter(lambda: response.read(1024 * 1024), b""):
            size += len(block)
            if size > maximum_bytes:
                raise ValueError("Public download exceeds audited size bound")
            output.write(block)
    if expected_bytes is not None and size != expected_bytes:
        raise ValueError("Public download byte count differs from pinned source")
    if sha256 is not None and digest(temporary) != sha256:
        raise ValueError("Public download SHA-256 differs from pinned Git LFS object")
    temporary.replace(destination)
    return destination


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    source = json.loads((RAW / "12788571.json").read_text(encoding="utf-8"))
    if source["metadata"]["license"]["id"] != "cc-by-4.0":
        raise ValueError("Unexpected published license for source study")
    files = []
    for filename in ("README.md", "USER FORM RESPONSE.xlsx"):
        entry = next(row for row in source["files"] if row["key"] == filename)
        url = entry.get("links", {}).get("self") or f"https://zenodo.org/records/12788571/files/{urllib.parse.quote(filename)}?download=1"
        path = download(url, DESTINATION / filename, maximum_bytes=1000000)
        algorithm, expected = entry["checksum"].split(":", 1)
        if digest(path, algorithm) != expected:
            raise ValueError("Original study file differs from published checksum")
        files.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size,
                      "url": url, "published_checksum": entry["checksum"]})
        print(f"Verified original study file: {filename}", flush=True)
    url = "https://media.githubusercontent.com/media/payalmohapatra/WorkerFatigue/main/Predictive_Models/MxD_Data_User_Study.rar"
    path = download(url, DESTINATION / "MxD_Data_User_Study.rar", maximum_bytes=ARCHIVE_BYTES,
                    expected_bytes=ARCHIVE_BYTES, sha256=ARCHIVE_SHA256)
    files.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size,
                  "url": url, "github_lfs_pointer_blob_sha1": "8607ab329eea231c39bbd75427ddea7ab916b8aa"})
    lock = {"source": "Wearable network for multilevel physical fatigue prediction in manufacturing workers",
            "study": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11474982/", "doi": "10.5281/zenodo.12788571",
            "license": "CC-BY-4.0 (original deposited dataset)",
            "repository": "https://github.com/payalmohapatra/WorkerFatigue",
            "status": "downloaded_for_audit_not_yet_approved_for_combining",
            "synthetic_rows_permitted": False, "interpolated_targets_permitted": False, "files": files}
    (DESTINATION / "download-receipt.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(f"Verified processed sensor archive: {path.stat().st_size} bytes", flush=True)
    print(f"Extracted {len(extract_sensor_csvs(path))} whitelisted sensor CSV members", flush=True)


if __name__ == "__main__":
    main()
