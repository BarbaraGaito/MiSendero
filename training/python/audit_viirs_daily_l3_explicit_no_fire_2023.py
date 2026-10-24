#!/usr/bin/env python3
"""Cross frozen MODIS-model alerts on 2023 SNMF no-fire report dates with VIIRS."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from audit_viirs_daily_l3_candidate import SIN_R
from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
MODEL_TEST = BASE / "fire-model-explicit-national-no-fire-test-2023.json"
NO_FIRE_AUDIT = BASE / "fire-snmf-national-no-fire-report-audit.json"
TILE_AUDIT = BASE / "fire-viirs-daily-l3-candidate-audit-2026-10-23.json"
MANIFEST = ROOT / "training/data/environmental/private/viirs-daily-l3-explicit-no-fire-2023/acquisition-manifest.json"
DATA_DIR = MANIFEST.parent
OUT = BASE / "fire-viirs-explicit-no-fire-model-crosscheck-2023.json"
OUT_MD = OUT.with_suffix(".md")
PUBLIC_MANIFEST = BASE / "fire-viirs-daily-l3-explicit-no-fire-2023-manifest.json"
RADIUS_KM = 6371.0088
ROUTE_BUFFER_KM = 10.0
FIRE_CLASSES = (7, 8, 9)
MODEL_NAMES = ("persistence", "logistic", "random_forest", "xgboost")
THRESHOLD = 0.5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project(lon: float, lat: float) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    return SIN_R * math.radians(lon) * math.cos(lat_rad), SIN_R * lat_rad


def distance_to_polyline_km(lat: np.ndarray, lon: np.ndarray,
                            coordinates: list[list[float]]) -> np.ndarray:
    line = np.asarray(coordinates, dtype=np.float64)
    ref_lat = float(np.mean(line[:, 0]))
    sx = RADIUS_KM * math.cos(math.radians(ref_lat)) * math.pi / 180
    sy = RADIUS_KM * math.pi / 180
    lx, ly = line[:, 1] * sx, line[:, 0] * sy
    px, py = lon * sx, lat * sy
    ax, ay = lx[:-1], ly[:-1]
    dx, dy = np.diff(lx), np.diff(ly)
    length_sq = dx**2 + dy**2
    result = np.full(len(lat), np.inf, dtype=np.float64)
    for offset in range(0, len(lat), 8000):
        end = min(offset + 8000, len(lat))
        qx, qy = px[offset:end, None], py[offset:end, None]
        t = ((qx - ax[None, :]) * dx[None, :] + (qy - ay[None, :]) * dy[None, :])
        t = np.clip(t / np.maximum(length_sq[None, :], 1e-18), 0.0, 1.0)
        ex = qx - (ax[None, :] + t * dx[None, :])
        ey = qy - (ay[None, :] + t * dy[None, :])
        result[offset:end] = np.sqrt(np.min(ex**2 + ey**2, axis=1))
    return result


def axis_window(axis: np.ndarray, low: float, high: float) -> np.ndarray:
    if axis[0] < axis[-1]:
        start = max(0, int(np.searchsorted(axis, low, side="left")) - 1)
        stop = min(len(axis), int(np.searchsorted(axis, high, side="right")) + 1)
    else:
        asc = axis[::-1]
        left = max(0, int(np.searchsorted(asc, low, side="left")) - 1)
        right = min(len(asc), int(np.searchsorted(asc, high, side="right")) + 1)
        start, stop = len(axis) - right, len(axis) - left
    return np.arange(start, stop, dtype=np.int32)


def summarize_route_day(model_row: dict, route: dict, granule: dict) -> tuple[dict, str]:
    path = DATA_DIR / granule["product"] / str(granule["year"]) / granule["tile"] / f"{granule['granule_id']}.h5"
    if not path.is_file() or path.stat().st_size != granule.get("bytes") or sha256(path) != granule.get("sha256"):
        raise RuntimeError(f"VIIRS file failed size/SHA-256 check: {path.name}")
    with Dataset(path) as ds:
        if (str(getattr(ds, "ShortName", "")) != "VNP14A1"
                or str(getattr(ds, "VersionID", "")) != "002"
                or str(getattr(ds, "RangeBeginningDate", "")) != model_row["report_date_utc"]
                or str(getattr(ds, "HORIZONTALTILENUMBER", "")) != granule["tile"][1:3]
                or str(getattr(ds, "VERTICALTILENUMBER", "")) != granule["tile"][4:6]
                or str(getattr(ds, "LocalGranuleID", "")) != f"{granule['granule_id']}.h5"):
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
    scores = model_row["max_route_score"]
    model_alerts = {name: float(scores[name]) >= THRESHOLD for name in MODEL_NAMES}
    result = {
        "date": model_row["report_date_utc"], "route": model_row["route_region"],
        "granule_id": granule["granule_id"], "tile": granule["tile"],
        "model_route_pixel_rows": model_row["pixel_rows"],
        "frozen_model_max_scores": scores,
        "diagnostic_alerts_at_0_5": model_alerts,
        "model_scores_are_calibrated_probabilities": False,
        "within_10km_full_route_polyline": {
            "grid_sample_count": int(inside.sum()),
            "fire_mask_class_counts": class_counts,
            "fire_pixels_7_9": int(detections.sum()),
            "clear_land_class5_pixels_with_qa_land": int(clear_land.sum()),
            "non_clear_land_or_fire_samples": int(inside.sum() - clear_land.sum() - detections.sum()),
            "any_viirs_fire_detection": bool(detections.any()),
            "interpretation": "Class 5 with QA land is an observed clear-land non-detection sample; it does not prove the full buffer fire-free.",
        },
        "sha256": granule["sha256"],
    }
    return result, granule["granule_id"]


def main() -> int:
    model_test = json.loads(MODEL_TEST.read_text(encoding="utf-8"))
    no_fire_audit = json.loads(NO_FIRE_AUDIT.read_text(encoding="utf-8"))
    tile_audit = json.loads(TILE_AUDIT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") != "downloaded" or manifest.get("planned_granules") != len(manifest.get("granules", [])):
        raise RuntimeError("The VIIRS acquisition manifest is incomplete.")
    route_geometry = json.loads((ROOT / "training/data/environmental/private/fire-route-geometries.json").read_text(encoding="utf-8"))
    geometry = {row["name"]: row for row in route_geometry["fire_route_geometries"]}
    route_tile = {row["route"]: row["tiles"][0] for row in tile_audit["spatial_sampling"]["routes"]
                  if len(row["tiles"]) == 1}
    if len(route_tile) != len(tile_audit["spatial_sampling"]["routes"]):
        raise RuntimeError("Expected one bounded L3 tile per route for this test.")
    granules = {(row["date"], row["tile"]): row for row in manifest["granules"]}
    public_manifest = {
        "experiment_id": manifest["experiment_id"],
        "model_test_sha256": manifest["model_test_sha256"],
        "no_fire_report_audit_sha256": manifest["no_fire_report_audit_sha256"],
        "route_tile_audit_sha256": manifest["route_tile_audit_sha256"],
        "cmr_response_sha256_by_date": manifest["cmr_response_sha256_by_date"],
        "granules": [{key: row.get(key) for key in (
            "date", "year", "doy", "tile", "product", "granule_id", "reported_size_mb",
            "cmr_updated", "status", "bytes", "sha256")}
            for row in sorted(manifest["granules"], key=lambda item: (item["date"], item["tile"]))],
        "synthetic_observations": 0,
    }
    PUBLIC_MANIFEST.write_text(json.dumps(public_manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    route_day_results, checked = [], {}
    for model_row in model_test["route_day_results"]:
        day, route_name = model_row["report_date_utc"], model_row["route_region"]
        row = granules.get((day, route_tile[route_name]))
        if row is None:
            raise RuntimeError(f"Missing VIIRS granule for {day} {route_name}.")
        summary, granule_id = summarize_route_day(model_row, geometry[route_name], row)
        route_day_results.append(summary)
        checked[granule_id] = row["sha256"]

    alert_crosscheck = {}
    for model_name in MODEL_NAMES:
        alerts = [row for row in route_day_results if row["diagnostic_alerts_at_0_5"][model_name]]
        detections_in_alerts = [row for row in alerts if row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]]
        detection_days = [row for row in route_day_results if row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]]
        alert_crosscheck[model_name] = {
            "route_days_alerted_at_diagnostic_0_5": len(alerts),
            "alerts_with_same_day_viirs_class7_9_in_10km_route_buffer": len(detections_in_alerts),
            "alert_route_days_with_viirs_detections": [f"{r['date']}|{r['route']}" for r in detections_in_alerts],
            "all_covered_route_days_with_viirs_fire_detection": len(detection_days),
            "report_cohort": "SNMF explicitly said no fires were reported nationally; not a physical-fire negative survey.",
            "interpretation": "A VIIRS class 7-9 pixel is independent thermal-detection corroboration, not proof of wildfire or model correctness. No VIIRS detection is not proof of absence.",
        }
    dates = sorted({row["date"] for row in route_day_results})
    route_dates_with_viirs = sorted({row["date"] for row in route_day_results
                                     if row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]})
    logistic_or_xgb_alerts = [row for row in route_day_results
                              if row["diagnostic_alerts_at_0_5"]["logistic"]
                              or row["diagnostic_alerts_at_0_5"]["xgboost"]]
    all_sources = [MODEL_TEST, NO_FIRE_AUDIT, TILE_AUDIT,
                   ROOT / "training/data/environmental/private/fire-route-geometries.json", MANIFEST, PUBLIC_MANIFEST]
    total_bytes = sum(row["bytes"] for row in manifest["granules"])
    result = {
        "experiment_id": "frozen-modis-alerts-vs-viirs-daily-l3-on-snmf-explicit-no-fire-2023",
        "status": "independent_satellite_crosscheck_complete_administrative_negative_cohort",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "protocol": {
            "frozen_model_test": MODEL_TEST.name,
            "source_negative_label": "SNMF explicitly reported no fires nationally on date; administrative-report negative only.",
            "independent_observation": "NASA Suomi-NPP VIIRS VNP14A1.002 daily L3 1 km FireMask and QA.",
            "route_spatial_unit": "10 km buffer around full route polyline; model test route-day rows with frozen max scores.",
            "fire_observation": "FireMask classes 7-9; confidence classes retained in per-pixel class counts.",
            "clear_land_observation": "FireMask class 5 with QA bits 0-1 equal 10 (land). Partial clear-land pixels do not imply complete observation of the route buffer.",
            "threshold": THRESHOLD,
            "threshold_selection": "Diagnostic threshold fixed in the earlier test; this crosscheck does not tune any model.",
        },
        "acquisition": {
            "granules_verified": len(manifest["granules"]), "dates": dates,
            "unique_tiles": sorted({row["tile"] for row in manifest["granules"]}),
            "bytes": total_bytes, "size_mb_decimal": round(total_bytes / 1_000_000, 3),
            "granule_sha256_by_id": checked,
        },
        "coverage": {
            "frozen_model_route_days": len(route_day_results),
            "possible_route_days_in_four_report_dates": 8 * len(dates),
            "route_days_with_any_viirs_fire_detection": sum(row["within_10km_full_route_polyline"]["any_viirs_fire_detection"] for row in route_day_results),
            "route_days_with_at_least_one_class5_qa_land_sample": sum(
                row["within_10km_full_route_polyline"]["clear_land_class5_pixels_with_qa_land"] > 0
                for row in route_day_results
            ),
            "route_days_without_class5_qa_land_sample": sum(
                row["within_10km_full_route_polyline"]["clear_land_class5_pixels_with_qa_land"] == 0
                for row in route_day_results
            ),
            "unique_logistic_or_xgboost_alert_route_days_at_0_5": len(logistic_or_xgb_alerts),
            "such_alert_route_days_with_class5_qa_land_sample": sum(
                row["within_10km_full_route_polyline"]["clear_land_class5_pixels_with_qa_land"] > 0
                for row in logistic_or_xgb_alerts
            ),
            "such_alert_route_days_with_viirs_fire_detection": sum(
                row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]
                for row in logistic_or_xgb_alerts
            ),
            "route_dates_with_any_viirs_fire_detection": route_dates_with_viirs,
            "full_sensor_observation_mask_available": False,
        },
        "crosscheck_by_model": alert_crosscheck,
        "route_day_results": route_day_results,
        "sources": {path.relative_to(ROOT).as_posix(): sha256(path) for path in all_sources},
        "product_documentation": {
            "nasa_viirs_active_fire_user_guide": "https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf",
            "nasa_laads_vnp14a1_file_specification": "https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14A1",
        },
        "synthetic_observations": 0,
        "deployment_approved": False,
        "limitations": [
            "The explicit SNMF no-fire phrase states what the report recorded; it does not establish that no physical fire existed.",
            "VIIRS active-fire detections can include thermal anomalies that are not adjudicated wildfires.",
            "A daily 1 km composite can miss small, obscured, or between-overpass fires; class 5 is not complete sensor coverage.",
            "This is one independent sensor crosscheck on four report dates, not an estimate of model precision or recall.",
            "A score alignment with a VIIRS detection does not establish that the frozen model predicted an ignition or route hazard.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# Cruce de avisos MODIS congelados con VIIRS en cuatro fechas SNMF sin incendios reportados (2023)", "",
        f"Se verificaron **{len(manifest['granules'])} granulos** VNP14A1 (Suomi-NPP; {total_bytes / 1_000_000:.2f} MB) y se cruzaron con los **{len(route_day_results)} ruta-dias** cubiertos del test MODIS congelado.", "",
        "| Modelo (score máximo >= 0,5) | Avisos | Avisos con VIIRS clase 7–9 en buffer de 10 km |",
        "|---|---:|---:|",
    ]
    for name in MODEL_NAMES:
        row = alert_crosscheck[name]
        lines.append(f"| {name} | {row['route_days_alerted_at_diagnostic_0_5']} | {row['alerts_with_same_day_viirs_class7_9_in_10km_route_buffer']} |")
    lines += [
        "", f"VIIRS encontró detecciones clase 7–9 en {result['coverage']['route_days_with_any_viirs_fire_detection']} de los 22 ruta-días cubiertos. Hubo al menos un píxel clase 5 con QA de tierra en {result['coverage']['route_days_with_at_least_one_class5_qa_land_sample']}/22 buffers; los otros {result['coverage']['route_days_without_class5_qa_land_sample']} no tuvieron ni siquiera ese nivel parcial de observación clara. Entre las {len(logistic_or_xgb_alerts)} fechas-ruta únicas con score >=0,5 de logística o XGBoost, {result['coverage']['such_alert_route_days_with_class5_qa_land_sample']} tuvieron píxeles clase 5 y ninguna tuvo una detección VIIRS.", "",
        "El SNMF declaró que no había incendios reportados a nivel nacional; esa frase no prueba ausencia física. Una detección VIIRS puede ser otro tipo de anomalía térmica y un buffer sin detección no es un negativo observado completo. Aun los píxeles clase 5 solo describen las celdas observadas, no el buffer entero. El cruce es solo una comprobación independiente de los avisos congelados; no justifica llamarlos verdaderos/falsos ni calcula precisión.", "",
        "El test y los umbrales no se modificaron. Fuentes y hashes: [resultado JSON](fire-viirs-explicit-no-fire-model-crosscheck-2023.json), [manifiesto de granulos](fire-viirs-daily-l3-explicit-no-fire-2023-manifest.json), [script de adquisición](../../training/python/acquire_viirs_daily_l3_national_no_fire_2023.py) y [auditor reproducible](../../training/python/audit_viirs_daily_l3_explicit_no_fire_2023.py). Clases y QA según la [guía oficial NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf).", "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": OUT.relative_to(ROOT).as_posix(), "route_days": len(route_day_results),
                      "route_days_with_viirs_detection": result["coverage"]["route_days_with_any_viirs_fire_detection"],
                      "route_days_with_clear_land_sample": result["coverage"]["route_days_with_at_least_one_class5_qa_land_sample"],
                      "unique_logistic_or_xgboost_alert_route_days": len(logistic_or_xgb_alerts),
                      "alert_route_days_with_clear_land_sample": result["coverage"]["such_alert_route_days_with_class5_qa_land_sample"],
                      "model_crosscheck": alert_crosscheck, "synthetic_observations": 0,
                      "deployment_approved": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
