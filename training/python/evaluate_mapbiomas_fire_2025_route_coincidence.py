#!/usr/bin/env python3
"""Compare MapBiomas 2025 burned-month pixels with SNMF route-event days.

This is a descriptive, source-to-source check. It does not evaluate a fire
forecast and a route/month coincidence is not a match to a specific incident.
The national GeoTIFF is downloaded to a temporary directory and removed after
the small route-level JSON result is written.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import transform
from rasterio.windows import from_bounds


ROOT = Path(__file__).resolve().parents[2]
GEO_PATH = ROOT / "training/data/environmental/geography.json"
EVENT_PATH = ROOT / "docs/environmental-models-2026-10-22/fire-smn-wrf-snmf-2025-event-test.json"
SNMF_PATH = ROOT / "docs/environmental-models-2026-10-22/snmf-2025-daily-occurrence-events.json"
OUT_PATH = ROOT / "docs/environmental-models-2026-10-22/fire-mapbiomas-snmf-route-month-2025.json"
BUCKET = "mapbiomas-public"
OBJECT_NAME = (
    "initiatives/argentina/fire/collection_01/monthly_burned/"
    "monthly_burned-argentina_burned_monthly_2025.tif"
)
OBJECT_API = "https://storage.googleapis.com/storage/v1/b/{}/o/{}".format(
    BUCKET, urllib.parse.quote(OBJECT_NAME, safe="")
)
OBJECT_URL = "https://storage.googleapis.com/{}/{}".format(BUCKET, OBJECT_NAME)
USER_AGENT = "MiSenderoResearch/1.0"


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def inspect_route(dataset: rasterio.DatasetReader, route: dict[str, Any]) -> dict[str, Any]:
    latitude = float(route["latitude"])
    longitude = float(route["longitude"])
    x_values, y_values = transform(
        "EPSG:4326", dataset.crs, [longitude], [latitude]
    )
    x, y = x_values[0], y_values[0]
    row, col = dataset.index(x, y)
    point_month = int(dataset.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])

    buffers: dict[str, Any] = {}
    for radius_km in (5, 10):
        # EPSG:3857 distances are locally inflated by sec(latitude).
        projected_radius = radius_km * 1000 / max(math.cos(math.radians(latitude)), 0.5)
        window = from_bounds(
            x - projected_radius,
            y - projected_radius,
            x + projected_radius,
            y + projected_radius,
            dataset.transform,
        ).round_offsets().round_lengths()
        values = dataset.read(1, window=window)
        rows, cols = np.indices(values.shape)
        transform_for_window = dataset.window_transform(window)
        pixel_x = (
            transform_for_window.c
            + cols * transform_for_window.a
            + rows * transform_for_window.b
        )
        pixel_y = (
            transform_for_window.f
            + cols * transform_for_window.d
            + rows * transform_for_window.e
        )
        # Local ground distance: projected metres multiplied by cos(latitude).
        distance_km = (
            np.sqrt((pixel_x - x) ** 2 + (pixel_y - y) ** 2)
            * math.cos(math.radians(latitude))
            / 1000
        )
        within = distance_km <= radius_km
        burned = within & (values >= 1) & (values <= 12)
        month_counts = {
            str(month): int(np.count_nonzero(burned & (values == month)))
            for month in range(1, 13)
            if np.any(burned & (values == month))
        }

        # The raster grid is 30 m in Web Mercator; adjust area for its local
        # ground scale at each pixel latitude (approximate, not survey area).
        pixel_latitude = 2 * np.arctan(np.exp(pixel_y / 6_378_137.0)) - math.pi / 2
        area_ha = float(np.sum(0.09 * np.cos(pixel_latitude[burned]) ** 2))
        total_pixels = int(within.sum())
        burned_pixels = int(burned.sum())
        buffers[str(radius_km)] = {
            "total_grid_pixels": total_pixels,
            "burned_pixels": burned_pixels,
            "burned_fraction_of_buffer": (
                round(burned_pixels / total_pixels, 8) if total_pixels else None
            ),
            "estimated_burned_area_ha": round(area_ha, 3),
            "burned_pixels_by_month": month_counts,
        }

    return {
        "name": route["name"],
        "location": route.get("location"),
        "latitude": latitude,
        "longitude": longitude,
        "geometry_sha256": route.get("geometry_sha256"),
        "center_month_value": point_month,
        "buffers": buffers,
    }


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    delta_lat, delta_lon = lat2_r - lat1_r, lon2_r - lon1_r
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(delta_lon / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def inspect_snmf_events(
    dataset: rasterio.DatasetReader,
    route_events: list[dict[str, Any]],
    official_events: list[dict[str, Any]],
    routes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    route_by_name = {route["name"]: route for route in routes}
    checks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for route_day in route_events:
        route = route_by_name[route_day["route_sector"]]
        route_lat, route_lon = float(route["latitude"]), float(route["longitude"])
        target_date = route_day["target_date"]
        target_month = int(target_date[5:7])
        matches = []
        for event in official_events:
            if event.get("reported_start_date") != target_date:
                continue
            if event.get("latitude") is None or event.get("longitude") is None:
                continue
            lat, lon = float(event["latitude"]), float(event["longitude"])
            route_distance = distance_km(route_lat, route_lon, lat, lon)
            if route_distance > 10:
                continue
            key = (
                target_date,
                f"{lat:.4f}",
                f"{lon:.4f}",
                str(event.get("province", "")).casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            x_values, y_values = transform("EPSG:4326", dataset.crs, [lon], [lat])
            x, y = x_values[0], y_values[0]
            radius_counts = {}
            for radius_m in (100, 250, 500, 1000, 2000):
                radius_km = radius_m / 1000
                projected_radius = radius_m / max(math.cos(math.radians(lat)), 0.5)
                window = from_bounds(
                    x - projected_radius,
                    y - projected_radius,
                    x + projected_radius,
                    y + projected_radius,
                    dataset.transform,
                ).round_offsets().round_lengths()
                values = dataset.read(1, window=window)
                rows, cols = np.indices(values.shape)
                window_transform = dataset.window_transform(window)
                pixel_x = window_transform.c + cols * window_transform.a + rows * window_transform.b
                pixel_y = window_transform.f + cols * window_transform.d + rows * window_transform.e
                distance = (
                    np.sqrt((pixel_x - x) ** 2 + (pixel_y - y) ** 2)
                    * math.cos(math.radians(lat))
                    / 1000
                )
                in_radius = distance <= radius_km
                burned_month = in_radius & (values == target_month)
                radius_counts[str(radius_m)] = {
                    "target_month_pixels": int(burned_month.sum()),
                    "any_burned_month_pixels": int((in_radius & (values >= 1) & (values <= 12)).sum()),
                    "same_month_coincidence": bool(burned_month.any()),
                }
            matches.append({
                "incident_name": event["incident_name"],
                "province": event.get("province"),
                "latitude": lat,
                "longitude": lon,
                "reported_start_date": target_date,
                "route_center_distance_km": round(route_distance, 3),
                "status": event.get("status"),
                "mapbiomas_month_neighborhood": radius_counts,
            })
        checks.extend(matches)
    return checks


def main() -> int:
    geography_bytes = GEO_PATH.read_bytes()
    geography = json.loads(geography_bytes)
    event_data = json.loads(EVENT_PATH.read_text(encoding="utf-8"))
    snmf_inventory = json.loads(SNMF_PATH.read_text(encoding="utf-8"))
    source_metadata = get_json(OBJECT_API)
    expected_size = int(source_metadata["size"])
    expected_md5 = source_metadata["md5Hash"]

    with tempfile.TemporaryDirectory(prefix="misendero-mapbiomas-") as directory:
        raster_path = Path(directory) / "monthly_burned_2025.tif"
        request = urllib.request.Request(
            OBJECT_URL, headers={"User-Agent": USER_AGENT}
        )
        sha256 = hashlib.sha256()
        # Cloud Storage exposes MD5 solely as an acquisition integrity checksum.
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

        with rasterio.open(raster_path) as dataset:
            raster_metadata = {
                "crs": str(dataset.crs),
                "bounds": [round(float(value), 3) for value in dataset.bounds],
                "width": dataset.width,
                "height": dataset.height,
                "band_count": dataset.count,
                "dtype": dataset.dtypes[0],
                "nodata": dataset.nodata,
                "block_shape": list(dataset.block_shapes[0]),
            }
            route_results = [
                inspect_route(dataset, route)
                for route in geography["fire_regions"]
            ]
            incident_checks = inspect_snmf_events(
                dataset,
                event_data["result"]["per_event_scores"],
                snmf_inventory["deduplicated_events"],
                geography["fire_regions"],
            )

    # Each row is a route/start-day already within 10 km by the source
    # inventory protocol. Check only whether any mapped burn occurs in that
    # same calendar month somewhere in the route's 10 km center buffer.
    event_checks = []
    for event in event_data["result"]["per_event_scores"]:
        month = int(event["target_date"][5:7])
        route = next(
            item for item in route_results if item["name"] == event["route_sector"]
        )
        months = route["buffers"]["10"]["burned_pixels_by_month"]
        event_checks.append({
            "route_sector": event["route_sector"],
            "target_date": event["target_date"],
            "incident_names": event["incident_names"],
            "reported_incident_distance_from_center_km": event["nearest_reported_incident_km"],
            "target_calendar_month": month,
            "same_month_burn_in_10km_center_buffer": str(month) in months,
            "interpretation": (
                "route-month spatial coincidence only; not an incident-to-polygon match"
            ),
        })

    hit_count = sum(item["same_month_burn_in_10km_center_buffer"] for item in event_checks)
    incident_hit_counts = {
        str(radius): sum(
            item["mapbiomas_month_neighborhood"][str(radius)]["same_month_coincidence"]
            for item in incident_checks
        )
        for radius in (100, 250, 500, 1000, 2000)
    }
    record = {
        "experiment_id": "mapbiomas-fire-2025-route-month-snmf-coincidence",
        "status": "descriptive-label-source-audit",
        "acquired_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {
            "product": "MapBiomas Argentina Fuego Collection 1, monthly burned area, 2025",
            "object_name": OBJECT_NAME,
            "url": OBJECT_URL,
            "bucket_metadata_url": OBJECT_API,
            "generation": source_metadata["generation"],
            "time_created_utc": source_metadata["timeCreated"],
            "size_bytes": size,
            "catalog_md5_base64": expected_md5,
            "verified_catalog_md5": True,
            "sha256": sha256.hexdigest(),
            "license_statement": "MapBiomas fire product page states public/open use with attribution; verify current terms before redistribution.",
        },
        "raster": raster_metadata,
        "geography": {
            "file": "training/data/environmental/geography.json",
            "sha256": hashlib.sha256(geography_bytes).hexdigest(),
            "route_geometry_limitation": "Catalog supplies route center points here, not full trail lines.",
        },
        "protocol": {
            "route_radius_km": [5, 10],
            "event_inventory": "SNMF 2025 event test selected four route-start-days within 10 km of a route-sector center with a WRF forecast available.",
            "month_match": "Any mapped burned pixel within 10 km of the route center in the SNMF event's calendar month.",
            "distance": "Approximate local ground distance from EPSG:3857 pixel centers, scaled by cos(route latitude).",
            "area": "Approximate 30 m Web-Mercator ground-pixel area, adjusted by cos(pixel latitude)^2.",
        },
        "routes": route_results,
        "snmf_event_route_month_checks": event_checks,
        "snmf_incident_coordinate_checks": incident_checks,
        "summary": {
            "snmf_event_route_days": len(event_checks),
            "same_month_burned_area_route_month_coincidences": hit_count,
            "coincidence_fraction_descriptive_only": round(hit_count / len(event_checks), 4) if event_checks else None,
            "deduplicated_incident_coordinates": len(incident_checks),
            "same_month_pixel_coincidences_by_incident_radius_m": incident_hit_counts,
        },
        "limitations": [
            "This is not a forecast evaluation; the burned-area layer is retrospective.",
            "Same-month presence in a 10 km center buffer can be an unrelated nearby fire, not the named SNMF incident.",
            "The four events are a small, selected subset, not a random or exhaustive incident cohort.",
            "A missing burned pixel is not a verified no-fire label; Landsat mapping can omit small scars or shift date/location.",
            "A 10 km buffer around a catalog center is a proxy, not a trail-line intersection.",
            "The local area correction is approximate and should not be cited as a survey-grade burned area measurement.",
        ],
        "synthetic_observations": 0,
        "deployment_approved": False,
    }
    OUT_PATH.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT_PATH)
    print(json.dumps({"verified_md5": True, **record["summary"]}, ensure_ascii=False))
    for incident in incident_checks:
        print(json.dumps({
            "incident": incident["incident_name"],
            "date": incident["reported_start_date"],
            "route_distance_km": incident["route_center_distance_km"],
            "same_month_pixels": {
                radius: incident["mapbiomas_month_neighborhood"][radius]["target_month_pixels"]
                for radius in ("100", "250", "500", "1000", "2000")
            },
        }, ensure_ascii=False))
    for route in route_results:
        print(json.dumps({
            "route": route["name"],
            "center_month_value": route["center_month_value"],
            "5km": route["buffers"]["5"],
            "10km": route["buffers"]["10"],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
