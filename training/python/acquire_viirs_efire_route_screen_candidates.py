#!/usr/bin/env python3
"""Download exact NOAA VIIRS E-FIRE/GITCO pairs found by a route swath screen."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
DEFAULT_SCREEN = BASE / "fire-viirs-efire-route-screen-2024-07-10-30min-noaa20-21.json"
OUT_DIR = ROOT / "training/data/environmental/private/viirs-efire-route-screen-2024-07-10"
MANIFEST = OUT_DIR / "download-manifest.json"
BUCKETS = {
    "noaa-nesdis-snpp-pds": "npp",
    "noaa-nesdis-n20-pds": "n20",
    "noaa-nesdis-n21-pds": "n21",
}
GEO_PLATFORM = {"npp": "npp", "n20": "j01", "n21": "j02"}
EFIRE_RE = re.compile(r"^EFIRE-VIIRSI_v1r3_(?P<platform>npp|n20|n21)_s(?P<start>\d{15})_e(?P<end>\d{15})_c\d{15}\.nc$")
GITCO_RE = re.compile(r"^GITCO_(?P<platform>npp|j01|j02)_d(?P<day>\d{8})_t(?P<start>\d{7})_e(?P<end>\d{7})_b\d+_c\d+_(?:oeac|oebc)_ops\.h5$")
USER_AGENT = "MiSenderoResearch/1.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_screen(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [row for row in data.get("scans", []) if row.get("candidate_routes_within_40km")]
    if not rows:
        raise RuntimeError("The screen has no swath candidates for exact download.")
    return data, rows


def resolve_geo(bucket: str, efire_key: str) -> tuple[str, bytes]:
    filename = efire_key.rsplit("/", 1)[-1]
    match = EFIRE_RE.fullmatch(filename)
    if not match:
        raise ValueError("Unexpected E-FIRE key; refusing to construct a geolocation query.")
    platform = match["platform"]
    geo_platform = GEO_PLATFORM[platform]
    day = match["start"][:8]
    start_hms = match["start"][8:]
    end_hms = match["end"][8:]
    prefix = f"VIIRS-IMG-GEO-TC/{day[:4]}/{day[4:6]}/{day[6:8]}/GITCO_{geo_platform}_d{day}_t{start_hms}_e{end_hms}_"
    params = urllib.parse.urlencode({"list-type": "2", "prefix": prefix, "max-keys": "20"})
    request = urllib.request.Request(
        f"https://{bucket}.s3.amazonaws.com/?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    root = ET.fromstring(raw)
    keys = [node.text for node in root.iter() if node.tag.endswith("Key") and node.text]
    keys = [key for key in keys if GITCO_RE.fullmatch(key.rsplit("/", 1)[-1])]
    if len(keys) != 1:
        raise RuntimeError(f"Expected exactly one matching GITCO object for {filename}; found {len(keys)}.")
    return keys[0], raw


def download(bucket: str, key: str, output: Path, expected_length: int | None = None) -> dict:
    if not key.startswith(("VIIRS_EFIRE_VIIRSI_EDR/", "VIIRS-IMG-GEO-TC/")):
        raise ValueError("Unexpected NOAA object key prefix.")
    name = key.rsplit("/", 1)[-1]
    if not (EFIRE_RE.fullmatch(name) or GITCO_RE.fullmatch(name)):
        raise ValueError("Unexpected NOAA filename; refusing to download.")
    destination = output / name
    if destination.is_file() and destination.stat().st_size:
        return {"filename": name, "status": "present", "bytes": destination.stat().st_size, "sha256": sha256(destination)}
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    url = f"https://{bucket}.s3.amazonaws.com/{urllib.parse.quote(key, safe='/')}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(request, timeout=240) as response, temporary.open("wb") as stream:
            header_length = response.headers.get("Content-Length")
            if expected_length is not None and header_length and int(header_length) != expected_length:
                raise RuntimeError(f"NOAA object size changed for {name}.")
            while block := response.read(1024 * 1024):
                stream.write(block)
                digest.update(block)
                size += len(block)
        if not size:
            raise RuntimeError(f"NOAA returned an empty object {name}.")
        if expected_length is not None and size != expected_length:
            raise RuntimeError(f"Downloaded size mismatch for {name}.")
        temporary.replace(destination)
    except urllib.error.HTTPError as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"NOAA S3 returned HTTP {error.code} for {name}.") from None
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"filename": name, "status": "downloaded", "bytes": size, "sha256": digest.hexdigest()}


def write_manifest(manifest: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen", type=Path, default=DEFAULT_SCREEN)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    args = parser.parse_args()
    screen, candidates = load_screen(args.screen)
    resolved = []
    for row in candidates:
        bucket = row["platform_bucket"]
        if bucket not in BUCKETS:
            raise ValueError(f"Unexpected NOAA bucket {bucket!r}.")
        key = row["key"]
        if not key.startswith("VIIRS_EFIRE_VIIRSI_EDR/") or not EFIRE_RE.fullmatch(key.rsplit("/", 1)[-1]):
            raise ValueError("Screen returned an unexpected E-FIRE key.")
        geo_key, list_response = resolve_geo(bucket, key)
        resolved.append({
            "platform_bucket": bucket,
            "platform_code": BUCKETS[bucket],
            "efire_key": key,
            "efire_expected_bytes": None,
            "geolocation_key": geo_key,
            "candidate_routes_within_40km": row["candidate_routes_within_40km"],
            "minimum_distance_to_routes_km": row["minimum_distance_to_coarse_swath_sample_km"],
            "time_coverage_start_utc": row.get("time_coverage_start"),
            "time_coverage_end_utc": row.get("time_coverage_end"),
            "gitco_list_response_sha256": hashlib.sha256(list_response).hexdigest(),
        })
    planned_objects = 2 * len(resolved)
    if args.plan_only:
        print(json.dumps({"candidate_swaths": len(resolved), "planned_objects": planned_objects,
                          "candidates": resolved, "download_requested": False}, ensure_ascii=False, indent=2))
        return 0
    if not args.download:
        parser.error("Specify --plan-only or --download.")

    manifest = {
        "experiment_id": "noaa-viirs-efire-route-screen-candidates-2024-07-10",
        "screen_file": args.screen.relative_to(ROOT).as_posix(),
        "screen_sha256": sha256(args.screen),
        "screen_interval_minutes": screen["source"]["screen_interval_minutes"],
        "status": "download_in_progress",
        "candidate_swaths": resolved,
        "downloaded_objects": [],
        "synthetic_observations": 0,
    }
    write_manifest(manifest)
    for swath_index, row in enumerate(resolved, start=1):
        for kind, key in (("efire", row["efire_key"]), ("geolocation", row["geolocation_key"])):
            downloaded = download(row["platform_bucket"], key, OUT_DIR)
            manifest["downloaded_objects"] = [item for item in manifest["downloaded_objects"] if item["filename"] != downloaded["filename"]]
            manifest["downloaded_objects"].append({
                "kind": kind,
                "platform_bucket": row["platform_bucket"],
                "key": key,
                **downloaded,
            })
            write_manifest(manifest)
            print(json.dumps({"swath": swath_index, "swaths": len(resolved), **downloaded}, ensure_ascii=False), flush=True)
            time.sleep(max(0.0, args.pause_seconds))
    manifest["status"] = "downloaded"
    write_manifest(manifest)
    print(json.dumps({"manifest": MANIFEST.relative_to(ROOT).as_posix(), "candidate_swaths": len(resolved),
                      "downloaded_objects": len(manifest["downloaded_objects"]),
                      "total_bytes": sum(row["bytes"] for row in manifest["downloaded_objects"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
