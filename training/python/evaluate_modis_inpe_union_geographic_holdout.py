"""Spatially blocked, forward-in-time test for the unified route-day cohort.

Each test fold holds out a connected geographic group of nearby trail routes.
Models train on other routes in 2022, validate thresholds on other routes in
2023, and score only the held-out routes in 2024-2026.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date

import evaluate_modis_inpe_union_weather as union
from environmental_sources import ROOT, sha256
from evaluate_argentina_trail_corridor_weather import (
    WEATHER_FEATURES, add_calendar, choose_threshold, fit_logistic,
    predict, summary, wilson_lower,
)

REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
OUT = REPORT_DIR / "fire-modis-inpe-union-jma-geographic-holdout-all-41.json"
OUT_MD = REPORT_DIR / "fire-modis-inpe-union-jma-geographic-holdout-all-41.md"
TRAIN_START, VALIDATION_START, TEST_START, TEST_END = (
    "2022-01-01", "2023-01-01", "2024-01-01", "2027-01-01")
REGION_RADIUS_KM = 100.0
ROUTE_SAMPLE_KM = 10.0
EARTH_KM = 6371.0088


def haversine(a: list[float], b: list[float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def sample_route(points: list[list[float]]) -> list[list[float]]:
    samples = [points[0]]
    for first, second in zip(points, points[1:]):
        distance = haversine(first, second)
        if distance == 0:
            continue
        steps = max(1, math.ceil(distance / ROUTE_SAMPLE_KM))
        samples.extend([[first[0] + (second[0] - first[0]) * i / steps,
                         first[1] + (second[1] - first[1]) * i / steps]
                        for i in range(1, steps + 1)])
    return samples


def route_regions(routes: dict[str, list[list[float]]]) -> list[list[str]]:
    """Connect trails whose 10 km sampled lines approach within 100 km."""
    sampled = {name: sample_route(points) for name, points in routes.items()}
    bounds = {}
    for name, points in sampled.items():
        lats, lons = [p[0] for p in points], [p[1] for p in points]
        lat_pad = REGION_RADIUS_KM / 110.574
        cos_lat = max(math.cos(math.radians(sum(lats) / len(lats))), 0.1)
        lon_pad = REGION_RADIUS_KM / (111.32 * cos_lat)
        bounds[name] = (min(lats) - lat_pad, max(lats) + lat_pad,
                        min(lons) - lon_pad, max(lons) + lon_pad)
    names = sorted(routes)
    parent = {name: name for name in names}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(a: str, b: str) -> None:
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    for i, first in enumerate(names):
        for second in names[i + 1:]:
            a, b = bounds[first], bounds[second]
            if a[1] < b[0] or b[1] < a[0] or a[3] < b[2] or b[3] < a[2]:
                continue
            nearby = False
            # Sampling bounds make this an approximate route-to-route distance;
            # a 10 km sample interval is small relative to the 100 km block.
            for p in sampled[first]:
                if any(haversine(p, q) <= REGION_RADIUS_KM for q in sampled[second]):
                    nearby = True
                    break
            if nearby:
                union(first, second)
    groups = defaultdict(list)
    for name in names:
        groups[find(name)].append(name)
    return sorted((sorted(group) for group in groups.values()), key=lambda x: x[0])


def build_rows() -> tuple[list[dict], dict]:
    weather = union.load_weather()
    modis_rows, quality = union.load_cached_modis_route_days()
    routes = union.route_lines()
    weather_routes = {route for route, _ in weather}
    routes = {name: line for name, line in routes.items() if name in weather_routes}
    inpe, inpe_summary = union.extract_inpe_days(routes)
    catalog = json.loads(union.UNIFIED_CATALOG.read_text(encoding="utf-8"))
    catalog_sources = defaultdict(set)
    unmapped = defaultdict(int)
    for event in catalog["events"]:
        route = event["route"]
        if route not in routes:
            unmapped[event["route"]] += 1
            continue
        catalog_sources[(route, event["start_date"])].update(event["source_families"])
    rows = []
    for modis in modis_rows:
        route, day = modis["route"], modis["date"]
        forecast = weather.get((route, day))
        if forecast is None:
            continue
        inpe_points = inpe.get((route, day), set())
        event_sources = catalog_sources.get((route, day), set())
        label = int(bool(modis["label_modis_detection"] or inpe_points or event_sources))
        rows.append({"route": route, "date": day, "label": label,
            "label_modis_detection": label,
            "features": [forecast[name] for name in WEATHER_FEATURES] + list(add_calendar(day)),
            "sources": (["MOD14A1"] if modis["label_modis_detection"] else [])
                + (["INPE_Aqua_MODIS"] if inpe_points else []) + sorted(event_sources)})
    dataset_manifest = json.loads(union.DATASET_MANIFEST.read_text(encoding="utf-8"))
    return rows, {"route_count": len(routes), "modis_qa": quality, "inpe": inpe_summary,
        "unmapped_catalog_routes": dict(unmapped),
        "label_sha256": sha256(union.LABELS),
        "catalog_sha256": sha256(union.UNIFIED_CATALOG),
        "unified_dataset": {"path": union.DATASET.relative_to(ROOT).as_posix(),
            "sha256": sha256(union.DATASET), "rows": dataset_manifest["rows"],
            "manifest_path": union.DATASET_MANIFEST.relative_to(ROOT).as_posix(),
            "manifest_sha256": sha256(union.DATASET_MANIFEST),
            "uncompressed_sha256": dataset_manifest.get("uncompressed_sha256")}}


def group_metrics(rows: list[dict], scores: list[float], threshold: float) -> dict:
    result = summary(rows, scores, threshold)
    result["observations"] = result.pop("route_days")
    result["positive_observations"] = result.pop("positive_route_days")
    return result


def best_validation_precision(rows: list[dict], scores: list[float], min_alerts: int = 5) -> dict | None:
    candidates = []
    for threshold in sorted(set(scores)):
        predicted = [score >= threshold for score in scores]
        alerts = sum(predicted)
        if alerts < min_alerts:
            continue
        positives = sum(row["label"] for row in rows)
        tp = sum(row["label"] and alert for row, alert in zip(rows, predicted))
        precision = tp / alerts
        recall = tp / positives if positives else 0.0
        candidates.append((precision, recall, -alerts, threshold, tp, alerts))
    if not candidates:
        return None
    precision, recall, _, threshold, tp, alerts = max(candidates)
    return {"threshold": threshold, "validation_precision": precision,
        "validation_recall": recall, "validation_true_positives": tp,
        "validation_alerts": alerts, "minimum_alerts": min_alerts}


def aggregate_date_scores(rows: list[dict], scores: list[float]) -> tuple[list[dict], list[float]]:
    groups = defaultdict(lambda: {"label": 0, "score": 0.0})
    for row, score in zip(rows, scores):
        group = groups[row["date"]]
        group["label"] = max(group["label"], row["label"])
        group["score"] = max(group["score"], score)
    date_rows = [{"route": "all_argentine_routes", "date": day,
        "label": group["label"], "label_modis_detection": group["label"],
        "features": []} for day, group in sorted(groups.items())]
    return date_rows, [groups[row["date"]]["score"] for row in date_rows]


def main() -> None:
    rows, source_provenance = build_rows()
    routes = union.route_lines()
    routes = {name: line for name, line in routes.items()
              if any(row["route"] == name for row in rows)}
    regions = route_regions(routes)
    feature_names = list(WEATHER_FEATURES) + ["annual_sin", "annual_cos"]
    route_ids = sorted(routes)
    fold_results = []
    pooled_predictions = []
    no_test_coverage = []
    for fold_index, heldout_routes in enumerate(regions, start=1):
        held = set(heldout_routes)
        train = [row for row in rows if row["route"] not in held
                 and TRAIN_START <= row["date"] < VALIDATION_START]
        validation = [row for row in rows if row["route"] not in held
                      and VALIDATION_START <= row["date"] < TEST_START]
        test = [row for row in rows if row["route"] in held
                and TEST_START <= row["date"] < TEST_END]
        counts = {"train_route_days": len(train), "train_positives": sum(r["label"] for r in train),
            "validation_route_days": len(validation), "validation_positives": sum(r["label"] for r in validation),
            "test_route_days": len(test), "test_positives": sum(r["label"] for r in test),
            "test_positive_dates": len({r["date"] for r in test if r["label"]})}
        fold = {"fold": fold_index, "heldout_routes": heldout_routes,
            "region_radius_km": REGION_RADIUS_KM, "counts": counts}
        if not test:
            fold["status"] = "no_aligned_test_coverage"
            no_test_coverage.extend(heldout_routes)
            fold_results.append(fold)
            continue
        if not train or not any(r["label"] for r in train) or not any(not r["label"] for r in train):
            fold["status"] = "not_estimable_missing_training_class"
            fold_results.append(fold)
            continue
        model = fit_logistic(train, feature_names, route_ids)
        val_scores = predict(model, validation) if validation else []
        threshold = choose_threshold([r["label"] for r in validation], val_scores) if validation else None
        best_route_threshold = best_validation_precision(validation, val_scores) if validation else None
        validation_date_rows, validation_date_scores = aggregate_date_scores(validation, val_scores)
        best_date_threshold = (best_validation_precision(validation_date_rows, validation_date_scores)
                               if validation_date_rows else None)
        test_scores = predict(model, test)
        fold["status"] = "scored"
        fold["validation_threshold_90pct_precision_min_5_alerts"] = threshold
        fold["validation_max_precision_threshold_route_day"] = best_route_threshold
        fold["validation_max_precision_threshold_event_date"] = best_date_threshold
        fold["diagnostic_test_metrics_at_0_5"] = group_metrics(test, test_scores, 0.5)
        fold["diagnostic_test_metrics_at_validation_threshold"] = (
            group_metrics(test, test_scores, threshold["threshold"]) if threshold else None)
        fold["test_route_day_metrics_at_validation_max_precision"] = (
            group_metrics(test, test_scores, best_route_threshold["threshold"])
            if best_route_threshold else None)
        test_date_rows, test_date_scores = aggregate_date_scores(test, test_scores)
        fold["test_event_date_metrics_at_validation_max_precision"] = (
            group_metrics(test_date_rows, test_date_scores, best_date_threshold["threshold"])
            if best_date_threshold else None)
        fold_results.append(fold)
        pooled_predictions.extend({"row": row, "score": score,
            "selected_threshold": best_date_threshold["threshold"] if best_date_threshold else None}
                                  for row, score in zip(test, test_scores))

    pooled_rows = [item["row"] for item in pooled_predictions]
    pooled_scores = [item["score"] for item in pooled_predictions]
    pooled_metrics = (group_metrics(pooled_rows, pooled_scores, 0.5) if pooled_rows else None)
    date_groups = defaultdict(lambda: {"label": 0, "score": 0.0, "routes": set()})
    for row, score in zip(pooled_rows, pooled_scores):
        group = date_groups[row["date"]]
        group["label"] = max(group["label"], row["label"])
        group["score"] = max(group["score"], score)
        group["routes"].add(row["route"])
    date_rows = [{"route": "geographic_holdout_date", "date": day, "label": v["label"],
        "label_modis_detection": v["label"], "features": []}
        for day, v in sorted(date_groups.items())]
    date_scores = [date_groups[row["date"]]["score"] for row in date_rows]
    date_metrics = group_metrics(date_rows, date_scores, 0.5) if date_rows else None
    if date_metrics:
        date_metrics["event_dates"] = date_metrics.pop("observations")
        date_metrics["positive_event_dates"] = date_metrics.pop("positive_observations")
    selected_date_groups = defaultdict(lambda: {"label": 0, "alert": False})
    for item in pooled_predictions:
        row, score, threshold = item["row"], item["score"], item["selected_threshold"]
        group = selected_date_groups[row["date"]]
        group["label"] = max(group["label"], row["label"])
        group["alert"] = group["alert"] or (threshold is not None and score >= threshold)
    selected_tp = sum(v["label"] and v["alert"] for v in selected_date_groups.values())
    selected_fp = sum((not v["label"]) and v["alert"] for v in selected_date_groups.values())
    selected_fn = sum(v["label"] and (not v["alert"]) for v in selected_date_groups.values())
    selected_alerts = selected_tp + selected_fp
    selected_event_metrics = {"event_dates": len(selected_date_groups),
        "positive_event_dates": sum(v["label"] for v in selected_date_groups.values()),
        "alerts": selected_alerts, "true_positives": selected_tp,
        "false_positives": selected_fp, "false_negatives": selected_fn,
        "precision": selected_tp / selected_alerts if selected_alerts else 0.0,
        "recall": selected_tp / sum(v["label"] for v in selected_date_groups.values())
            if any(v["label"] for v in selected_date_groups.values()) else 0.0,
        "wilson_lower_95_descriptive": wilson_lower(selected_tp, selected_alerts) if selected_alerts else None,
        "threshold_policy": "Per-region cutoff maximized precision on 2023 validation dates with >=5 alerts; no >=90% precision threshold passed."}

    result = {"experiment_id": "unified-fire-jma-geographic-region-holdout-forward-time-v1",
        "status": "spatially_blocked_exploratory_evaluation_not_reliable_prediction",
        "target": "Any source-preserved route-day detection/event evidence in the MOD14A1 + INPE Aqua/MODIS + SNMF/GFA union.",
        "negative_definition": "At least 80% clear-land MOD14A1 route-corridor QA with no MODIS fire detection and no catalogued source event; not physical-fire absence.",
        "forecast": "JMA GSM Previous Runs previous_day1 (24 h lead), aggregated at each route midpoint.",
        "time_protocol": {"train": [TRAIN_START, VALIDATION_START],
            "validation": [VALIDATION_START, TEST_START], "test": [TEST_START, TEST_END]},
        "geography_protocol": {"unit": "connected group of route polylines",
            "grouping": f"Route polylines sampled at {ROUTE_SAMPLE_KM:g} km intervals; groups connected when sampled positions are within {REGION_RADIUS_KM:g} km. Every held-out group is excluded from that fold's train and validation.",
            "groups": regions,
            "warning": "This is a route-neighborhood block, not an official ecoregion or province partition; routes beyond the block radius can still share broad weather/fire regimes."},
        "model": {"algorithm": "same class-balanced logistic regression for every fold; weather, annual season terms, route effect.",
            "threshold_policy": "0.5 is a fixed diagnostic only. A >=90% precision with >=5 validation alerts threshold is selected independently in each fold when possible; test outcomes are never used for threshold selection.",
            "features": feature_names},
        "source_provenance": source_provenance,
        "fold_count": len(fold_results), "scored_fold_count": sum(f["status"] == "scored" for f in fold_results),
        "folds_with_positive_test_evidence": sum(f.get("counts", {}).get("test_positives", 0) > 0 for f in fold_results),
        "folds_with_validation_threshold_meeting_gate": sum(f.get("validation_threshold_90pct_precision_min_5_alerts") is not None for f in fold_results),
        "folds_with_validation_max_precision_threshold": sum(f.get("validation_max_precision_threshold_event_date") is not None for f in fold_results),
        "unscored_test_routes": no_test_coverage, "folds": fold_results,
        "pooled_heldout_route_day_metrics_at_fixed_0_5": pooled_metrics,
        "pooled_heldout_event_date_metrics_at_fixed_0_5": date_metrics,
        "pooled_heldout_event_date_metrics_at_fold_validation_max_precision_threshold": selected_event_metrics,
        "pooled_event_date_wilson_lower_95_descriptive": (wilson_lower(date_metrics["true_positives"], date_metrics["alerts"]) if date_metrics and date_metrics["alerts"] else None),
        "limitations": ["The positive target is heterogeneous evidence; lack of an entry is not proof that no fire occurred.",
            "INPE's AMS reference detections use Aqua/MODIS and are not an independent sensor from MOD14A1.",
            "MODIS clear QA creates observed no-detection labels for sampled pixels only; unresolved route corridor cells remain unobserved.",
            "Weather is represented by one midpoint and the test archive has incomplete satellite periods in 2024-2026.",
            "A 100 km route-neighborhood holdout is stronger than a random route-day split but does not establish transfer to unseen ecological or climatic regimes.",
            "Wilson intervals are descriptive and ignore temporal autocorrelation and shared physical incidents.",
            "This experiment does not establish calibrated fire probability, safe alert precision, or deployment readiness."],
        "synthetic_observations": 0, "model_artifact_written": False, "deployment_approved": False}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    OUT_MD.write_text("# Validación geográfica y temporal del dataset unificado\n\n" +
        f"Se reservaron grupos completos de rutas próximas (distancia entre trazados muestreados ≤{REGION_RADIUS_KM:g} km). Cada pliegue entrenó con rutas de otros grupos en 2022, seleccionó umbral en 2023 y probó rutas reservadas en 2024-2026. El corte 0,5 se muestra solo como diagnóstico.\n\n" +
        f"Pliegues puntuados: {result['scored_fold_count']} de {result['fold_count']}; solo {result['folds_with_positive_test_evidence']} grupos tuvieron evidencia positiva en el test y {result['folds_with_validation_threshold_meeting_gate']} encontraron un umbral de validación de 90% con cinco alertas mínimas. Métricas agregadas ruta-día a 0,5: {json.dumps(pooled_metrics, ensure_ascii=False)}.\n\n" +
        f"Con el corte de máxima precisión seleccionado por validación en cada región, el resultado agregado por fecha es {json.dumps(selected_event_metrics, ensure_ascii=False)}.\n\n" +
        f"Métricas agrupadas por fecha: {json.dumps(date_metrics, ensure_ascii=False)}; límite inferior Wilson descriptivo: {result['pooled_event_date_wilson_lower_95_descriptive']}.\n\n" +
        "Esta prueba reduce la contaminación geográfica entre rutas cercanas, pero los bloques son aproximaciones espaciales y la etiqueta no es verdad exhaustiva del fuego físico. Consultar el JSON para tamaños de pliegue, regiones, umbrales y linaje de fuentes.\n", encoding="utf-8")
    print(json.dumps({"report": OUT.relative_to(ROOT).as_posix(),
        "region_count": len(regions), "region_sizes": [len(g) for g in regions],
        "scored_folds": result["scored_fold_count"], "unscored_routes": no_test_coverage,
        "pooled_route_day": pooled_metrics, "pooled_event_date": date_metrics,
        "pooled_event_date_at_validation_max_precision": selected_event_metrics,
        "precision_wilson_lower_descriptive": result["pooled_event_date_wilson_lower_95_descriptive"]},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
