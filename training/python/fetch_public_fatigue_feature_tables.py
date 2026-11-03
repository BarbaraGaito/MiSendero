"""Fetch two original public feature tables, verifying publisher checksums."""
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from public_sources import ROOT, digest

DIRECTORY = ROOT/"training/data/raw/public_audit"
FILES = [("fourth-fatigue-v1", 15104079, "database.xlsx", 1202325),
         ("biceps-fatigue-v1", 24309619, "Dataset.txt", 1345359)]


def main():
    for name, article, filename, size in FILES:
        folder = DIRECTORY/name
        metadata_path = folder/f"article-{article}.json"
        metadata = json.loads(metadata_path.read_text())
        if metadata["id"] != article or metadata["is_embargoed"] or metadata["license"]["name"] != "CC BY 4.0":
            raise ValueError("Unexpected original public metadata, access or license")
        entry = next(f for f in metadata["files"] if f["name"] == filename)
        original_md5 = entry["computed_md5"]
        if entry["size"] != size or not re.fullmatch(r"[0-9a-f]{1,32}", original_md5):
            raise ValueError("Unexpected official feature table size/checksum")
        # Preserve the publisher value and normalize its hexadecimal width.
        # Both currently pinned records already contain the full 32 digits.
        expected_md5 = original_md5.zfill(32)
        path = folder/filename
        if not path.exists():
            temporary = path.with_suffix(path.suffix+".part")
            request = urllib.request.Request(entry["download_url"], headers={"User-Agent":"MiSendero public fatigue dataset audit"})
            with urllib.request.urlopen(request, timeout=30) as response, temporary.open("wb") as output:
                if not response.url.startswith("https://"):
                    raise ValueError("Public data redirected outside HTTPS")
                count = 0
                for block in iter(lambda: response.read(65536), b""):
                    count += len(block)
                    if count > size:
                        raise ValueError("Public table exceeded its published byte count")
                    output.write(block)
            if count != size or digest(temporary,"md5") != expected_md5:
                raise ValueError("Downloaded public table differs from its official checksum/size")
            temporary.rename(path)
        if path.stat().st_size != size or digest(path,"md5") != expected_md5:
            raise ValueError("Cached public feature table changed")
        receipt = {"version":1, "verified_at":datetime.now(timezone.utc).isoformat(), "article_id":article,
            "doi":metadata["doi"], "license":metadata["license"], "metadata_sha256":digest(metadata_path),
            "file":filename, "url":entry["download_url"], "bytes":size,
            "published_md5_original":original_md5, "published_md5_zero_padded":expected_md5,
            "sha256":digest(path), "fetch_code_sha256":digest(Path(__file__)), "used_for_training":False,
            "new_native_borg_targets":0, "note":"Data-only inspection pending; no included scripts, formulas or models executed."}
        receipt_path = folder/"table-receipt.json"
        if not receipt_path.exists():
            receipt_path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"dataset":name,"bytes":size,"sha256":receipt["sha256"],"published_md5_verified":expected_md5}),flush=True)


if __name__ == "__main__":
    main()
