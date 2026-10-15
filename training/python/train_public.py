"""Train/evaluate native public labels with a sealed group-held-out test.

Outputs are research artifacts. Exporting a forest does not authorize using a
different label, time scale or population in the mobile app.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from common.augment import augment_dataset
from common.evaluation import evaluate_training_run
from common.export_forest import export_random_forest
from public_sources import ADAPTERS, OUTPUT, ROOT, build_public_dataset, digest


def group_split(frame: pd.DataFrame, geographic_holdout: dict | None = None):
    groups = frame["group_key"]
    if groups.nunique() < 4:
        raise ValueError("At least four independent groups are required; do not fall back to row splitting")
    if geographic_holdout:
        test_units = set(geographic_holdout["test_units"])
        field = "park" if geographic_holdout["unit"] == "park" else "regions"
        units = frame["lineage"].map(lambda row: {row[field]} if field == "park" else set(row[field]))
        observed = set().union(*units)
        if not test_units <= observed:
            raise ValueError("Prespecified geographic test units are absent; do not silently change the holdout")
        if any(unit & test_units and unit - test_units for unit in units):
            raise ValueError("Connected network crosses the geographic test boundary")
        is_test = units.map(lambda unit: bool(unit & test_units)).to_numpy()
        train, test = np.flatnonzero(~is_test), np.flatnonzero(is_test)
        if not len(train) or not len(test):
            raise ValueError("Empty prespecified geographic partition")
    else:
        # One fixed split. Never search seeds or select a test partition for scores.
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=42)
        train, test = next(splitter.split(frame, groups=groups))
    if set(groups.iloc[train]) & set(groups.iloc[test]):
        raise AssertionError("Group leakage")
    return train, test


def augmented(features, labels, enabled):
    if not enabled:
        return features, labels, 0
    if any(name.startswith("distance_basis_") or name.startswith("duration_basis_") or name.startswith("dem_") for name in features.columns):
        raise ValueError("Augmentation for APN categorical route bases and linked DEM features requires a validated joint transformation; use original observations")
    rows = features.reset_index(drop=True).copy()
    rows["label"] = labels.to_numpy()
    result = augment_dataset(rows, "label", list(features.columns), target_rows_per_label=80)
    return result[list(features.columns)], result["label"], len(result)-len(rows)


def grouped_cv(features, labels, groups, params, use_augmentation):
    splits = min(5, groups.nunique())
    if splits < 2:
        raise ValueError("Insufficient training groups for grouped validation")
    scores, folds = [], []
    for train, validation in GroupKFold(n_splits=splits).split(features, labels, groups):
        if set(groups.iloc[train]) & set(groups.iloc[validation]):
            raise AssertionError("CV group leakage")
        x_fit, y_fit, synthetic = augmented(features.iloc[train], labels.iloc[train], use_augmentation)
        clf = RandomForestClassifier(**params, random_state=42, class_weight="balanced")
        clf.fit(x_fit, y_fit.to_numpy(dtype=str))
        prediction = clf.predict(features.iloc[validation])
        scores.append(float(f1_score(labels.iloc[validation], prediction, labels=sorted(labels.unique()), average="macro", zero_division=0)))
        folds.append({"train_groups": sorted(set(groups.iloc[train])), "validation_groups": sorted(set(groups.iloc[validation])), "synthetic_training_rows": synthetic})
    return {"folds": splits, "f1_macro_mean": float(np.mean(scores)), "f1_macro_std": float(np.std(scores)), "partitions": folds}


def baseline_for(y_train, y_test):
    counts = y_train.value_counts()
    majority = str(counts.index[0])
    tied = sorted(str(label) for label in counts[counts.eq(counts.max())].index)
    return {
        "strategy": "most_frequent_training_label", "label": majority,
        "test_accuracy": float(accuracy_score(y_test, [majority] * len(y_test))),
        "training_counts": {str(label): int(count) for label, count in counts.items()},
        "tie_breaker": "First occurrence in original training partition; never select using test results",
        # Report every equally frequent training label when tied. These are
        # counterfactual reference scores, not selection of the best test label.
        "tied_labels_test_accuracy": {label: float(accuracy_score(y_test, [label] * len(y_test))) for label in tied},
    }


def train(model: str, use_augmentation: bool = False) -> dict:
    frame, provenance = build_public_dataset(model)
    features = provenance["features"]
    geographic_holdout = provenance["source"].get("geographic_holdout")
    train_idx, test_idx = group_split(frame, geographic_holdout)
    x_train, x_test = frame.iloc[train_idx][features], frame.iloc[test_idx][features]
    y_train, y_test = frame.iloc[train_idx]["label"], frame.iloc[test_idx]["label"]
    groups = frame.iloc[train_idx]["group_key"]
    if y_train.nunique() < 2:
        raise ValueError("Fixed training partition has fewer than two observed labels; no test-seed search permitted")
    # Small train-only grid. Augmentation is re-created inside each CV fold.
    candidates = [{"n_estimators": 150, "max_depth": depth, "min_samples_leaf": leaf}
                  for depth in (4, 8) for leaf in (2, 5)]
    scored = [(params, grouped_cv(x_train, y_train, groups, params, use_augmentation)) for params in candidates]
    params, cv = max(scored, key=lambda entry: entry[1]["f1_macro_mean"])
    x_fit, y_fit, synthetic = augmented(x_train, y_train, use_augmentation)
    clf = RandomForestClassifier(**params, random_state=42, class_weight="balanced")
    clf.fit(x_fit, y_fit.to_numpy(dtype=str))
    labels = sorted(frame["label"].unique())
    # The shared legacy evaluator's row-level CV is disabled here; our audited
    # grouped CV above is the only approved cross-validation result.
    metrics = evaluate_training_run(
        clf=clf, dataset_name={"fatigue": "Fatiga observada — Borg nativo", "physio_risk": "AMS observado — estudio nocturno", "route_difficulty": "Tramos argentinos — OSM + IGN", "apn_route_difficulty": "Recorridos argentinos — dificultad APN"}[model],
        declared_source=provenance["source"]["source"], source_note=provenance["source"]["scope"],
        feature_cols=features, labels=labels, full_features=frame[features], full_labels=frame["label"],
        x_train=x_fit, x_test=x_test, y_train=y_fit, y_test=y_test,
        x_train_real=x_train, y_train_real=y_train,
        augmentation_used=use_augmentation and synthetic > 0, synthetic_rows=synthetic,
        calculate_cross_validation=False,
    )
    metrics["metrics"]["cross_validation"] = {k: v for k, v in cv.items() if k != "partitions"}
    warnings = [w for w in metrics["guardrails"]["warnings"] if "aprobacion" not in w]
    warnings.insert(0, provenance["source"]["scope"])
    unseen = sorted(set(y_test) - set(y_train))
    if unseen:
        warnings.append("Etiquetas observadas solo en test, sin ejemplos de entrenamiento: " + ", ".join(unseen))
    if not use_augmentation:
        warnings.append("Entrenamiento sin augmentation; todas las filas base provienen de observaciones públicas.")
    metrics["guardrails"]["status"] = "requires_more_real_data" if metrics["guardrails"]["insufficient_real_data"] or groups.nunique() < 10 else "review_recommended"
    metrics["guardrails"]["warnings"] = warnings
    metrics["guardrails"]["high_variance_risk"] = cv["f1_macro_std"] > 0.18
    metrics["augmentation"]["requires_approval"] = False
    metrics["augmentation"]["authorization"] = "User permits augmentation within training folds only"
    metrics["trained_at"] = datetime.now(timezone.utc).isoformat()
    metrics["evaluation_validity"] = {
        "real_public_ground_truth": True, "status": "observed_public_labels_group_holdout",
        "reason": provenance["source"]["scope"], "deployment_approved": False,
        "native_labels": True, "test_synthetic_rows": 0,
    }
    metrics["baseline"] = baseline_for(y_train, y_test)
    metrics["hyperparameters"] = {**params, "selection_method": "cross_validated", "cv_folds": cv["folds"], "cv_f1_macro_mean": cv["f1_macro_mean"]}
    metrics["evaluation_protocol"] = {
        "seed": 42, "split": "geographic_holdout" if geographic_holdout else "group_holdout", "independent_group_count": int(frame["group_key"].nunique()),
        **({"geographic_holdout": geographic_holdout} if geographic_holdout else {}),
        "train_groups": sorted(set(groups)), "test_groups": sorted(set(frame.iloc[test_idx]["group_key"])),
        "train_row_keys": frame.iloc[train_idx]["row_key"].tolist(), "test_row_keys": frame.iloc[test_idx]["row_key"].tolist(),
        "cv_training_only": True, "cv_partitions": cv["partitions"],
        "provenance_sha256": digest(OUTPUT / model / "provenance.json"),
    }
    # Held-out predictions permit independent recomputation of every metric.
    test_prediction = clf.predict(x_test)
    pd.DataFrame({"row_key": frame.iloc[test_idx]["row_key"].to_numpy(), "observed": y_test.to_numpy(), "predicted": test_prediction}).to_csv(OUTPUT / model / "test_predictions.csv", index=False)
    metrics["test_predictions_sha256"] = digest(OUTPUT / model / "test_predictions.csv")
    payload = export_random_forest(clf, features, list(clf.classes_), {"evaluation_validity": metrics["evaluation_validity"]})
    (OUTPUT / model / "model.forest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / model / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    target = {"fatigue": "fatigueMetrics.json", "physio_risk": "riskMetrics.json", "route_difficulty": "routeDifficultyMetrics.json", "apn_route_difficulty": "apnRouteDifficultyMetrics.json"}[model]
    (ROOT / "ai/models" / target).write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"{model}: real_rows={len(frame)} train={len(train_idx)} test={len(test_idx)} groups={frame['group_key'].nunique()} test_accuracy={metrics['accuracy']:.3f}", flush=True)
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=list(ADAPTERS), action="append")
    parser.add_argument("--augment", action="store_true", help="Generate rows only inside training folds")
    args = parser.parse_args()
    for model in args.model or list(ADAPTERS):
        train(model, args.augment)


if __name__ == "__main__":
    main()
