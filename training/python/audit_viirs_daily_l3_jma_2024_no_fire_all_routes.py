#!/usr/bin/env python3
"""Audit VIIRS observations across all Argentine routes on 2024 SNMF no-fire days."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from audit_viirs_daily_l3_candidate import SIN_R
from audit_viirs_daily_l3_explicit_no_fire_2023 import axis_window, distance_to_polyline_km, project
from acquire_viirs_daily_l3_jma_2024_no_fire_all_routes import (
    MANIFEST,
    MODEL_TEST,
    NO_FIRE_AUDIT,
    TILE_AUDIT,
    THRESHOLD,
    expected_items,
)
from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
OUT = BASE / "fire-viirs-jma-2024-explicit-no-fire-all-routes.json"
OUT_MD = OUT.with_suffix(".md")
PUBLIC_MANIFEST = BASE / "fire-viirs-daily-l3-jma-2024-no-fire-all-routes-manifest.json"
DATA_DIR = MANIFEST.parent
ROUTE_BUFFER_KM = 10.0
FIRE_CLASSES = (7, 8, 9)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_route(row: dict, route: dict, data_dir: Path = DATA_DIR) -> dict:
    path = data_dir / row["product"] / str(row["year"]) / row["tile"] / f"{row['granule_id']}.h5"
    if not path.is_file() or path.stat().st_size != row.get("bytes") or sha256(path) != row.get("sha256"):
        raise RuntimeError(f"VIIRS file failed size/SHA-256 check: {path.name}")
    with Dataset(path) as ds:
        if (str(getattr(ds, "ShortName", "")) != row["product"]
                or str(getattr(ds, "VersionID", "")) != "002"
                or str(getattr(ds, "RangeBeginningDate", "")) != row["date"]
                or str(getattr(ds, "HORIZONTALTILENUMBER", "")) != row["tile"][1:3]
                or str(getattr(ds, "VERTICALTILENUMBER", "")) != row["tile"][4:6]
                or str(getattr(ds, "LocalGranuleID", "")) != f"{row['granule_id']}.h5"):
            raise RuntimeError(f"VIIRS metadata does not match expected date/tile: {path.name}")
        grid = ds.groups["HDFEOS"].groups["GRIDS"].groups["VIIRS_Grid_Daily_Fire"]
        fields = grid.groups["Data Fields"]
        x = np.asarray(grid.variables["XDim"][:], dtype=np.float64)
        y = np.asarray(grid.variables["YDim"][:], dtype=np.float64)
        fire = np.asarray(fields.variables["FireMask"][:], dtype=np.uint8)
        qa = np.asarray(fields.variables["QA"][:], dtype=np.uint8)
        radius = float(getattr(fields.variables["Projection"], "earth_radius", 0))
    if fire.shape != (1200, 1200) or qa.shape != fire.shape or len(x) != 1200 or len(y) != 1200:
        raise RuntimeError(f"Unexpected VIIRS L3 dimensions: {path.name}")
    if not (np.all(np.diff(x) > 0) and np.all(np.diff(y) < 0)
            and math.isclose(radius, SIN_R, rel_tol=0, abs_tol=1e-3)):
        raise RuntimeError(f"Unexpected VIIRS sinusoidal grid: {path.name}")

    coordinates = route["route_coordinates"]
    route_xy = np.asarray([project(float(lon), float(lat)) for lat, lon in coordinates])
    margin = (ROUTE_BUFFER_KM + 1.5) * 1000
    cols = axis_window(x, float(route_xy[:, 0].min()) - margin, float(route_xy[:, 0].max()) + margin)
    rows = axis_window(y, float(route_xy[:, 1].min()) - margin, float(route_xy[:, 1].max()) + margin)
    xx, yy = np.meshgrid(x[cols], y[rows])
    lat = np.degrees(yy / SIN_R)
    lon = np.degrees(xx / (SIN_R * np.cos(np.radians(lat))))
    fire_window = fire[np.ix_(rows, cols)]
    qa_window = qa[np.ix_(rows, cols)]
    distance = distance_to_polyline_km(lat.ravel(), lon.ravel(), coordinates).reshape(lat.shape)
    inside = distance <= ROUTE_BUFFER_KM
    detections = inside & np.isin(fire_window, FIRE_CLASSES)
    clear_land = inside & ((qa_window & 0b11) == 0b10) & (fire_window == 5)
    classes = {str(code): int(np.count_nonzero(inside & (fire_window == code))) for code in range(10)}
    fixed_alert = next((item for item in row["fixed_threshold_alerts"] if item["route"] == route["name"]), None)
    return {
        "date": row["date"],
        "route": route["name"],
        "fixed_diagnostic_alert_at_0_1": fixed_alert is not None,
        "frozen_model_score": fixed_alert["score"] if fixed_alert else None,
        "granule_id": row["granule_id"],
        "tile": row["tile"],
        "within_10km_full_route_polyline": {
            "grid_sample_count": int(inside.sum()),
            "fire_mask_class_counts": classes,
            "fire_pixels_7_9": int(detections.sum()),
            "clear_land_class5_pixels_with_qa_land": int(clear_land.sum()),
            "any_viirs_fire_detection": bool(detections.any()),
            "interpretation": "Class 5 with QA land is a partially observed non-detection; it does not certify the route buffer as fire-free.",
        },
        "granule_sha256": row["sha256"],
    }


def adjacent_date_clusters(days: list[str]) -> int:
    clusters = 0
    previous = None
    for value in sorted(date.fromisoformat(day) for day in set(days)):
        if previous is None or (value - previous).days > 1:
            clusters += 1
        previous = value
    return clusters


def main() -> int:
    no_fire = json.loads(NO_FIRE_AUDIT.read_text(encoding="utf-8"))
    model = json.loads(MODEL_TEST.read_text(encoding="utf-8"))
    tile_audit = json.loads(TILE_AUDIT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") not in ("downloaded", "partial_downloaded"):
        raise RuntimeError("VIIRS acquisition is not complete or explicitly partial.")
    items = expected_items()
    if manifest.get("requested_date_tile_pairs") != len(items):
        raise RuntimeError("Acquisition manifest does not match the expected 2024 route-date cohort.")
    available = {(row["date"], row["tile"]): row for row in manifest["granules"]}
    unresolved = {(row["date"], row["tile"]): row for row in manifest["unresolved_date_tile_batches"]}
    expected_keys = {(row["date"], row["tile"]) for row in items}
    if set(available) | set(unresolved) != expected_keys or set(available) & set(unresolved):
        raise RuntimeError("Manifest does not account for every requested tile/date exactly once.")

    geometry_data = json.loads((ROOT / "training/data/environmental/private/fire-route-geometries.json").read_text(encoding="utf-8"))
    geometries = {row["name"]: row for row in geometry_data["fire_route_geometries"]}
    routes_by_tile: dict[str, set[str]] = {}
    for row in tile_audit["spatial_sampling"]["routes"]:
        routes_by_tile.setdefault(row["tiles"][0], set()).add(row["route"])
    route_results = []
    checked = {}
    for item in items:
        granule = available.get((item["date"], item["tile"]))
        if granule is None:
            continue
        for route_name in item["routes"]:
            if route_name not in geometries or route_name not in routes_by_tile[granule["tile"]]:
                raise RuntimeError("Route geometry and audited tile mapping do not match.")
            route_results.append(audit_route(granule, geometries[route_name]))
        checked[granule["granule_id"]] = granule["sha256"]

    expected_dates = sorted({row["date"] for row in items})
    expected_routes = sorted({route for row in tile_audit["spatial_sampling"]["routes"] for route in [row["route"]]})
    all_report_dates = sorted({row["report_date_in_archive"] for row in no_fire["verified_explicit_no_fire_reports"]
                               if row["report_date_in_archive"].startswith("2024-")})
    missing_route_days = [
        {"date": day, "route": route, "reason": "No requested VIIRS granule was returned by CMR for this date/tile."}
        for day, tile in sorted(unresolved)
        for route in unresolved[(day, tile)]["routes"]
    ]
    alerts = [alert for row in items for alert in row["fixed_threshold_alerts"]]
    alert_results = [row for row in route_results if row["fixed_diagnostic_alert_at_0_1"]]
    nonalert_results = [row for row in route_results if not row["fixed_diagnostic_alert_at_0_1"]]
    detections = [row for row in route_results if row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]]
    clear = [row for row in route_results if row["within_10km_full_route_polyline"]["clear_land_class5_pixels_with_qa_land"] > 0]
    alert_detections = [row for row in alert_results if row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]]
    nonalert_detections = [row for row in nonalert_results if row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]]
    public_manifest = {
        "experiment_id": manifest["experiment_id"],
        "model_test_sha256": manifest["model_test_sha256"],
        "no_fire_report_audit_sha256": manifest["no_fire_report_audit_sha256"],
        "route_tile_audit_sha256": manifest["route_tile_audit_sha256"],
        "cmr_response_sha256_by_date": manifest["cmr_response_sha256_by_date"],
        "requested_date_tile_pairs": manifest["requested_date_tile_pairs"],
        "unresolved_date_tile_batches": manifest["unresolved_date_tile_batches"],
        "granules": [{key: row.get(key) for key in (
            "date", "year", "doy", "tile", "product", "granule_id", "reported_size_mb", "cmr_updated",
            "status", "bytes", "sha256", "routes", "fixed_threshold_alerts")}
            for row in sorted(manifest["granules"], key=lambda value: (value["date"], value["tile"]))],
        "synthetic_observations": 0,
    }
    PUBLIC_MANIFEST.write_text(json.dumps(public_manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    total_bytes = sum(row["bytes"] for row in manifest["granules"])
    sources = [MODEL_TEST, NO_FIRE_AUDIT, TILE_AUDIT,
               ROOT / "training/data/environmental/private/fire-route-geometries.json", MANIFEST, PUBLIC_MANIFEST]
    results_by_date = {
        day: sum(row["date"] == day for row in route_results)
        for day in expected_dates
    }
    missing_by_date: dict[str, set[str]] = {}
    for missing_day, missing_tile in unresolved:
        missing_by_date.setdefault(missing_day, set()).add(missing_tile)
    expected_tiles = {row["tile"] for row in items}
    dates_without_any_matching_tile = sorted(
        day for day, missing_tiles in missing_by_date.items() if missing_tiles >= expected_tiles
    )
    report = {
        "experiment_id": "viirs-daily-l3-jma-2024-explicit-no-fire-all-route-days",
        "status": "independent_observation_audit_complete_with_cmr_gaps",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "protocol": {
            "cohort": "Every route listed in the audited route-tile file on each hash-verified SNMF explicit national no-fire report date in 2024.",
            "no_fire_source": "SNMF explicitly said no fires were reported nationally; this is an administrative report status, not physical no-fire truth.",
            "independent_observation": "Suomi-NPP VIIRS VNP14A1.002 daily L3 FireMask and QA at nominal 1 km.",
            "spatial_unit": "All pixels within 10 km of each complete route polyline.",
            "detection_classes": list(FIRE_CLASSES),
            "clear_land_rule": "FireMask class 5 and QA bits 0-1 equal 10.",
            "model_alignment": f"Whether the frozen JMA model emitted an alert at the pre-existing diagnostic threshold {THRESHOLD}; no score or threshold was tuned using VIIRS.",
            "threshold_is_calibrated_probability": False,
        },
        "cohort": {
            "explicit_no_fire_report_dates": len(all_report_dates),
            "adjacent_date_clusters": adjacent_date_clusters(all_report_dates),
            "requested_route_days": len(expected_dates) * len(expected_routes),
            "observed_route_days": len(route_results),
            "unobserved_route_days": len(missing_route_days),
            "routes": expected_routes,
            "dates_without_any_matching_cmr_tile": dates_without_any_matching_tile,
            "observed_routes_per_date": results_by_date,
        },
        "acquisition": {
            "requested_date_tile_pairs": manifest["requested_date_tile_pairs"],
            "verified_granules": len(manifest["granules"]),
            "unresolved_date_tile_pairs": len(unresolved),
            "bytes": total_bytes,
            "size_mb_decimal": round(total_bytes / 1_000_000, 3),
            "granule_sha256_by_id": checked,
            "unobserved_route_days": missing_route_days,
        },
        "observations": {
            "route_days_with_viirs_classes_7_9": len(detections),
            "route_days_with_some_class5_qa_land_sample": len(clear),
            "route_days_without_class5_qa_land_sample": len(route_results) - len(clear),
            "fixed_0_1_alert_route_days_observed": len(alert_results),
            "fixed_0_1_alert_route_days_unobserved": len(alerts) - len(alert_results),
            "fixed_0_1_alerts_with_viirs_classes_7_9": len(alert_detections),
            "fixed_0_1_alerts_with_some_class5_qa_land_sample": sum(
                row["within_10km_full_route_polyline"]["clear_land_class5_pixels_with_qa_land"] > 0
                for row in alert_results
            ),
            "non_alert_route_days_observed": len(nonalert_results),
            "non_alert_route_days_with_viirs_classes_7_9": len(nonalert_detections),
            "model_alert_alignment_is_predictive_validation": False,
        },
        "route_day_results": route_results,
        "sources": {path.relative_to(ROOT).as_posix(): sha256(path) for path in sources},
        "product_documentation": {
            "nasa_viirs_active_fire_user_guide": "https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf",
            "nasa_laads_vnp14a1_file_specification": "https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14A1",
        },
        "synthetic_observations": 0,
        "deployment_approved": False,
        "limitations": [
            "An explicit nationwide no-fire report describes what SNMF recorded; it does not verify physical absence.",
            "VIIRS active-fire class 7-9 is thermal-detection evidence, not adjudicated wildfire truth.",
            "Class 5 QA-land pixels are partial clear observations and do not certify an entire route buffer as fire-free.",
            "The daily 1 km composite can miss small, obscured, or between-overpass fires.",
            "CMR returned no exact VNP14A1 tile for two dates; their route-days are unknown, not negative.",
            "These selected report dates do not form a representative prevalence sample and cannot estimate model precision or recall.",
            "The JMA threshold 0.1 is diagnostic, and its model scores are not calibrated probabilities; this alignment is descriptive only.",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# VIIRS diario en las ocho rutas durante partes SNMF sin incendios reportados (2024)", "",
        f"Se auditaron {report['cohort']['observed_route_days']} de {report['cohort']['requested_route_days']} ruta-días posibles, usando {len(manifest['granules'])} granulas VNP14A1 descargadas y verificadas ({total_bytes / 1_000_000:.2f} MB). NASA CMR no devolvió un tile exacto en dos fechas; sus {len(missing_route_days)} ruta-días quedan desconocidos.", "",
        f"VIIRS mostró clase 7–9 en {len(detections)}/{len(route_results)} buffers observados. {len(clear)}/{len(route_results)} tuvieron alguna muestra clase 5 con QA de tierra, una observación parcial. Entre las alertas del modelo al umbral diagnóstico fijo de {THRESHOLD}, se observaron {len(alert_results)} y {len(alert_detections)} tuvieron detección VIIRS; los scores no son probabilidades calibradas.", "",
        "Los partes SNMF declaran que no se reportaron incendios, pero no certifican ausencia física. La falta de detecciones VIIRS tampoco es un negativo completo. Este análisis caracteriza la cobertura de observación y la correspondencia con un umbral diagnóstico; no mide precisión, recall ni validez de pronóstico.", "",
        "Ver el [JSON reproducible](fire-viirs-jma-2024-explicit-no-fire-all-routes.json), [manifiesto público de hashes](fire-viirs-daily-l3-jma-2024-no-fire-all-routes-manifest.json), [adquisidor](../../training/python/acquire_viirs_daily_l3_jma_2024_no_fire_all_routes.py) y [auditor](../../training/python/audit_viirs_daily_l3_jma_2024_no_fire_all_routes.py). Las clases y QA siguen la [guía NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf).", "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "output": OUT.relative_to(ROOT).as_posix(),
        "requested_route_days": report["cohort"]["requested_route_days"],
        "observed_route_days": len(route_results),
        "unobserved_route_days": len(missing_route_days),
        "verified_granules": len(manifest["granules"]),
        "route_days_with_viirs_fire_detection": len(detections),
        "route_days_with_class5_qa_land_sample": len(clear),
        "fixed_threshold_alerts_observed": len(alert_results),
        "fixed_threshold_alerts_with_viirs_detections": len(alert_detections),
        "synthetic_observations": 0,
        "deployment_approved": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
