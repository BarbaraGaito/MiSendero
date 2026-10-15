"""Recompute reported held-out scores and verify source/partition evidence."""
import json
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

from common.privacy import assert_no_restricted_columns
from public_sources import ADAPTERS, OUTPUT, digest, verify_source_snapshot


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(model):
    directory = OUTPUT / model
    verify_source_snapshot(model)
    provenance = json.loads((directory / "provenance.json").read_text())
    metrics = json.loads((directory / "metrics.json").read_text())
    protocol = metrics["evaluation_protocol"]
    if digest(directory / "dataset.csv") != provenance["dataset_sha256"]:
        raise ValueError("Dataset was modified after its source audit")
    if digest(directory / "provenance.json") != protocol["provenance_sha256"]:
        raise ValueError("Provenance was modified after evaluation")
    if digest(directory / "test_predictions.csv") != metrics["test_predictions_sha256"]:
        raise ValueError("Held-out predictions were modified")
    assert_no_restricted_columns(pd.read_csv(directory / "dataset.csv"), model)
    train, test = set(protocol["train_groups"]), set(protocol["test_groups"])
    require(not train & test, "Train/test group leakage")
    for fold in protocol["cv_partitions"]:
        a, b = set(fold["train_groups"]), set(fold["validation_groups"])
        require(not a & b and not (a | b) & test and (a | b) <= train, "CV used overlapping or held-out groups")
    rows = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
    lineage = provenance["lineage"]
    # Rebuild from the pinned ORIGINALS without writing artifacts. This rejects
    # a CSV whose hashes were updated together with fabricated features/labels.
    original, source_info = ADAPTERS[model]()
    require(len(original) == len(rows) == len(lineage), "Source/CSV row count mismatch")
    require(original["label"].tolist() == rows["label"].tolist(), "CSV labels differ from independent public observations")
    require(np.allclose(original[provenance["features"]].to_numpy(dtype=float), rows[provenance["features"]].to_numpy(dtype=float), rtol=1e-12, atol=1e-12), "CSV measurements differ from public sources")
    require(original["row_key"].tolist() == [item["row_key"] for item in lineage], "Source row lineage mismatch")
    require(original["group_key"].tolist() == [item["group_key"] for item in lineage], "Independent source groups were modified")
    train_keys, test_keys = set(protocol["train_row_keys"]), set(protocol["test_row_keys"])
    if source_info.get("geographic_holdout"):
        from train_public import group_split
        expected_train, expected_test = group_split(original, source_info["geographic_holdout"])
        require(protocol.get("geographic_holdout") == source_info["geographic_holdout"], "Geographic protocol differs from audited source catalog")
        require(train_keys == set(original.iloc[expected_train]["row_key"]) and test_keys == set(original.iloc[expected_test]["row_key"]), "Prespecified geographic holdout was changed")
    require(not train_keys & test_keys and (train_keys | test_keys) == set(original["row_key"]), "Row partitions overlap or omit real observations")
    require(set(original.loc[original["row_key"].isin(train_keys), "group_key"]) == train, "Training rows/group mismatch")
    require(set(original.loc[original["row_key"].isin(test_keys), "group_key"]) == test, "Test rows/group mismatch")
    labels = {row["row_key"]: value for row, value in zip(lineage, rows["label"])}
    held_out = pd.read_csv(directory / "test_predictions.csv", dtype=str)
    require(not held_out["row_key"].duplicated().any() and set(held_out["row_key"]) == test_keys, "Test prediction rows mismatch")
    require(all(labels[key] == observed for key, observed in zip(held_out["row_key"], held_out["observed"])), "Test labels differ from public observations")
    for key, actual in {
        "accuracy": accuracy_score(held_out["observed"], held_out["predicted"]),
        "f1_macro": f1_score(held_out["observed"], held_out["predicted"], labels=metrics["labels"], average="macro", zero_division=0),
    }.items():
        require(np.isclose(actual, metrics["metrics"]["test"][key], rtol=0, atol=1e-12), "Reported test metric differs from predictions")
    require(metrics["evaluation_validity"]["test_synthetic_rows"] == 0 and provenance["synthetic_base_rows"] == 0, "Synthetic observations in base/test")
    majority = original.loc[original["row_key"].isin(train_keys), "label"].value_counts().index[0]
    require(majority == metrics["baseline"]["label"], "Baseline was not fitted only on training")
    require(np.isclose(accuracy_score(held_out["observed"], [majority]*len(held_out)), metrics["baseline"]["test_accuracy"]), "Incorrect reported baseline")
    if "tied_labels_test_accuracy" in metrics["baseline"]:
        from train_public import baseline_for
        expected_baseline = baseline_for(original.loc[original["row_key"].isin(train_keys), "label"], held_out["observed"])
        require(metrics["baseline"] == expected_baseline, "Baseline tie disclosure differs from original training counts/test labels")
    print(f"verified {model}: source hashes, real labels, sealed groups and recomputed test metrics")


if __name__ == "__main__":
    for model in ADAPTERS:
        validate(model)
