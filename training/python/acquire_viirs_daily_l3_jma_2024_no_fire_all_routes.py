#!/usr/bin/env python3
"""Acquire VIIRS tiles for all route-days on 2024 SNMF explicit no-fire dates."""
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
from acquire_viirs_daily_l3_national_no_fire_2023 import cmr_url_for_date
from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
NO_FIRE_AUDIT = BASE / "fire-snmf-national-no-fire-report-audit.json"
MODEL_TEST = BASE / "fire-jma-2023-train-2024-test-snmf-report-proxy.json"
TILE_AUDIT = BASE / "fire-viirs-daily-l3-candidate-audit-2026-10-23.json"
OUT_DIR = ROOT / "training/data/environmental/private/viirs-daily-l3-jma-2024-no-fire-all-routes"
MANIFEST = OUT_DIR / "acquisition-manifest.json"
PRODUCT = "VNP14A1"
THRESHOLD = 0.1
USER_AGENT = "MiSenderoResearch/1.0"


def expected_items() -> list[dict]:
    no_fire = json.loads(NO_FIRE_AUDIT.read_text(encoding="utf-8"))
    model = json.loads(MODEL_TEST.read_text(encoding="utf-8"))
    tile_audit = json.loads(TILE_AUDIT.read_text(encoding="utf-8"))
    dates = sorted({
        row["report_date_in_archive"]
        for row in no_fire["verified_explicit_no_fire_reports"]
        if row["report_date_in_archive"].startswith("2024-")
    })
    test_dates = set(model["counts"]["explicit_national_no_fire_dates"])
    if set(dates) != test_dates:
        raise RuntimeError("The frozen JMA test and hash-verified SNMF no-fire dates differ.")
    alert_rows = model["explicit_no_fire_negative_challenge"]["threshold_results"][str(THRESHOLD)]["alerts"]
    alerts_by_key = {(row["date"], row["route_sector"]): float(row["score"]) for row in alert_rows}
    route_by_tile: dict[str, list[str]] = {}
    for route in tile_audit["spatial_sampling"]["routes"]:
        if len(route["tiles"]) != 1:
            raise RuntimeError(f"Expected one audited L3 tile for {route['route']!r}.")
        route_by_tile.setdefault(route["tiles"][0], []).append(route["route"])
    items = []
    for day in dates:
        parsed = date.fromisoformat(day)
        for tile, routes in sorted(route_by_tile.items()):
            alerts = [
                {"route": route, "score": alerts_by_key[(day, route)], "threshold": THRESHOLD}
                for route in sorted(routes)
                if (day, route) in alerts_by_key
            ]
            items.append({
                "date": day,
                "year": parsed.year,
                "doy": parsed.timetuple().tm_yday,
                "tile": tile,
                "product": PRODUCT,
                "routes": sorted(routes),
                "fixed_threshold_alerts": alerts,
            })
    return items


def resolve_date_partial(day: str, items: list[dict]) -> tuple[list[dict], list[dict], str]:
    request = urllib.request.Request(cmr_url_for_date(day), headers={
        "Accept": "application/json", "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    entries = json.loads(raw).get("feed", {}).get("entry")
    if not isinstance(entries, list):
        raise RuntimeError(f"Unexpected NASA CMR response for {day}.")
    resolved, unresolved = [], []
    for item in items:
        prefix = f"{PRODUCT}.A{item['year']}{item['doy']:03d}.{item['tile']}.002."
        matches = []
        for entry in entries:
            granule_id = entry.get("producer_granule_id")
            match = GRANULE.fullmatch(granule_id or "")
            if not match or not granule_id.startswith(prefix):
                continue
            if (match["product"], int(match["year"]), int(match["doy"]), match["tile"]) != (
                    PRODUCT, item["year"], item["doy"], item["tile"]):
                continue
            data_url = next((link.get("href") for link in entry.get("links", [])
                             if link.get("rel", "").endswith("/data#")), None)
            if safe_data_url(item, granule_id, data_url):
                matches.append((entry, data_url))
        if not matches:
            unresolved.append({
                "date": day, "tile": item["tile"], "routes": item["routes"],
                "reason": "NASA CMR returned no exact daily granule for this date/tile.",
            })
            continue
        entry, data_url = max(matches, key=lambda pair: pair[0].get("updated", ""))
        granule_id = entry["producer_granule_id"]
        resolved.append({
            **item,
            "granule_id": granule_id,
            "url": data_url,
            "reported_size_mb": float(entry["granule_size"]) if entry.get("granule_size") else None,
            "cmr_updated": entry.get("updated"),
        })
    return resolved, unresolved, hashlib.sha256(raw).hexdigest()


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
    parser.add_argument("--limit", type=int, help="Limit date/tile pairs during a metadata pilot.")
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    items = expected_items()
    if args.limit is not None:
        items = items[:args.limit]
    if args.plan_only:
        print(json.dumps({
            "route_count": 8,
            "route_days": len({row["date"] for row in items}) * 8,
            "dates": len({row["date"] for row in items}),
            "tile_date_pairs": len(items),
            "unique_tiles": sorted({row["tile"] for row in items}),
            "fixed_diagnostic_alerts_in_cohort": sum(len(row["fixed_threshold_alerts"]) for row in items),
            "download_requested": False,
        }, ensure_ascii=False, indent=2))
        return 0

    token = local_token() if args.download else None
    if args.download and not token:
        parser.error("Set NASA_EARTHDATA_TOKEN in ignored .env or process environment.")
    by_date: dict[str, list[dict]] = {}
    for item in items:
        by_date.setdefault(item["date"], []).append(item)

    resolved, response_hashes, unresolved = [], {}, []
    for index, (day, date_items) in enumerate(sorted(by_date.items()), start=1):
        rows, missing, response_hash = resolve_date_partial(day, date_items)
        resolved.extend(rows)
        unresolved.extend(missing)
        response_hashes[day] = response_hash
        print(json.dumps({"date_metadata_completed": index, "expected_dates": len(by_date),
                          "granules_resolved": len(rows), "granules_missing": len(missing)}), flush=True)

    manifest = {
        "experiment_id": "viirs-daily-l3-jma-2024-explicit-no-fire-all-routes",
        "status": "metadata_resolved_download_pending" if not unresolved else "partial_metadata_resolved",
        "threshold_for_model_alert_alignment": THRESHOLD,
        "model_test_sha256": sha256(MODEL_TEST),
        "no_fire_report_audit_sha256": sha256(NO_FIRE_AUDIT),
        "route_tile_audit_sha256": sha256(TILE_AUDIT),
        "cmr_response_sha256_by_date": response_hashes,
        "requested_date_tile_pairs": len(items),
        "planned_granules": len(resolved),
        "unresolved_date_tile_batches": unresolved,
        "granules": [],
        "synthetic_observations": 0,
    }
    write_manifest(manifest)
    if args.download:
        assert token is not None
        manifest["status"] = "download_in_progress"
        for index, row in enumerate(resolved, start=1):
            result = download_one(row, token)
            manifest["granules"].append({
                **{key: value for key, value in row.items() if key != "url"}, **result,
            })
            manifest["status"] = ("partial_downloaded" if unresolved else "downloaded") if index == len(resolved) else "download_in_progress"
            write_manifest(manifest)
            print(json.dumps({"completed": index, "expected": len(resolved), **result}), flush=True)
            time.sleep(max(0.0, args.pause_seconds))
        del token
    else:
        manifest["granules"] = [{key: value for key, value in row.items() if key != "url"} for row in resolved]
        write_manifest(manifest)
    print(json.dumps({"manifest": MANIFEST.relative_to(ROOT).as_posix(), "resolved_granules": len(resolved),
                      "requested_date_tile_pairs": len(items), "unresolved_batches": len(unresolved),
                      "download_requested": args.download}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
