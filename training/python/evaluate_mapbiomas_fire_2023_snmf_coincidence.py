#!/usr/bin/env python3
"""Descriptive 2023 SNMF/MapBiomas burned-month source audit.

This compares reported SNMF incident coordinates and route-sector buffers to
MapBiomas monthly burned area. It does not evaluate a forecast or establish
verified fire/no-fire labels.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "training/python/evaluate_mapbiomas_fire_2025_route_coincidence.py"
SPEC = importlib.util.spec_from_file_location("mapbiomas_2025_helpers", HELPER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load shared MapBiomas raster helpers")
HELPERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPERS)

YEAR = 2023
BUCKET = "mapbiomas-public"
OBJECT_NAME = (
    "initiatives/argentina/fire/collection_01/monthly_burned/"
    f"monthly_burned-argentina_burned_monthly_{YEAR}.tif"
)
OBJECT_API = "https://storage.googleapis.com/storage/v1/b/{}/o/{}".format(
    BUCKET, urllib.parse.quote(OBJECT_NAME, safe="")
)
OBJECT_URL = f"https://storage.googleapis.com/{BUCKET}/{OBJECT_NAME}"
SNMF_PATH = ROOT / f"docs/environmental-models-2026-10-22/snmf-{YEAR}-daily-occurrence-events.json"
GEO_PATH = ROOT / "training/data/environmental/geography.json"
OUT_PATH = ROOT / f"docs/environmental-models-2026-10-22/fire-mapbiomas-snmf-route-month-{YEAR}.json"


def get_json(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": HELPERS.USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def build_route_days(events: list[dict], routes: list[dict]) -> list[dict]:
    route_days: dict[tuple[str, str], list[dict]] = {}
    for event in events:
        if event.get("latitude") is None or event.get("longitude") is None:
            continue
        date = event.get("reported_start_date")
        if not date:
            continue
        for route in routes:
            distance = HELPERS.distance_km(
                float(route["latitude"]), float(route["longitude"]),
                float(event["latitude"]), float(event["longitude"]),
            )
            if distance <= 10:
                key = (route["name"], date)
                route_days.setdefault(key, []).append(event)
    result = []
    for (route_name, date), matching in sorted(route_days.items()):
        nearest = min(
            HELPERS.distance_km(
                float(next(r for r in routes if r["name"] == route_name)["latitude"]),
                float(next(r for r in routes if r["name"] == route_name)["longitude"]),
                float(event["latitude"]), float(event["longitude"]),
            )
            for event in matching
        )
        result.append({
            "route_sector": route_name,
            "target_date": date,
            "incident_names": sorted({event["incident_name"] for event in matching}),
            "nearest_reported_incident_km": round(nearest, 3),
        })
    return result


def main() -> int:
    geography_bytes = GEO_PATH.read_bytes()
    routes = json.loads(geography_bytes)["fire_regions"]
    inventory = json.loads(SNMF_PATH.read_text(encoding="utf-8"))
    events = inventory["deduplicated_events"]
    route_days = build_route_days(events, routes)
    metadata = get_json(OBJECT_API)
    expected_size = int(metadata["size"])
    expected_md5 = metadata["md5Hash"]

    with tempfile.TemporaryDirectory(prefix=f"misendero-mapbiomas-{YEAR}-") as directory:
        raster_path = Path(directory) / f"monthly_burned_{YEAR}.tif"
        request = urllib.request.Request(OBJECT_URL, headers={"User-Agent": HELPERS.USER_AGENT})
        sha256 = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        size = 0
        with urllib.request.urlopen(request, timeout=180) as response, raster_path.open("wb") as target:
            last_modified = response.headers.get("Last-Modified")
            while block := response.read(1024 * 1024):
                target.write(block)
                sha256.update(block)
                md5.update(block)
                size += len(block)
        if size != expected_size:
            raise RuntimeError(f"Downloaded {size} bytes; catalog declares {expected_size}")
        if base64.b64encode(md5.digest()).decode("ascii") != expected_md5:
            raise RuntimeError("GeoTIFF MD5 does not match the public Cloud Storage catalog")

        import rasterio

        with rasterio.open(raster_path) as dataset:
            raster_metadata = {
                "crs": str(dataset.crs), "bounds": [round(float(x), 3) for x in dataset.bounds],
                "width": dataset.width, "height": dataset.height,
                "band_count": dataset.count, "dtype": dataset.dtypes[0],
                "nodata": dataset.nodata, "block_shape": list(dataset.block_shapes[0]),
            }
            route_results = [HELPERS.inspect_route(dataset, route) for route in routes]
            incident_checks = HELPERS.inspect_snmf_events(
                dataset, route_days, events, routes
            )

    route_by_name = {route["name"]: route for route in route_results}
    route_month_checks = []
    for item in route_days:
        month = item["target_date"][5:7]
        mapped_months = route_by_name[item["route_sector"]]["buffers"]["10"]["burned_pixels_by_month"]
        route_month_checks.append({
            **item,
            "target_calendar_month": int(month),
            "same_month_burn_in_10km_center_buffer": month in mapped_months,
        })

    incident_hits = {
        str(radius): sum(
            check["mapbiomas_month_neighborhood"][str(radius)]["same_month_coincidence"]
            for check in incident_checks
        )
        for radius in (100, 250, 500, 1000, 2000)
    }
    summary = {
        "snmf_route_days_with_event_within_10km": len(route_month_checks),
        "same_month_route_buffer_coincidences": sum(
            check["same_month_burn_in_10km_center_buffer"] for check in route_month_checks
        ),
        "deduplicated_incidents_with_coordinates": len(incident_checks),
        "same_month_incident_coordinate_coincidences_by_radius_m": incident_hits,
    }
    record = {
        "experiment_id": f"mapbiomas-fire-{YEAR}-snmf-route-month-coincidence",
        "status": "descriptive-label-source-audit",
        "acquired_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {
            "product": f"MapBiomas Argentina Fuego Collection 1, monthly burned area, {YEAR}",
            "object_name": OBJECT_NAME, "url": OBJECT_URL, "bucket_metadata_url": OBJECT_API,
            "generation": metadata["generation"], "time_created_utc": metadata["timeCreated"],
            "size_bytes": size, "catalog_md5_base64": expected_md5,
            "verified_catalog_md5": True, "sha256": sha256.hexdigest(),
        },
        "raster": raster_metadata,
        "geography": {
            "file": "training/data/environmental/geography.json",
            "sha256": hashlib.sha256(geography_bytes).hexdigest(),
            "route_geometry_limitation": "Catalog supplies route center points here, not full trail lines.",
        },
        "protocol": {
            "route_radius_km": 10,
            "event_inventory": f"All {YEAR} deduplicated SNMF events with coordinates, joined to a route center within 10 km.",
            "month_match": "Any mapped burned pixel within 10 km of a route center in the event's reported calendar month.",
            "interpretation": "Descriptive spatial/month coincidence only; not a forecast score or verified event identity.",
        },
        "snmf_inventory_limitations": inventory.get("limitations", []),
        "routes": route_results,
        "snmf_event_route_month_checks": route_month_checks,
        "snmf_incident_coordinate_checks": incident_checks,
        "summary": summary,
        "limitations": [
            "This is not a forecast evaluation; MapBiomas burned area is retrospective.",
            "The 2023 SNMF inventory notes that 65 of 184 archive dates were not observed; missing reports are not negatives.",
            "A same-month scar within 10 km may be unrelated to a named SNMF incident.",
            "A missing burned pixel is not a verified no-fire label; mapped scars, administrative dates, and reported coordinates can differ.",
            "The buffer uses a route-sector center, not a trail line, and only two route-days had a nearby SNMF event.",
            "These observations cannot support precision, recall, or a claim of reliable future prediction.",
        ],
        "synthetic_observations": 0,
        "deployment_approved": False,
    }
    OUT_PATH.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT_PATH), "verified_md5": True, **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
