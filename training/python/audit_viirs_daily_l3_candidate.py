#!/usr/bin/env python3
"""Audit daily 1-km VIIRS active-fire labels as a candidate for route studies.

This checks local route coverage and public product metadata only. It does not
download data or produce model metrics.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT / "training/data/environmental/private/fire-route-geometries.json"
OUT = ROOT / "docs/environmental-models-2026-10-22/fire-viirs-daily-l3-candidate-audit-2026-10-23.json"
RADIUS_KM = 6371.0088
SIN_R = 6371007.181
TILE_M = 1111950.519667
X0 = -20015109.354
Y0 = 10007554.677
BUFFER_KM = 10.0
COVERAGE_MARGIN_KM = 0.5
SAMPLE_STEP_KM = 0.25
AZIMUTH_STEP_DEG = 0.5
PRODUCTS = {
    "VNP14A1.002": {"platform": "Suomi-NPP", "doi": "https://doi.org/10.5067/VIIRS/VNP14A1.002"},
    "VJ114A1.002": {"platform": "NOAA-20 / JPSS-1", "doi": "https://doi.org/10.5067/VIIRS/VJ114A1.002"},
    "VJ214A1.002": {"platform": "NOAA-21 / JPSS-2", "doi": "https://doi.org/10.5067/VIIRS/VJ214A1.002"},
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    v = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * RADIUS_KM * math.asin(math.sqrt(v))


def destination(lon: float, lat: float, bearing_deg: float, distance_km: float) -> tuple[float, float]:
    delta = distance_km / RADIUS_KM
    bearing, lat1, lon1 = map(math.radians, (bearing_deg, lat, lon))
    lat2 = math.asin(math.sin(lat1) * math.cos(delta) + math.cos(lat1) * math.sin(delta) * math.cos(bearing))
    lon2 = lon1 + math.atan2(math.sin(bearing) * math.sin(delta) * math.cos(lat1),
                             math.cos(delta) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lon2), math.degrees(lat2)


def tile(lon: float, lat: float) -> str:
    latitude_rad = math.radians(lat)
    longitude_rad = math.radians(lon)
    # MODIS sinusoidal projection: x = R * lambda * cos(phi), y = R * phi.
    x = SIN_R * longitude_rad * math.cos(latitude_rad)
    y = SIN_R * latitude_rad
    # The published origin/tile width are rounded; absorb only their sub-mm
    # floating-point boundary discrepancy (e.g. the exact (0, 0) grid corner).
    h = math.floor((x - X0) / TILE_M + 1e-10)
    v = math.floor((Y0 - y) / TILE_M + 1e-10)
    if not 0 <= h <= 35 or not 0 <= v <= 17:
        raise ValueError(f"Route coordinate outside sinusoidal tile grid: {lon}, {lat}")
    return f"h{h:02d}v{v:02d}"


def route_tiles(route: dict) -> list[str]:
    points = [(float(lon), float(lat)) for lat, lon in route["route_coordinates"]]
    centres = []
    for a, b in zip(points, points[1:]):
        n = max(1, math.ceil(distance_km(a, b) / SAMPLE_STEP_KM))
        centres.extend((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n))
    centres.append(points[-1])
    found = {tile(lon, lat) for lon, lat in centres}
    for lon, lat in centres:
        for step in range(round(360 / AZIMUTH_STEP_DEG)):
            bearing = step * AZIMUTH_STEP_DEG
            edge = destination(lon, lat, bearing, BUFFER_KM + COVERAGE_MARGIN_KM)
            found.add(tile(*edge))
    return sorted(found)


def main() -> int:
    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    route_rows = []
    all_tiles: set[str] = set()
    for route in geometry["fire_route_geometries"]:
        tiles = route_tiles(route)
        all_tiles.update(tiles)
        route_rows.append({"route": route["name"], "geometry_sha256": route["geometry_sha256"],
                           "vertices": len(route["route_coordinates"]), "tiles": tiles})
    report = {
        "experiment_id": "viirs-daily-l3-candidate-audit-2026-10-23",
        "status": "metadata_candidate_requires_pilot_download_and_scene_decode",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "target": "Quality-screened VIIRS fire-mask detection in a 1-km route buffer during the next UTC day; not exact ignition prediction.",
        "source_geometry": {"path": GEOMETRY.relative_to(ROOT).as_posix(), "sha256": digest(GEOMETRY), "route_count": len(route_rows)},
        "spatial_sampling": {
            "buffer_radius_km": BUFFER_KM, "coverage_margin_km": COVERAGE_MARGIN_KM,
            "route_sample_step_km": SAMPLE_STEP_KM,
            "buffer_azimuth_step_degrees": AZIMUTH_STEP_DEG,
            "projection": "MODIS sinusoidal grid: x=R*longitude_radians*cos(latitude_radians), y=R*latitude_radians; tile indices use the official h/v origins and tile width.",
            "unique_tiles": sorted(all_tiles), "unique_tile_count": len(all_tiles), "routes": route_rows,
        },
        "products": PRODUCTS,
        "product_metadata": {
            "grid_resolution_m": 1000, "composite_period_hours": 24,
            "source_fire_pixel_resolution_m": 750, "layers": ["FireMask", "MaxFRP", "QA", "sample"],
            "fire_mask": {"0": "not processed / no data or poor quality", "1": "bowtie deletion",
                          "2": "unused", "3": "water", "4": "cloud", "5": "land/no fire class assigned",
                          "6": "unclassified", "7": "low-confidence fire", "8": "nominal-confidence fire",
                          "9": "high-confidence fire"},
            "qa_note": "QA includes land/water and day/night fields; it is not ground truth.",
        },
        "local_acquisition_status": {"granules_downloaded": 0, "scenes_decoded": 0, "model_metrics_created": False},
        "next_test": [
            "Download a small set of daily tiles for independent SNMF event dates and candidate clear-land days.",
            "Verify exact date, tile, product version, hashes, FireMask and QA against the official product guide.",
            "Keep classes 0-4 and 6, missing granules and incomplete observation as unknown; class 5 is only an observed composite non-detection.",
            "If the pilot passes, forecast next-day detections using only weather forecasts issued before the UTC day and test on untouched seasons.",
        ],
        "limitations": [
            "A 24-hour composite cannot validate hourly warning lead time or ignition time.",
            "The 1-km grid is coarser than the 375-m I-band product.",
            "Satellite fire detections are not independently confirmed wildfire events; SNMF/field records are still needed for that claim.",
            "Clear-land non-detection cannot rule out small fires, cloud/smoke-obscured fires or fires between overpasses.",
        ],
        "synthetic_observations": 0, "deployment_approved": False,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": OUT.relative_to(ROOT).as_posix(), "tile_count": len(all_tiles),
                      "tiles": sorted(all_tiles), "status": report["status"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
