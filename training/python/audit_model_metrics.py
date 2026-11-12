"""Recompute the five dashboard evaluations from saved holdout predictions, without fitting."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, recall_score

from common.evaluation import _summary_metrics
from compare_public import paired_group_bootstrap
from public_sources import OUTPUT, ROOT, digest


PUBLIC_MODELS = {
    "fatigue": "fatigueMetrics",
    "physio_risk": "riskMetrics",
    "route_difficulty": "routeDifficultyMetrics",
    "apn_route_difficulty": "apnRouteDifficultyMetrics",
}
CALIBRATED = ROOT / "training/data/fatigue-research/calibrated-alternatives-v1/evaluation"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_evaluation(directory, admin_name, provenance_directory):
    path = directory / "metrics.json"
    dashboard = ROOT / "ai/models" / f"{admin_name}.json"
    require(path.read_bytes() == dashboard.read_bytes(), f"Dashboard differs: {admin_name}")
    saved = read_json(path)
    protocol = saved["evaluation_protocol"]
    csv_path = directory / "test_predictions.csv"
    provenance_path = provenance_directory / "provenance.json"
    require(digest(csv_path) == saved["test_predictions_sha256"], f"Prediction hash: {admin_name}")
    require(digest(provenance_path) == protocol["provenance_sha256"], f"Provenance hash: {admin_name}")
    provenance = read_json(provenance_path)
    group_by_key = {row["row_key"]: row["group_key"] for row in provenance["lineage"]}
    predictions = pd.read_csv(csv_path, dtype=str).set_index("row_key")
    require(predictions.index.is_unique and set(predictions.index) == set(protocol["test_row_keys"]),
            f"Holdout keys: {admin_name}")
    train_groups = {group_by_key[key] for key in protocol["train_row_keys"]}
    groups = [group_by_key[key] for key in predictions.index]
    require(train_groups == set(protocol["train_groups"]) and set(groups) == set(protocol["test_groups"])
            and not train_groups.intersection(groups), f"Group partitions: {admin_name}")
    actual = predictions["observed"]
    predicted = predictions["predicted"]
    labels = saved["labels"]
    require((set(actual) | set(predicted)) <= set(labels), f"Unknown label: {admin_name}")
    summary = _summary_metrics(actual, predicted, labels)
    matrix = confusion_matrix(actual, predicted, labels=labels)
    require(summary == saved["metrics"]["test"] and matrix.tolist() == saved["confusion_matrix"],
            f"Saved test metrics differ: {admin_name}")
    result = {
        "accuracy": summary["accuracy"],
        "correct": int(matrix.trace()),
        "test_rows": len(predictions),
        "test_groups": len(set(groups)),
        "f1_macro": summary["f1_macro"],
        "balanced_accuracy_present_classes": recall_score(
            actual, predicted, labels=sorted(set(actual)), average="macro", zero_division=0
        ),
        "labels": labels,
        "confusion_matrix_observed_rows": matrix.tolist(),
        "recall_counts": {label: {"correct": int(matrix[i, i]), "observed": int(matrix[i].sum())}
                          for i, label in enumerate(labels)},
        "deployment_approved": saved["evaluation_validity"]["deployment_approved"],
        "test_predictions_sha256": digest(csv_path),
    }
    if "baseline" in saved:
        result["training_majority_baselines"] = {
            label: _summary_metrics(actual, [label] * len(actual), labels)
            for label in saved["baseline"]["tied_labels_test_accuracy"]
        }
    return saved, predictions, groups, result


def borg_error_summary(observed, predicted):
    actual = np.array([int(value.removeprefix("Borg ")) for value in observed])
    forecast = np.array([int(value.removeprefix("Borg ")) for value in predicted])
    error = forecast - actual
    high = actual >= 7  # Descriptive slice of the native scale; not an alert threshold.
    return {
        "mae_points": float(np.abs(error).mean()),
        "within_one_point": int((np.abs(error) <= 1).sum()),
        "underestimated": int((error < 0).sum()),
        "overestimated": int((error > 0).sum()),
        "observed_borg_7_or_above": int(high.sum()),
        "predicted_7_or_above_on_those_cases": int((forecast[high] >= 7).sum()),
        "predicted_7_or_above_on_lower_cases": int((forecast[~high] >= 7).sum()),
    }


def main():
    models = {name: read_evaluation(OUTPUT / name, admin, OUTPUT / name)
              for name, admin in PUBLIC_MODELS.items()}
    calibrated = read_evaluation(CALIBRATED, "calibratedFatigueMetrics", OUTPUT / "fatigue")
    models["calibrated_fatigue"] = calibrated
    results = {name: model[3] for name, model in models.items()}
    sensor = models["fatigue"]
    saved, calibrated_rows, groups, _ = calibrated
    require(set(sensor[1].index) == set(calibrated_rows.index), "Fatigue holdouts differ")
    sensor_rows = sensor[1].loc[calibrated_rows.index]
    actual = calibrated_rows["observed"]
    require(actual.equals(sensor_rows["observed"]), "Fatigue holdout labels differ")
    prior = [f"Borg {float(value):g}" for value in calibrated_rows["previous_borg"]]
    predictions = {
        "sensor_forest": sensor_rows["predicted"],
        "prior_borg": prior,
        "prior_borg_mlp": calibrated_rows["predicted"],
    }
    labels = saved["labels"]
    common_borg = {}
    for name, forecast in predictions.items():
        summary = _summary_metrics(actual, forecast, labels)
        common_borg[name] = {
            "correct": int((actual == forecast).sum()),
            "accuracy": summary["accuracy"],
            "f1_macro_11_labels": summary["f1_macro"],
            **borg_error_summary(actual, forecast),
        }
    require(_summary_metrics(actual, prior, labels) == {
        key: value for key, value in saved["previous_borg_baseline"].items() if key != "strategy"
    }, "Saved prior Borg baseline differs")
    result = {
        "models": results,
        "borg_common_179_row_holdout": common_borg,
        "borg_prior_vs_mlp_paired_uncertainty": paired_group_bootstrap(
            actual, prior, predictions["prior_borg_mlp"], groups, labels, repetitions=5000
        ),
    }
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
