"""Fetch the public original STS archive from its pinned Figshare version.

Downloads data only and lists archive members; never extracts/runs code. The
study's interpolated Borg labels are not approved as new ground truth.
"""
import hashlib
import json
import urllib.request
import zipfile
from datetime import datetime, timezone

from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/sit-to-stand-v1"
METADATA = ROOT / "training/data/raw/fatigue-research/public-candidates-80-v1/sit-to-stand-v1.json"


def main():
    source = json.loads(METADATA.read_text(encoding="utf-8"))
    if source["license"]["name"] != "CC BY 4.0" or source["is_embargoed"]:
        raise ValueError("Unexpected public source access/license")
    entry = next(f for f in source["files"] if f["name"] == "STS_data.zip")
    if entry["size"] != 174675613 or entry["computed_md5"] != "2f8a8fcb1b8e4fd1361ce938ead90d33":
        raise ValueError("Public archive differs from inspected original metadata")
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = DIRECTORY / "STS_data.zip"
    if not path.exists():
        temporary = DIRECTORY / "STS_data.zip.part"
        request = urllib.request.Request(entry["download_url"], headers={"User-Agent": "MiSendero-Borg-research/1.0"})
        size, md5 = 0, hashlib.md5()
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as output:
            if not response.url.startswith("https://"):
                raise ValueError("Archive redirected outside HTTPS")
            for block in iter(lambda: response.read(65536), b""):
                size += len(block)
                if size > entry["size"]:
                    raise ValueError("Archive exceeded pinned download size")
                output.write(block)
                md5.update(block)
        if size != entry["size"] or md5.hexdigest() != entry["computed_md5"]:
            raise ValueError("Archive does not match official checksum/size")
        temporary.rename(path)
    if path.stat().st_size != entry["size"] or digest(path, "md5") != entry["computed_md5"]:
        raise ValueError("Cached original STS archive changed")
    with zipfile.ZipFile(path) as archive:
        members = [{"name": i.filename, "bytes": i.file_size, "compressed_bytes": i.compress_size} for i in archive.infolist()]
    receipt = {"downloaded_at": datetime.now(timezone.utc).isoformat(), "metadata_sha256": digest(METADATA),
               "doi": source["doi"], "url": entry["download_url"], "bytes": path.stat().st_size,
               "published_md5": entry["computed_md5"], "sha256": digest(path), "license": source["license"],
               "training_merge_approved": False, "interpolated_targets_permitted": False, "members": members}
    (DIRECTORY / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Verified original STS archive: {path.stat().st_size} bytes, {len(members)} members; not yet approved for training", flush=True)
    print(json.dumps(members[:18], indent=2))


if __name__ == "__main__":
    main()
