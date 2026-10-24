#!/usr/bin/env python3
"""Quantify VIIRS clear-land coverage for 2024 SNMF no-fire report route-days.

This evaluates satellite-observation completeness and alignment with frozen
JMA alerts. It does not infer physical fire absence or estimate precision.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "docs/environmental-models-2026-10-22"
SNPP_PATH = REPORTS / "fire-viirs-jma-2024-explicit-no-fire-all-routes.json"
GAP_PATH = REPORTS / "fire-viirs-jma-2024-cmr-gap-fill-noaa20-21.json"
EVENT_PATH = REPORTS / "fire-viirs-daily-l3-snmf-event-audit-2023-2025.json"
OUT_JSON = REPORTS / "fire-viirs-2024-no-fire-clear-land-completeness.json"
OUT_MD = OUT_JSON.with_suffix(".md")
THRESHOLDS = (0.90, 0.95, 1.0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def record_coverage(row: dict[str, Any], sensor: str) -> dict[str, Any]:
    obs = row["within_10km_full_route_polyline"]
    grid_count = int(obs["grid_sample_count"])
    clear_count = int(obs["clear_land_class5_pixels_with_qa_land"])
    if grid_count <= 0 or clear_count < 0 or clear_count > grid_count:
        raise ValueError(f"Invalid coverage counts for {row['date']} / {row['route']} / {sensor}")
    return {
        "sensor": sensor,
        "grid_sample_count": grid_count,
        "clear_land_pixels": clear_count,
        "clear_land_fraction": clear_count / grid_count,
        "fire_pixels_7_9": int(obs["fire_pixels_7_9"]),
        "granule_id": row.get("granule_id"),
        "granule_sha256": row.get("granule_sha256"),
    }


def main() -> int:
    snpp = read(SNPP_PATH)
    gap = read(GAP_PATH)
    events = read(EVENT_PATH)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    alerts: dict[tuple[str, str], set[bool]] = defaultdict(set)
    scores: dict[tuple[str, str], set[float | None]] = defaultdict(set)
    for row in snpp["route_day_results"]:
        key = (row["date"], row["route"])
        grouped[key].append(record_coverage(row, "Suomi-NPP"))
        alerts[key].add(bool(row["fixed_diagnostic_alert_at_0_1"]))
        scores[key].add(row.get("frozen_model_score"))
    for row in gap["route_day_sensor_results"]:
        key = (row["date"], row["route"])
        grouped[key].append(record_coverage(row, row.get("sensor", row.get("platform_product", "unknown"))))
        alerts[key].add(bool(row["fixed_diagnostic_alert_at_0_1"]))
        scores[key].add(row.get("frozen_model_score"))

    expected = snpp["cohort"]["requested_route_days"]
    if len(grouped) != expected:
        raise ValueError(f"Expected {expected} unique route-days after gap-fill; found {len(grouped)}")
    records = []
    for (day, route), observations in sorted(grouped.items()):
        if len(alerts[(day, route)]) != 1 or len(scores[(day, route)]) != 1:
            raise ValueError(f"Model score/alert differs by sensor for {day} / {route}")
        # Select the single best-observed sensor for the route-day; do not
        # union pixels across overpasses because source reports store only counts.
        best = max(observations, key=lambda item: (item["clear_land_fraction"], item["sensor"]))
        fire_observed = any(item["fire_pixels_7_9"] > 0 for item in observations)
        records.append({
            "date": day,
            "route": route,
            "sensor_observations": observations,
            "best_single_sensor": best["sensor"],
            "best_clear_land_pixels": best["clear_land_pixels"],
            "grid_sample_count": best["grid_sample_count"],
            "best_clear_land_fraction": round(best["clear_land_fraction"], 6),
            "fire_detected_by_any_available_sensor": fire_observed,
            "jma_alert_at_fixed_diagnostic_0_1": next(iter(alerts[(day, route)])),
            "jma_score": next(iter(scores[(day, route)])),
            "report_date_cluster": None,
        })

    # Number each cohort of adjacent SNMF report dates once. Consecutive dates
    # are dependent observations and must not be treated as separate incidents.
    days = sorted({date.fromisoformat(row["date"]) for row in records})
    cluster = -1
    previous = None
    cluster_by_day: dict[str, int] = {}
    for current in days:
        if previous is None or (current - previous).days > 1:
            cluster += 1
        cluster_by_day[current.isoformat()] = cluster
        previous = current
    for row in records:
        row["report_date_cluster"] = cluster_by_day[row["date"]]

    summary: dict[str, Any] = {
        "route_days": len(records),
        "unique_report_dates": len(days),
        "adjacent_report_date_clusters": cluster + 1,
        "route_days_with_fire_class_7_9_on_any_sensor": sum(row["fire_detected_by_any_available_sensor"] for row in records),
        "route_days_with_zero_fire_detections_on_all_available_sensors": sum(not row["fire_detected_by_any_available_sensor"] for row in records),
        "clear_land_coverage_thresholds": {},
        "overall_best_sensor_clear_land_fraction": {
            "minimum": round(min(row["best_clear_land_fraction"] for row in records), 6),
            "median": round(statistics.median(row["best_clear_land_fraction"] for row in records), 6),
            "maximum": round(max(row["best_clear_land_fraction"] for row in records), 6),
        },
    }
    for threshold in THRESHOLDS:
        eligible = [row for row in records if row["best_clear_land_fraction"] >= threshold]
        summary["clear_land_coverage_thresholds"][str(threshold)] = {
            "eligible_route_days": len(eligible),
            "route_days_with_fire_detection": sum(row["fire_detected_by_any_available_sensor"] for row in eligible),
            "route_days_without_fire_detection": sum(not row["fire_detected_by_any_available_sensor"] for row in eligible),
            "jma_alerts_on_observed_non_detection_days": sum(
                row["jma_alert_at_fixed_diagnostic_0_1"] and not row["fire_detected_by_any_available_sensor"]
                for row in eligible
            ),
            "jma_alert_counts_by_diagnostic_score_cutoff": {
                str(cutoff): sum(
                    row["jma_score"] is not None and row["jma_score"] >= cutoff
                    and not row["fire_detected_by_any_available_sensor"]
                    for row in eligible
                )
                for cutoff in (0.1, 0.5)
            },
            "jma_non_alerts_on_observed_non_detection_days": sum(
                not row["jma_alert_at_fixed_diagnostic_0_1"] and not row["fire_detected_by_any_available_sensor"]
                for row in eligible
            ),
            "unique_snmf_date_clusters": len({row["report_date_cluster"] for row in eligible}),
        }

    by_route = {}
    for route in sorted({row["route"] for row in records}):
        route_rows = [row for row in records if row["route"] == route]
        by_route[route] = {
            "route_days": len(route_rows),
            "median_best_clear_land_fraction": round(statistics.median(row["best_clear_land_fraction"] for row in route_rows), 6),
            "route_days_at_least_90pct_clear": sum(row["best_clear_land_fraction"] >= 0.90 for row in route_rows),
            "route_days_at_least_100pct_clear": sum(row["best_clear_land_fraction"] >= 1.0 for row in route_rows),
            "jma_alerts_with_at_least_90pct_clear_and_no_viirs_detection": sum(
                row["best_clear_land_fraction"] >= 0.90 and row["jma_alert_at_fixed_diagnostic_0_1"]
                and not row["fire_detected_by_any_available_sensor"] for row in route_rows
            ),
        }

    event_groups: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events["event_rows"]:
        key = (event["reported_start_date"], event["route"])
        group = event_groups.setdefault(key, {"event_records": 0, "granules": {}})
        group["event_records"] += 1
        for granule in event["granules"]:
            observation = granule["within_10km_of_full_route_polyline"]
            group["granules"][granule["granule_id"]] = {
                "sensor": granule["sensor"],
                "grid_sample_count": int(observation["grid_samples"]),
                "clear_land_pixels": int(observation["clear_land_class5_pixels"]),
                "fire_pixels_7_9": int(observation["fire_pixels_7_9"]),
                "granule_id": granule["granule_id"],
                "granule_sha256": granule["source"]["sha256"],
            }
    event_point_results = {
        (row["reported_start_date"], row["route"]): row
        for row in events["route_date_positive_event_coincidence"]["route_date_results"]
    }
    event_route_days = []
    for (day, route), group in sorted(event_groups.items()):
        sensor_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for granule in group["granules"].values():
            sensor_groups[granule["sensor"]].append(granule)
        sensor_summaries = []
        for sensor, granules in sorted(sensor_groups.items()):
            sample_count = sum(row["grid_sample_count"] for row in granules)
            clear_count = sum(row["clear_land_pixels"] for row in granules)
            sensor_summaries.append({
                "sensor": sensor,
                "grid_sample_count": sample_count,
                "clear_land_pixels": clear_count,
                "clear_land_fraction": clear_count / sample_count if sample_count else 0.0,
                "fire_pixels_7_9": sum(row["fire_pixels_7_9"] for row in granules),
                "granules": [row["granule_id"] for row in granules],
            })
        best = max(sensor_summaries, key=lambda row: (row["clear_land_fraction"], row["sensor"]))
        point_result = event_point_results[(day, route)]
        event_route_days.append({
            "reported_start_date": day,
            "route": route,
            "snmf_event_records": group["event_records"],
            "sensor_observations": sensor_summaries,
            "best_single_sensor": best["sensor"],
            "best_clear_land_fraction": round(best["clear_land_fraction"], 6),
            "fire_detected_by_any_sensor_within_10km_of_route": any(row["fire_pixels_7_9"] > 0 for row in sensor_summaries),
            "event_point_cells_clear_land_in_all_sensors": point_result["exact_event_point_cells_class5_land_all_sensors"],
        })
    event_summary = {
        "unique_snmf_event_records": events["selected_route_event_clusters"],
        "unique_reported_route_days": len(event_route_days),
        "route_days_with_fire_detection_within_10km_of_full_route": sum(
            row["fire_detected_by_any_sensor_within_10km_of_route"] for row in event_route_days
        ),
        "route_days_with_event_point_cells_clear_land_all_sensors": sum(
            row["event_point_cells_clear_land_in_all_sensors"] for row in event_route_days
        ),
        "clear_land_coverage_thresholds": {},
    }
    for threshold in THRESHOLDS:
        eligible = [row for row in event_route_days if row["best_clear_land_fraction"] >= threshold]
        event_summary["clear_land_coverage_thresholds"][str(threshold)] = {
            "eligible_reported_route_days": len(eligible),
            "route_days_with_fire_detection": sum(row["fire_detected_by_any_sensor_within_10km_of_route"] for row in eligible),
            "route_days_without_fire_detection": sum(not row["fire_detected_by_any_sensor_within_10km_of_route"] for row in eligible),
        }

    result = {
        "experiment_id": "viirs-2024-clear-land-observation-completeness-on-explicit-snmf-no-fire-dates",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "purpose": "Quantify VIIRS clear-land observation coverage across route buffers and diagnose frozen JMA alerts on selected report dates.",
        "protocol": {
            "cohort": "All eight routes on 27 dates where the national SNMF report explicitly listed no fires in 2024.",
            "spatial_unit": "Grid samples within 10 km of each complete route polyline.",
            "clear_land_fraction": "FireMask class 5 with QA land divided by all route-buffer grid samples.",
            "sensor_choice": "Use the single available sensor with the highest clear-land fraction for each route-day; do not union sensor pixels because source audits retain aggregate counts only.",
            "fire_detection": "Any FireMask class 7-9 from any available same-day sensor.",
            "model_alignment": "Frozen JMA score at diagnostic threshold 0.1; no threshold tuning in this analysis.",
            "independence_unit": "Report dates are clustered when consecutive; route-days within a date and sensor passes are dependent.",
        },
        "summary": summary,
        "by_route": by_route,
        "route_day_results": records,
        "positive_snmf_event_route_day_check": {
            "summary": event_summary,
            "route_day_results": event_route_days,
            "limitations": [
                "SNMF reported start date does not specify exact active-fire time during each VIIRS observation.",
                "A clear-land no-detection at the pass does not negate an official fire event; timing, containment, fire size and sensor sensitivity can explain disagreement.",
                "This selected event cohort measures coincidence and observation quality, not a definitive sensitivity or false-negative rate.",
            ],
        },
        "sources": {
            SNPP_PATH.relative_to(ROOT).as_posix(): sha256(SNPP_PATH),
            GAP_PATH.relative_to(ROOT).as_posix(): sha256(GAP_PATH),
            EVENT_PATH.relative_to(ROOT).as_posix(): sha256(EVENT_PATH),
        },
        "interpretation": "High clear-land fraction supports a well-observed VIIRS non-detection for the sensor-detection target, not proof of physical fire absence. This selected negative-report cohort has no detected fire positives, is clustered in time, and cannot estimate fire-alert precision, recall, or prevalence. JMA alerts without VIIRS detections are disagreement cases, not confirmed false alarms.",
        "synthetic_observations": 0,
        "deployment_approved": False,
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    thresholds_md = [
        "| Clear-land coverage | Route-days | VIIRS detections | JMA alerts >=0.1 | JMA alerts >=0.5 |",
        "|---:|---:|---:|---:|---:|",
    ]
    for threshold, values in summary["clear_land_coverage_thresholds"].items():
        thresholds_md.append(
            f"| >= {float(threshold):.0%} | {values['eligible_route_days']} | {values['route_days_with_fire_detection']} | {values['jma_alert_counts_by_diagnostic_score_cutoff']['0.1']} | {values['jma_alert_counts_by_diagnostic_score_cutoff']['0.5']} |"
        )
    markdown = [
        "# Cobertura de tierra despejada VIIRS en rutas (2024)",
        "",
        f"Se calcularon fracciones de tierra despejada en {len(records)} ruta-dias de las ocho rutas y 27 fechas con reporte nacional SNMF sin incendios. Para las fechas faltantes de S-NPP se uso, por ruta-dia, el mejor de NOAA-20 y NOAA-21; no se combinaron pixeles entre sensores.",
        "",
        *thresholds_md,
        "",
        f"En la cohorte no hubo clases VIIRS 7-9 en los sensores disponibles. Al exigir cobertura despejada de al menos 90%, quedan {summary['clear_land_coverage_thresholds']['0.9']['eligible_route_days']} ruta-dias; el JMA congelado dio {summary['clear_land_coverage_thresholds']['0.9']['jma_alert_counts_by_diagnostic_score_cutoff']['0.1']} avisos con corte diagnostico 0.1 y {summary['clear_land_coverage_thresholds']['0.9']['jma_alert_counts_by_diagnostic_score_cutoff']['0.5']} con 0.5. Al exigir 100%, quedan {summary['clear_land_coverage_thresholds']['1.0']['eligible_route_days']} y los conteos son {summary['clear_land_coverage_thresholds']['1.0']['jma_alert_counts_by_diagnostic_score_cutoff']['0.1']} y {summary['clear_land_coverage_thresholds']['1.0']['jma_alert_counts_by_diagnostic_score_cutoff']['0.5']}, respectivamente.",
        "",
        "Estos casos son no-detecciones observadas por VIIRS, no ausencias fisicas confirmadas. Los avisos discordantes no se cuentan como falsos positivos, la muestra se eligio por reportes nacionales sin incendios y los dias consecutivos se agrupan en 14 bloques. Esta cohorte no estima precision, recall ni prevalencia; sirve para medir cobertura de observacion y decidir que etiquetas pueden considerarse conocidas para el objetivo de deteccion VIIRS.",
        "",
        f"En otra cohorte seleccionada de {event_summary['unique_reported_route_days']} ruta-dias con reportes positivos SNMF ({event_summary['unique_snmf_event_records']} registros/evento), {event_summary['route_days_with_event_point_cells_clear_land_all_sensors']} tuvieron la celda del evento como tierra despejada en todos los sensores. Con >=90% de cobertura del buffer, hubo {event_summary['clear_land_coverage_thresholds']['0.9']['eligible_reported_route_days']} ruta-dias y VIIRS detecto fuego en {event_summary['clear_land_coverage_thresholds']['0.9']['route_days_with_fire_detection']}. La fecha reportada no fija la hora de actividad durante el paso, asi que esto es coincidencia, no sensibilidad definitiva ni falsos negativos.",
        "",
        f"Resultados reproducibles: [JSON con resultados ruta-dia y hashes]({OUT_JSON.name}). Fuentes: [auditoria S-NPP de las ocho rutas]({SNPP_PATH.name}), [relleno NOAA-20/21]({GAP_PATH.name}) y [cohorte positiva SNMF](fire-viirs-daily-l3-snmf-event-audit-2023-2025.json). Script: [`evaluate_viirs_2024_clear_land_completeness.py`](../../training/python/evaluate_viirs_2024_clear_land_completeness.py).",
        "",
    ]
    OUT_MD.write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({"output": OUT_JSON.relative_to(ROOT).as_posix(), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
