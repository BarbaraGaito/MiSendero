#!/usr/bin/env python3
"""Audit daily VIIRS L3 masks around independently reported SNMF route events.

This is an observation/corroboration audit, not a fire forecast evaluation.
Only class 5 on land is counted as observed clear-land non-detection; all
unprocessed, water, cloud, and unknown mask states remain unknown.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from audit_viirs_daily_l3_candidate import SIN_R, tile
from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
COHORT = BASE / "fire-viirs-daily-l3-event-cohort-2023-2025.json"
MANIFEST = ROOT / "training/data/environmental/private/viirs-daily-l3-snmf-route-events-2023-2025/acquisition-manifest.json"
DATA_DIR = MANIFEST.parent
GEOMETRY = ROOT / "training/data/environmental/private/fire-route-geometries.json"
OUT = BASE / "fire-viirs-daily-l3-snmf-event-audit-2023-2025.json"
OUT_MD = OUT.with_suffix(".md")
PUBLIC_MANIFEST = BASE / "fire-viirs-daily-l3-acquisition-manifest-2023-2025.json"
RADIUS_KM = 6371.0088
ROUTE_BUFFER_KM = 10.0
POINT_BUFFER_KM = 10.0
FIRE_CLASSES = (7, 8, 9)
PRODUCT_SENSOR = {"VNP14A1": "Suomi-NPP", "VJ114A1": "NOAA-20", "VJ214A1": "NOAA-21"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project(lon: float, lat: float) -> tuple[float, float]:
    latitude = math.radians(lat)
    return SIN_R * math.radians(lon) * math.cos(latitude), SIN_R * latitude


def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    phi1, phi2 = math.radians(lat1), np.radians(lat2)
    dphi = phi2 - phi1
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlon / 2) ** 2
    return 2 * RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def distance_to_polyline_km(lat: np.ndarray, lon: np.ndarray,
                            coordinates: list[list[float]]) -> np.ndarray:
    line = np.asarray(coordinates, dtype=np.float64)
    reference_lat = float(np.mean(line[:, 0]))
    scale_x = RADIUS_KM * math.cos(math.radians(reference_lat)) * math.pi / 180
    scale_y = RADIUS_KM * math.pi / 180
    line_x, line_y = line[:, 1] * scale_x, line[:, 0] * scale_y
    point_x, point_y = lon * scale_x, lat * scale_y
    start_x, start_y = line_x[:-1], line_y[:-1]
    delta_x, delta_y = np.diff(line_x), np.diff(line_y)
    length_sq = delta_x**2 + delta_y**2
    result = np.full(len(lat), np.inf, dtype=np.float64)
    for offset in range(0, len(lat), 8000):
        end = min(offset + 8000, len(lat))
        px, py = point_x[offset:end, None], point_y[offset:end, None]
        numerator = ((px - start_x[None, :]) * delta_x[None, :]
                     + (py - start_y[None, :]) * delta_y[None, :])
        fraction = np.clip(numerator / np.maximum(length_sq[None, :], 1e-18), 0.0, 1.0)
        dx = px - (start_x[None, :] + fraction * delta_x[None, :])
        dy = py - (start_y[None, :] + fraction * delta_y[None, :])
        result[offset:end] = np.sqrt(np.min(dx**2 + dy**2, axis=1))
    return result


def class_counts(mask: np.ndarray) -> dict[str, int]:
    return {str(code): int(np.count_nonzero(mask == code)) for code in range(10)}


def file_path(row: dict) -> Path:
    return DATA_DIR / row["product"] / str(row["year"]) / row["tile"] / f"{row['granule_id']}.h5"


def load_and_check(row: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    path = file_path(row)
    if not path.is_file() or path.stat().st_size != row.get("bytes") or sha256(path) != row.get("sha256"):
        raise RuntimeError(f"VIIRS granule failed size/SHA-256 verification: {path.name}")
    with Dataset(path) as data:
        if (str(getattr(data, "ShortName", "")) != row["product"]
                or str(getattr(data, "VersionID", "")) != "002"
                or str(getattr(data, "RangeBeginningDate", "")) != row["date"]
                or str(getattr(data, "HORIZONTALTILENUMBER", "")) != row["tile"][1:3]
                or str(getattr(data, "VERTICALTILENUMBER", "")) != row["tile"][4:6]
                or str(getattr(data, "LocalGranuleID", "")) != f"{row['granule_id']}.h5"):
            raise RuntimeError(f"VIIRS product metadata mismatch: {path.name}")
        grid = data.groups["HDFEOS"].groups["GRIDS"].groups["VIIRS_Grid_Daily_Fire"]
        fields = grid.groups["Data Fields"]
        x = np.asarray(grid.variables["XDim"][:], dtype=np.float64)
        y = np.asarray(grid.variables["YDim"][:], dtype=np.float64)
        fire = np.asarray(fields.variables["FireMask"][:], dtype=np.uint8)
        qa = np.asarray(fields.variables["QA"][:], dtype=np.uint8)
        projection = fields.variables["Projection"]
        radius = float(getattr(projection, "earth_radius", 0))
    if (fire.shape != (1200, 1200) or qa.shape != fire.shape or len(x) != 1200 or len(y) != 1200
            or not np.all(np.diff(x) > 0) or not np.all(np.diff(y) < 0)
            or not math.isclose(radius, SIN_R, rel_tol=0, abs_tol=1e-3)):
        raise RuntimeError(f"Unexpected daily VIIRS grid structure: {path.name}")
    return x, y, fire, qa, {"path": path.relative_to(ROOT).as_posix(), "sha256": row["sha256"], "bytes": row["bytes"]}


def window_indices(axis: np.ndarray, low: float, high: float) -> np.ndarray:
    if axis[0] < axis[-1]:
        left = max(0, int(np.searchsorted(axis, low, side="left")) - 1)
        right = min(len(axis), int(np.searchsorted(axis, high, side="right")) + 1)
    else:
        descending = axis[::-1]
        left_r = max(0, int(np.searchsorted(descending, low, side="left")) - 1)
        right_r = min(len(axis), int(np.searchsorted(descending, high, side="right")) + 1)
        left, right = len(axis) - right_r, len(axis) - left_r
    return np.arange(left, right, dtype=np.int32)


def summarize_granule(row: dict, route: dict, event: dict) -> dict:
    x, y, fire, qa, source = load_and_check(row)
    px, py = project(float(event["longitude"]), float(event["latitude"]))
    point_col = int(np.argmin(np.abs(x - px)))
    point_row = int(np.argmin(np.abs(y - py)))
    point_tile = tile(float(event["longitude"]), float(event["latitude"]))
    point_in_tile = row["tile"] == point_tile
    point_mask = int(fire[point_row, point_col]) if point_in_tile else None
    point_qa = int(qa[point_row, point_col]) if point_in_tile else None
    point_land = point_in_tile and (point_qa & 0b11) == 0b10

    route_xy = np.asarray([project(float(lon), float(lat))
                           for lat, lon in route["route_coordinates"]], dtype=np.float64)
    margin_m = (ROUTE_BUFFER_KM + 1.5) * 1000
    cols = window_indices(x, float(route_xy[:, 0].min()) - margin_m,
                          float(route_xy[:, 0].max()) + margin_m)
    rows = window_indices(y, float(route_xy[:, 1].min()) - margin_m,
                          float(route_xy[:, 1].max()) + margin_m)
    grid_x, grid_y = np.meshgrid(x[cols], y[rows])
    lat = np.degrees(grid_y / SIN_R)
    cos_lat = np.cos(np.radians(lat))
    lon = np.degrees(grid_x / (SIN_R * cos_lat))
    local_mask = fire[np.ix_(rows, cols)]
    local_qa = qa[np.ix_(rows, cols)]
    route_distance = distance_to_polyline_km(lat.ravel(), lon.ravel(), route["route_coordinates"]).reshape(lat.shape)
    route_inside = route_distance <= ROUTE_BUFFER_KM
    route_counts = class_counts(local_mask[route_inside])
    route_land = (local_qa & 0b11) == 0b10
    observed_clear_land = route_inside & route_land & (local_mask == 5)
    route_fire = route_inside & np.isin(local_mask, FIRE_CLASSES)
    fire_rows, fire_cols = np.nonzero(route_fire)
    fire_distances_to_event = haversine_km(
        float(event["latitude"]), float(event["longitude"]), lat[fire_rows, fire_cols], lon[fire_rows, fire_cols]
    ) if len(fire_rows) else np.asarray([], dtype=np.float64)

    point_cols = window_indices(x, px - POINT_BUFFER_KM * 1000, px + POINT_BUFFER_KM * 1000)
    point_rows = window_indices(y, py - POINT_BUFFER_KM * 1000, py + POINT_BUFFER_KM * 1000)
    point_x, point_y = np.meshgrid(x[point_cols], y[point_rows])
    point_lat = np.degrees(point_y / SIN_R)
    point_lon = np.degrees(point_x / (SIN_R * np.cos(np.radians(point_lat))))
    point_mask_window = fire[np.ix_(point_rows, point_cols)]
    point_qa_window = qa[np.ix_(point_rows, point_cols)]
    point_distances = haversine_km(float(event["latitude"]), float(event["longitude"]),
                                   point_lat.ravel(), point_lon.ravel()).reshape(point_lat.shape)
    in_point_buffer = point_distances <= POINT_BUFFER_KM
    point_buffer_fire = in_point_buffer & np.isin(point_mask_window, FIRE_CLASSES)
    point_buffer_land_clear = (in_point_buffer & ((point_qa_window & 0b11) == 0b10)
                               & (point_mask_window == 5))
    return {
        "date": row["date"], "tile": row["tile"], "product": row["product"],
        "sensor": PRODUCT_SENSOR[row["product"]], "granule_id": row["granule_id"],
        "source": source,
        "event_point_nearest_grid_sample": {
            "tile_contains_event_coordinate": point_in_tile,
            "row": point_row if point_in_tile else None,
            "column": point_col if point_in_tile else None,
            "mask_class": point_mask,
            "qa": point_qa, "land_water_bits": point_qa & 0b11 if point_in_tile else None,
            "observed_clear_land_without_detection": bool(point_in_tile and point_mask == 5 and point_land),
            "fire_detection": bool(point_in_tile and point_mask in FIRE_CLASSES),
            "distance_from_event_to_sample_km": round(float(haversine_km(
                float(event["latitude"]), float(event["longitude"]),
                np.asarray([math.degrees(y[point_row] / SIN_R)]),
                np.asarray([math.degrees(x[point_col] / (SIN_R * math.cos(y[point_row] / SIN_R)))])
            )[0]), 4) if point_in_tile else None,
        },
        "within_10km_of_reported_event_point": {
            "fire_pixels_7_9": int(np.count_nonzero(point_buffer_fire)),
            "clear_land_class5_pixels": int(np.count_nonzero(point_buffer_land_clear)),
            "nearest_fire_pixel_distance_km": round(float(point_distances[point_buffer_fire].min()), 3)
            if np.any(point_buffer_fire) else None,
            "fire_pixels_by_confidence": {str(code): int(np.count_nonzero(point_buffer_fire & (point_mask_window == code)))
                                           for code in FIRE_CLASSES},
        },
        "within_10km_of_full_route_polyline": {
            "grid_samples": int(route_inside.sum()),
            "mask_class_counts": route_counts,
            "clear_land_class5_pixels": int(observed_clear_land.sum()),
            "fire_pixels_7_9": int(route_fire.sum()),
            "nearest_fire_pixel_to_reported_event_km": round(float(fire_distances_to_event.min()), 3)
            if len(fire_distances_to_event) else None,
            "fire_pixels_by_confidence": {str(code): int(np.count_nonzero(route_inside & (local_mask == code)))
                                           for code in FIRE_CLASSES},
        },
        "daily_composite_window": "UTC date in RangeBeginningDate; 24-hour daily composite, not an exact ignition/pass time",
    }


def main() -> int:
    cohort_payload = json.loads(COHORT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    geometry_payload = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    geometry = {row["name"]: row for row in geometry_payload["fire_route_geometries"]}
    tiles_payload = json.loads((BASE / "fire-viirs-daily-l3-candidate-audit-2026-10-23.json").read_text(encoding="utf-8"))
    tiles_by_route = {row["route"]: row["tiles"] for row in tiles_payload["spatial_sampling"]["routes"]}
    if manifest.get("planned_granules") != len(manifest.get("granules", [])):
        raise RuntimeError("Acquisition manifest is incomplete; refusing to label a partial cohort.")
    if any(row.get("status") not in {"downloaded", "present"} for row in manifest["granules"]):
        raise RuntimeError("Acquisition manifest contains an unverified or missing download.")
    public_manifest = {
        "experiment_id": "viirs-daily-l3-snmf-route-events-2023-2025",
        "source_private_manifest_sha256": sha256(MANIFEST),
        "cmr_response_sha256": manifest.get("cmr_response_sha256", {}),
        "granules": [
            {key: row.get(key) for key in (
                "date", "year", "doy", "tile", "product", "granule_id",
                "reported_size_mb", "cmr_updated", "status", "bytes", "sha256",
            )}
            for row in sorted(manifest["granules"], key=lambda item: (item["date"], item["tile"], item["product"]))
        ],
        "synthetic_observations": 0,
    }
    PUBLIC_MANIFEST.write_text(json.dumps(public_manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    granules = {(row["date"], row["tile"], row["product"]): row for row in manifest["granules"]}
    if len(granules) != len(manifest["granules"]):
        raise RuntimeError("Duplicate date/tile/product records in acquisition manifest.")

    event_rows = []
    files_checked = {}
    for event in cohort_payload["cohort"]:
        route = geometry[event["route"]]
        route_tiles = tiles_by_route[event["route"]]
        point_tile = tile(float(event["longitude"]), float(event["latitude"]))
        product_observations = []
        for route_tile in route_tiles:
            for product in sorted(PRODUCT_SENSOR):
                row = granules.get((event["reported_start_date"], route_tile, product))
                if row is None:
                    raise RuntimeError(f"Missing expected granule for {event['reported_start_date']} {route_tile} {product}.")
                observation = summarize_granule(row, route, event)
                product_observations.append(observation)
                files_checked[row["granule_id"]] = row["sha256"]
        route_fire_count = sum(obs["within_10km_of_full_route_polyline"]["fire_pixels_7_9"]
                               for obs in product_observations)
        route_clear_count = sum(obs["within_10km_of_full_route_polyline"]["clear_land_class5_pixels"]
                                for obs in product_observations)
        point_fire_count = sum(obs["within_10km_of_reported_event_point"]["fire_pixels_7_9"]
                               for obs in product_observations)
        event_rows.append({
            "reported_start_date": event["reported_start_date"], "route": event["route"],
            "incident_names": event["source_name_variants_collapsed"],
            "incident_status_in_source": event.get("status_in_source_snapshot"),
            "incident_coordinates": {"latitude": event["latitude"], "longitude": event["longitude"]},
            "reported_point_distance_to_route_km": event["distance_to_route_km"],
            "incident_point_tile": point_tile,
            "incident_point_tile_in_acquisition": point_tile in route_tiles,
            "route_tile_count": len(route_tiles),
            "granules": product_observations,
            "summary_across_sensors_not_independent": {
                "daily_l3_fire_pixels_within_10km_full_route": route_fire_count,
                "daily_l3_class5_land_pixels_within_10km_full_route": route_clear_count,
                "daily_l3_fire_pixels_within_10km_reported_point": point_fire_count,
                "sensors_with_fire_near_reported_point": sorted({
                    obs["sensor"] for obs in product_observations
                    if obs["within_10km_of_reported_event_point"]["fire_pixels_7_9"]
                }),
                "interpretation": "Counts across sensors and nearby route-events can duplicate a single physical fire and are not independent trials.",
            },
        })

    by_sensor = {}
    for product, sensor in PRODUCT_SENSOR.items():
        rows = [obs for event in event_rows for obs in event["granules"] if obs["product"] == product]
        by_sensor[sensor] = {
            "granule_event_observations": len(rows),
            "event_point_cells_class5_land": sum(obs["event_point_nearest_grid_sample"]["observed_clear_land_without_detection"] for obs in rows),
            "event_point_cells_fire": sum(obs["event_point_nearest_grid_sample"]["fire_detection"] for obs in rows),
            "event_points_within_10km_fire_pixels": sum(obs["within_10km_of_reported_event_point"]["fire_pixels_7_9"] > 0 for obs in rows),
            "route_buffers_with_fire_pixels": sum(obs["within_10km_of_full_route_polyline"]["fire_pixels_7_9"] > 0 for obs in rows),
            "route_buffers_with_class5_land_pixels": sum(obs["within_10km_of_full_route_polyline"]["clear_land_class5_pixels"] > 0 for obs in rows),
        }
    route_date_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for event in event_rows:
        route_date_groups[(event["reported_start_date"], event["route"])].append(event)
    route_date_results = []
    for (event_date, route_name), events in sorted(route_date_groups.items()):
        all_observations = [obs for event in events for obs in event["granules"]]
        detecting_sensors = sorted({
            obs["sensor"] for obs in all_observations
            if obs["within_10km_of_reported_event_point"]["fire_pixels_7_9"] > 0
        })
        route_date_results.append({
            "reported_start_date": event_date,
            "route": route_name,
            "snmf_event_clusters": len(events),
            "sensors_with_same_day_fire_detection_within_10km_of_reported_point": detecting_sensors,
            "same_day_detection_coincidence": bool(detecting_sensors),
            "exact_event_point_cells_class5_land_all_sensors": all(
                obs["event_point_nearest_grid_sample"]["observed_clear_land_without_detection"]
                for obs in all_observations
            ),
            "interpretation": "No nearby VIIRS detection is not a verified no-fire label; this route-date is a positive-event corroboration result only.",
        })
    route_dates_with_detection = sum(row["same_day_detection_coincidence"] for row in route_date_results)
    source_paths = [COHORT, MANIFEST, PUBLIC_MANIFEST, GEOMETRY,
                    BASE / "fire-viirs-daily-l3-candidate-audit-2026-10-23.json"]
    total_bytes = sum(int(row["bytes"]) for row in manifest["granules"])
    report = {
        "experiment_id": "viirs-daily-l3-snmf-route-events-2023-2025",
        "status": "observed_masks_audited_positive_event_only_cohort",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "target": "Independent positive-event corroboration and observed-mask coverage around Argentine trekking route corridors; not an ignition or advance fire-risk prediction.",
        "protocol": {
            "event_source": "Official SNMF reported events, deduplicated by date/route/coordinate cluster; 10 km route buffer.",
            "products": "VNP14A1.002, VJ114A1.002, VJ214A1.002 daily 1 km VIIRS fire-mask composites.",
            "spatial_coordinates": "Use the product's XDim/YDim projection-coordinate vectors with its sinusoidal projection and earth radius; nearest grid sample for incident point and full-polyline buffer extraction.",
            "fire_label": "FireMask 7-9; confidence class retained separately.",
            "observed_clear_non_detection": "FireMask 5 and QA land/water bits 0-1 equal 10 (land).",
            "unknown_labels": "Mask classes 0-4 and 6, missing tiles, QA coast/water/missing, and incomplete coverage are not converted to negative labels.",
            "independence": "Sensor products for one date/event and multiple report records may observe the same physical event; no precision confidence interval or model score is estimated.",
        },
        "acquisition": {
            "granules_expected_and_verified": len(manifest["granules"]),
            "unique_event_dates": len({row["date"] for row in manifest["granules"]}),
            "unique_date_tile_pairs": len({(row["date"], row["tile"]) for row in manifest["granules"]}),
            "bytes_verified": total_bytes,
            "size_mb_decimal": round(total_bytes / 1_000_000, 3),
            "granule_sha256_by_id": files_checked,
        },
        "coverage_by_sensor": by_sensor,
        "selected_route_event_clusters": len(event_rows),
        "route_date_positive_event_coincidence": {
            "route_dates_with_snmf_event_cluster": len(route_date_results),
            "route_dates_with_same_day_viirs_fire_detection_within_10km_of_report_point": route_dates_with_detection,
            "descriptive_event_coincidence_fraction": route_dates_with_detection / len(route_date_results) if route_date_results else None,
            "route_dates_without_nearby_detection_are_not_negative_labels": len(route_date_results) - route_dates_with_detection,
            "route_dates_with_all_event_point_cells_observed_class5_land_in_each_sensor": sum(
                row["exact_event_point_cells_class5_land_all_sensors"] for row in route_date_results
            ),
            "route_date_results": route_date_results,
            "warning": "This is a selected positive-event corroboration fraction, not model precision, recall against all physical fires, or a rate of false negatives. Route-date observations are not guaranteed independent physical incidents.",
        },
        "event_rows": event_rows,
        "sources": {path.relative_to(ROOT).as_posix(): sha256(path) for path in source_paths},
        "product_documentation": {
            "nasa_viirs_active_fire_user_guide": "https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf",
            "nasa_laads_vnp14a1_hdf5_file_specification": "https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14A1",
            "doi_by_product": {
                "VNP14A1": "https://doi.org/10.5067/VIIRS/VNP14A1.002",
                "VJ114A1": "https://doi.org/10.5067/VIIRS/VJ114A1.002",
                "VJ214A1": "https://doi.org/10.5067/VIIRS/VJ214A1.002",
            },
        },
        "synthetic_observations": 0,
        "deployment_approved": False,
        "limitations": [
            "The event cohort contains reported positives only; it cannot estimate alert precision, specificity, or false-alarm rate.",
            "A daily composite has no exact overpass or ignition time and may include a fire detected before or after the reported start date.",
            "An SNMF coordinate near a route is not proof the fire affected the trail; incident coordinates may be approximate.",
            "Class 5 describes a clear-land non-detection in the composite cell, not proof of no physical fire in the wider route buffer.",
            "Repeated satellite detections and product sensors are not independent physical-fire events.",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# VIIRS diario frente a eventos SNMF cercanos a senderos (2023–2025)", "",
        f"Se verificaron por SHA-256 **{len(manifest['granules'])} granulos** ({total_bytes / 1_000_000:.2f} MB) de VNP14A1, VJ114A1 y VJ214A1 para **{len(event_rows)} clusters reportados** en {len(route_date_results)} fechas-ruta y {len({r['reported_start_date'] for r in event_rows})} fechas distintas.", "",
        "La máscara 7–9 se conserva como detección térmica VIIRS; la clase 5 con QA de tierra es una celda terrestre observada sin detección en el compuesto diario. Nubes, agua, clases no procesadas o desconocidas siguen siendo desconocidas.", "",
        "| Sensor | Eventos con clase 5 en celda de coordenada | Celda de coordenada con fuego | Eventos con fuego a 10 km de coordenada | Buffers de ruta con fuego | Buffers con clase 5 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for sensor, summary in by_sensor.items():
        lines.append(f"| {sensor} | {summary['event_point_cells_class5_land']} | {summary['event_point_cells_fire']} | {summary['event_points_within_10km_fire_pixels']} | {summary['route_buffers_with_fire_pixels']} | {summary['route_buffers_with_class5_land_pixels']} |")
    lines += [
        "", f"Agrupando los dos clusters del mismo día y ruta, hubo detecciones VIIRS clase 7–9 a menos de 10 km de la coordenada reportada en **{route_dates_with_detection}/{len(route_date_results)} fechas-ruta** ({100*route_dates_with_detection/len(route_date_results):.1f}% de coincidencia descriptiva). Las celdas exactas de las coordenadas reportadas fueron clase 5 terrestre en los tres sensores en las {sum(r['exact_event_point_cells_class5_land_all_sensors'] for r in route_date_results)} fechas-ruta. Esto muestra que la coordenada del parte no coincide necesariamente con el píxel de fuego y que el radio de búsqueda importa.", "",
        "La cohorte solo contiene positivos candidatos del SNMF; por eso esta fracción no es precisión, sensibilidad frente a todos los incendios, tasa de falsas alarmas ni desempeño predictivo. Las fechas sin detección cercana siguen siendo desconocidas, aunque la celda reportada haya sido clase 5. Los compuestos diarios no identifican hora de ignición, y varios sensores o reportes pueden corresponder al mismo incendio. No se crearon datos sintéticos ni etiquetas negativas.", "",
        "Definiciones del producto: [guía oficial NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf) y [especificación HDF5 NASA LAADS](https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14A1).",
        "",
        f"Resultados reproducibles: [{OUT.name}]({OUT.name}); [manifiesto de adquisición con hashes](fire-viirs-daily-l3-acquisition-manifest-2023-2025.json); auditor: [`audit_viirs_daily_l3_snmf_route_events.py`](../../training/python/audit_viirs_daily_l3_snmf_route_events.py).",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": OUT.relative_to(ROOT).as_posix(), "markdown": OUT_MD.relative_to(ROOT).as_posix(),
                      "granules_verified": len(manifest["granules"]), "events": len(event_rows),
                      "total_bytes": total_bytes, "coverage_by_sensor": by_sensor,
                      "route_dates": len(route_date_results), "route_dates_with_detection": route_dates_with_detection,
                      "synthetic_observations": 0, "deployment_approved": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
