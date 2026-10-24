"""Nested spatial-temporal validation of tabular fire-evidence classifiers.

Each spatial fold holds out a complete route-neighborhood. Candidate family,
operating threshold and hyperparameters are selected only on 2023 data from
the other regions; the held-out region's 2024-2026 rows are scored once.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

import evaluate_modis_inpe_union_geographic_holdout as spatial
from environmental_sources import ROOT, sha256
from evaluate_argentina_trail_corridor_weather import average_precision, summary, wilson_lower

REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
OUT = REPORT_DIR / "fire-modis-inpe-snmf-gfa-nested-geographic-model-family-all-41.json"
OUT_MD = REPORT_DIR / "fire-modis-inpe-snmf-gfa-nested-geographic-model-family-all-41.md"
NUMERIC_FEATURES = ["temperature_mean", "temperature_max", "humidity_mean", "humidity_min",
                    "wind_mean", "wind_max", "precipitation_sum", "annual_sin", "annual_cos"]
TRAIN_START, VALIDATION_START, TEST_START, TEST_END = (
    "2022-01-01", "2023-01-01", "2024-01-01", "2027-01-01")
MIN_ALERTS = 5


def model_candidates(train_rows: list[dict]) -> dict:
    positives = sum(row["label"] for row in train_rows)
    negatives = len(train_rows) - positives
    return {
        "logistic_c0.1_balanced": LogisticRegression(
            C=0.1, class_weight="balanced", max_iter=1000, random_state=41),
        "random_forest_regularized": RandomForestClassifier(
            n_estimators=200, max_depth=4, min_samples_leaf=30, max_features="sqrt",
            class_weight="balanced_subsample", n_jobs=4, random_state=41),
        "extra_trees_regularized": ExtraTreesClassifier(
            n_estimators=200, max_depth=4, min_samples_leaf=30, max_features="sqrt",
            class_weight="balanced", n_jobs=4, random_state=41),
        "xgboost_depth2_regularized": XGBClassifier(
            n_estimators=150, max_depth=2, learning_rate=0.03, min_child_weight=8,
            subsample=0.8, colsample_bytree=0.8, reg_lambda=10,
            scale_pos_weight=negatives / max(1, positives), tree_method="hist",
            eval_metric="logloss", n_jobs=4, random_state=41),
    }


def fit_model(train: list[dict], validation: list[dict], test: list[dict], estimator):
    # Dense encoded matrix is small (~28k x 50); fit all transforms on training only.
    train_rows = train
    all_rows = train + validation + test
    numeric = np.asarray([row["features"] for row in all_rows], dtype=float)
    route = np.asarray([row["route"] for row in all_rows], dtype=object).reshape(-1, 1)
    x = np.empty((len(all_rows), len(NUMERIC_FEATURES) + 1), dtype=object)
    x[:, :len(NUMERIC_FEATURES)] = numeric
    x[:, len(NUMERIC_FEATURES):] = route
    n_train, n_val = len(train), len(validation)
    preprocessor = ColumnTransformer([
        ("numeric", StandardScaler(), list(range(len(NUMERIC_FEATURES)))),
        ("route", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
         [len(NUMERIC_FEATURES)]),
    ], sparse_threshold=0)
    pipeline = Pipeline([("features", preprocessor), ("classifier", estimator)])
    y_train = np.asarray([row["label"] for row in train_rows], dtype=int)
    pipeline.fit(x[:n_train], y_train)
    val_scores = pipeline.predict_proba(x[n_train:n_train + n_val])[:, 1]
    test_scores = pipeline.predict_proba(x[n_train + n_val:])[:, 1]
    return val_scores, test_scores


def select_validation_cutoff(rows: list[dict], scores: np.ndarray) -> dict | None:
    candidates = []
    y = np.asarray([row["label"] for row in rows], dtype=int)
    for threshold in np.unique(scores):
        alerts = scores >= threshold
        alert_count = int(alerts.sum())
        if alert_count < MIN_ALERTS:
            continue
        tp = int(np.sum((y == 1) & alerts))
        precision = tp / alert_count
        recall = tp / int(y.sum()) if y.sum() else 0.0
        ap = average_precision(y.tolist(), scores.tolist())
        candidates.append((precision, recall, ap, -alert_count, float(threshold), tp, alert_count))
    if not candidates:
        return None
    precision, recall, ap, _, threshold, tp, alerts = max(candidates)
    return {"threshold": threshold, "validation_precision": precision,
        "validation_recall": recall, "validation_average_precision": ap,
        "validation_true_positives": tp, "validation_alerts": alerts}


def date_predictions(rows: list[dict], scores: np.ndarray, threshold: float) -> dict[str, dict]:
    result = defaultdict(lambda: {"label": 0, "score": 0.0, "alert": False})
    for row, score in zip(rows, scores):
        item = result[row["date"]]
        item["label"] = max(item["label"], row["label"])
        item["score"] = max(item["score"], float(score))
        item["alert"] = item["alert"] or float(score) >= threshold
    return result


def main() -> None:
    rows, source_provenance = spatial.build_rows()
    routes = spatial.union.route_lines()
    routes = {name: line for name, line in routes.items()
              if any(row["route"] == name for row in rows)}
    regions = spatial.route_regions(routes)
    fold_results, pooled = [], []
    for fold_index, heldout_routes in enumerate(regions, start=1):
        held = set(heldout_routes)
        train = [row for row in rows if row["route"] not in held
            and TRAIN_START <= row["date"] < VALIDATION_START]
        validation = [row for row in rows if row["route"] not in held
            and VALIDATION_START <= row["date"] < TEST_START]
        test = [row for row in rows if row["route"] in held
            and TEST_START <= row["date"] < TEST_END]
        fold = {"fold": fold_index, "heldout_routes": heldout_routes,
            "counts": {"train_rows": len(train), "train_positives": sum(r["label"] for r in train),
                "validation_rows": len(validation), "validation_positives": sum(r["label"] for r in validation),
                "test_rows": len(test), "test_positives": sum(r["label"] for r in test)}}
        if not train or not validation or not test or not any(r["label"] for r in train):
            fold["status"] = "not_estimable"
            fold_results.append(fold)
            continue
        candidate_validation = []
        for model_name, estimator in model_candidates(train).items():
            val_scores, test_scores = fit_model(train, validation, test, estimator)
            cutoff = select_validation_cutoff(validation, val_scores)
            if cutoff is None:
                continue
            candidate_validation.append((cutoff["validation_precision"],
                cutoff["validation_recall"], cutoff["validation_average_precision"],
                model_name, estimator, cutoff, test_scores, val_scores))
        if not candidate_validation:
            fold["status"] = "no_validation_cutoff_with_minimum_alerts"
            fold_results.append(fold)
            continue
        selected = max(candidate_validation, key=lambda item: item[:3])
        precision, recall, ap, model_name, estimator, cutoff, test_scores, val_scores = selected
        fold["status"] = "scored"
        fold["selected_model"] = model_name
        fold["selected_validation_cutoff"] = cutoff
        fold["candidate_validation_results"] = [{"model": item[3], **item[5]}
            for item in candidate_validation]
        test_summary = summary(test, test_scores.tolist(), cutoff["threshold"])
        fold["heldout_test_route_day_metrics_at_validation_selected_threshold"] = test_summary
        per_date = date_predictions(test, test_scores, cutoff["threshold"])
        fold["heldout_test_event_date_metrics_at_validation_selected_threshold"] = {
            "event_dates": len(per_date),
            "positive_event_dates": sum(v["label"] for v in per_date.values()),
            "alerts": sum(v["alert"] for v in per_date.values()),
            "true_positives": sum(v["label"] and v["alert"] for v in per_date.values()),
            "false_positives": sum((not v["label"]) and v["alert"] for v in per_date.values()),
            "false_negatives": sum(v["label"] and (not v["alert"]) for v in per_date.values())}
        fold_results.append(fold)
        pooled.extend({"row": row, "score": float(score), "threshold": cutoff["threshold"]}
                      for row, score in zip(test, test_scores))

    date_groups = defaultdict(lambda: {"label": 0, "alert": False, "score": 0.0})
    for item in pooled:
        row = item["row"]
        group = date_groups[row["date"]]
        group["label"] = max(group["label"], row["label"])
        group["score"] = max(group["score"], item["score"])
        group["alert"] = group["alert"] or item["score"] >= item["threshold"]
    tp = sum(v["label"] and v["alert"] for v in date_groups.values())
    fp = sum((not v["label"]) and v["alert"] for v in date_groups.values())
    fn = sum(v["label"] and (not v["alert"]) for v in date_groups.values())
    alerts = tp + fp
    pooled_metrics = {"event_dates": len(date_groups),
        "positive_event_dates": sum(v["label"] for v in date_groups.values()),
        "alerts": alerts, "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": tp / alerts if alerts else 0.0,
        "wilson_lower_95_descriptive": wilson_lower(tp, alerts) if alerts else None,
        "recall": tp / sum(v["label"] for v in date_groups.values()) if any(v["label"] for v in date_groups.values()) else 0.0}
    result = {"experiment_id": "all-41-nested-spatial-temporal-tabular-model-family-v1",
        "status": "exploratory_not_reliable_fire_prediction",
        "target": "Unified source-evidence detection, not verified physical fire occurrence.",
        "method": {"train": [TRAIN_START, VALIDATION_START],
            "validation": [VALIDATION_START, TEST_START], "test": [TEST_START, TEST_END],
            "geographic_grouping": f"Full route polylines sampled every {spatial.ROUTE_SAMPLE_KM:g} km, connected if within {spatial.REGION_RADIUS_KM:g} km.",
            "model_selection": "Within each held-out geographic fold, select model and cutoff on 2023 data from non-held-out routes only. Maximize validation precision with at least five alerts, then recall and AP.",
            "candidate_families": ["regularized class-balanced logistic regression", "regularized Random Forest", "regularized Extra Trees", "regularized XGBoost"],
            "precision_gate": ">=90% validation precision and at least five alerts."},
        "source_provenance": source_provenance, "geographic_fold_count": len(fold_results),
        "scored_folds": sum(f.get("status") == "scored" for f in fold_results),
        "folds_passing_90pct_precision_gate": sum(
            f.get("selected_validation_cutoff", {}).get("validation_precision", 0) >= 0.90
            for f in fold_results),
        "folds": fold_results,
        "pooled_heldout_event_date_metrics_at_validation_selected_models_and_cutoffs": pooled_metrics,
        "limitations": ["The 2022 training set contains very few positive route-days and the validation period has sparse event records.",
            "INPE and GFA detections share the MODIS family; route labels are mixed sensor/report evidence.",
            "A source-evidence negative uses clear MODIS QA in sampled corridor pixels and is not proof of no physical fire.",
            "Model and threshold choices can overfit one validation season; a new prospective fire season remains necessary.",
            "Historical test results were previously inspected with logistic regression; these model-family results are exploratory.",
            "VGG19/YOLO are not applicable because there are no training images in this tabular cohort."],
        "synthetic_observations": 0, "deployment_approved": False}
    result["dataset"] = {"path": spatial.union.DATASET.relative_to(ROOT).as_posix(),
        "sha256": sha256(spatial.union.DATASET),
        "manifest_sha256": sha256(spatial.union.DATASET_MANIFEST),
        "rows": len(rows)}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    OUT_MD.write_text("# Comparación tabular anidada geográfica-temporal\n\n" +
        f"Se evaluaron cuatro familias dentro de cada uno de {result['geographic_fold_count']} bloques geográficos. La región de test no interviene en la elección de modelo ni del umbral; selección con 2023 y mínimo cinco alertas. Bloques que pasan gate 90%: {result['folds_passing_90pct_precision_gate']}.\n\n" +
        f"Métricas agrupadas por fecha en el test 2024-2026, con los modelos y cortes elegidos en validación: {json.dumps(pooled_metrics, ensure_ascii=False)}.\n\n" +
        "El JSON detalla candidatos, umbrales y métricas por región. La etiqueta representa evidencia registrada y no incendios físicos exhaustivos.\n", encoding="utf-8")
    print(json.dumps({"report": OUT.relative_to(ROOT).as_posix(),
        "folds": result["geographic_fold_count"], "scored": result["scored_folds"],
        "folds_passing_gate": result["folds_passing_90pct_precision_gate"],
        "pooled_test_event_dates": pooled_metrics,
        "selected_by_fold": [{"fold": f["fold"], "routes": f["heldout_routes"],
            "model": f.get("selected_model"), "validation": f.get("selected_validation_cutoff")}
            for f in fold_results]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
