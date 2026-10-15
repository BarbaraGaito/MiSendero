"""Serialize a fitted sklearn RandomForestClassifier to plain JSON.

The mobile TypeScript inference engine (`ai/inferenceEngine.ts`) has no
Python/sklearn runtime available on-device, so the forest is flattened into
arrays that a small hand-written TS tree-walker can traverse without any ML
library.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.tree import DecisionTreeClassifier


def _export_tree(tree_clf: DecisionTreeClassifier) -> dict[str, Any]:
    tree = tree_clf.tree_
    values = []

    for node_index in range(tree.node_count):
        counts = tree.value[node_index][0]
        total = counts.sum()
        probabilities = (counts / total) if total > 0 else counts
        values.append([float(probability) for probability in probabilities])

    return {
        "feature": [int(feature) for feature in tree.feature],
        "threshold": [float(threshold) for threshold in tree.threshold],
        "left": [int(child) for child in tree.children_left],
        "right": [int(child) for child in tree.children_right],
        "value": values,
    }


def export_random_forest(
    clf, feature_order: list[str], classes: list[str], metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = {
        "type": "random_forest_json",
        "version": 1,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_order": list(feature_order),
        "classes": list(classes),
        "trees": [_export_tree(estimator) for estimator in clf.estimators_],
    }

    if metadata:
        payload.update(metadata)

    return payload


def export_metrics(y_true, y_pred, labels: list[str]) -> dict[str, Any]:
    accuracy = float(np.mean(np.asarray(y_true) == np.asarray(y_pred)))
    matrix = confusion_matrix(y_true, y_pred, labels=labels).tolist()
    report = classification_report(
        y_true, y_pred, labels=labels, output_dict=True, zero_division=0
    )

    return {
        "accuracy": accuracy,
        "labels": list(labels),
        "confusion_matrix": matrix,
        "classification_report": report,
    }
