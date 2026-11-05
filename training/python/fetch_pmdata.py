"""Bounded public OSF discovery and SHA-pinned PMData downloads.

Default fetches only metadata. --probe downloads p01 exertion/HR documents;
--all downloads the same whitelist for the public cohort, never food images.
The original publisher hashes and versions are required for every data file.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fetch_fatigue_extra import download
from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/pmdata-v1"
ROOT_URL = "https://api.osf.io/v2/nodes/vx4bk/files/osfstorage/"


def metadata(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "api.osf.io":
        raise ValueError("Only official public OSF metadata is in scope")
    cache = DIRECTORY / "metadata"
    cache.mkdir(parents=True, exist_ok=True)
    import hashlib
    path = cache / (hashlib.sha256(url.encode()).hexdigest()[:20] + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    request = urllib.request.Request(url, headers={"User-Agent": "MiSendero-Borg-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Public metadata exceeds the audited 2 MB bound")
    result = json.loads(raw)
    path.write_bytes(raw)
    return result


def entries(folder_url):
    result = []
    url = folder_url + ("&" if "?" in folder_url else "?") + "page[size]=100"
    pages = 0
    while url:
        page = metadata(url)
        result.extend(page["data"])
        url = page["links"]["next"]
        pages += 1
        if pages > 5:
            raise ValueError("Unexpectedly large public folder")
    return result


def folder_url(entry):
    return entry["relationships"]["files"]["links"]["related"]["href"]


def discover():
    roots = entries(ROOT_URL)
    pmdata = next(e for e in roots if e["attributes"]["name"] == "pmdata" and e["attributes"]["kind"] == "folder")
    first = entries(folder_url(pmdata))
    people = [e for e in first if e["attributes"]["kind"] == "folder" and re.fullmatch(r"p\d{2}", e["attributes"]["name"])]
    if not 10 <= len(people) <= 20:
        raise ValueError("Public PMData cohort size differs from inspected study")
    found = [e for e in roots + first if e["attributes"]["kind"] == "file"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        person_contents = list(pool.map(lambda e: entries(folder_url(e)), people))
        allowed = [e for contents in person_contents for e in contents
                   if e["attributes"]["kind"] == "folder" and e["attributes"]["name"] in ("pmsys", "fitbit")]
        found.extend(e for contents in person_contents for e in contents if e["attributes"]["kind"] == "file")
        source_contents = list(pool.map(lambda e: entries(folder_url(e)), allowed))
    found.extend(e for contents in source_contents for e in contents if e["attributes"]["kind"] == "file")
    selected = []
    for entry in found:
        a = entry["attributes"]
        path = a["materialized_path"]
        if (re.fullmatch(r"/pmdata/p\d{2}/(?:pmsys/(?:srpe|srpe_info)\.(?:csv|txt)|fitbit/(?:heart_rate|exercise)\.(?:json|txt))", path)
                or path in ("/license.txt", "/pmdata/README.md", "/pmdata/README.txt", "/pmdata/participant-overview.csv")):
            hashes = a["extra"]["hashes"]
            if not hashes.get("sha256") or not hashes.get("md5") or not 0 < a["size"] < 200_000_000:
                raise ValueError("Missing official checksums or unexpected data-file size")
            selected.append({"path": path, "bytes": a["size"], "sha256": hashes["sha256"], "md5": hashes["md5"],
                             "version": a["current_version"], "osf_file_id": entry["id"], "url": entry["links"]["download"]})
    if not any(e["path"].endswith("/srpe.csv") for e in selected):
        raise ValueError("No original session exertion files in public metadata")
    report = {"source": "https://datasets.simula.no/pmdata/", "osf": "https://osf.io/vx4bk/", "participants_folders": len(people),
              "selected_files": sorted(selected, key=lambda e: e["path"]), "inventory_files_seen": len(found),
              "selected_bytes": sum(e["bytes"] for e in selected), "training_merge_approved": False}
    path = DIRECTORY / "inventory.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != report:
        raise ValueError("Preserve the previous PMData inventory before changing versions")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "selected_files"}), flush=True)
    for entry in report["selected_files"]:
        print(entry["path"], entry["bytes"], flush=True)
    return report


def fetch(mode):
    inventory_path = DIRECTORY / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8")) if inventory_path.exists() else discover()
    selected = [e for e in inventory["selected_files"] if mode in ("all", "annotations") or "/p01/" in e["path"] or not re.search(r"/p\d{2}/", e["path"])]
    if mode == "annotations":
        selected = [e for e in selected if not e["path"].endswith("/heart_rate.json")]
    if sum(e["bytes"] for e in selected) > 2_000_000_000:
        raise ValueError("Selected public downloads exceed the 2 GB scope bound")
    def one(entry):
        relative = Path(entry["path"].lstrip("/"))
        target = (DIRECTORY / "files" / relative).resolve()
        if not target.is_relative_to((DIRECTORY / "files").resolve()):
            raise ValueError("Source path escapes its dedicated download directory")
        for attempt in range(4):
            try:
                url = (entry["url"] if attempt % 2 == 0 else "https://files.osf.io/v1/resources/vx4bk/providers/osfstorage/"
                       + entry["osf_file_id"] + "?action=download&version=" + str(entry["version"]))
                path = download(url, target, maximum_bytes=entry["bytes"], expected_bytes=entry["bytes"], sha256=entry["sha256"])
                break
            except urllib.error.URLError as error:
                if attempt == 3 or (isinstance(error, urllib.error.HTTPError) and error.code < 500):
                    raise
                time.sleep(attempt + 1)
        if path.stat().st_size != entry["bytes"] or digest(path, "md5") != entry["md5"]:
            raise ValueError("PMData file differs from published OSF checksums")
        print("Verified", entry["path"], flush=True)
        return {**entry, "local_path": str(path.relative_to(DIRECTORY.resolve())).replace("\\", "/")}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(one, selected))
    receipt = {"inventory_sha256": digest(inventory_path), "mode": mode, "files": files,
               "complete_and_publisher_verified": True, "training_merge_approved": False}
    (DIRECTORY / (mode + "-receipt.json")).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"PMData {mode}: {len(files)} files verified; no training labels merged", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("metadata", "probe", "annotations", "all"), default="metadata")
    mode = parser.parse_args().mode
    discover() if mode == "metadata" else fetch(mode)
