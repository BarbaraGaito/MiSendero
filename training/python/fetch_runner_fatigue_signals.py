"""Fetch only predeclared fitting-person F/NF traces, checking Zenodo MD5s."""
from __future__ import annotations

import json
import re
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fetch_runner_fatigue_metadata import DIRECTORY
from public_sources import digest

FILES = DIRECTORY / "files"


def fetch_one(record):
    name, size = record["filename"], record["bytes"]
    if not re.fullmatch(r"\d{3}_(F|NF)\.csv", name) or not record["url"].startswith("https://zenodo.org/api/records/11114096/files/"):
        raise ValueError("Unexpected fitting waveform filename or public URL")
    path = FILES / name
    probe = DIRECTORY / "schema-probe" / name
    expected = record["published_checksum"].removeprefix("md5:")
    if not path.exists() and probe.exists():
        if probe.stat().st_size != size or digest(probe, "md5") != expected:
            raise ValueError("Original schema probe no longer matches the publisher")
        shutil.copyfile(probe, path)
    if not path.exists():
        part = path.with_suffix(".csv.part")
        last_error = None
        for attempt in range(3):
            try:
                have = part.stat().st_size if part.exists() else 0
                if have > size:
                    raise ValueError("Unexpected oversized partial waveform")
                if have < size:
                    headers = {"User-Agent": "MiSendero public fitting signal research"}
                    if have:
                        headers["Range"] = f"bytes={have}-"
                    request = urllib.request.Request(record["url"], headers=headers)
                    with urllib.request.urlopen(request, timeout=40) as response:
                        if have and response.status != 206:
                            have = 0
                        with part.open("ab" if have else "wb") as output:
                            while block := response.read(131072):
                                if have+len(block) > size:
                                    raise ValueError("Server returned more than the published waveform size")
                                output.write(block)
                                have += len(block)
                if part.stat().st_size != size or digest(part, "md5") != expected:
                    raise ValueError("Downloaded waveform length or publisher MD5 mismatch")
                part.replace(path)
                break
            except Exception as error:
                last_error = error
        if not path.exists():
            raise RuntimeError(f"Incomplete public waveform {name}: {last_error}")
    if path.stat().st_size != size or digest(path, "md5") != expected:
        raise ValueError("Previously verified waveform changed; preserve it for inspection")
    return {**record, "path": name, "sha256": digest(path), "publisher_md5_verified": True}


def download():
    inventory_path = DIRECTORY / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    records = [r for r in inventory["files"] if r["participant"] in inventory["fit_participants"]
               and r["protocol_segment"] in ("F", "NF")]
    if len(records) != 30 or sum(r["bytes"] for r in records) != 238626573:
        raise ValueError("The inspected 15-person fitting signal inventory changed")
    if set(r["participant"] for r in records) & set(inventory["reserved_participants"]):
        raise ValueError("Reserved runners must not enter signal population fitting")
    FILES.mkdir(exist_ok=True)
    receipt = {"version": 1, "inventory_sha256": digest(inventory_path),
        "download_code_sha256": digest(Path(__file__)), "fitting_participants": inventory["fit_participants"],
        "reserved_participants": inventory["reserved_participants"], "expected_files": 30,
        "expected_bytes": 238626573, "files": [], "errors": [], "all_complete_and_verified": False,
        "reserved_waveforms_downloaded": False, "native_borg_supervision_rows": 0,
        "policy": "Only original fitting-person F/NF segments; protocol labels remain distinct from native Borg. No BeepTest or reserved-person waveform download."}
    path = DIRECTORY / "signals-receipt.json"
    if path.exists():
        previous = json.loads(path.read_text())
        if previous["inventory_sha256"] != receipt["inventory_sha256"] or previous["download_code_sha256"] != receipt["download_code_sha256"]:
            raise ValueError("Preserve the earlier download receipt before changing code or source")
    def save():
        receipt["files"].sort(key=lambda r: r["filename"])
        content = json.dumps(receipt, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
    save()
    with ThreadPoolExecutor(max_workers=3) as executor:
        pending = {executor.submit(fetch_one, r): r for r in records}
        for future in as_completed(pending):
            try:
                receipt["files"].append(future.result())
                print(f"Runner signals {len(receipt['files'])}/30 publisher-verified", flush=True)
            except Exception as error:
                receipt["errors"].append({"filename": pending[future]["filename"], "error": str(error)})
            save()
    receipt["all_complete_and_verified"] = len(receipt["files"]) == 30 and not receipt["errors"]
    save()
    if not receipt["all_complete_and_verified"]:
        raise RuntimeError("Inspect incomplete runner files before resuming the terminal downloader")
    print("All 30 fitting-only runner waveforms verified: 238626573 bytes; no new Borg labels", flush=True)
    return receipt


if __name__ == "__main__":
    download()
