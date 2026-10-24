#!/usr/bin/env python3
"""Acquire NOAA-20/21 VIIRS daily tiles for route-days missing Suomi-NPP coverage."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from acquire_viirs_daily_l3_event_cohort import GRANULE, local_token, safe_data_url, sha256
from acquire_viirs_daily_l3_jma_2024_no_fire_all_routes import (
    BASE,
    MODEL_TEST,
    TILE_AUDIT,
    THRESHOLD,
    expected_items as all_route_items,
)
from environmental_sources import ROOT


ALL_ROUTE_AUDIT = BASE / "fire-viirs-jma-2024-explicit-no-fire-all-routes.json"
OUT_DIR = ROOT / "training/data/environmental/private/viirs-daily-l3-jma-2024-cmr-gaps"
MANIFEST = OUT_DIR / "acquisition-manifest.json"
NO_FIRE_AUDIT = BASE / "fire-snmf-national-no-fire-report-audit.json"
PRODUCTS = ("VJ114A1", "VJ214A1")
VERSION = "002"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
USER_AGENT = "MiSenderoResearch/1.0"


def expected_items() -> list[dict]:
    audit = json.loads(ALL_ROUTE_AUDIT.read_text(encoding="utf-8"))
    missing_dates = set(audit["cohort"]["dates_without_any_matching_cmr_tile"])
    if not missing_dates:
        return []
    base = [row for row in all_route_items() if row["date"] in missing_dates]
    if {row["date"] for row in base} != missing_dates:
        raise RuntimeError("Could not map every CMR-missing date to all audited routes.")
    items = []
    for row in base:
        for product in PRODUCTS:
            items.append({**row, "product": product})
    return sorted(items, key=lambda row: (row["date"], row["product"], row["tile"]))


def query_url(product: str, day: str) -> str:
    params = urllib.parse.urlencode({
        "short_name": product,
        "version": VERSION,
        "temporal[]": f"{day}T00:00:00Z,{day}T23:59:59Z",
        "page_size": 2000,
    })
    return f"{CMR}?{params}"


def resolve_product_date(product: str, day: str, items: list[dict]) -> tuple[list[dict], list[dict], str]:
    request = urllib.request.Request(query_url(product, day), headers={
        "Accept": "application/json", "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    entries = json.loads(raw).get("feed", {}).get("entry")
    if not isinstance(entries, list):
        raise RuntimeError(f"Unexpected NASA CMR response for {product} {day}.")
    resolved, missing = [], []
    for item in items:
        prefix = f"{product}.A{item['year']}{item['doy']:03d}.{item['tile']}.{VERSION}."
        matches = []
        for entry in entries:
            granule_id = entry.get("producer_granule_id")
            match = GRANULE.fullmatch(granule_id or "")
            if not match or not granule_id.startswith(prefix):
                continue
            if (match["product"], int(match["year"]), int(match["doy"]), match["tile"]) != (
                    product, item["year"], item["doy"], item["tile"]):
                continue
            url = next((link.get("href") for link in entry.get("links", [])
                        if link.get("rel", "").endswith("/data#")), None)
            if safe_data_url(item, granule_id, url):
                matches.append((entry, url))
        if not matches:
            missing.append({"date": day, "product": product, "tile": item["tile"], "routes": item["routes"]})
            continue
        entry, url = max(matches, key=lambda pair: pair[0].get("updated", ""))
        resolved.append({
            **item,
            "granule_id": entry["producer_granule_id"],
            "url": url,
            "reported_size_mb": float(entry["granule_size"]) if entry.get("granule_size") else None,
            "cmr_updated": entry.get("updated"),
        })
    return resolved, missing, hashlib.sha256(raw).hexdigest()


def download_one(row: dict, token: str) -> dict:
    destination_dir = OUT_DIR / row["product"] / str(row["year"]) / row["tile"]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{row['granule_id']}.h5"
    if destination.is_file() and destination.stat().st_size:
        return {"status": "present", "bytes": destination.stat().st_size, "sha256": sha256(destination)}
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
    return {"status": "downloaded", "bytes": size, "sha256": digest.hexdigest()}


def write_manifest(payload: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    items = expected_items()
    if args.limit is not None:
        items = items[:args.limit]
    if args.plan_only:
        print(json.dumps({"planned_granules": len(items), "dates": sorted({row["date"] for row in items}),
                          "products": list(PRODUCTS), "tiles": sorted({row["tile"] for row in items}),
                          "download_requested": False}, ensure_ascii=False, indent=2))
        return 0
    token = local_token() if args.download else None
    if args.download and not token:
        parser.error("Set NASA_EARTHDATA_TOKEN in ignored .env or process environment.")

    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        grouped.setdefault((item["product"], item["date"]), []).append(item)
    resolved, unresolved, response_hashes = [], [], {}
    for index, ((product, day), group) in enumerate(sorted(grouped.items()), start=1):
        rows, missing, digest = resolve_product_date(product, day, group)
        resolved.extend(rows)
        unresolved.extend(missing)
        response_hashes[f"{product}:{day}"] = digest
        print(json.dumps({"metadata_batches_completed": index, "expected": len(grouped),
                          "resolved": len(rows), "missing": len(missing)}), flush=True)

    manifest = {
        "experiment_id": "viirs-daily-l3-jma-2024-no-fire-cmr-gap-fill",
        "status": "metadata_resolved_download_pending" if not unresolved else "partial_metadata_resolved",
        "products": list(PRODUCTS),
        "threshold_for_model_alignment": THRESHOLD,
        "base_observation_audit_sha256": sha256(ALL_ROUTE_AUDIT),
        "model_test_sha256": sha256(MODEL_TEST),
        "no_fire_report_audit_sha256": sha256(NO_FIRE_AUDIT),
        "route_tile_audit_sha256": sha256(TILE_AUDIT),
        "cmr_response_sha256_by_product_date": response_hashes,
        "requested_product_date_tile_pairs": len(items),
        "planned_granules": len(resolved),
        "unresolved_product_date_tile_pairs": unresolved,
        "granules": [],
        "synthetic_observations": 0,
    }
    write_manifest(manifest)
    if args.download:
        assert token is not None
        manifest["status"] = "download_in_progress"
        for index, row in enumerate(resolved, start=1):
            outcome = download_one(row, token)
            manifest["granules"].append({
                **{key: value for key, value in row.items() if key != "url"}, **outcome,
            })
            manifest["status"] = ("partial_downloaded" if unresolved else "downloaded") if index == len(resolved) else "download_in_progress"
            write_manifest(manifest)
            print(json.dumps({"completed": index, "expected": len(resolved), **outcome}), flush=True)
            time.sleep(max(0.0, args.pause_seconds))
        del token
    else:
        manifest["granules"] = [{key: value for key, value in row.items() if key != "url"} for row in resolved]
        write_manifest(manifest)
    print(json.dumps({"manifest": MANIFEST.relative_to(ROOT).as_posix(), "resolved_granules": len(resolved),
                      "requested_pairs": len(items), "unresolved_pairs": len(unresolved),
                      "download_requested": args.download}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
