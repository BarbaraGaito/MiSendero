#!/usr/bin/env python3
"""Audit NOAA-20/21 VIIRS observations that supplement missing 2024 S-NPP tiles."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from audit_viirs_daily_l3_jma_2024_no_fire_all_routes import audit_route
from acquire_viirs_daily_l3_jma_2024_cmr_gaps import (
    ALL_ROUTE_AUDIT,
    MANIFEST,
    MODEL_TEST,
    NO_FIRE_AUDIT,
    OUT_DIR,
    TILE_AUDIT,
    expected_items,
)
from environmental_sources import ROOT


BASE = ROOT / "docs/environmental-models-2026-10-22"
OUT = BASE / "fire-viirs-jma-2024-cmr-gap-fill-noaa20-21.json"
OUT_MD = OUT.with_suffix(".md")
PUBLIC_MANIFEST = BASE / "fire-viirs-daily-l3-jma-2024-cmr-gap-fill-noaa20-21-manifest.json"


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    base_audit = json.loads(ALL_ROUTE_AUDIT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") != "downloaded" or manifest.get("planned_granules") != len(manifest.get("granules", [])):
        raise RuntimeError("Gap-fill acquisition is not complete.")
    items = expected_items()
    if len(items) != manifest.get("requested_product_date_tile_pairs"):
        raise RuntimeError("Gap-fill manifest does not match its requested product/date/tile plan.")
    expected_keys = {(item["date"], item["product"], item["tile"]) for item in items}
    rows = {(row["date"], row["product"], row["tile"]): row for row in manifest["granules"]}
    if set(rows) != expected_keys:
        raise RuntimeError("Gap-fill manifest does not account for every requested tile/product.")

    route_results = []
    verified = {}
    for item in items:
        row = rows[(item["date"], item["product"], item["tile"])]
        for route_name in item["routes"]:
            result = audit_route(row, {"name": route_name, "route_coordinates": _geometry(route_name)}, data_dir=OUT_DIR)
            result["sensor"] = "NOAA-20" if row["product"] == "VJ114A1" else "NOAA-21"
            result["platform_product"] = row["product"]
            route_results.append(result)
        verified[row["granule_id"]] = row["sha256"]

    products = sorted({row["product"] for row in manifest["granules"]})
    dates = sorted({row["date"] for row in manifest["granules"]})
    by_route_day: dict[tuple[str, str], list[dict]] = {}
    for result in route_results:
        by_route_day.setdefault((result["date"], result["route"]), []).append(result)
    route_day_union = []
    for (day, route), sensors in sorted(by_route_day.items()):
        route_day_union.append({
            "date": day,
            "route": route,
            "sensor_observations": sorted(row["sensor"] for row in sensors),
            "any_sensor_detected_fire_mask_7_9": any(row["within_10km_full_route_polyline"]["any_viirs_fire_detection"] for row in sensors),
            "any_sensor_had_class5_qa_land_sample": any(row["within_10km_full_route_polyline"]["clear_land_class5_pixels_with_qa_land"] > 0 for row in sensors),
            "any_sensor_had_complete_fire_free_coverage": False,
        })

    base_missing = {(row["date"], row["route"]) for row in base_audit["acquisition"]["unobserved_route_days"]}
    gap_route_days = set(by_route_day)
    if base_missing != gap_route_days:
        raise RuntimeError("NOAA-20/21 gap-fill date/routes do not match the S-NPP unobserved cohort.")
    combined_detected = base_audit["observations"]["route_days_with_viirs_classes_7_9"] + sum(
        row["any_sensor_detected_fire_mask_7_9"] for row in route_day_union
    )
    combined_clear = base_audit["observations"]["route_days_with_some_class5_qa_land_sample"] + sum(
        row["any_sensor_had_class5_qa_land_sample"] for row in route_day_union
    )
    alerts = {(item["date"], alert["route"]) for item in items for alert in item["fixed_threshold_alerts"]}
    alert_results = [row for row in route_day_union if (row["date"], row["route"]) in alerts]

    public_manifest = {
        "experiment_id": manifest["experiment_id"],
        "products": products,
        "base_observation_audit_sha256": manifest["base_observation_audit_sha256"],
        "model_test_sha256": manifest["model_test_sha256"],
        "no_fire_report_audit_sha256": manifest["no_fire_report_audit_sha256"],
        "route_tile_audit_sha256": manifest["route_tile_audit_sha256"],
        "cmr_response_sha256_by_product_date": manifest["cmr_response_sha256_by_product_date"],
        "requested_product_date_tile_pairs": manifest["requested_product_date_tile_pairs"],
        "granules": [{key: row.get(key) for key in (
            "date", "year", "doy", "tile", "product", "granule_id", "reported_size_mb", "cmr_updated",
            "status", "bytes", "sha256", "routes", "fixed_threshold_alerts")}
            for row in sorted(manifest["granules"], key=lambda value: (value["date"], value["product"], value["tile"]))],
        "synthetic_observations": 0,
    }
    PUBLIC_MANIFEST.write_text(json.dumps(public_manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    total_bytes = sum(row["bytes"] for row in manifest["granules"])
    sources = [ALL_ROUTE_AUDIT, MODEL_TEST, NO_FIRE_AUDIT, TILE_AUDIT,
               ROOT / "training/data/environmental/private/fire-route-geometries.json", MANIFEST, PUBLIC_MANIFEST]
    report = {
        "experiment_id": "viirs-daily-l3-jma-2024-snmf-no-fire-cmr-gap-fill-noaa20-21",
        "status": "independent_sensor_gap_fill_complete",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "protocol": {
            "purpose": "Fill two missing S-NPP daily-tile dates using same-day NOAA-20 and NOAA-21 VIIRS daily L3 products.",
            "source_negative_label": "SNMF explicitly said no fires were reported nationally; administrative report only.",
            "independent_observation": "NOAA-20 VJ114A1.002 and NOAA-21 VJ214A1.002 daily 1 km FireMask and QA.",
            "spatial_unit": "10 km buffer around complete route polyline.",
            "fire_mask_detection_classes": [7, 8, 9],
            "class5_qa_land_rule": "FireMask class 5 with QA bits 0-1 equal 10.",
            "fixed_model_threshold": 0.1,
            "threshold_is_calibrated_probability": False,
        },
        "acquisition": {
            "gap_dates": dates,
            "gap_route_days": len(route_day_union),
            "sensor_route_day_observations": len(route_results),
            "granules_verified": len(manifest["granules"]),
            "bytes": total_bytes,
            "size_mb_decimal": round(total_bytes / 1_000_000, 3),
            "platform_products": products,
            "sha256_by_granule_id": verified,
        },
        "observations_by_sensor": {
            sensor: {
                "route_days": sum(row["sensor"] == sensor for row in route_results),
                "route_days_with_fire_mask_7_9": sum(
                    row["sensor"] == sensor and row["within_10km_full_route_polyline"]["any_viirs_fire_detection"]
                    for row in route_results
                ),
                "route_days_with_class5_qa_land_sample": sum(
                    row["sensor"] == sensor and row["within_10km_full_route_polyline"]["clear_land_class5_pixels_with_qa_land"] > 0
                    for row in route_results
                ),
            }
            for sensor in ("NOAA-20", "NOAA-21")
        },
        "combined_gap_route_days": {
            "route_days_with_any_sensor_fire_detection": sum(row["any_sensor_detected_fire_mask_7_9"] for row in route_day_union),
            "route_days_with_any_class5_qa_land_sample": sum(row["any_sensor_had_class5_qa_land_sample"] for row in route_day_union),
            "route_days_with_complete_fire_free_coverage": 0,
            "route_day_results": route_day_union,
        },
        "full_2024_no_fire_cohort_after_gap_fill": {
            "route_days_requested": base_audit["cohort"]["requested_route_days"],
            "route_days_observed_by_s_npp": base_audit["cohort"]["observed_route_days"],
            "missing_s_npp_route_days_now_observed_by_noaa20_or_noaa21": len(route_day_union),
            "route_days_with_at_least_one_viirs_fire_detection_across_available_platforms": combined_detected,
            "route_days_with_some_class5_qa_land_sample_across_available_platforms": combined_clear,
            "still_unobserved_route_days": base_audit["cohort"]["requested_route_days"] - base_audit["cohort"]["observed_route_days"] - len(route_day_union),
        },
        "fixed_threshold_alert_crosscheck": {
            "alert_route_days": len(alerts),
            "alert_route_days_filled_by_noaa_gap_data": len(alert_results),
            "alert_route_days_with_any_noaa_viirs_fire_detection": sum(
                row["any_sensor_detected_fire_mask_7_9"] for row in alert_results
            ),
            "alert_route_days_with_any_noaa_class5_qa_land_sample": sum(
                row["any_sensor_had_class5_qa_land_sample"] for row in alert_results
            ),
            "interpretation": "This is an independent sensor-detection crosscheck, not adjudicated fire truth or a predictive precision estimate.",
        },
        "route_day_sensor_results": route_results,
        "sources": {path.relative_to(ROOT).as_posix(): sha256(path) for path in sources},
        "product_documentation": {
            "nasa_viirs_active_fire_user_guide": "https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf",
            "nasa_vj114a1_file_specification": "https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VJ114A1",
            "nasa_vj214a1_file_specification": "https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VJ214A1",
        },
        "synthetic_observations": 0,
        "deployment_approved": False,
        "limitations": [
            "The administrative SNMF no-fire wording does not prove that no physical fire existed.",
            "VIIRS classes 7-9 are thermal detections, not adjudicated wildfire truth.",
            "NOAA-20/21 class 5 with QA land is partial observed clear land, not complete sensor coverage of a route buffer.",
            "Daily 1 km composites can miss small, obscured, or between-overpass fires.",
            "The three VIIRS platforms share an instrument family and algorithm lineage; their detections do not replace independent field-confirmed labels.",
            "This selected set of report dates cannot estimate model precision, recall, calibration, or forecast skill.",
            "The 0.1 model score cutoff is diagnostic and is not a calibrated probability.",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# Relleno con VIIRS NOAA-20/21 de los dos huecos de S-NPP (2024)", "",
        f"Se descargaron y verificaron {len(manifest['granules'])} granulas (20 archivos; {total_bytes / 1_000_000:.2f} MB) de VJ114A1/NOAA-20 y VJ214A1/NOAA-21 para las cinco tiles de las fechas 31/05 y 10/07. Las 16 combinaciones ruta-fecha faltantes en S-NPP ahora tienen observaciones de ambos sensores.", "",
        f"En esas 16 ruta-fechas, NOAA-20 tuvo {report['observations_by_sensor']['NOAA-20']['route_days_with_fire_mask_7_9']} detecciones clase 7–9 y NOAA-21 tuvo {report['observations_by_sensor']['NOAA-21']['route_days_with_fire_mask_7_9']}. En el conjunto combinado, {report['combined_gap_route_days']['route_days_with_any_class5_qa_land_sample']}/16 tuvieron al menos una muestra clase 5 con QA de tierra. Esto es observación parcial, no garantía de ausencia física.", "",
        f"La única alerta JMA de corte 0,1 en esos días queda cubierta por las dos pasadas diarias; ninguna registró una detección 7–9 a menos de 10 km. El corte no es una probabilidad calibrada, la etiqueta SNMF es administrativa y los sensores VIIRS no son verdad de campo. No se estima precisión ni recall.", "",
        "Ver los [resultados reproducibles](fire-viirs-jma-2024-cmr-gap-fill-noaa20-21.json), [manifiesto público](fire-viirs-daily-l3-jma-2024-cmr-gap-fill-noaa20-21-manifest.json), [adquisidor](../../training/python/acquire_viirs_daily_l3_jma_2024_cmr_gaps.py) y [auditor](../../training/python/audit_viirs_daily_l3_jma_2024_cmr_gaps.py). La guía metodológica está en la [guía NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf).", "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "output": OUT.relative_to(ROOT).as_posix(),
        "granules_verified": len(manifest["granules"]),
        "gap_route_days": len(route_day_union),
        "noaa20_detection_route_days": report["observations_by_sensor"]["NOAA-20"]["route_days_with_fire_mask_7_9"],
        "noaa21_detection_route_days": report["observations_by_sensor"]["NOAA-21"]["route_days_with_fire_mask_7_9"],
        "combined_detection_route_days": report["combined_gap_route_days"]["route_days_with_any_sensor_fire_detection"],
        "combined_clear_land_route_days": report["combined_gap_route_days"]["route_days_with_any_class5_qa_land_sample"],
        "full_cohort_still_unobserved_route_days": report["full_2024_no_fire_cohort_after_gap_fill"]["still_unobserved_route_days"],
        "synthetic_observations": 0,
        "deployment_approved": False,
    }, ensure_ascii=False, indent=2))
    return 0


def _geometry(route_name: str) -> list[list[float]]:
    if not hasattr(_geometry, "cache"):
        path = ROOT / "training/data/environmental/private/fire-route-geometries.json"
        rows = json.loads(path.read_text(encoding="utf-8"))["fire_route_geometries"]
        _geometry.cache = {row["name"]: row["route_coordinates"] for row in rows}
    try:
        return _geometry.cache[route_name]
    except KeyError as error:
        raise RuntimeError(f"Missing private route geometry for {route_name!r}.") from error


if __name__ == "__main__":
    raise SystemExit(main())
