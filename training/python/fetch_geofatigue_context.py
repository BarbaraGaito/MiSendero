"""Download only checksummed public GeoFatigue phone CSVs and demographics.

The native cohort/targets are never changed. No images, point clouds, software
or executable content is fetched. Metadata is already pinned locally. Default
mode probes one phone file; --all downloads the bounded whitelist (about 3 GB).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import shutil
import urllib.request
from datetime import datetime, timezone

from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/geofatigue-context-v1"
METADATA_PATH = ROOT / "training/data/raw/fatigue-research/public-candidates-80-v1/geofatigue-current.json"


def download(entry):
    data = entry["dataFile"]
    name = data.get("originalFileName", data["filename"])
    path = DIRECTORY / name
    expected_size = data.get("originalFileSize", data["filesize"])
    checksum = data["checksum"]
    if entry.get("restricted") or expected_size > 40_000_000 or checksum["type"] != "MD5":
        raise ValueError("Source is restricted, too large or lacks the expected publisher checksum")
    url = f"https://borealisdata.ca/api/access/datafile/{data['id']}?format=original"
    try:
        if not path.exists():
            # A download that fails validation is retained only as .part and
            # cannot become a source file for preparation/training.
            temporary = path.with_suffix(path.suffix + ".part")
            size, md5, sha256 = 0, hashlib.md5(), hashlib.sha256()
            if temporary.exists():
                with temporary.open("rb") as previous:
                    for block in iter(lambda: previous.read(1024 * 1024), b""):
                        size += len(block)
                        md5.update(block)
                        sha256.update(block)
                if size > expected_size:
                    raise ValueError("Partial download exceeds publisher size; preserve for audit")
            # The server supports authenticated-free HTTP byte ranges. The
            # unbounded full response was very slow despite a successful
            # probe; bounded 4 MB requests make progress observable and verify
            # every returned range before accepting the publisher checksum.
            with temporary.open("ab" if size else "wb") as output:
                for offset in range(size, expected_size, 4 * 1024 * 1024):
                    end = min(offset + 4 * 1024 * 1024, expected_size) - 1
                    request = urllib.request.Request(url, headers={"User-Agent": "MiSendero-Borg-research/1.0", "Range": f"bytes={offset}-{end}"})
                    received = 0
                    with urllib.request.urlopen(request, timeout=45) as response:
                        if not response.url.startswith("https://") or response.status != 206:
                            raise ValueError("Expected a public HTTPS partial-content response")
                        if response.headers.get("Content-Range") != f"bytes {offset}-{end}/{expected_size}":
                            raise ValueError("Server returned a different byte range")
                        for block in iter(lambda: response.read(65536), b""):
                            received += len(block)
                            size += len(block)
                            if received > end - offset + 1 or size > expected_size:
                                raise ValueError("Public download exceeded its pinned byte range")
                            output.write(block)
                            md5.update(block)
                            sha256.update(block)
                    if received != end - offset + 1:
                        raise ValueError("Public byte-range response was incomplete")
                    output.flush()
            if size != expected_size or md5.hexdigest() != checksum["value"]:
                raise ValueError(f"Publisher checksum/size mismatch for {name}: bytes={size}, md5={md5.hexdigest()}")
            # The final filename is new: it never replaces any frozen source.
            temporary.rename(path)
        if path.stat().st_size != expected_size or digest(path, "md5") != checksum["value"]:
            raise ValueError("Cached public source changed after download")
        return {"filename": name, "id": data["id"], "url": url, "bytes": path.stat().st_size,
                "published_md5": checksum["value"], "sha256": digest(path), "status": "verified"}
    except Exception as error:
        return {"filename": name, "id": data["id"], "url": url, "status": "failed", "error": f"{type(error).__name__}: {error}"}


def main(all_files=False, workers=6):
    if not 1 <= workers <= 8:
        raise ValueError("Public download concurrency must remain between 1 and 8")
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    version = metadata["data"]["latestVersion"]
    allowed = []
    for entry in version["files"]:
        name = entry["dataFile"]["filename"]
        if name == "demographics.tab" or (entry.get("directoryLabel") == "Contextual Data/Contextual Sensing Data"
                and re.fullmatch(r"p\d+-(?:flat_ground|ground|ramp|stairs|staris)(?:-\d+)?\.tab", name)):
            allowed.append(entry)
    if not all_files:
        allowed = [entry for entry in allowed if entry["dataFile"]["filename"] in ("demographics.tab", "p0-flat_ground.tab")]
    if not allowed or len(allowed) > 150:
        raise ValueError("Unexpected official context-file inventory")
    total = sum(e["dataFile"].get("originalFileSize", e["dataFile"]["filesize"]) for e in allowed)
    if total > 3_500_000_000:
        raise ValueError("Public source whitelist exceeds the 3.5 GB bound")
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    pending = sum(e["dataFile"].get("originalFileSize", e["dataFile"]["filesize"]) for e in allowed
                  if not (DIRECTORY / e["dataFile"].get("originalFileName", e["dataFile"]["filename"])).exists())
    if shutil.disk_usage(DIRECTORY).free < pending + 300_000_000:
        raise ValueError("Insufficient free space for the bounded public CSV download")
    # Independent downloads keep resource use bounded and print progress
    # as each file completes. The receipt is updated without deleting files.
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(download, entry) for entry in allowed]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            records.append(result)
            receipt = {"downloaded_at": datetime.now(timezone.utc).isoformat(), "metadata_sha256": digest(METADATA_PATH),
                       "doi": "10.5683/SP3/I0KSNR", "version": [version["versionNumber"], version["versionMinorNumber"]],
                       "official_license": version.get("license"), "mode": "all" if all_files else "probe",
                       "expected_files": len(allowed), "source_bytes_bound": total,
                       "maximum_parallel_downloads": workers,
                       "all_complete_and_verified": len(records) == len(allowed) and all(r["status"] == "verified" for r in records),
                       "training_merge_approved": False, "files": sorted(records, key=lambda r: r["filename"])}
            (DIRECTORY / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            print(f"{len(records)}/{len(allowed)} {result['filename']}: {result['status']} {result.get('error', '')}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    main(args.all, args.workers)
