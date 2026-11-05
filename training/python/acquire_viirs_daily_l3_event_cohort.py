#!/usr/bin/env python3
"""Acquire the bounded 2023-2025 VIIRS daily L3 SNMF event cohort.

By default this queries public CMR metadata and records exact product/date/tile
matches. Pass --download to fetch HDF5 files into the ignored private research
directory. The Earthdata token is read from the process environment or ignored
local .env and is never printed or written to the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from environmental_sources import ROOT


COHORT = ROOT / "docs/environmental-models-2026-10-22/fire-viirs-daily-l3-event-cohort-2023-2025.json"
OUT_DIR = ROOT / "training/data/environmental/private/viirs-daily-l3-snmf-route-events-2023-2025"
MANIFEST = OUT_DIR / "acquisition-manifest.json"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
LPDAAC_HOST = "data.lpdaac.earthdatacloud.nasa.gov"
SIN_R = 6371007.181
TILE_M = 1111950.519667
X0 = -20015109.354
Y0 = 10007554.677
PRODUCTS = ("VNP14A1", "VJ114A1", "VJ214A1")
GRANULE = re.compile(
    r"^(?P<product>VNP14A1|VJ114A1|VJ214A1)\.A(?P<year>\d{4})(?P<doy>\d{3})\."
    r"(?P<tile>h\d{2}v\d{2})\.002\.(?P<processed>\d{13})$"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_token() -> str | None:
    token = os.environ.get("NASA_EARTHDATA_TOKEN")
    if token:
        return token.strip().strip('"').strip("'") or None
    env_file = ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "NASA_EARTHDATA_TOKEN":
            return value.split("#", 1)[0].strip().strip('"').strip("'") or None
    return None


def expected_items() -> list[dict]:
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    dates_and_tiles = cohort["acquisition_plan"]["event_route_tile_pairs"]
    items = []
    for row in dates_and_tiles:
        event_date = date.fromisoformat(row["date"])
        for product in PRODUCTS:
            items.append({
                "date": event_date.isoformat(),
                "year": event_date.year,
                "doy": event_date.timetuple().tm_yday,
                "tile": row["tile"],
                "product": product,
            })
    return sorted(items, key=lambda item: (item["date"], item["tile"], item["product"]))


def tile_center(tile: str) -> tuple[float, float]:
    match = re.fullmatch(r"h(?P<h>\d{2})v(?P<v>\d{2})", tile)
    if not match:
        raise ValueError(f"Invalid sinusoidal tile identifier: {tile!r}")
    h, v = int(match["h"]), int(match["v"])
    if h > 35 or v > 17:
        raise ValueError(f"Sinusoidal tile is outside the global grid: {tile!r}")
    x = X0 + (h + 0.5) * TILE_M
    y = Y0 - (v + 0.5) * TILE_M
    latitude = y / SIN_R
    longitude = x / (SIN_R * math.cos(latitude))
    return math.degrees(longitude), math.degrees(latitude)


def cmr_query_url(item: dict) -> str:
    event_date = item["date"]
    params = urllib.parse.urlencode({
        "short_name": item["product"],
        "version": "002",
        "temporal[]": f"{event_date}T00:00:00Z,{event_date}T23:59:59Z",
        "page_size": 2000,
    })
    return f"{CMR}?{params}"


def safe_data_url(item: dict, granule_id: str, url: str | None) -> bool:
    if not isinstance(url, str):
        return False
    parsed_url = urllib.parse.urlsplit(url)
    expected_url_path = f"/lp-prod-protected/{item['product']}.002/{granule_id}/{granule_id}.h5"
    return (parsed_url.scheme == "https" and parsed_url.hostname == LPDAAC_HOST
            and parsed_url.port is None and parsed_url.username is None and parsed_url.password is None
            and not parsed_url.query and not parsed_url.fragment
            and parsed_url.path == expected_url_path)


def cmr_match(item: dict) -> tuple[dict, str]:
    request = urllib.request.Request(
        cmr_query_url(item),
        headers={"Accept": "application/json", "User-Agent": "MiSenderoResearch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    entries = json.loads(raw).get("feed", {}).get("entry")
    if not isinstance(entries, list):
        raise RuntimeError(f"CMR returned an unexpected response for {pattern}.")
    valid = []
    expected_name = f"{item['product']}.A{item['year']}{item['doy']:03d}.{item['tile']}.002."
    for row in entries:
        granule_id = row.get("producer_granule_id")
        match = GRANULE.fullmatch(granule_id or "")
        if not match:
            continue
        if not granule_id.startswith(expected_name):
            continue
        if (match["product"], int(match["year"]), int(match["doy"]), match["tile"]) != (
                item["product"], item["year"], item["doy"], item["tile"]):
            continue
        url = next((link.get("href") for link in row.get("links", [])
                    if link.get("rel", "").endswith("/data#")), None)
        if not safe_data_url(item, granule_id, url):
            continue
        valid.append((row, url))
    if not valid:
        raise RuntimeError(f"No safe exact CMR granule found for {expected_name}*.")
    row, url = max(valid, key=lambda pair: pair[0].get("updated", ""))
    granule_id = row["producer_granule_id"]
    return ({**item,
             "granule_id": granule_id,
             "url": url,
             "reported_size_mb": float(row["granule_size"]) if row.get("granule_size") else None,
             "cmr_updated": row.get("updated")}, hashlib.sha256(raw).hexdigest())


def download(item: dict, token: str) -> dict:
    granule_id = item["granule_id"]
    destination_dir = OUT_DIR / item["product"] / str(item["year"]) / item["tile"]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{granule_id}.h5"
    if destination.exists() and destination.stat().st_size:
        return {"granule_id": granule_id, "status": "present", "bytes": destination.stat().st_size,
                "sha256": sha256(destination)}
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        item["url"],
        headers={"Authorization": f"Bearer {token}", "User-Agent": "MiSenderoResearch/1.0"},
    )
    try:
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
                digest.update(block)
                size += len(block)
        if not size:
            raise RuntimeError(f"NASA returned an empty file for {granule_id}.")
        temporary.replace(destination)
    except urllib.error.HTTPError as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"NASA LAADS returned HTTP {error.code} for {granule_id}.") from None
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"granule_id": granule_id, "status": "downloaded", "bytes": size,
            "sha256": digest.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true", help="Show local date/tile plan; no network.")
    parser.add_argument("--download", action="store_true", help="Download granules after CMR validation.")
    parser.add_argument("--limit", type=int, help="Limit metadata queries/downloads for an access pilot.")
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    items = expected_items()
    if args.limit is not None:
        items = items[:args.limit]
    if args.plan_only:
        print(json.dumps({"planned_granules": len(items), "products": list(PRODUCTS),
                          "date_tile_pairs": len({(item["date"], item["tile"]) for item in items}),
                          "download_requested": False}, ensure_ascii=False, indent=2))
        return

    if args.download and not local_token():
        parser.error("Set NASA_EARTHDATA_TOKEN in ignored .env or process environment; never pass it on the command line.")
    resolved = []
    response_hashes = {}
    for index, item in enumerate(items, start=1):
        row, response_hash = cmr_match(item)
        resolved.append(row)
        response_hashes[f"{item['product']}:{item['date']}:{item['tile']}"] = response_hash
        if index % 10 == 0 or index == len(items):
            print(json.dumps({"metadata_queries_completed": index, "expected": len(items)}, ensure_ascii=False), flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "experiment_id": "viirs-daily-l3-snmf-route-events-2023-2025",
        "status": "downloaded" if args.download else "metadata_resolved_download_pending",
        "cohort_sha256": sha256(COHORT),
        "planned_granules": len(resolved),
        "cmr_response_sha256": response_hashes,
        "granules": [],
        "synthetic_observations": 0,
    }
    if args.download:
        token = local_token()
        assert token is not None
        for index, row in enumerate(resolved, start=1):
            result = download(row, token)
            manifest["granules"].append({**{key: value for key, value in row.items() if key != "url"}, **result})
            manifest["status"] = "downloaded" if index == len(resolved) else "download_in_progress"
            temporary = MANIFEST.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(MANIFEST)
            print(json.dumps({"completed": index, **result}, ensure_ascii=False), flush=True)
            time.sleep(max(0.0, args.pause_seconds))
        del token
    else:
        manifest["granules"] = [{key: value for key, value in row.items() if key != "url"} for row in resolved]
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": MANIFEST.relative_to(ROOT).as_posix(),
                      "resolved_granules": len(resolved), "download_requested": args.download}, indent=2))


if __name__ == "__main__":
    main()
