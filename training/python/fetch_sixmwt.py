"""Retrieve one pinned CC BY walking archive for eligibility inspection."""
import json
import zipfile
from datetime import datetime, timezone

from fetch_fatigue_extra import download
from fetch_gait_candidates import DIRECTORY as METADATA_DIRECTORY
from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/sixmwt-v1"
METADATA = METADATA_DIRECTORY / "sixmwt-article-29665850.json"


def fetch():
    source = json.loads(METADATA.read_text(encoding="utf-8"))
    if source["license"]["name"] != "CC BY 4.0" or source.get("is_embargoed", False):
        raise ValueError("Inspected walking dataset must remain open CC BY 4.0")
    entry = next(f for f in source["files"] if f["id"] == 59322830)
    if entry["size"] != 148390237 or entry["computed_md5"] != "a23fb3753fc33648624725c33ec9d57e":
        raise ValueError("Walking source differs from inspected official checksum/size")
    DIRECTORY.mkdir(exist_ok=True)
    path = download(entry["download_url"], DIRECTORY / "6MWT_IMU_Dataset.zip",
                    maximum_bytes=entry["size"], expected_bytes=entry["size"])
    if path.stat().st_size != entry["size"] or digest(path, "md5") != entry["computed_md5"]:
        raise ValueError("Cached or downloaded walking archive differs from its publisher")
    with zipfile.ZipFile(path) as archive:
        members = [{"name": i.filename, "bytes": i.file_size, "compressed_bytes": i.compress_size} for i in archive.infolist()]
    receipt = {"version": 1, "retrieved_at": datetime.now(timezone.utc).isoformat(), "url": entry["download_url"],
               "doi": source["doi"], "metadata_sha256": digest(METADATA), "published_md5": entry["computed_md5"],
               "sha256": digest(path), "bytes": path.stat().st_size, "license": source["license"], "members": members,
               "used_for_training": False, "training_merge_approved": False, "downloaded_code_executed": False}
    (DIRECTORY / "receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    print(f"Verified six-minute walking archive: {path.stat().st_size} bytes / {len(members)} ZIP members; no training merge", flush=True)
    print(json.dumps(members[:18], indent=2), flush=True)


if __name__ == "__main__":
    fetch()
