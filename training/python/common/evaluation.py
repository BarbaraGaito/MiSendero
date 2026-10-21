"""Shared evaluation helpers for real-data model training."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
    recall_score,
)

MIN_REAL_ROWS_TOTAL = 30
MIN_REAL_ROWS_PER_LABEL = 10
OVERFITTING_F1_GAP = 0.15
UNDERFITTING_F1 = 0.60


def holdout_details(y_train, y_test, predictions, labels, train_groups, test_groups):
    """Compare fixed predictions with a train-only baseline, without fitting or sampling rows."""
    y_train, y_test, predictions = list(y_train), list(y_test), list(predictions)
    train_groups, test_groups = list(train_groups), list(test_groups)
    if (not y_train or not y_test or len(y_test) != len(predictions)
            or len(y_train) != len(train_groups) or len(y_test) != len(test_groups)):
        raise ValueError("Holdout rows, predictions and groups must match")
    if set(train_groups) & set(test_groups):
        raise ValueError("Holdout group leakage")
    if len(labels) != len(set(labels)) or not set(y_train + y_test + predictions) <= set(labels):
        raise ValueError("Unknown or duplicate evaluation labels")
    # Keep the original train-only majority tie policy (first occurrence).
    baseline_label = pd.Series(y_train).value_counts().index[0]

    def score(values):
        result = _summary_metrics(y_test, values, labels)
        # Balanced accuracy averages recall only over classes observed in test.
        # F1 macro above retains the full, explicitly declared label vocabulary.
        result["balanced_accuracy"] = float(recall_score(y_test, values, labels=sorted(set(y_test)), average="macro", zero_division=0))
        return result

    model_scores = score(predictions)
    baseline_scores = score([baseline_label] * len(y_test))
    train_counts, test_counts = Counter(y_train), Counter(y_test)
    return {
        "version": 1,
        "model": model_scores,
        "baseline": {"label": str(baseline_label), **baseline_scores},
        "difference_from_baseline": {key: model_scores[key] - baseline_scores[key]
                                     for key in ("accuracy", "f1_macro", "balanced_accuracy")},
        "class_coverage": {
            "training_counts": {label: int(train_counts[label]) for label in labels},
            "test_counts": {label: int(test_counts[label]) for label in labels},
            "missing_in_training": [label for label in labels if not train_counts[label]],
            "missing_in_test": [label for label in labels if not test_counts[label]],
            "labels_total": len(labels), "labels_in_training": len(train_counts), "labels_in_test": len(test_counts),
        },
        "group_support": {"training": len(set(train_groups)), "test": len(set(test_groups))},
        "interpretation": "Descriptive comparison on the existing held-out observations; not a significance test or deployment approval.",
    }


def _summary_metrics(y_true, y_pred, labels: list[str]) -> dict[str, Any]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average="macro", zero_division=0
    )
    weighted_precision, weighted_recall, weighted_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average="weighted", zero_division=0
    )

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision),
        "recall_macro": float(recall),
        "f1_macro": float(f1),
        "precision_weighted": float(weighted_precision),
        "recall_weighted": float(weighted_recall),
        "f1_weighted": float(weighted_f1),
        "support": int(len(y_true)),
    }


def evaluate_training_run(
    *,
    clf,
    dataset_name: str,
    declared_source: str,
    source_note: str,
    feature_cols: list[str],
    labels: list[str],
    full_features: pd.DataFrame,
    full_labels: pd.Series,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> dict[str, Any]:
    train_pred = clf.predict(x_train)
    test_pred = clf.predict(x_test)
    train_metrics = _summary_metrics(y_train, train_pred, labels)
    test_metrics = _summary_metrics(y_test, test_pred, labels)

    label_counts = dict(sorted(Counter(full_labels).items()))
    train_test_f1_gap = train_metrics["f1_macro"] - test_metrics["f1_macro"]
    overfitting_risk = train_test_f1_gap > OVERFITTING_F1_GAP
    underfitting_risk = test_metrics["f1_macro"] < UNDERFITTING_F1
    insufficient_real_data = (
        len(full_labels) < MIN_REAL_ROWS_TOTAL
        or min(label_counts.values()) < MIN_REAL_ROWS_PER_LABEL
    )

    warnings: list[str] = []
    if insufficient_real_data:
        warnings.append(
            "Dataset real chico: sumar muestras reales por clase antes de usar "
            "estas metricas como evidencia de performance en campo."
        )
    if overfitting_risk:
        warnings.append(
            "Posible overfitting: la diferencia de F1 macro entre train y test "
            f"es {train_test_f1_gap:.2f}."
        )
    if underfitting_risk:
        warnings.append(
            "F1 macro de test bajo el umbral heurístico de revisión "
            f"({UNDERFITTING_F1:.2f}); este resultado no identifica por sí solo la causa del error."
        )

    if insufficient_real_data:
        status = "requires_more_real_data"
    elif overfitting_risk or underfitting_risk:
        status = "review_recommended"
    else:
        status = "ok"

    return {
        "schema_version": 3,
        "dataset": {
            "name": dataset_name,
            "declared_source": declared_source,
            "source_note": source_note,
            "rows_total": int(len(full_labels)),
            "rows_train": int(len(y_train)),
            "rows_test": int(len(y_test)),
            "rows_by_label": label_counts,
            "features": list(feature_cols),
        },
        "metrics": {
            "train": train_metrics,
            "test": test_metrics,
            "cross_validation": None,
        },
        "guardrails": {
            "status": status,
            "overfitting_risk": bool(overfitting_risk),
            "underfitting_risk": bool(underfitting_risk),
            "high_variance_risk": False,
            "insufficient_real_data": bool(insufficient_real_data),
            "train_test_f1_gap": float(train_test_f1_gap),
            "warnings": warnings,
        },
        "accuracy": test_metrics["accuracy"],
        "labels": list(labels),
        "confusion_matrix": confusion_matrix(y_test, test_pred, labels=labels).tolist(),
        "classification_report": classification_report(
            y_test, test_pred, labels=labels, output_dict=True, zero_division=0
        ),
    }
