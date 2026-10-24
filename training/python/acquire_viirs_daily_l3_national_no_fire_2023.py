#!/usr/bin/env python3
"""Acquire one VIIRS daily product for frozen-model alerts on explicit SNMF no-fire dates."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from acquire_viirs_daily_l3_event_cohort import CMR, GRANULE, local_token, safe_data_url, sha256
from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
NO_FIRE_AUDIT = BASE / "fire-snmf-national-no-fire-report-audit.json"
MODEL_TEST = BASE / "fire-model-explicit-national-no-fire-test-2023.json"
ROUTE_TILE_AUDIT = BASE / "fire-viirs-daily-l3-candidate-audit-2026-10-23.json"
OUT_DIR = ROOT / "training/data/environmental/private/viirs-daily-l3-explicit-no-fire-2023"
MANIFEST = OUT_DIR / "acquisition-manifest.json"
PRODUCT = "VNP14A1"
VERSION = "002"
USER_AGENT = "MiSenderoResearch/1.0"


def expected_items() -> list[dict]:
    report = json.loads(NO_FIRE_AUDIT.read_text(encoding="utf-8"))
    model_test = json.loads(MODEL_TEST.read_text(encoding="utf-8"))
    route_tiles = json.loads(ROUTE_TILE_AUDIT.read_text(encoding="utf-8"))
    verified_dates = {row["report_date_in_archive"] for row in report["verified_explicit_no_fire_reports"]}
    dates = sorted(set(model_test["protocol"]["test_dates"]))
    if not dates or not set(dates).issubset(verified_dates):
        raise RuntimeError("Frozen model test dates are not all backed by hash-verified explicit SNMF no-fire reports.")
    tile_routes: dict[str, list[str]] = {}
    for route in route_tiles["spatial_sampling"]["routes"]:
        for tile_id in route["tiles"]:
            tile_routes.setdefault(tile_id, []).append(route["route"])
    return [
        {"date": day, "year": date.fromisoformat(day).year,
         "doy": date.fromisoformat(day).timetuple().tm_yday,
         "tile": tile_id, "product": PRODUCT, "routes": sorted(names)}
        for day in dates for tile_id, names in sorted(tile_routes.items())
    ]


def cmr_url_for_date(day: str) -> str:
    params = urllib.parse.urlencode({
        "short_name": PRODUCT,
        "version": VERSION,
        "temporal[]": f"{day}T00:00:00Z,{day}T23:59:59Z",
        "page_size": 2000,
    })
    return f"{CMR}?{params}"


def resolve_date(day: str, items: list[dict]) -> tuple[list[dict], str]:
    request = urllib.request.Request(cmr_url_for_date(day), headers={
        "Accept": "application/json", "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    entries = json.loads(raw).get("feed", {}).get("entry")
    if not isinstance(entries, list):
        raise RuntimeError(f"Unexpected NASA CMR response for {day}.")
    result = []
    for item in items:
        expected_prefix = f"{PRODUCT}.A{item['year']}{item['doy']:03d}.{item['tile']}.{VERSION}."
        matches = []
        for row in entries:
            granule_id = row.get("producer_granule_id")
            match = GRANULE.fullmatch(granule_id or "")
            if not match or not granule_id.startswith(expected_prefix):
                continue
            if (match["product"], int(match["year"]), int(match["doy"]), match["tile"]) != (
                    PRODUCT, item["year"], item["doy"], item["tile"]):
                continue
            if not str(row.get("time_start", "")).startswith(f"{day}T"):
                continue
            url = next((link.get("href") for link in row.get("links", [])
                        if link.get("rel", "").endswith("/data#")), None)
            if not safe_data_url(item, granule_id, url):
                continue
            matches.append((row, url))
        if not matches:
            raise RuntimeError(f"No safe exact {PRODUCT} granule for {day} {item['tile']}.")
        row, url = max(matches, key=lambda pair: pair[0].get("updated", ""))
        granule_id = row["producer_granule_id"]
        result.append({**item, "granule_id": granule_id, "url": url,
                       "reported_size_mb": float(row["granule_size"]) if row.get("granule_size") else None,
                       "cmr_updated": row.get("updated")})
    return result, hashlib.sha256(raw).hexdigest()


def write_manifest(payload: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST)


def download_one(row: dict, token: str) -> dict:
    destination_dir = OUT_DIR / row["product"] / str(row["year"]) / row["tile"]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{row['granule_id']}.h5"
    if destination.is_file() and destination.stat().st_size:
        return {"granule_id": row["granule_id"], "status": "present", "bytes": destination.stat().st_size,
                "sha256": sha256(destination)}
    temporary = destination.with_suffix(".h5.part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(row["url"], headers={
        "Authorization": f"Bearer {token}", "User-Agent": USER_AGENT,
    })
    try:
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
                digest.update(block)
                size += len(block)
        if not size:
            raise RuntimeError(f"NASA returned an empty granule {row['granule_id']}.")
        temporary.replace(destination)
    except urllib.error.HTTPError as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"NASA LP DAAC returned HTTP {error.code} for {row['granule_id']}.") from None
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"granule_id": row["granule_id"], "status": "downloaded", "bytes": size,
            "sha256": digest.hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true", help="Print the bounded date/tile plan only.")
    parser.add_argument("--download", action="store_true", help="Download granules after exact CMR checks.")
    parser.add_argument("--limit", type=int, help="Limit the date/tile pairs for a metadata pilot.")
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    items = expected_items()
    if args.limit is not None:
        items = items[:args.limit]
    if args.plan_only:
        print(json.dumps({"planned_granules": len(items), "dates": len({row["date"] for row in items}),
                          "unique_tiles": len({row["tile"] for row in items}), "product": PRODUCT,
                          "routes": sorted({route for row in items for route in row["routes"]}),
                          "download_requested": False}, ensure_ascii=False, indent=2))
        return 0
    token = local_token() if args.download else None
    if args.download and not token:
        parser.error("Set NASA_EARTHDATA_TOKEN in ignored .env or process environment.")
    by_date: dict[str, list[dict]] = {}
    for row in items:
        by_date.setdefault(row["date"], []).append(row)
    resolved, response_hashes = [], {}
    for index, (day, date_items) in enumerate(sorted(by_date.items()), start=1):
        rows, response_hash = resolve_date(day, date_items)
        resolved.extend(rows)
        response_hashes[day] = response_hash
        print(json.dumps({"metadata_dates_completed": index, "expected_dates": len(by_date)}, ensure_ascii=False), flush=True)
    manifest = {
        "experiment_id": "viirs-daily-l3-explicit-national-no-fire-model-test-2023",
        "status": "metadata_resolved_download_pending",
        "model_test_sha256": sha256(MODEL_TEST),
        "no_fire_report_audit_sha256": sha256(NO_FIRE_AUDIT),
        "route_tile_audit_sha256": sha256(ROUTE_TILE_AUDIT),
        "cmr_response_sha256_by_date": response_hashes,
        "planned_granules": len(resolved), "granules": [], "synthetic_observations": 0,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.download:
        assert token is not None
        manifest["status"] = "download_in_progress"
        for index, row in enumerate(resolved, start=1):
            result = download_one(row, token)
            manifest["granules"].append({
                **{key: value for key, value in row.items() if key != "url"}, **result,
            })
            manifest["status"] = "downloaded" if index == len(resolved) else "download_in_progress"
            write_manifest(manifest)
            print(json.dumps({"completed": index, "expected": len(resolved), **result}, ensure_ascii=False), flush=True)
            time.sleep(max(0.0, args.pause_seconds))
        del token
    else:
        manifest["status"] = "metadata_resolved_download_pending"
        manifest["granules"] = [{key: value for key, value in row.items() if key != "url"} for row in resolved]
        write_manifest(manifest)
    print(json.dumps({"manifest": MANIFEST.relative_to(ROOT).as_posix(),
                      "resolved_granules": len(resolved), "download_requested": args.download}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
