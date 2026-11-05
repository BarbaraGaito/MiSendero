"""Validation-selected tabular model-family comparison for the all-41 cohort."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from environmental_sources import ROOT

PRIVATE = ROOT / "training/data/environmental/private"
DATASET = PRIVATE / "argentina-route-fire-evidence-jma-unified-all-41-2022-2026.csv.gz"
MANIFEST = PRIVATE / "argentina-route-fire-evidence-jma-unified-all-41-2022-2026-manifest.json"
REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
OUT = REPORT_DIR / "fire-modis-inpe-snmf-gfa-tabular-model-family-all-41.json"
OUT_MD = REPORT_DIR / "fire-modis-inpe-snmf-gfa-tabular-model-family-all-41.md"
NUMERIC = ["temperature_mean", "temperature_max", "humidity_mean", "humidity_min",
           "wind_mean", "wind_max", "precipitation_sum", "annual_sin", "annual_cos"]
TRAIN, VALIDATION, TEST = "train_2022", "validation_2023", "test_2024_2026"
MIN_VALIDATION_ALERTS = 5


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def average_precision(y: np.ndarray, scores: np.ndarray) -> float:
    positives = int(y.sum())
    if not positives:
        return 0.0
    order = np.argsort(-scores)
    sorted_y = y[order]
    precision_at = np.cumsum(sorted_y) / (np.arange(len(y)) + 1)
    return float((precision_at * sorted_y).sum() / positives)


def brier(y: np.ndarray, scores: np.ndarray) -> float:
    return float(np.mean((y - scores) ** 2))


def wilson_lower(successes: int, total: int) -> float | None:
    if not total:
        return None
    z = 1.6448536269514722
    p = successes / total
    d = 1 + z * z / total
    center = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, (center - margin) / d)


def threshold_metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    alert = scores >= threshold
    tp = int(np.sum((y == 1) & alert))
    fp = int(np.sum((y == 0) & alert))
    fn = int(np.sum((y == 1) & ~alert))
    alerts = tp + fp
    return {"threshold": float(threshold), "observations": len(y),
        "positives": int(y.sum()), "alerts": alerts, "true_positives": tp,
        "false_positives": fp, "false_negatives": fn,
        "precision": tp / alerts if alerts else 0.0,
        "precision_wilson_lower_95_descriptive": wilson_lower(tp, alerts),
        "recall": tp / int(y.sum()) if y.sum() else 0.0,
        "average_precision": average_precision(y, scores), "brier": brier(y, scores)}


def max_validation_precision_threshold(y: np.ndarray, scores: np.ndarray) -> dict | None:
    candidates = []
    for threshold in np.unique(scores):
        alert = scores >= threshold
        alerts = int(alert.sum())
        if alerts < MIN_VALIDATION_ALERTS:
            continue
        tp = int(np.sum((y == 1) & alert))
        precision = tp / alerts
        recall = tp / int(y.sum()) if y.sum() else 0.0
        candidates.append((precision, recall, -alerts, float(threshold), tp, alerts))
    if not candidates:
        return None
    precision, recall, _, threshold, tp, alerts = max(candidates)
    return {"threshold": threshold, "validation_precision": precision,
        "validation_recall": recall, "validation_true_positives": tp,
        "validation_alerts": alerts, "minimum_alerts": MIN_VALIDATION_ALERTS}


def make_pipeline(estimator) -> Pipeline:
    features = ColumnTransformer([
        ("numeric", StandardScaler(), list(range(len(NUMERIC)))),
        ("route", OneHotEncoder(handle_unknown="ignore", sparse_output=False), [len(NUMERIC)]),
    ], sparse_threshold=0)
    return Pipeline([("features", features), ("model", estimator)])


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dataset_hash = sha256(DATASET)
    if dataset_hash != manifest["dataset_sha256"]:
        raise ValueError("Unified dataset hash mismatch")
    with gzip.open(DATASET, "rt", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    numeric = np.asarray([[float(row[name]) for name in NUMERIC] for row in rows], dtype=float)
    route = np.asarray([row["route_id"] for row in rows], dtype=object).reshape(-1, 1)
    x = np.empty((len(rows), len(NUMERIC) + 1), dtype=object)
    x[:, :len(NUMERIC)] = numeric
    x[:, len(NUMERIC):] = route
    y = np.asarray([int(row["source_evidence_label"]) for row in rows], dtype=int)
    partition = np.asarray([row["temporal_partition"] for row in rows], dtype=object)
    train_mask, val_mask, test_mask = partition == TRAIN, partition == VALIDATION, partition == TEST
    if not all(mask.any() for mask in (train_mask, val_mask, test_mask)):
        raise ValueError("Missing train, validation, or test temporal partition")
    train_pos = int(y[train_mask].sum())
    scale_pos = float((train_mask & (y == 0)).sum() / max(1, train_pos))
    candidates = {
        "logistic_c_0_01_balanced": LogisticRegression(C=0.01, class_weight="balanced", max_iter=1000, random_state=41),
        "logistic_c_0_1_balanced": LogisticRegression(C=0.1, class_weight="balanced", max_iter=1000, random_state=41),
        "logistic_c_1_balanced": LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000, random_state=41),
        "random_forest_leaf_10": RandomForestClassifier(n_estimators=300, max_depth=6, min_samples_leaf=10,
            max_features="sqrt", class_weight="balanced_subsample", n_jobs=4, random_state=41),
        "random_forest_leaf_30": RandomForestClassifier(n_estimators=300, max_depth=4, min_samples_leaf=30,
            max_features="sqrt", class_weight="balanced_subsample", n_jobs=4, random_state=41),
        "extra_trees_leaf_10": ExtraTreesClassifier(n_estimators=300, max_depth=6, min_samples_leaf=10,
            max_features="sqrt", class_weight="balanced", n_jobs=4, random_state=41),
        "extra_trees_leaf_30": ExtraTreesClassifier(n_estimators=300, max_depth=4, min_samples_leaf=30,
            max_features="sqrt", class_weight="balanced", n_jobs=4, random_state=41),
        "xgboost_depth_2": XGBClassifier(n_estimators=180, max_depth=2, learning_rate=0.03,
            min_child_weight=8, subsample=0.8, colsample_bytree=0.8, reg_lambda=10,
            scale_pos_weight=scale_pos, tree_method="hist", eval_metric="logloss", n_jobs=4, random_state=41),
        "xgboost_depth_3": XGBClassifier(n_estimators=180, max_depth=3, learning_rate=0.03,
            min_child_weight=12, subsample=0.8, colsample_bytree=0.8, reg_lambda=20,
            scale_pos_weight=scale_pos, tree_method="hist", eval_metric="logloss", n_jobs=4, random_state=41),
    }
    results, fitted = [], {}
    for name, estimator in candidates.items():
        model = make_pipeline(estimator)
        model.fit(x[train_mask], y[train_mask])
        val_scores = model.predict_proba(x[val_mask])[:, 1]
        threshold = max_validation_precision_threshold(y[val_mask], val_scores)
        result = {"model": name, "validation_average_precision": average_precision(y[val_mask], val_scores),
            "validation_brier": brier(y[val_mask], val_scores),
            "validation_at_0_5": threshold_metrics(y[val_mask], val_scores, 0.5),
            "validation_max_precision_cutoff_min_5": threshold}
        results.append(result)
        fitted[name] = model
    eligible = [r for r in results if r["validation_max_precision_cutoff_min_5"]]
    selected = max(eligible, key=lambda r: (
        r["validation_max_precision_cutoff_min_5"]["validation_precision"],
        r["validation_max_precision_cutoff_min_5"]["validation_recall"],
        r["validation_average_precision"]))
    selected_name = selected["model"]
    threshold = selected["validation_max_precision_cutoff_min_5"]["threshold"]
    test_scores = fitted[selected_name].predict_proba(x[test_mask])[:, 1]
    y_test = y[test_mask]
    test_metrics = threshold_metrics(y_test, test_scores, threshold)
    test_at_half = threshold_metrics(y_test, test_scores, 0.5)
    gate_passed = selected["validation_max_precision_cutoff_min_5"]["validation_precision"] >= 0.90
    result = {"experiment_id": "unified-all-41-tabular-model-family-validation-selected-2022-train-2023-val-2024-2026-test",
        "status": "exploratory_model_comparison_not_deployable_fire_probability",
        "target": "Unified source-evidence label for MOD14A1/INPE/SNMF/GFA on clear-QA observed route-days; not physical-fire truth.",
        "dataset": {"path": DATASET.relative_to(ROOT).as_posix(), "sha256": dataset_hash,
            "manifest_sha256": sha256(MANIFEST), "rows": len(rows),
            "train_rows": int(train_mask.sum()), "validation_rows": int(val_mask.sum()),
            "test_rows": int(test_mask.sum()), "train_positives": train_pos,
            "validation_positives": int(y[val_mask].sum()), "test_positives": int(y_test.sum())},
        "model_selection": {"criterion": "Maximize validation precision with at least five alerts; tie-break with validation recall then average precision. Never select by test.",
            "selected_model": selected_name, "validation_threshold": threshold,
            "validation_precision": selected["validation_max_precision_cutoff_min_5"]["validation_precision"],
            "validation_recall": selected["validation_max_precision_cutoff_min_5"]["validation_recall"],
            "90pct_precision_gate_passed": gate_passed, "minimum_validation_alerts": MIN_VALIDATION_ALERTS,
            "candidate_models": results},
        "temporal_test_at_validation_selected_threshold": test_metrics,
        "temporal_test_at_fixed_0_5_diagnostic": test_at_half,
        "limitations": ["Only 28 positive route-days are available for training in 2022; tree models can overfit despite regularization.",
            "Model-family selection uses one temporal validation year and is not geographic model selection.",
            "The 2024-2026 test was inspected during prior logistic experiments; this family comparison is exploratory even though this script selects models only by validation.",
            "Scores are not calibrated physical-fire probabilities; source-label coverage is incomplete and satellite families overlap.",
            "VGG19 and YOLO are image models and do not fit this tabular weather plus route-day dataset."],
        "synthetic_observations": 0, "deployment_approved": False}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    OUT_MD.write_text("# Comparación de modelos tabulares con fuentes unificadas all-41\n\n" +
        f"Se compararon {len(results)} configuraciones. El criterio fue maximizar la precisión en validación con al menos {MIN_VALIDATION_ALERTS} alertas. Modelo seleccionado: {selected_name}; precisión/recall de validación: {selected['validation_max_precision_cutoff_min_5']['validation_precision']:.3f}/{selected['validation_max_precision_cutoff_min_5']['validation_recall']:.3f}; gate 90%: {'aprobado' if gate_passed else 'no aprobado'}.\n\n" +
        f"En el test temporal 2024-2026 al umbral elegido en validación: {json.dumps(test_metrics, ensure_ascii=False)}.\n\n" +
        f"Diagnóstico test a 0,5: {json.dumps(test_at_half, ensure_ascii=False)}. El JSON guarda parámetros y métricas de todos los candidatos.\n\n" +
        "VGG19/YOLO son modelos de imagen y no corresponden a estas variables tabulares. El objetivo es evidencia registrada, no probabilidad exhaustiva de incendio físico.\n", encoding="utf-8")
    print(json.dumps({"report": OUT.relative_to(ROOT).as_posix(), "selected_model": selected_name,
        "validation_cutoff": selected["validation_max_precision_cutoff_min_5"],
        "90pct_precision_gate_passed": gate_passed, "test_at_selected_threshold": test_metrics,
        "test_at_0_5": test_at_half,
        "validation_candidates": [{"name": r["model"],
            "average_precision": r["validation_average_precision"],
            "max_precision": r["validation_max_precision_cutoff_min_5"]["validation_precision"],
            "recall": r["validation_max_precision_cutoff_min_5"]["validation_recall"],
            "threshold": r["validation_max_precision_cutoff_min_5"]["threshold"]}
            for r in results]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
