"""Shared evaluation helpers for real-data model training."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split

MIN_REAL_ROWS_TOTAL = 30
MIN_REAL_ROWS_PER_LABEL = 10
OVERFITTING_F1_GAP = 0.15
UNDERFITTING_F1 = 0.60
HIGH_VARIANCE_CV_STD = 0.18
HIGH_SYNTHETIC_RATIO = 5.0


def validate_training_frame(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    dataset_name: str,
) -> pd.DataFrame:
    """Validate and normalize a training CSV before any split or fit."""
    required = [*feature_cols, label_col]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{dataset_name}: missing required columns: {', '.join(missing)}")

    cleaned = df[required].copy()
    cleaned[label_col] = cleaned[label_col].astype(str).str.strip()

    if cleaned[label_col].eq("").any():
        raise ValueError(f"{dataset_name}: labels cannot be empty")

    for column in feature_cols:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    if cleaned[feature_cols].isna().any().any():
        bad_columns = [
            column for column in feature_cols if cleaned[column].isna().any()
        ]
        raise ValueError(
            f"{dataset_name}: feature columns contain non-numeric or empty values: "
            f"{', '.join(bad_columns)}"
        )

    label_counts = Counter(cleaned[label_col])
    if len(label_counts) < 2:
        raise ValueError(f"{dataset_name}: at least two labels are required for training")

    too_small = [label for label, count in label_counts.items() if count < 2]
    if too_small:
        raise ValueError(
            f"{dataset_name}: every label needs at least 2 real rows for stratified "
            f"train/test evaluation. Too small: {', '.join(too_small)}"
        )

    return cleaned.reset_index(drop=True)


def real_train_test_split(
    features: pd.DataFrame,
    labels: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    return train_test_split(
        features,
        labels,
        test_size=0.30,
        stratify=labels,
        random_state=42,
    )


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


def _cross_validation_metrics(clf, features, labels) -> dict[str, Any] | None:
    label_counts = Counter(labels)
    splits = min(5, min(label_counts.values()))

    if splits < 2:
        return None

    cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=42)
    scores = cross_validate(
        clone(clf),
        features,
        labels,
        cv=cv,
        scoring={
            "accuracy": "accuracy",
            "precision_macro": "precision_macro",
            "recall_macro": "recall_macro",
            "f1_macro": "f1_macro",
        },
        error_score="raise",
    )

    return {
        "folds": int(splits),
        "accuracy_mean": float(np.mean(scores["test_accuracy"])),
        "accuracy_std": float(np.std(scores["test_accuracy"])),
        "precision_macro_mean": float(np.mean(scores["test_precision_macro"])),
        "precision_macro_std": float(np.std(scores["test_precision_macro"])),
        "recall_macro_mean": float(np.mean(scores["test_recall_macro"])),
        "recall_macro_std": float(np.std(scores["test_recall_macro"])),
        "f1_macro_mean": float(np.mean(scores["test_f1_macro"])),
        "f1_macro_std": float(np.std(scores["test_f1_macro"])),
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
    x_train_real: pd.DataFrame | None = None,
    y_train_real: pd.Series | None = None,
    augmentation_used: bool = False,
    synthetic_rows: int = 0,
    calculate_cross_validation: bool = True,
) -> dict[str, Any]:
    train_pred = clf.predict(x_train)
    test_pred = clf.predict(x_test)
    train_metrics = _summary_metrics(y_train, train_pred, labels)
    test_metrics = _summary_metrics(y_test, test_pred, labels)
    train_real_metrics = None

    if x_train_real is not None and y_train_real is not None:
        train_real_pred = clf.predict(x_train_real)
        train_real_metrics = _summary_metrics(y_train_real, train_real_pred, labels)

    cv_metrics = _cross_validation_metrics(
        clf,
        x_train_real if x_train_real is not None else x_train,
        y_train_real if y_train_real is not None else y_train,
    ) if calculate_cross_validation else None

    label_counts = dict(sorted(Counter(full_labels).items()))
    gap_source = train_real_metrics or train_metrics
    train_test_f1_gap = gap_source["f1_macro"] - test_metrics["f1_macro"]
    overfitting_risk = train_test_f1_gap > OVERFITTING_F1_GAP
    underfitting_risk = test_metrics["f1_macro"] < UNDERFITTING_F1
    high_variance_risk = (
        cv_metrics is not None and cv_metrics["f1_macro_std"] > HIGH_VARIANCE_CV_STD
    )
    insufficient_real_data = (
        len(full_labels) < MIN_REAL_ROWS_TOTAL
        or min(label_counts.values()) < MIN_REAL_ROWS_PER_LABEL
    )
    augmentation_ratio = (
        float(synthetic_rows / len(y_train_real))
        if y_train_real is not None and len(y_train_real) > 0
        else float(synthetic_rows / len(y_train)) if len(y_train) > 0 else 0.0
    )
    high_synthetic_ratio = augmentation_ratio > HIGH_SYNTHETIC_RATIO

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
            "Posible underfitting: el F1 macro de test esta por debajo del umbral "
            f"minimo ({UNDERFITTING_F1:.2f})."
        )
    if high_variance_risk:
        warnings.append(
            "Validacion cruzada inestable: la desviacion de F1 macro entre folds "
            "es alta."
        )
    if augmentation_used:
        warnings.append(
            "Data augmentation aplicada solo sobre train: el conjunto de test "
            "no recibe augmentation; la procedencia de atributos y etiquetas debe auditarse por separado."
        )
        if high_synthetic_ratio:
            warnings.append(
                "Proporcion alta de muestras sinteticas: usar estas metricas "
                "como apoyo tecnico, no como validacion clinica/de campo."
            )
    else:
        warnings.append(
            "Data augmentation desactivada: no se generaron muestras sinteticas "
            "porque requiere aprobacion previa."
        )

    if insufficient_real_data:
        status = "requires_more_real_data"
    elif overfitting_risk or underfitting_risk or high_variance_risk:
        status = "review_recommended"
    else:
        status = "ok"

    return {
        "schema_version": 2,
        "dataset": {
            "name": dataset_name,
            "declared_source": declared_source,
            "source_note": source_note,
            "rows_total": int(len(full_labels)),
            "rows_train": int(len(y_train_real) if y_train_real is not None else len(y_train)),
            "rows_train_after_augmentation": int(len(y_train)),
            "rows_test": int(len(y_test)),
            "rows_by_label": label_counts,
            "features": list(feature_cols),
        },
        "augmentation": {
            "used": bool(augmentation_used),
            "synthetic_rows": int(synthetic_rows),
            "synthetic_to_real_train_ratio": float(augmentation_ratio),
            "requires_approval": True,
        },
        "metrics": {
            "train": train_metrics,
            "train_real": train_real_metrics,
            "test": test_metrics,
            "cross_validation": cv_metrics,
        },
        "guardrails": {
            "status": status,
            "overfitting_risk": bool(overfitting_risk),
            "underfitting_risk": bool(underfitting_risk),
            "high_variance_risk": bool(high_variance_risk),
            "insufficient_real_data": bool(insufficient_real_data),
            "high_synthetic_ratio": bool(high_synthetic_ratio),
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
