"""Download only FireComp test/index metadata for a route-coverage screen.

This script intentionally excludes the multi-gigabyte HDF5 shards and the
55-GB VIIRS event file. It downloads public JSON/JSONL index files only.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from environmental_sources import ROOT

BASE_URL = "https://huggingface.co/datasets/justuskarlsson/FireComp/resolve/main"
OUT_DIR = ROOT / "training/data/environmental/private/firecomp-metadata"
MAX_FILE_BYTES = 8 * 1024 * 1024
FILES = [
    "next_day_v3/splits/test.jsonl",
    *(f"next_day_v3/dataset_{index}.json" for index in range(8)),
]


def validate_json(path: Path, relative_path: str) -> None:
    if relative_path.endswith(".jsonl"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict) or "region_id" not in row:
                    raise ValueError(f"Unexpected JSONL row at line {line_number}")
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Expected an index array in {relative_path}")


def download(relative_path: str) -> Path:
    url = f"{BASE_URL}/{relative_path}"
    destination = OUT_DIR / relative_path.replace("/", "_")
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "MiSenderoResearch/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        declared_size = int(response.headers.get("Content-Length", "0"))
        if declared_size > MAX_FILE_BYTES:
            raise ValueError(f"Refusing oversized metadata file {relative_path}: {declared_size} bytes")
        total = 0
        with temporary.open("wb") as output:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_FILE_BYTES:
                    raise ValueError(f"Refusing oversized metadata file {relative_path}")
                output.write(block)
    try:
        validate_json(temporary, relative_path)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = [download(relative_path) for relative_path in FILES]
    print(json.dumps({"downloaded_index_files": len(files), "total_bytes": sum(p.stat().st_size for p in files),
                      "files": [{"name": p.name, "bytes": p.stat().st_size} for p in files]}, indent=2))


if __name__ == "__main__":
    main()
