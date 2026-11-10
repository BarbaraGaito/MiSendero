"""Bounded retrieval of public walking SPE/HR tables; no training approval.

Only original metadata and explicitly requested data filenames are fetched.
No downloaded code is executed, no scale is converted, no cells interpolated.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fetch_fatigue_extra import download
from public_sources import ROOT, digest

DATASET = "mn3xyg2gh6"
DIRECTORY = ROOT/"training/data/raw/fatigue-research/walking-spe-v1"
PAGE = f"https://data.mendeley.com/datasets/{DATASET}/1"


def metadata_file(name, url):
    path = DIRECTORY/name
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "MiSendero public walking data eligibility audit",
            "Accept": "application/vnd.mendeley-public-dataset.1+json" if name.endswith(".json") else "text/html"})
        with urllib.request.urlopen(request, timeout=40) as response:
            payload = response.read(2_000_001)
            if not response.url.startswith("https://"):
                raise ValueError("Public metadata left HTTPS")
        if len(payload) > 2_000_000:
            raise ValueError("Public metadata exceeds 2 MB bound")
        if name.endswith(".json"):
            json.loads(payload)
        path.write_bytes(payload)
    return {"path": name, "url": url, "bytes": path.stat().st_size, "sha256": digest(path)}


def inventory():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    entries = [metadata_file("page.html", PAGE),
               metadata_file("folders.json", f"https://data.mendeley.com/public-api/datasets/{DATASET}/folders/1")]
    html = (DIRECTORY/"page.html").read_text(encoding="utf-8")
    state, _ = json.JSONDecoder().raw_decode(html.split("window.INITIAL_STATE = ", 1)[1])
    source = state["dataset"]["snapshot"]
    if source["version"] != 1 or source["is_confidential"] or source["licence"]["short_name"] != "CC BY 4.0":
        raise ValueError("Expected public original version1 under CC BY4.0")
    folders = json.loads((DIRECTORY/"folders.json").read_text())
    if not isinstance(folders, list) or len(folders) > 20:
        raise ValueError("Inspect an unexpected source folder tree")
    listed = []
    for folder in [{"id": "root", "name": "root"}]+folders:
        folder_id = folder["id"]
        if not re.fullmatch(r"[A-Za-z0-9-]+", folder_id):
            raise ValueError("Unexpected public folder identifier")
        url = f"https://data.mendeley.com/public-api/datasets/{DATASET}/files?"+urllib.parse.urlencode(
            {"folder_id": folder_id, "version": 1, "$start": 0, "$limit": 1000})
        entry = metadata_file(f"files-{folder_id}.json", url)
        entries.append(entry)
        values = json.loads((DIRECTORY/entry["path"]).read_text())
        if not isinstance(values, list) or len(values) > 300:
            raise ValueError("Unexpected walking source file count")
        for item in values:
            details = item["content_details"]
            listed.append({"id": item["id"], "filename": item["filename"], "folder_id": folder_id,
                           "folder_name": folder["name"], "content_details": details})
    if len({row["id"] for row in listed}) != len(listed):
        raise ValueError("Source file listing contains duplicate identities")
    result = {"version": 1, "source": PAGE, "doi": source["doi"], "title": source["name"],
              "license": source["licence"], "metadata": entries, "files": listed,
              "metadata_only": True, "used_for_training": False, "code_sha256": digest(Path(__file__)),
              "policy": "Original public data only, explicit table files only. Metadata description is evidence about acquisition, not approval to equate SPE with native Borg or to invent participant IDs, report times or questionnaires."}
    path = DIRECTORY/"inventory.json"
    if path.exists() and json.loads(path.read_text()) != result:
        raise ValueError("Preserve frozen source inventory before accepting changed metadata")
    path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"doi": result["doi"], "title": result["title"], "license": result["license"],
        "folders": folders, "files": [{"filename": row["filename"], "bytes": row["content_details"]["size"], "folder": row["folder_name"]} for row in listed]}, indent=2), flush=True)
    return result


def fetch_names(names):
    record = inventory()
    files = []
    for name in names:
        matches = [row for row in record["files"] if row["filename"] == name]
        if len(matches) != 1 or Path(name).name != name or "/" in name or "\\" in name or not name.lower().endswith((".txt", ".csv", ".md", ".pdf")):
            raise ValueError("Explicit unambiguous original data/document filename required")
        entry = matches[0]
        content = entry["content_details"]
        if not 0 < content["size"] <= 1_000_000 or not re.fullmatch(r"[0-9a-f]{64}", content["sha256_hash"]):
            raise ValueError("Data file exceeds 1 MB bound or lacks publisher SHA256")
        if not content["download_url"].startswith(f"https://data.mendeley.com/public-files/datasets/{DATASET}/"):
            raise ValueError("Download URL is outside the inspected public dataset")
        path = download(content["download_url"], DIRECTORY/"files"/name, maximum_bytes=content["size"],
            expected_bytes=content["size"], sha256=content["sha256_hash"])
        if path.stat().st_size != content["size"] or digest(path) != content["sha256_hash"]:
            raise ValueError("Original table bytes/checksum changed")
        files.append({"filename": name, "source_file_id": entry["id"], "url": content["download_url"], "bytes": content["size"],
                      "published_sha256": content["sha256_hash"], "sha256": digest(path)})
        print(f"Verified public walking data file {name}: {content['size']} bytes", flush=True)
    result = {"version": 1, "retrieved_at": datetime.now(timezone.utc).isoformat(), "inventory_sha256": digest(DIRECTORY/"inventory.json"),
              "code_sha256": digest(Path(__file__)), "files": files, "publisher_hashes_verified": True,
              "used_for_training": False, "native_target_merge_approved": False, "synthetic_rows_permitted": False}
    path = DIRECTORY/"files-receipt.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old[key] != result[key] for key in result if key != "retrieved_at"):
            raise ValueError("Preserve frozen table receipt before fetching a changed file set")
    else:
        path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--names", nargs="+")
    args = parser.parse_args()
    fetch_names(args.names) if args.names else inventory()
