"""Download small official candidate workbooks for eligibility audit only."""
import concurrent.futures
import json
import urllib.request

from fetch_fatigue_extra import download
from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/public-candidates-80-v2"
FILES = {
    15377599: ("[All] IMU_HR _Updated.xlsx", "biceps-updated.xlsx", "4783b23e4a48fcc50f35f6cf6f2d7a99", 30_000_000),
    14891916: ("SMARTWATCH + OCRA (FIXED).xlsx", "pharmaceutical.xlsx", "5ef2e2276cb480019a635eb445739753", 300_000),
    21724451: ("Database_EIH.xlsx", "exercise-ppt.xlsx", "0dd1bc1e97556f69b980913e0534d73b", 100_000),
}


def fetch(record):
    remote_name, local_name, expected_md5, bound = FILES[record]
    metadata_path = DIRECTORY / f"{record}.json"
    if not metadata_path.exists():
        with urllib.request.urlopen(f"https://zenodo.org/api/records/{record}", timeout=30) as response:
            content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError("Candidate public metadata exceeds 2 MB")
        json.loads(content)
        metadata_path.write_bytes(content)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["metadata"]["access_right"] != "open" or metadata["metadata"]["license"]["id"] != "cc-by-4.0":
        raise ValueError("Expected inspected open CC BY 4.0 candidate")
    entry = next(row for row in metadata["files"] if row["key"] == remote_name)
    if entry["checksum"] != "md5:" + expected_md5 or entry["size"] > bound:
        raise ValueError("Published candidate file differs from the inspected version")
    path = download(entry["links"]["self"], DIRECTORY / local_name, maximum_bytes=bound, expected_bytes=entry["size"])
    if path.stat().st_size != entry["size"] or digest(path, "md5") != expected_md5:
        raise ValueError("Original workbook differs from publisher byte count/checksum")
    return {"record": record, "source": f"https://zenodo.org/records/{record}", "file": local_name,
            "original_filename": remote_name, "bytes": entry["size"], "publisher_md5": expected_md5,
            "sha256": digest(path), "metadata_sha256": digest(metadata_path), "training_merge_approved": False}


def main():
    DIRECTORY.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        files = list(pool.map(fetch, FILES))
    receipt = {"files": files, "all_complete_and_publisher_verified": True, "training_merge_approved": False,
               "reason": "Inspect original outcome definitions, participant independence and timing before any auxiliary fitting."}
    (DIRECTORY / "workbooks-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
