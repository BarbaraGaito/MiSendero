"""Fetch small official metadata snapshots for public native-Borg candidates.

No credentials, remote code execution, archive extraction or training occurs.
Each HTTPS response is bounded to 2 MB; raw metadata and SHA-256 are retained.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import urllib.request
from datetime import datetime, timezone

from public_sources import ROOT

DIRECTORY = ROOT / "training/data/raw/fatigue-research/public-candidates-80-v1"
SOURCES = {
    "sit-to-stand": "https://api.figshare.com/v2/articles/15001362",
    "sit-to-stand-v1": "https://api.figshare.com/v2/articles/15001362/versions/1",
    "sit-to-stand-v2": "https://api.figshare.com/v2/articles/15001362/versions/2",
    "borg-scale-comparison": "https://api.figshare.com/v2/articles/19732099",
    "treadmill": "https://zenodo.org/api/records/23208045",
    "native-borg6to20": "https://zenodo.org/api/records/13906740",
    "geofatigue-current": "https://borealisdata.ca/api/datasets/:persistentId/?persistentId=doi:10.5683/SP3/I0KSNR",
}


def fetch(name, url):
    path = DIRECTORY / f"{name}.json"
    try:
        if path.exists():
            content = path.read_bytes()
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "MiSendero-Borg-research/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                if not response.url.startswith("https://"):
                    raise ValueError("Public metadata redirected outside HTTPS")
                content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Official metadata exceeds 2 MB bound")
            json.loads(content)
            path.write_bytes(content)
        metadata = json.loads(content)
        files = metadata.get("files", metadata.get("data", {}).get("latestVersion", {}).get("files", []))
        return {"name": name, "url": url, "status": "metadata_downloaded", "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(), "path": path.relative_to(ROOT).as_posix(),
                "files": [{k: f[k] for k in ("id", "name", "key", "size", "download_url", "checksum", "dataFile") if k in f} for f in files],
                "access": metadata.get("access"), "license": metadata.get("license", metadata.get("metadata", {}).get("license"))}
    except Exception as error:
        return {"name": name, "url": url, "status": "fetch_failed", "error": f"{type(error).__name__}: {error}"}


def main():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda item: fetch(*item), SOURCES.items()))
    receipt = {"fetched_at": datetime.now(timezone.utc).isoformat(), "sources": results,
               "training_merge_approved": False, "synthetic_or_interpolated_labels_permitted": False}
    (DIRECTORY / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for source in results:
        print(json.dumps({k: v for k, v in source.items() if k != "files"} | {"file_count": len(source.get("files", []))}, allow_nan=False))


if __name__ == "__main__":
    main()
