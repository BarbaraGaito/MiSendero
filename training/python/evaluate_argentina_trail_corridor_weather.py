"""Evaluate archived JMA weather against in-app trail-corridor MODIS labels.

Research-only. A positive means a MOD14A1 active-fire pixel was detected in
the sampled corridor on that route/date; a negative requires at least 80%
clear-land QA coverage. It does not claim physical-fire ground truth.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta

from environmental_sources import ROOT

PRIVATE = ROOT / "training/data/environmental/private"
LABEL_DIR = PRIVATE / "argentina-trail-modis-labels-all-routes-full-archive-2026-10"
LABELS = LABEL_DIR / "observations.csv.gz"
LABEL_MANIFEST = LABEL_DIR / "manifest.json"
WEATHER_ARCHIVES = [
    PRIVATE / "openmeteo-jma-gsm-trail-midpoints-2022-01-01-2024-01-01.json.gz",
    PRIVATE / "openmeteo-jma-gsm-trail-midpoints-2024-01-01-2026-10-16.json.gz",
]
WEATHER_MANIFESTS = [path.with_name(path.name.removesuffix(".json.gz") + "-manifest.json")
                     for path in WEATHER_ARCHIVES]
OUT_DIR = ROOT / "docs/environmental-models-2026-10-22"
OUT = OUT_DIR / "argentina-trail-corridor-jma-weather-evaluation-all-routes-2026-10.json"
OUT_MD = OUT_DIR / "argentina-trail-corridor-jma-weather-evaluation-all-routes-2026-10.md"
WEATHER_VARIABLES = ("temperature_2m_previous_day1", "relative_humidity_2m_previous_day1",
                     "wind_speed_10m_previous_day1", "precipitation_previous_day1")
WEATHER_FEATURES = ("temperature_mean", "temperature_max", "humidity_mean", "humidity_min",
                    "wind_mean", "wind_max", "precipitation_sum")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_weather() -> dict:
    daily = {}
    for archive, manifest_path in zip(WEATHER_ARCHIVES, WEATHER_MANIFESTS):
        with gzip.open(archive, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        locations = manifest["locations"]
        if len(payload) != len(locations):
            raise ValueError(f"Forecast rows and route metadata misaligned in {archive.name}")
        for route, location in zip(locations, payload):
            hourly = location.get("hourly", {})
            times = hourly.get("time", [])
            if not times:
                raise ValueError(f"No forecast hours for {route['route_id']}")
            variables = {v: hourly.get(v, []) for v in WEATHER_VARIABLES}
            if any(len(values) != len(times) for values in variables.values()):
                raise ValueError(f"Misaligned weather variables for {route['route_id']}")
            indices_by_day = defaultdict(list)
            for index, time in enumerate(times):
                indices_by_day[time[:10]].append(index)
            for day, indices in indices_by_day.items():
                if len(indices) != 24 or any(variables[v][i] is None for v in WEATHER_VARIABLES for i in indices):
                    continue
                values = {name: [variables[source][i] for i in indices]
                          for name, source in zip(("temperature", "humidity", "wind", "precipitation"), WEATHER_VARIABLES)}
                key = (route["route_id"], day)
                if key in daily:
                    raise ValueError(f"Overlapping forecast archives at {key}")
                daily[key] = {
                    "temperature_mean": sum(values["temperature"]) / 24,
                    "temperature_max": max(values["temperature"]),
                    "humidity_mean": sum(values["humidity"]) / 24,
                    "humidity_min": min(values["humidity"]),
                    "wind_mean": sum(values["wind"]) / 24,
                    "wind_max": max(values["wind"]),
                    "precipitation_sum": sum(values["precipitation"])}
    return daily


def load_route_day_labels() -> tuple[list, dict]:
    stats = defaultdict(lambda: {"pixels": 0, "valid": 0, "positive_pixels": 0,
                                 "clear_pixels": 0, "positive_sources": set()})
    with gzip.open(LABELS, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            key_date = row["observed_date"]
            qa, mask = int(row["qa"]), int(row["fire_mask"])
            valid_land = (qa & 3) == 2 and mask in (5, 8, 9)
            positive = valid_land and mask in (8, 9)
            clear = valid_land and mask == 5
            for route in row["route_ids"].split("|"):
                item = stats[(route, key_date)]
                item["pixels"] += 1
                item["valid"] += int(valid_land)
                item["positive_pixels"] += int(positive)
                item["clear_pixels"] += int(clear)
                if positive:
                    item["positive_sources"].add(row["item_id"])
    rows, excluded = [], {"insufficient_qa_coverage": 0}
    for (route, day), item in stats.items():
        coverage = item["valid"] / item["pixels"] if item["pixels"] else 0
        if coverage < 0.80:
            excluded["insufficient_qa_coverage"] += 1
            continue
        rows.append({"route": route, "date": day,
            "label_modis_detection": int(item["positive_pixels"] > 0),
            "positive_pixels": item["positive_pixels"], "clear_pixels": item["clear_pixels"],
            "observed_pixels": item["pixels"], "valid_pixels": item["valid"],
            "qa_coverage": coverage, "source_items": len(item["positive_sources"])})
    return rows, {"route_dates_before_qa_rule": len(stats),
                   "route_dates_after_qa_rule": len(rows), **excluded}


def add_calendar(day: str) -> tuple[float, float]:
    day_of_year = datetime.fromisoformat(day).timetuple().tm_yday
    return math.sin(2 * math.pi * day_of_year / 365.25), math.cos(2 * math.pi * day_of_year / 365.25)


def average_precision(y: list, scores: list) -> float | None:
    positives = sum(y)
    if not positives:
        return None
    order = sorted(range(len(y)), key=lambda i: scores[i], reverse=True)
    found, area = 0, 0.0
    for rank, index in enumerate(order, start=1):
        if y[index]:
            found += 1
            area += found / rank
    return area / positives


def wilson_lower(successes: int, total: int) -> float | None:
    if total == 0:
        return None
    z = 1.6448536269514722
    phat = successes / total
    denominator = 1 + z * z / total
    center = phat + z * z / (2 * total)
    margin = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total))
    return max(0.0, (center - margin) / denominator)


def summary(rows: list, probability: list, threshold: float) -> dict:
    y = [row["label_modis_detection"] for row in rows]
    predicted = [score >= threshold for score in probability]
    tp = sum(positive and alert for positive, alert in zip(y, predicted))
    fp = sum((not positive) and alert for positive, alert in zip(y, predicted))
    fn = sum(positive and (not alert) for positive, alert in zip(y, predicted))
    tn = len(y) - tp - fp - fn
    positives, alerts = sum(y), tp + fp
    return {"route_days": len(y), "positive_route_days": positives,
        "prevalence": positives / len(y) if y else None,
        "threshold": float(threshold), "alerts": alerts, "true_positives": tp,
        "false_positives": fp, "false_negatives": fn,
        "precision": tp / alerts if alerts else 0.0,
        "precision_wilson_one_sided_95_lower_bound_independent_days": wilson_lower(tp, alerts),
        "recall": tp / positives if positives else 0.0,
        "average_precision": average_precision(y, probability),
        "brier": sum((score - label) ** 2 for score, label in zip(probability, y)) / len(y) if y else None,
        "confusion_matrix_tn_fp_fn_tp": [tn, fp, fn, tp]}


def choose_threshold(y: list, probability: list) -> dict | None:
    feasible = []
    for threshold in sorted(set(probability)):
        predicted = [score >= threshold for score in probability]
        alerts = sum(predicted)
        if alerts < 5:
            continue
        tp = sum(bool(label) and alert for label, alert in zip(y, predicted))
        precision = tp / alerts if alerts else 0.0
        recall = tp / sum(y) if sum(y) else 0.0
        if precision >= 0.90:
            feasible.append((recall, precision, -alerts, float(threshold)))
    if not feasible:
        return None
    recall, precision, neg_alerts, threshold = max(feasible)
    return {"threshold": threshold, "validation_precision": precision,
            "validation_recall": recall, "validation_alerts": -neg_alerts}


def count_events(rows: list) -> dict:
    positives = sorted((row for row in rows if row["label_modis_detection"]), key=lambda row: (row["route"], row["date"]))
    episodes, previous, positive_dates, positive_routes = 0, {}, set(), set()
    for row in positives:
        day = datetime.fromisoformat(row["date"]).date()
        last = previous.get(row["route"])
        if last is None or day - last > timedelta(days=2):
            episodes += 1
        previous[row["route"]] = day
        positive_dates.add(row["date"])
        positive_routes.add(row["route"])
    return {"positive_route_days": len(positives), "positive_route_dates": len(positive_dates),
            "positive_route_fire_episodes_gap_gt_2_days": episodes,
            "routes_with_positive_days": len(positive_routes)}


def fit_logistic(train: list, features: list, routes: list, epochs: int = 180) -> dict:
    means = [sum(row["features"][i] for row in train) / len(train) for i in range(len(features))]
    scales = []
    for i, mean in enumerate(means):
        variance = sum((row["features"][i] - mean) ** 2 for row in train) / len(train)
        scales.append(math.sqrt(variance) or 1.0)
    normalized = [[(row["features"][i] - means[i]) / scales[i] for i in range(len(features))]
                  for row in train]
    positives = sum(row["label_modis_detection"] for row in train)
    negatives = len(train) - positives
    if not positives or not negatives:
        raise ValueError("Both classes are required for model fitting")
    pos_weight, neg_weight = len(train) / (2 * positives), len(train) / (2 * negatives)
    weights, route_weights, bias = [0.0] * len(features), {route: 0.0 for route in routes}, 0.0
    learning_rate, regularization = 0.3, 0.01
    for epoch in range(epochs):
        grad = [0.0] * len(features)
        route_grad = {route: 0.0 for route in routes}
        bias_grad = 0.0
        for row, vector in zip(train, normalized):
            z = bias + route_weights[row["route"]] + sum(w * x for w, x in zip(weights, vector))
            probability = 1 / (1 + math.exp(-max(-35.0, min(35.0, z))))
            label = row["label_modis_detection"]
            error = (probability - label) * (pos_weight if label else neg_weight)
            bias_grad += error
            route_grad[row["route"]] += error
            for i, value in enumerate(vector):
                grad[i] += error * value
        rate = learning_rate / math.sqrt(1 + epoch / 25)
        count = len(train)
        bias -= rate * bias_grad / count
        for i in range(len(weights)):
            weights[i] -= rate * (grad[i] / count + regularization * weights[i])
        for route in routes:
            route_weights[route] -= rate * (route_grad[route] / count + regularization * route_weights[route])
    return {"means": means, "scales": scales, "weights": weights,
            "route_weights": route_weights, "bias": bias}


def predict(model: dict, rows: list) -> list:
    output = []
    for row in rows:
        vector = [(row["features"][i] - model["means"][i]) / model["scales"][i]
                  for i in range(len(model["weights"]))]
        z = model["bias"] + model["route_weights"].get(row["route"], 0.0)
        z += sum(w * x for w, x in zip(model["weights"], vector))
        output.append(1 / (1 + math.exp(-max(-35.0, min(35.0, z)))))
    return output


def main() -> None:
    required = [LABELS, LABEL_MANIFEST, *WEATHER_ARCHIVES, *WEATHER_MANIFESTS]
    if not all(path.is_file() for path in required):
        raise FileNotFoundError("Missing route corridor labels or JMA archive")
    label_manifest = json.loads(LABEL_MANIFEST.read_text(encoding="utf-8"))
    weather_manifests = [json.loads(path.read_text(encoding="utf-8")) for path in WEATHER_MANIFESTS]
    if sha256(LABELS) != label_manifest["observations_sha256"]:
        raise ValueError("MODIS route-corridor label hash mismatch")
    for archive, manifest in zip(WEATHER_ARCHIVES, weather_manifests):
        if sha256(archive) != manifest["compressed_response_sha256"]:
            raise ValueError(f"JMA archive hash mismatch: {archive.name}")
    labels, label_quality = load_route_day_labels()
    weather = load_weather()
    rows = []
    for label in labels:
        forecast = weather.get((label["route"], label["date"]))
        if forecast is None:
            continue
        season = add_calendar(label["date"])
        rows.append(label | {"features": [forecast[name] for name in WEATHER_FEATURES] + list(season)})
    if not rows:
        raise ValueError("No route/date labels aligned with forecast archive")
    rows.sort(key=lambda row: (row["date"], row["route"]))
    train = [row for row in rows if row["date"] < "2023-01-01"]
    validation = [row for row in rows if "2023-01-01" <= row["date"] < "2024-01-01"]
    test = [row for row in rows if row["date"] >= "2024-01-01"]
    if not train or not validation or not test:
        raise ValueError("Temporal partitions are empty")
    route_ids = sorted({row["route"] for row in rows})
    feature_names = list(WEATHER_FEATURES) + ["annual_sin", "annual_cos"]
    model = fit_logistic(train, feature_names, route_ids)
    validation_probability = predict(model, validation)
    test_probability = predict(model, test)
    y_valid = [row["label_modis_detection"] for row in validation]
    threshold_choice = choose_threshold(y_valid, validation_probability)
    threshold = threshold_choice["threshold"] if threshold_choice else 0.5
    validation_metrics = {"metrics_at_0_5_diagnostic": summary(validation, validation_probability, 0.5),
        "precision_threshold_choice": threshold_choice}
    test_metrics = {"threshold_from_validation_or_0_5_diagnostic": threshold,
        "threshold_source": "validation_90pct_precision" if threshold_choice else "fixed_0.5_diagnostic_no_feasible_validation_threshold",
        "metrics": summary(test, test_probability, threshold)}
    predictions = [{"route": row["route"], "date": row["date"],
        "observed_modis_detection": int(row["label_modis_detection"]), "score": float(score),
        "threshold": threshold, "alert": bool(score >= threshold)}
        for row, score in zip(test, test_probability)]
    baseline_train = [{**row, "features": row["features"][-2:]} for row in train]
    baseline_validation = [{**row, "features": row["features"][-2:]} for row in validation]
    baseline_test = [{**row, "features": row["features"][-2:]} for row in test]
    baseline = fit_logistic(baseline_train, ["annual_sin", "annual_cos"], route_ids)
    baseline_valid_probability = predict(baseline, baseline_validation)
    baseline_test_probability = predict(baseline, baseline_test)
    baseline_threshold = choose_threshold(y_valid, baseline_valid_probability)
    baseline_threshold_value = baseline_threshold["threshold"] if baseline_threshold else 0.5
    baseline_validation_metrics = {"metrics_at_0_5_diagnostic": summary(validation, baseline_valid_probability, 0.5),
        "precision_threshold_choice": baseline_threshold}
    baseline_test_metrics = {"threshold_from_validation_or_0_5_diagnostic": baseline_threshold_value,
        "threshold_source": "validation_90pct_precision" if baseline_threshold else "fixed_0.5_diagnostic_no_feasible_validation_threshold",
        "metrics": summary(test, baseline_test_probability, baseline_threshold_value)}
    selected = ("jma_weather_logistic"
                if validation_metrics["metrics_at_0_5_diagnostic"]["average_precision"]
                >= baseline_validation_metrics["metrics_at_0_5_diagnostic"]["average_precision"]
                else "seasonal_base_rate")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {"experiment_id": "argentina-in-app-trail-corridor-jma-weather-modis-temporal-test",
        "status": "exploratory_not_reliable_for_operational_alerts",
        "prediction_target": "Next-UTC-day Terra MOD14A1 active-fire detection (FireMask 8/9) somewhere in the sampled corridor for a given route.",
        "negative_definition": "No active-fire detection, with at least 80% of the sampled route-corridor pixels classified as clear land by MODIS QA on that date.",
        "forecast_alignment": "JMA GSM fixed 24-hour lead archived forecasts are grouped by UTC target date; one route midpoint represents each trail.",
        "labels": {"manifest_sha256": sha256(LABEL_MANIFEST), "observations_sha256": sha256(LABELS),
            "manifest_counts": label_manifest["counts"], "route_day_quality": label_quality,
            "independent_positive_episode_summary": count_events(rows)},
        "weather": {"archives": [{"manifest_sha256": sha256(manifest_path),
                "archive_sha256": sha256(archive), "archive_bytes": archive.stat().st_size,
                "route_count": manifest["route_count"],
                "locations_with_missing_forecast_values": sum(any(v for v in item["missing_by_variable"].values())
                    for item in manifest["locations"])}
                for archive, manifest_path, manifest in zip(WEATHER_ARCHIVES, WEATHER_MANIFESTS, weather_manifests)],
            "complete_route_day_forecast_rows": len(weather)},
        "partitions": {"train": {"start": "2022-01-01", "end_exclusive": "2023-01-01", "rows": len(train), **count_events(train)},
            "validation": {"start": "2023-01-01", "end_exclusive": "2024-01-01", "rows": len(validation), **count_events(validation)},
            "temporal_test": {"start": "2024-01-01", "end_exclusive": "2027-01-01", "rows": len(test),
                "observed_years": sorted({row["date"][:4] for row in test}), **count_events(test)}},
        "features": {"baseline": ["annual_sin", "annual_cos"], "weather_candidate": feature_names,
            "algorithm": "class-balanced logistic regression, standardized continuous features, one-hot route effect; batch gradient descent (180 epochs, L2=0.01)"},
        "selection": {"selected_by_validation_average_precision": selected,
            "threshold_rule": "Validation only: maximize recall subject to precision >=90% and at least five route-day alerts; otherwise report 0.5 as a diagnostic."},
        "validation": {"weather_candidate": validation_metrics, "seasonal_base_rate": baseline_validation_metrics},
        "heldout_temporal_test": {"weather_candidate": test_metrics, "seasonal_base_rate": baseline_test_metrics},
        "test_predictions": ([{"model": "jma_weather_logistic", **item} for item in predictions]
            + [{"model": "seasonal_base_rate", "route": row["route"], "date": row["date"],
                "observed_modis_detection": int(row["label_modis_detection"]),
                "score": float(score), "threshold": baseline_threshold_value,
                "alert": bool(score >= baseline_threshold_value)}
                for row, score in zip(test, baseline_test_probability)]),
        "limitations": ["The target is satellite active-fire detection, not all fires, ignition probability, or verified fire on the trail.",
            "A clear QA pixel is a valid non-detection, not a guarantee that no physical fire existed.",
            "The 11x11 pixel corridor includes off-trail land; adjacent pixels and nearby days are correlated.",
            "A single route midpoint forecast may not represent weather across long routes.",
            "MODIS rasters are discontinuous after 2023: source coverage is limited to 2024-01-01 through 2024-03-12, 2025-06-18 through 2026-01-03, and 2026-07-20 through 2026-10-15; missing dates are unknown, not negatives.",
            "The positive route-day count is small. Daily route rows and same-date detections across routes are correlated; Wilson bounds assume independence and are optimistic for repeated fires.",
            "No synthetic records, production model artifact, app change, or deployment approval is produced."],
        "synthetic_observations": 0, "model_artifact_written": False, "deployment_approved": False}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Evaluación temporal por corredor de sendero con JMA y MODIS", "",
        "La unidad es ruta-fecha: se predice si MOD14A1 detectará fuego activo en el corredor muestreado al día siguiente. El negativo requiere al menos 80% de cobertura QA despejada. No representa incendios físicos confirmados ni fuego dentro del sendero.", "",
        f"Se alinearon {len(rows)} ruta-fechas de {len(route_ids)} rutas. Conteo de positivos: {json.dumps(result['labels']['independent_positive_episode_summary'], ensure_ascii=False)}.", "",
        f"Modelo JMA, validación: {json.dumps(validation_metrics, ensure_ascii=False)}; modelo estacional base: {json.dumps(baseline_validation_metrics, ensure_ascii=False)}.", "",
        f"Test temporal en las ventanas satelitales disponibles desde 2024, modelo JMA: {json.dumps(test_metrics, ensure_ascii=False)}; base estacional: {json.dumps(baseline_test_metrics, ensure_ascii=False)}.", "",
        "Las escenas posteriores a 2023 son discontinuas; sus fechas sin raster no se cuentan. La precisión no se considera fiable para alertas operativas: hay pocos episodios independientes, MODIS no es verdad de terreno completa y los días consecutivos no son independientes. El JSON incluye cortes, predicciones, hashes, definición QA, métricas y limitaciones."]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": OUT.relative_to(ROOT).as_posix(), "rows": len(rows),
        "positive_summary": result["labels"]["independent_positive_episode_summary"],
        "partitions": result["partitions"], "selected": selected,
        "validation": validation_metrics, "test": test_metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
