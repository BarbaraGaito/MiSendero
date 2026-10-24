"""Compare a frozen MODIS detection baseline with the same model plus 24h weather forecasts.

Research experiment only. Labels remain real MOD14A1 daily FireMask/QA and the
existing temporal/geographic split. Weather is added from archived previous
runs; this script never writes an app artifact or changes the frozen baseline.
"""
from __future__ import annotations

from array import array
from collections import Counter
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             confusion_matrix, precision_score, recall_score)
from xgboost import XGBClassifier

from environmental_sources import ROOT, sha256, utc
from fire_sources import OBSERVATIONS, PRIVATE, PROTOCOL, REPORT_DIR, protocol
from fire_features import FEATURES, iter_examples, load_cells, partitions
from train_snmf_report_proxy_gfs_model import load_weather_with_geography

WEATHER_FILES = [
    PRIVATE / "openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2022-01-01-2023-07-01.json.gz",
    PRIVATE / "openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2023-07-01-2024-01-01.json.gz",
]
SOURCE_AUDIT = REPORT_DIR / "fire-source-audit.json"
OUT = REPORT_DIR / "fire-weather-feature-comparison.json"
OUT_MD = REPORT_DIR / "fire-weather-feature-comparison.md"
WEATHER_FEATURES = ["temperature_mean", "temperature_max", "humidity_mean", "humidity_min",
                    "wind_mean", "wind_max", "precipitation_sum"]


def load_weather() -> pd.DataFrame:
    daily = load_weather_with_geography(WEATHER_FILES)
    daily["date"] = daily["date"].astype(str)
    return daily.set_index(["region", "date"]).sort_index()


def prepare_frame(cells, plan, weather: pd.DataFrame):
    columns = FEATURES + WEATHER_FEATURES
    data, rejected, region_codes, tile_codes = array("d"), Counter(), {}, {}
    weather_lookup = weather.to_dict(orient="index")
    for row in iter_examples(cells, plan, rejected):
        key = (row["region"], row["issued_at"][:10])
        forecast = weather_lookup.get(key)
        if forecast is None:
            rejected["no_archived_weather_for_region_date"] += 1
            continue
        values = [row[name] for name in FEATURES] + [forecast[name] for name in WEATHER_FEATURES]
        if any(pd.isna(value) for value in values):
            rejected["incomplete_archived_weather_features"] += 1
            continue
        region_code = region_codes.setdefault(row["region"], len(region_codes))
        tile_code = tile_codes.setdefault(row["tile"], len(tile_codes))
        data.extend(values + [row["observed"],
            *(utc(row[name]).timestamp() for name in ("issued_at", "target_at", "target_available_at")),
            region_code, tile_code])
    output_columns = columns + ["observed", "issued_at", "target_at", "target_available_at", "region_code", "tile_code"]
    frame = pd.DataFrame(np.frombuffer(data, dtype=np.float64).reshape((-1, len(output_columns))), columns=output_columns)
    for name in ("issued_at", "target_at", "target_available_at"):
        frame[name] = pd.to_datetime(frame[name], unit="s", utc=True)
    frame["region"] = pd.Categorical.from_codes(frame.region_code.to_numpy(dtype=int), list(region_codes))
    frame["tile"] = pd.Categorical.from_codes(frame.tile_code.to_numpy(dtype=int), list(tile_codes))
    return frame, dict(rejected)


def summarize(y, probability, threshold=0.5):
    y = np.asarray(y, dtype=np.uint8)
    p = np.asarray(probability, dtype=float)
    predicted = p >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {
        "observations": int(len(y)), "positive_observations": int(y.sum()),
        "threshold": float(threshold), "alerts": int(predicted.sum()),
        "true_positives": int(tp), "false_positives": int(fp),
        "false_negatives": int(fn), "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "average_precision": float(average_precision_score(y, p)) if y.sum() else None,
        "brier": float(brier_score_loss(y, p)) if len(y) else None,
        "confusion_matrix_tn_fp_fn_tp": [int(tn), int(fp), int(fn), int(tp)],
    }


def choose_threshold(y, probability, precision_target=0.90, minimum_alerts=5):
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y, probability)
    feasible = []
    for index, threshold in enumerate(thresholds):
        alerts = int(np.count_nonzero(probability >= threshold))
        if alerts >= minimum_alerts and precision[index] >= precision_target:
            feasible.append((float(recall[index]), float(precision[index]), -alerts, float(threshold), alerts))
    if not feasible:
        return None
    rec, prec, _, threshold, alerts = max(feasible)
    return {"threshold": threshold, "validation_precision": prec,
            "validation_recall": rec, "validation_alerts": alerts}


def aggregate_region_days(frame, mask, probability):
    selected = frame.loc[mask, ["region", "target_at", "observed"]].copy()
    selected["probability"] = probability
    grouped = selected.groupby(["region", "target_at"], observed=True, sort=True).agg(
        observed=("observed", "max"), probability=("probability", "max"), pixels=("observed", "size"))
    grouped = grouped.reset_index()
    grouped["target_date"] = grouped["target_at"].dt.strftime("%Y-%m-%d")
    return grouped


def main() -> None:
    if not all(path.is_file() for path in WEATHER_FILES + [OBSERVATIONS, PROTOCOL, SOURCE_AUDIT]):
        raise FileNotFoundError("Missing frozen MODIS labels, protocol, audit, or JMA previous-run archive")
    audit = json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))
    if audit["protocol_sha256"] != sha256(PROTOCOL) or audit["summary"]["observations_sha256"] != sha256(OBSERVATIONS):
        raise ValueError("MODIS source/protocol hash mismatch")
    plan = protocol()
    weather = load_weather()
    cells, quality = load_cells()
    frame, rejected = prepare_frame(cells, plan, weather)
    del cells
    if frame.empty:
        raise ValueError("No fire examples remain after archived forecast join")
    split = partitions(frame, plan)
    counts = {name: {"rows": int(mask.sum()), "positive_pixel_days": int(frame.loc[mask, "observed"].sum()),
                     "negative_pixel_days": int(mask.sum() - frame.loc[mask, "observed"].sum()),
                     "distinct_target_dates": int(frame.loc[mask, "target_at"].dt.date.nunique()),
                     "tiles": sorted(frame.loc[mask, "tile"].astype(str).unique().tolist())}
              for name, mask in split.items()}
    train_mask, valid_mask = split["train"], split["validation"]
    y = frame["observed"].to_numpy(dtype=np.uint8)
    class_ratio = float(np.count_nonzero(y[train_mask] == 0) / np.count_nonzero(y[train_mask] == 1))
    common = dict(n_estimators=150, max_depth=3, learning_rate=0.05,
                  objective="binary:logistic", tree_method="hist", scale_pos_weight=class_ratio,
                  subsample=1, colsample_bytree=1, random_state=42, n_jobs=2)
    candidates = {
        "frozen_xgboost_features": (FEATURES, XGBClassifier(**common)),
        "xgboost_plus_jma_24h_forecast": (FEATURES + WEATHER_FEATURES, XGBClassifier(**common)),
    }
    validation, test, validation_probabilities, models = {}, {}, {}, {}
    region_validation, region_test = {}, {}
    region_predictions = []
    for name, (feature_columns, model) in candidates.items():
        print(f"Fitting {name} on {int(train_mask.sum())} rows", flush=True)
        model.fit(frame.loc[train_mask, feature_columns], y[train_mask], verbose=False)
        models[name] = model
        valid_p = model.predict_proba(frame.loc[valid_mask, feature_columns])[:, 1]
        validation_probabilities[name] = valid_p
        validation[name] = summarize(y[valid_mask], valid_p)
        validation[name]["precision_threshold_choice"] = choose_threshold(y[valid_mask], valid_p)
        valid_groups = aggregate_region_days(frame, valid_mask, valid_p)
        region_validation[name] = summarize(valid_groups["observed"], valid_groups["probability"])
        region_validation[name]["precision_threshold_choice"] = choose_threshold(
            valid_groups["observed"], valid_groups["probability"])
    selected = max(candidates, key=lambda name: region_validation[name]["average_precision"] or -1)
    for name, (feature_columns, model) in candidates.items():
        test[name] = {}
        region_test[name] = {}
        for split_name in ("temporal_test", "geographic_test"):
            mask = split[split_name]
            probability = model.predict_proba(frame.loc[mask, feature_columns])[:, 1] if mask.any() else np.array([])
            test[name][split_name] = summarize(y[mask], probability)
            grouped = aggregate_region_days(frame, mask, probability)
            valid_choice = region_validation[name]["precision_threshold_choice"]
            threshold = valid_choice["threshold"] if valid_choice else 0.5
            region_test[name][split_name] = summarize(grouped["observed"], grouped["probability"], threshold)
            region_test[name][split_name]["threshold_source"] = "validation" if valid_choice else "fixed_0.5_diagnostic_no_validation_threshold"
            region_predictions.extend({
                "model": name, "partition": split_name, "region": str(row.region),
                "target_date": row.target_date, "observed_any_sampled_pixel": int(row.observed),
                "max_pixel_score": float(row.probability), "sampled_pixels": int(row.pixels),
                "alert_threshold": threshold, "alert": bool(row.probability >= threshold),
            } for row in grouped.itertuples(index=False))
    result = {
        "experiment_id": "mod14a1-jma-previous-run-weather-feature-ablation",
        "status": "exploratory_heldout_comparison_not_operational",
        "target": "MOD14A1 nominal/high-confidence active-fire detection (FireMask 8/9) versus valid clear-land no-detection (mask 5, land QA) in the same sampled pixel during the next UTC day; not physical-fire probability.",
        "forecast_issue_valid_protocol": "JMA GSM previous_day1 variables are aligned by their valid UTC date with the MODIS target day; the archive records previous-run fixed-lead forecasts, not reanalysis weather.",
        "protocol_sha256": sha256(PROTOCOL), "source_audit_sha256": sha256(SOURCE_AUDIT),
        "observation_sha256": sha256(OBSERVATIONS),
        "weather_archives_sha256": {path.name: sha256(path) for path in WEATHER_FILES},
        "weather_feature_columns": WEATHER_FEATURES,
        "baseline_feature_columns": FEATURES,
        "data": {"quality": quality, "rows_rejected_after_weather_join": rejected,
                 "class_ratio_before_weighting": class_ratio, "partitions": counts,
                 "weather_daily_rows": int(len(weather))},
        "selection": {"rule": "Select the feature set by validation average precision after aggregating the maximum sampled-pixel score by region-day; report the temporal and geographic holdouts once.",
                      "selected_on_validation": selected,
                      "validation_threshold_rule": "At region-day level, 90% precision with at least five alerts; threshold selected on validation only. If infeasible, test reports the fixed 0.5 threshold as diagnostic.",
                      "independent_test_usage": "Heldout test metrics are reporting only and do not change model, threshold, or features."},
        "validation_pixel_day": validation, "heldout_tests_pixel_day": test,
        "validation_region_day": region_validation, "heldout_tests_region_day": region_test,
        "region_day_predictions": region_predictions,
        "limitations": [
            "MODIS labels represent satellite detection, not all physical fires or ignition probability.",
            "Validation has few independent positive pixel-days; neighboring pixels and dates within the same fire are correlated.",
            "Route-level forecast values are repeated across sampled pixels within each of the eight catalog regions.",
            "The same previous MODIS detection-history features appear in both candidates; the ablation only tests whether JMA weather adds out-of-sample signal.",
            "Precision is pixel-day precision, not fire-event precision on a hiking trail.",
            "No hyperparameter search, synthetic observations, app change, or deployment artifact is produced.",
        ],
        "synthetic_observations": 0, "model_artifact_written": False,
        "deployment_approved": False,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# Aporte de pronósticos JMA a la detección diaria MODIS",
        "",
        "Comparación exploratoria con el protocolo MOD14A1 congelado: XGBoost con variables históricas del píxel frente al mismo XGBoost más temperatura, humedad, viento y precipitación pronosticados por JMA GSM para la fecha objetivo. La etiqueta conserva FireMask y QA del producto real.",
        "",
        f"El conjunto se cruzó con {len(weather)} filas región-fecha de pronóstico archivado; quedaron {len(frame)} ejemplos MODIS válidos. Los cortes temporal y geográfico se heredan del protocolo original. La selección se hace solo con validación; las métricas test se informan una vez.",
        "",
        f"El candidato elegido por average precision de validación en agregación región-día es `{selected}`. Validación píxel-día: baseline AP={validation['frozen_xgboost_features']['average_precision']:.6g}, con tiempo AP={validation['xgboost_plus_jma_24h_forecast']['average_precision']:.6g}. Validación región-día: baseline AP={region_validation['frozen_xgboost_features']['average_precision']:.6g}, con tiempo AP={region_validation['xgboost_plus_jma_24h_forecast']['average_precision']:.6g}.",
        "",
        f"Prueba temporal baseline: {json.dumps(test['frozen_xgboost_features']['temporal_test'], ensure_ascii=False)}",
        "",
        f"Prueba temporal con JMA: {json.dumps(test['xgboost_plus_jma_24h_forecast']['temporal_test'], ensure_ascii=False)}",
        "",
        f"Prueba geográfica baseline: {json.dumps(test['frozen_xgboost_features']['geographic_test'], ensure_ascii=False)}",
        "",
        f"Prueba geográfica con JMA: {json.dumps(test['xgboost_plus_jma_24h_forecast']['geographic_test'], ensure_ascii=False)}",
        "",
        f"Prueba temporal región-día, modelo elegido: {json.dumps(region_test[selected]['temporal_test'], ensure_ascii=False)}",
        "",
        f"Prueba geográfica región-día, modelo elegido: {json.dumps(region_test[selected]['geographic_test'], ensure_ascii=False)}",
        "",
        "Estas son métricas de píxel-día para detección MODIS, no precisión de incendio por sendero. La base mantiene pocos positivos independientes, por lo que una mejora numérica no justificaría por sí sola alertas de seguridad. El JSON incluye hashes, particiones, reglas de selección y límites.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "selected_on_validation": selected,
        "partitions": counts, "validation": validation, "tests": test,
        "weather_rows_rejected": rejected}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
