"""Retrieve the explicitly inspected original walking data archive only."""
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import fetch_walking_spe as metadata
from fetch_fatigue_extra import download
from public_sources import digest


def fetch():
    directory = metadata.DIRECTORY
    inventory_path = directory/"inventory.json"
    inventory = json.loads(inventory_path.read_text())
    assert inventory["code_sha256"] == digest(Path(metadata.__file__))
    for entry in inventory["metadata"]:
        assert digest(directory/entry["path"]) == entry["sha256"]
    if len(inventory["files"]) != 1 or inventory["files"][0]["filename"] != "All_data.zip":
        raise ValueError("Public source archive differs from inspected inventory")
    source = inventory["files"][0]["content_details"]
    if not 0 < source["size"] <= 10_000_000 or not source["download_url"].startswith("https://data.mendeley.com/public-files/datasets/mn3xyg2gh6/"):
        raise ValueError("Archive exceeds bounded original download scope")
    path = download(source["download_url"], directory/"All_data.zip", maximum_bytes=source["size"],
                    expected_bytes=source["size"], sha256=source["sha256_hash"])
    if digest(path) != source["sha256_hash"] or path.stat().st_size != source["size"]:
        raise ValueError("Downloaded archive differs from publisher size/hash")
    with zipfile.ZipFile(path) as archive:
        members = [{"name": item.filename, "bytes": item.file_size, "compressed_bytes": item.compress_size} for item in archive.infolist()]
        if sum(item["bytes"] for item in members) > 50_000_000:
            raise ValueError("Inspect unexpectedly large expanded tables before reading")
    receipt = {"version": 1, "source": metadata.PAGE, "doi": inventory["doi"], "license": inventory["license"],
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "code_sha256": digest(Path(__file__)),
        "inventory_sha256": digest(inventory_path), "url": source["download_url"], "bytes": source["size"],
        "published_sha256": source["sha256_hash"], "sha256": digest(path), "members": members,
        "used_for_training": False, "native_target_merge_approved": False, "downloaded_code_executed": False}
    destination = directory/"archive-receipt.json"
    if destination.exists():
        previous = json.loads(destination.read_text())
        if any(previous[key] != receipt[key] for key in receipt if key != "retrieved_at"):
            raise ValueError("Preserve frozen archive receipt before accepting changed data")
    else:
        destination.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2), flush=True)
    return receipt


if __name__ == "__main__":
    fetch()
