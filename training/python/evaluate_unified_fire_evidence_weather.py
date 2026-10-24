"""Test JMA weather against a provenance-preserving union of route fire evidence.

This research-only experiment predicts the source-evidence target defined in
the report. Satellite candidates and SNMF reports are not physical-fire truth;
explicit national no-fire reports are negatives only for reported evidence.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime

from environmental_sources import ROOT, sha256
from evaluate_argentina_trail_corridor_weather import (
    WEATHER_ARCHIVES, WEATHER_MANIFESTS, WEATHER_FEATURES, add_calendar,
    average_precision, fit_logistic, load_weather, predict, sha256 as file_hash,
    summary as route_summary, wilson_lower,
)

REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
PRIVATE = ROOT / "training/data/environmental/private"
CATALOG = REPORT_DIR / "fire-unified-route-event-catalog.json"
NO_FIRE = REPORT_DIR / "fire-snmf-national-no-fire-report-audit.json"
GEOMETRY = PRIVATE / "fire-route-geometries.json"
OUT = REPORT_DIR / "fire-unified-evidence-jma-temporal-evaluation.json"
OUT_MD = REPORT_DIR / "fire-unified-evidence-jma-temporal-evaluation.md"
DATE_START = "2023-01-01"
TEST_START = "2024-01-01"
TEST_END = "2027-01-01"
THRESHOLD = 0.5


def route_id_map() -> dict[str, str]:
    # These source geometries are represented by the corresponding in-app OSM route IDs.
    return {
        "Sendero Macuco - Salto Arrechea": "macuco",
        "Refugio Frey desde Villa Catedral": "frey",
        "Quebrada del Condorito - Balcon Norte": "condorito",
        "Sendero Namuncura": "namuncura",
        "Cerro Ventana - Hueco de la Ventana": "ventana",
        "Bosque Tallado desde la plataforma del Piltriquitron": "bosqueTallado",
        "Sendero Che Roga - Mburucuyá": "mburucuya-che-roga",
        "Sendero La Chuña - El Rey": "el-rey-la-chuna",
    }


def build_labels() -> tuple[dict, dict]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    no_fire = json.loads(NO_FIRE.read_text(encoding="utf-8"))
    mapping = route_id_map()
    positives, lineage = {}, defaultdict(lambda: {"event_ids": [], "source_families": set(), "evidence_classes": set()})
    unknown_routes = Counter()
    for event in catalog["events"]:
        route = mapping.get(event["route"])
        if route is None:
            unknown_routes[event["route"]] += 1
            continue
        day = event["start_date"]
        if not DATE_START <= day < TEST_END:
            continue
        key = (route, day)
        positives[key] = 1
        item = lineage[key]
        item["event_ids"].append(event["event_id"])
        item["source_families"].update(event["source_families"])
        item["evidence_classes"].add(event["evidence_class"])

    negatives = {}
    for row in no_fire["verified_negative_route_day_labels"]:
        route = mapping.get(row["route_sector"])
        if route is None:
            unknown_routes[row["route_sector"]] += 1
            continue
        day = row["report_date"]
        if DATE_START <= day < TEST_END:
            negatives[(route, day)] = row
    conflicts = sorted(set(positives) & set(negatives))
    if conflicts:
        raise ValueError(f"Positive/negative source labels conflict: {conflicts[:5]}")
    return ({"positives": positives, "negatives": negatives, "lineage": lineage,
             "unknown_route_records": dict(unknown_routes), "conflicts": conflicts},
            {"catalog": catalog, "no_fire": no_fire, "geometry": json.loads(GEOMETRY.read_text(encoding="utf-8"))})


def metrics(rows: list[dict], scores: list[float]) -> dict:
    y = [row["label"] for row in rows]
    predicted = [score >= THRESHOLD for score in scores]
    tp = sum(label and alert for label, alert in zip(y, predicted))
    fp = sum((not label) and alert for label, alert in zip(y, predicted))
    fn = sum(label and (not alert) for label, alert in zip(y, predicted))
    tn = len(y) - tp - fp - fn
    alerts = tp + fp
    return {"observations": len(y), "positive_observations": sum(y), "threshold": THRESHOLD,
        "alerts": alerts, "true_positives": tp, "false_positives": fp,
        "false_negatives": fn, "precision": tp / alerts if alerts else 0.0,
        "recall": tp / sum(y) if sum(y) else 0.0,
        "average_precision": average_precision(y, scores),
        "confusion_matrix_tn_fp_fn_tp": [tn, fp, fn, tp]}


def aggregate_dates(rows: list[dict], scores: list[float]) -> tuple[list[dict], list[float]]:
    groups = defaultdict(lambda: {"label": 0, "score": 0.0, "routes": set()})
    for row, score in zip(rows, scores):
        group = groups[row["date"]]
        group["label"] = max(group["label"], row["label"])
        group["score"] = max(group["score"], score)
        group["routes"].add(row["route"])
    output = [{"date": day, "label": value["label"], "route_count": len(value["routes"])}
              for day, value in sorted(groups.items())]
    return output, [groups[row["date"]]["score"] for row in output]


def main() -> None:
    labels, provenance = build_labels()
    weather = load_weather()
    rows = []
    excluded = Counter()
    for (route, day), label in labels["positives"].items():
        key = (route, day)
        if key not in weather:
            excluded["positive_without_complete_route_forecast"] += 1
            continue
        rows.append({"route": route, "date": day, "label": label,
            "label_modis_detection": label,
            "label_source": "any_unified_source_event_evidence",
            "evidence_ids": sorted(set(labels["lineage"][key]["event_ids"])),
            "source_families": sorted(labels["lineage"][key]["source_families"]),
            "features": [weather[key][name] for name in WEATHER_FEATURES] + list(add_calendar(day))})
    for (route, day), report in labels["negatives"].items():
        key = (route, day)
        if key not in weather:
            excluded["negative_without_complete_route_forecast"] += 1
            continue
        rows.append({"route": route, "date": day, "label": 0,
            "label_modis_detection": 0,
            "label_source": "SNMF_explicit_national_no_fire_report",
            "evidence_ids": [report.get("evidence_pdf_sha256", "")], "source_families": [],
            "features": [weather[key][name] for name in WEATHER_FEATURES] + list(add_calendar(day))})
    rows.sort(key=lambda row: (row["date"], row["route"]))
    train = [row for row in rows if DATE_START <= row["date"] < TEST_START]
    test = [row for row in rows if TEST_START <= row["date"] < TEST_END]
    if not train or not test or not any(row["label"] for row in train):
        raise ValueError("Temporal training or test cohort is empty / lacks training positives")
    route_ids = sorted({row["route"] for row in rows})
    feature_names = list(WEATHER_FEATURES) + ["annual_sin", "annual_cos"]
    model = fit_logistic(train, feature_names, route_ids)
    test_scores = predict(model, test)
    date_rows, date_scores = aggregate_dates(test, test_scores)
    train_positive_dates = sorted({row["date"] for row in train if row["label"]})
    test_positive_dates = sorted({row["date"] for row in test if row["label"]})
    test_negative_dates = sorted({row["date"] for row in test if not row["label"]})
    source_family_counts = Counter()
    for row in train + test:
        source_family_counts.update(row["source_families"])
    test_date_metrics = metrics(date_rows, date_scores)
    positives = test_date_metrics["true_positives"]
    alerts = test_date_metrics["alerts"]
    result = {
        "experiment_id": "unified-fire-evidence-jma-24h-temporal-test-2023-train-2024-2026-test",
        "status": "exploratory_source_evidence_prediction_not_physical_fire_probability",
        "target": "At least one source-preserved event record from SNMF, GFA or INPE in an in-app route sector on the target date.",
        "negative_definition": "The SNMF national report explicitly said no fires were reported that day; this is a negative only for the defined source-evidence target, not proof of no physical fire.",
        "forecast_protocol": "JMA GSM previous_day1 forecast variables are aggregated over the target UTC day at the matching in-app route midpoint and used as a fixed one-day-lead predictor.",
        "source_evidence": {"catalog_sha256": sha256(CATALOG), "no_fire_audit_sha256": sha256(NO_FIRE),
            "geometry_sha256": sha256(GEOMETRY), "unified_event_count": provenance["catalog"]["unified_event_count"],
            "events_by_evidence_class": provenance["catalog"]["event_counts_by_evidence_class"],
            "route_date_conflicts": len(labels["conflicts"]), "unmapped_records": labels["unknown_route_records"],
            "source_families_in_aligned_cohort": dict(source_family_counts)},
        "weather_archives": [{"archive": path.relative_to(ROOT).as_posix(),
            "archive_sha256": sha256(path), "manifest_sha256": sha256(manifest),
            "manifest_route_count": json.loads(manifest.read_text(encoding="utf-8"))["route_count"]}
            for path, manifest in zip(WEATHER_ARCHIVES, WEATHER_MANIFESTS)],
        "data": {"rows_before_weather_join": len(labels["positives"]) + len(labels["negatives"]),
            "rows_without_complete_forecast": dict(excluded), "aligned_rows": len(rows),
            "aligned_route_days": len({(row["route"], row["date"]) for row in rows}),
            "train_period": {"start": DATE_START, "end_exclusive": TEST_START,
                "route_days": len(train), "positive_route_days": sum(row["label"] for row in train),
                "positive_dates": len(train_positive_dates),
                "negative_report_dates": len({row["date"] for row in train if not row["label"]})},
            "temporal_test": {"start": TEST_START, "end_exclusive": TEST_END,
                "route_days": len(test), "positive_route_days": sum(row["label"] for row in test),
                "positive_dates": len(test_positive_dates), "negative_report_dates": len(test_negative_dates),
                "positive_date_list": test_positive_dates, "negative_report_date_list": test_negative_dates}},
        "model": {"algorithm": "class-balanced logistic regression with standardized weather, route effect, and calendar season; batch gradient descent (180 epochs, L2=0.01)",
            "features": feature_names, "fixed_threshold": THRESHOLD,
            "threshold_selection": "Not tuned on the test; fixed at 0.5 as a diagnostic. No validation year is available that is both large and independent."},
        "test_route_day": metrics(test, test_scores),
        "test_event_date": test_date_metrics,
        "event_date_precision_wilson_one_sided_95_lower_bound": wilson_lower(positives, alerts),
        "minimum_independent_correct_event_dates_for_90pct_lower_bound": 29,
        "predictions": [{"route": row["route"], "date": row["date"], "label": row["label"],
            "score": score, "alert": score >= THRESHOLD, "evidence_ids": row["evidence_ids"]}
            for row, score in zip(test, test_scores)],
        "limitations": ["This prediction target is a union of heterogeneous source evidence, not a single sensor's fire detection and not verified physical-fire occurrence.",
            "INPE and GFA evidence share MODIS-family sensors; their agreement is not independent sensor confirmation.",
            "The event catalog intentionally leaves uncertain cross-source links separate; some resulting route-date events may still refer to the same physical fire.",
            "The explicit no-fire negatives are concentrated in report dates and do not establish absence of unreported or undetected fires.",
            "The temporal holdout has at most the listed number of distinct positive event dates; repeated route-days do not increase independent sample size.",
            "No synthetic observations, oversampling, test-driven threshold tuning, deployment artifact, or app change is produced."],
        "synthetic_observations": 0, "model_artifact_written": False, "deployment_approved": False}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Prueba temporal con evidencia de fuego unificada", "",
        f"El objetivo es predecir evidencia de incendio registrada por al menos una fuente unificada cerca de una ruta en la fecha objetivo. Entrenamiento: 2023. Test temporal: 2024-octubre de 2026. El umbral 0,5 se fijó como diagnóstico y no se ajustó con el test.", "",
        f"El test contiene {len(test)} ruta-fechas, {sum(row['label'] for row in test)} ruta-fechas positivas en {len(test_positive_dates)} fechas y negativos de {len(test_negative_dates)} fechas explícitas de no-fuego SNMF.", "",
        f"Métricas por ruta-fecha: {json.dumps(result['test_route_day'], ensure_ascii=False)}.", "",
        f"Métricas agrupadas por fecha-evento: {json.dumps(test_date_metrics, ensure_ascii=False)}; límite inferior Wilson unilateral 95% de precisión: {result['event_date_precision_wilson_one_sided_95_lower_bound']}.", "",
        "Las métricas describen evidencia registrada, no probabilidad de fuego físico. La independencia entre fuentes es parcial y los negativos oficiales no prueban ausencia de incendios no reportados. El JSON contiene hashes, linaje, predicciones y conteos por fecha."]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": OUT.relative_to(ROOT).as_posix(), "train": result["data"]["train_period"],
        "test": result["data"]["temporal_test"], "route_day_metrics": result["test_route_day"],
        "event_date_metrics": test_date_metrics,
        "precision_wilson_lower": result["event_date_precision_wilson_one_sided_95_lower_bound"]},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
