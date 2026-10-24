#!/usr/bin/env python3
"""Acquire VIIRS daily L3 tiles for frozen JMA alerts on explicit SNMF no-fire dates."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from acquire_viirs_daily_l3_event_cohort import cmr_match, local_token, safe_data_url, sha256
from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
MODEL_TEST = BASE / "fire-jma-2023-train-2024-test-snmf-report-proxy.json"
NO_FIRE_AUDIT = BASE / "fire-snmf-national-no-fire-report-audit.json"
TILE_AUDIT = BASE / "fire-viirs-daily-l3-candidate-audit-2026-10-23.json"
OUT_DIR = ROOT / "training/data/environmental/private/viirs-daily-l3-jma-2024-no-fire-alerts"
MANIFEST = OUT_DIR / "acquisition-manifest.json"
PRODUCT = "VNP14A1"
VERSION = "002"
THRESHOLD = 0.1


def expected_items() -> list[dict]:
    model = json.loads(MODEL_TEST.read_text(encoding="utf-8"))
    no_fire = json.loads(NO_FIRE_AUDIT.read_text(encoding="utf-8"))
    tile_audit = json.loads(TILE_AUDIT.read_text(encoding="utf-8"))
    verified_dates = {
        row["report_date_in_archive"]
        for row in no_fire["verified_explicit_no_fire_reports"]
    }
    threshold_data = model["explicit_no_fire_negative_challenge"]["threshold_results"]
    alerts = threshold_data[str(THRESHOLD)]["alerts"]
    if not alerts:
        raise RuntimeError("The frozen threshold has no alerts to cross-check.")

    route_tiles = {
        row["route"]: row["tiles"]
        for row in tile_audit["spatial_sampling"]["routes"]
    }
    selected = {}
    for alert in alerts:
        day = alert["date"]
        if day not in verified_dates:
            raise RuntimeError(f"Alert date lacks a hash-verified explicit no-fire report: {day}")
        tiles = route_tiles.get(alert["route_sector"])
        if not tiles:
            raise RuntimeError(f"No audited route tiles for {alert['route_sector']!r}.")
        parsed = date.fromisoformat(day)
        for tile in tiles:
            key = (day, tile)
            row = selected.setdefault(key, {
                "date": day,
                "year": parsed.year,
                "doy": parsed.timetuple().tm_yday,
                "tile": tile,
                "product": PRODUCT,
                "route_alerts": [],
            })
            row["route_alerts"].append({
                "route": alert["route_sector"],
                "score": float(alert["score"]),
                "frozen_threshold": THRESHOLD,
            })
    return [selected[key] for key in sorted(selected)]


def download_one(row: dict, token: str) -> dict:
    destination_dir = OUT_DIR / row["product"] / str(row["year"]) / row["tile"]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{row['granule_id']}.h5"
    if destination.is_file() and destination.stat().st_size:
        return {
            "status": "present",
            "bytes": destination.stat().st_size,
            "sha256": sha256(destination),
        }
    temporary = destination.with_suffix(".h5.part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(row["url"], headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "MiSenderoResearch/1.0",
    })
    try:
        import hashlib

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
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(MANIFEST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true", help="Show the bounded date/tile plan.")
    parser.add_argument("--download", action="store_true", help="Resolve metadata and download exact granules.")
    parser.add_argument("--limit", type=int, help="Limit date/tile pairs for an access pilot.")
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    items = expected_items()
    if args.limit is not None:
        items = items[:args.limit]
    if args.plan_only:
        print(json.dumps({
            "planned_granules": len(items),
            "dates": sorted({row["date"] for row in items}),
            "routes": sorted({alert["route"] for row in items for alert in row["route_alerts"]}),
            "frozen_threshold": THRESHOLD,
            "product": PRODUCT,
            "download_requested": False,
        }, ensure_ascii=False, indent=2))
        return 0

    token = local_token() if args.download else None
    if args.download and not token:
        parser.error("Set NASA_EARTHDATA_TOKEN in ignored .env or process environment.")

    resolved = []
    unresolved = []
    cmr_hashes = {}
    for index, row in enumerate(items, start=1):
        try:
            match, response_hash = cmr_match(row)
        except RuntimeError as error:
            message = str(error)
            if not message.startswith("No safe exact CMR granule found for "):
                raise
            unresolved.append({
                "date": row["date"],
                "tile": row["tile"],
                "product": row["product"],
                "routes": [alert["route"] for alert in row["route_alerts"]],
                "reason": "NASA CMR returned no matching daily granule.",
            })
            print(json.dumps({
                "metadata_pairs_completed": index,
                "expected": len(items),
                "status": "no_matching_cmr_granule",
                "date": row["date"],
                "tile": row["tile"],
            }), flush=True)
            continue
        if (match["date"], match["tile"], match["product"]) != (row["date"], row["tile"], PRODUCT):
            raise RuntimeError("CMR returned a product/date/tile mismatch.")
        if not safe_data_url(row, match["granule_id"], match["url"]):
            raise RuntimeError("CMR returned an unsafe or unexpected download URL.")
        resolved.append({**row, **match})
        cmr_hashes[f"{row['date']}:{row['tile']}"] = response_hash
        print(json.dumps({"metadata_pairs_completed": index, "expected": len(items)}), flush=True)

    manifest = {
        "experiment_id": "viirs-daily-l3-jma-2024-explicit-no-fire-alerts",
        "status": "metadata_resolved_download_pending" if not unresolved else "partial_metadata_resolved",
        "threshold": THRESHOLD,
        "model_test_sha256": sha256(MODEL_TEST),
        "no_fire_report_audit_sha256": sha256(NO_FIRE_AUDIT),
        "route_tile_audit_sha256": sha256(TILE_AUDIT),
        "cmr_response_sha256_by_date_tile": cmr_hashes,
        "planned_granules": len(resolved),
        "requested_date_tile_pairs": len(items),
        "unresolved_date_tile_pairs": unresolved,
        "granules": [],
        "synthetic_observations": 0,
    }
    write_manifest(manifest)
    if args.download:
        assert token is not None
        manifest["status"] = "download_in_progress"
        for index, row in enumerate(resolved, start=1):
            downloaded = download_one(row, token)
            manifest["granules"].append({
                **{key: value for key, value in row.items() if key != "url"},
                **downloaded,
            })
            if index == len(resolved):
                manifest["status"] = "partial_downloaded" if unresolved else "downloaded"
            else:
                manifest["status"] = "download_in_progress"
            write_manifest(manifest)
            print(json.dumps({"completed": index, "expected": len(resolved), **downloaded}), flush=True)
            time.sleep(max(0.0, args.pause_seconds))
        del token
    else:
        manifest["granules"] = [{key: value for key, value in row.items() if key != "url"} for row in resolved]
        write_manifest(manifest)
    print(json.dumps({
        "manifest": MANIFEST.relative_to(ROOT).as_posix(),
        "resolved_granules": len(resolved),
        "download_requested": args.download,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
