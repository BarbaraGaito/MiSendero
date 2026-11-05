#!/usr/bin/env python3
"""Cross frozen 2024 JMA alerts with independent daily VIIRS L3 route observations."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from audit_viirs_daily_l3_explicit_no_fire_2023 import (
    ROUTE_BUFFER_KM,
    axis_window,
    distance_to_polyline_km,
    project,
)
from acquire_viirs_daily_l3_jma_2024_no_fire_alerts import (
    MANIFEST,
    MODEL_TEST,
    NO_FIRE_AUDIT,
    TILE_AUDIT,
    THRESHOLD,
    expected_items,
)
from audit_viirs_daily_l3_candidate import SIN_R
from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
OUT = BASE / "fire-viirs-jma-2024-explicit-no-fire-alert-crosscheck.json"
OUT_MD = OUT.with_suffix(".md")
PUBLIC_MANIFEST = BASE / "fire-viirs-daily-l3-jma-2024-no-fire-alerts-manifest.json"
RADIUS_KM = 6371.0088
FIRE_CLASSES = (7, 8, 9)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_granule(row: dict, route: dict, route_alerts: list[dict]) -> dict:
    data_dir = MANIFEST.parent
    path = data_dir / row["product"] / str(row["year"]) / row["tile"] / f"{row['granule_id']}.h5"
    if (not path.is_file() or path.stat().st_size != row.get("bytes")
            or sha256(path) != row.get("sha256")):
        raise RuntimeError(f"VIIRS file failed size/SHA-256 check: {path.name}")
    with Dataset(path) as ds:
        if (str(getattr(ds, "ShortName", "")) != "VNP14A1"
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
    mask = fire[np.ix_(rows, cols)]
    qa_window = qa[np.ix_(rows, cols)]
    distance = distance_to_polyline_km(lat.ravel(), lon.ravel(), coordinates).reshape(lat.shape)
    inside = distance <= ROUTE_BUFFER_KM
    land = (qa_window & 0b11) == 0b10
    clear_land = inside & land & (mask == 5)
    detections = inside & np.isin(mask, FIRE_CLASSES)
    class_counts = {str(code): int(np.count_nonzero(inside & (mask == code))) for code in range(10)}
    return {
        "date": row["date"],
        "route": route["name"],
        "frozen_jma_alert_scores": route_alerts,
        "granule_id": row["granule_id"],
        "tile": row["tile"],
        "within_10km_full_route_polyline": {
            "grid_sample_count": int(inside.sum()),
            "fire_mask_class_counts": class_counts,
            "fire_pixels_7_9": int(detections.sum()),
            "clear_land_class5_pixels_with_qa_land": int(clear_land.sum()),
            "non_clear_land_or_fire_samples": int(inside.sum() - clear_land.sum() - detections.sum()),
            "any_viirs_fire_detection": bool(detections.any()),
            "interpretation": "Class 5 with QA land is a partially observed clear-land non-detection, not proof the whole buffer was fire-free.",
        },
        "sha256": row["sha256"],
    }


def main() -> int:
    model = json.loads(MODEL_TEST.read_text(encoding="utf-8"))
    no_fire = json.loads(NO_FIRE_AUDIT.read_text(encoding="utf-8"))
    tile_audit = json.loads(TILE_AUDIT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") not in ("downloaded", "partial_downloaded"):
        raise RuntimeError("VIIRS acquisition is not complete or explicitly partial.")
    planned_items = expected_items()
    if manifest.get("requested_date_tile_pairs") != len(planned_items):
        raise RuntimeError("Acquisition manifest does not match the frozen alert cohort.")
    available = {(row["date"], row["tile"]): row for row in manifest["granules"]}
    expected_keys = {(row["date"], row["tile"]) for row in planned_items}
    unresolved = {(row["date"], row["tile"]): row for row in manifest["unresolved_date_tile_pairs"]}
    if set(available) | set(unresolved) != expected_keys or set(available) & set(unresolved):
        raise RuntimeError("Manifest does not account for each requested date/tile exactly once.")

    geometry_data = json.loads((ROOT / "training/data/environmental/private/fire-route-geometries.json").read_text(encoding="utf-8"))
    geometry = {row["name"]: row for row in geometry_data["fire_route_geometries"]}
    route_tile = {row["route"]: row["tiles"] for row in tile_audit["spatial_sampling"]["routes"]}
    route_day_results = []
    checked = {}
    for item in planned_items:
        row = available.get((item["date"], item["tile"]))
        if row is None:
            continue
        for alert in item["route_alerts"]:
            if item["tile"] not in route_tile[alert["route"]]:
                raise RuntimeError("Alert route does not match its audited tile.")
            summary = audit_granule(row, geometry[alert["route"]], [alert])
            route_day_results.append(summary)
        checked[row["granule_id"]] = row["sha256"]

    public_manifest = {
        "experiment_id": manifest["experiment_id"],
        "model_test_sha256": manifest["model_test_sha256"],
        "no_fire_report_audit_sha256": manifest["no_fire_report_audit_sha256"],
        "route_tile_audit_sha256": manifest["route_tile_audit_sha256"],
        "cmr_response_sha256_by_date_tile": manifest["cmr_response_sha256_by_date_tile"],
        "requested_date_tile_pairs": manifest["requested_date_tile_pairs"],
        "unresolved_date_tile_pairs": manifest["unresolved_date_tile_pairs"],
        "granules": [{key: row.get(key) for key in (
            "date", "year", "doy", "tile", "product", "granule_id", "reported_size_mb",
            "cmr_updated", "status", "bytes", "sha256", "route_alerts")}
            for row in sorted(manifest["granules"], key=lambda value: (value["date"], value["tile"]))],
        "synthetic_observations": 0,
    }
    PUBLIC_MANIFEST.write_text(json.dumps(public_manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    total_bytes = sum(row["bytes"] for row in manifest["granules"])
    alerts = [alert for item in planned_items for alert in item["route_alerts"]]
    observed_alerts = len(route_day_results)
    detected = [row for row in route_day_results if row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]]
    clear_observed = [row for row in route_day_results if row["within_10km_full_route_polyline"]["clear_land_class5_pixels_with_qa_land"] > 0]
    coverage_by_alert = []
    for item in planned_items:
        key = (item["date"], item["tile"])
        for alert in item["route_alerts"]:
            coverage_by_alert.append({
                "date": item["date"], "route": alert["route"], "score": alert["score"],
                "coverage_status": "unavailable_no_cmr_granule" if key in unresolved else "observed",
            })
    sources = [MODEL_TEST, NO_FIRE_AUDIT, TILE_AUDIT,
               ROOT / "training/data/environmental/private/fire-route-geometries.json", MANIFEST, PUBLIC_MANIFEST]
    result = {
        "experiment_id": "frozen-jma-2024-alerts-vs-viirs-daily-l3-explicit-no-fire-report-days",
        "status": "independent_crosscheck_complete_with_one_cmr_gap",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "protocol": {
            "frozen_model_test": MODEL_TEST.name,
            "source_negative_label": "SNMF explicitly reported no fires nationally on date; administrative-report negative only.",
            "independent_observation": "NASA Suomi-NPP VIIRS VNP14A1.002 daily L3 1 km FireMask and QA.",
            "route_spatial_unit": "10 km buffer around full route polyline; frozen model-alert route-days only.",
            "fire_observation": "FireMask classes 7-9; confidence class retained in per-pixel class counts.",
            "clear_land_observation": "FireMask class 5 with QA bits 0-1 equal 10.",
            "threshold": THRESHOLD,
            "threshold_selection": "Inherited fixed diagnostic threshold from the frozen JMA 2024 test; not tuned with VIIRS.",
            "threshold_is_calibrated_probability": False,
        },
        "acquisition": {
            "requested_route_alerts": len(alerts),
            "observed_route_alerts": observed_alerts,
            "unavailable_route_alerts": len(unresolved),
            "verified_granules": len(manifest["granules"]),
            "dates": sorted({row["date"] for row in route_day_results}),
            "unique_tiles": sorted({row["tile"] for row in manifest["granules"]}),
            "bytes": total_bytes,
            "size_mb_decimal": round(total_bytes / 1_000_000, 3),
            "granule_sha256_by_id": checked,
            "unresolved_date_tile_pairs": manifest["unresolved_date_tile_pairs"],
        },
        "coverage": {
            "route_alerts_with_any_viirs_fire_detection": len(detected),
            "route_alerts_with_at_least_one_class5_qa_land_sample": len(clear_observed),
            "route_alerts_without_class5_qa_land_sample": observed_alerts - len(clear_observed),
            "alert_rows_by_sensor_observation": coverage_by_alert,
            "full_sensor_observation_mask_available": False,
        },
        "route_alert_results": route_day_results,
        "sources": {path.relative_to(ROOT).as_posix(): sha256(path) for path in sources},
        "product_documentation": {
            "nasa_viirs_active_fire_user_guide": "https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf",
            "nasa_laads_vnp14a1_file_specification": "https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14A1",
        },
        "synthetic_observations": 0,
        "deployment_approved": False,
        "limitations": [
            "SNMF explicit no-fire reports describe the administrative record and do not prove physical absence.",
            "VIIRS classes 7-9 are independent thermal detections, not adjudicated wildfire truth.",
            "A daily 1 km composite can miss small, obscured, or between-overpass fires; class 5 is partial observation only.",
            "NASA CMR returned no VNP14A1.002 granule for one requested date/tile; that alert is unknown and excluded from observed counts.",
            "The cohort contains only frozen model alerts on selected report dates; it cannot estimate precision, recall, calibration, or forecast reliability.",
            "The 0.1 score threshold is diagnostic and the model scores are not calibrated probabilities.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# Cruce de alertas JMA 2024 con VIIRS en fechas SNMF sin incendios reportados", "",
        f"El test JMA congelado emitió {len(alerts)} alertas en fechas con parte nacional explícito sin incendios, al corte diagnóstico fijo de {THRESHOLD:.1f}. Se verificaron {len(manifest['granules'])} granulas VIIRS para {observed_alerts} alertas; una alerta de Condorito del 10/07/2024 quedó sin cobertura porque CMR no devolvió ese tile.", "",
        f"VIIRS encontró detecciones FireMask 7–9 en {len(detected)}/{observed_alerts} alertas observadas. {len(clear_observed)}/{observed_alerts} tuvieron al menos una muestra clase 5 con QA de tierra; la cobertura restante no debe interpretarse como ausencia de fuego.", "",
        "La detección térmica puede ser independiente y útil para contrastar, pero no adjudica incendios forestales. Los días sin detección no son negativos observados completos. El parte nacional tampoco demuestra ausencia física. Este cruce no estima precisión ni valida una predicción de ignición; el corte 0,1 es diagnóstico y los scores no son probabilidades calibradas.", "",
        "Los datos y hashes quedan en el manifiesto reproducible; el análisis usa el test JMA y las geometrías existentes sin reentrenar ni modificar umbrales. Ver el [resultado JSON](fire-viirs-jma-2024-explicit-no-fire-alert-crosscheck.json), el [manifiesto público](fire-viirs-daily-l3-jma-2024-no-fire-alerts-manifest.json), el [script de adquisición](../../training/python/acquire_viirs_daily_l3_jma_2024_no_fire_alerts.py) y el [auditor](../../training/python/audit_viirs_daily_l3_jma_2024_no_fire_alerts.py). Las clases siguen la [guía NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf).", "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "output": OUT.relative_to(ROOT).as_posix(),
        "requested_alerts": len(alerts),
        "observed_alerts": observed_alerts,
        "unavailable_alerts": len(unresolved),
        "alerts_with_viirs_detection": len(detected),
        "alerts_with_clear_land_sample": len(clear_observed),
        "bytes": total_bytes,
        "synthetic_observations": 0,
        "deployment_approved": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
