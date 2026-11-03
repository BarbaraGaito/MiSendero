"""Audit native labels, causal feature snapshots and train-only CV evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from common.privacy import assert_no_restricted_columns
from fatigue_features import RESEARCH
from fetch_fatigue_extra import DESTINATION
from public_sources import OUTPUT, ROOT, digest, verify_source_snapshot


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate():
    verify_source_snapshot("fatigue")
    canonical = OUTPUT / "fatigue"
    original = pd.read_csv(canonical / "dataset.csv", dtype={"label": str})
    original_provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8"))
    published = json.loads((canonical / "metrics.json").read_text(encoding="utf-8"))
    registry = {row["row_key"]: (row["group_key"], label) for row, label in zip(original_provenance["lineage"], original["label"])}
    summary = {"objective": "accuracy >= 0.60 on exact native Borg ratings for the original fatigue task",
               "target_accuracy": .6, "feature_sets": {}, "experiments": {}}
    for name in ("multisensor-v1", "raw-v1"):
        directory = RESEARCH / name
        if not (directory / "provenance.json").exists():
            continue
        manifest = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
        frame = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
        require(digest(directory / "dataset.csv") == manifest["dataset_sha256"], "Derived predictors changed after preparation")
        assert_no_restricted_columns(frame, name)
        require(frame["label"].tolist() == original["label"].tolist(), "Original Borg responses were changed, binned or resampled")
        require([row["row_key"] for row in manifest["lineage"]] == list(registry), "Derived feature cohort changed")
        require(np.allclose(frame["hr_last"], original["hr"], rtol=0, atol=1e-12), "Original measured pulse-rate predictor changed")
        require(np.allclose(frame["elapsed_minutes"], original["elapsed_minutes"], rtol=0, atol=1e-12), "Original task timing changed")
        require(manifest["synthetic_rows"] == 0 and not manifest["rest_observations_added"], "Synthetic/rest observations were added to increase accuracy")
        for row in manifest["lineage"]:
            require(pd.Timestamp(row["latest_permitted_signal_start"]) + pd.Timedelta(minutes=1) == pd.Timestamp(row["response_time"]), "Sensor window can extend beyond response")
        summary["feature_sets"][name] = {"rows": len(frame), "predictors": len(manifest["features"]), "labels_identical_to_original": True}
    worker_path = RESEARCH / "worker-v1"
    worker = json.loads((worker_path / "provenance.json").read_text(encoding="utf-8"))
    extra = pd.read_csv(worker_path / "dataset.csv", dtype={"label": str})
    require(digest(worker_path / "dataset.csv") == worker["dataset_sha256"], "Additional-source observations changed")
    assert_no_restricted_columns(extra, "worker-v1")
    survey = pd.read_excel(DESTINATION / "USER FORM RESPONSE.xlsx")
    require(digest(DESTINATION / "USER FORM RESPONSE.xlsx") == worker["original_survey_sha256"], "Original additional-source questionnaire changed")
    require(len(extra) == len(worker["lineage"]) == worker["rows"], "Repeated sensor samples were counted as questionnaire observations")
    for value, row in zip(extra["label"], worker["lineage"]):
        rating = survey.iloc[row["questionnaire_worksheet_row"] - 2][row["questionnaire_column"]]
        require(value == f"Borg {float(rating):g}" and float(rating).is_integer() and 0 <= rating <= 10, "Additional native response differs from original questionnaire")
        require(digest(DESTINATION / "processed" / row["sensor_member"]) == row["sensor_file_sha256"], "Audited original sensor segment changed")
    require(worker["interpolated_targets"] == worker["synthetic_rows"] == worker["rest_labels_added"] == 0, "Fabricated/interpolated training responses")
    require(extra[[name for name in extra if name.startswith("prv_")]].isna().all().all(), "Different HRV definitions were silently combined")
    summary["additional_data"] = {"rows": len(extra), "participants": worker["participants"], "survey_labels_verified": True}
    external_groups = pd.Series([row["group_key"] for row in worker["lineage"]])
    require(not set(external_groups) & {group for group, _ in registry.values()}, "Cross-study participant namespace collision")
    ext_train, ext_test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(extra, groups=external_groups))
    external_keys = [row["row_key"] for row in worker["lineage"]]
    for directory in (RESEARCH / name for name in ("multisensor-v1", "transfer-v1", "ordinal-v1", "raw-v1")):
        path = directory / ("selection-v1.json" if directory.name == "multisensor-v1" else "selection.json")
        if not path.exists():
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        if "external_split" in report:
            split = report["external_split"]
            require(split["train_row_keys"] == [external_keys[i] for i in ext_train]
                    and split["test_row_keys"] == [external_keys[i] for i in ext_test], "Additional-source holdout was changed")
            require(not set(split["train_groups"]) & set(split["test_groups"]), "Additional-source participant leakage")
        keys = report.get("train_row_keys", report.get("target_train_row_keys"))
        require(set(keys) == set(published["evaluation_protocol"]["train_row_keys"]), "Search included held-out responses")
        groups = pd.Series([registry[key][0] for key in keys])
        truth = pd.Series([registry[key][1] for key in keys])
        require(not set(groups) & set(published["evaluation_protocol"]["test_groups"]), "Search included test participants")
        for result in report["results"]:
            predictions = np.asarray(result["cv"]["oof_predictions"], dtype=str)
            require(len(predictions) == len(truth), "OOF evaluation denominator changed")
            scores = []
            for (train, validation), fold in zip(GroupKFold(n_splits=5).split(truth, truth, groups), result["cv"]["folds"]):
                require(set(fold.get("train_groups", fold.get("target_train_groups"))) == set(groups.iloc[train]), "CV fitted different target participants")
                require(set(fold["validation_groups"]) == set(groups.iloc[validation]), "CV validation groups changed")
                score = accuracy_score(truth.iloc[validation], predictions[validation])
                require(np.isclose(score, fold["accuracy"], rtol=0, atol=1e-12), "CV fold accuracy differs from saved predictions")
                scores.append(score)
            require(len(result["cv"]["folds"]) == 5, "Not all target participants have OOF predictions")
            require(np.isclose(np.mean(scores), result["cv"]["accuracy_mean"], rtol=0, atol=1e-12), "Reported accuracy differs from native exact matches")
            require(np.isclose(accuracy_score(truth, predictions), result["cv"]["pooled_oof_accuracy"], rtol=0, atol=1e-12), "Pooled OOF accuracy changed")
        if report["results"]:
            best = max(report["results"], key=lambda row: row["cv"]["accuracy_mean"])
            require(best["candidate"]["id"] == report["winner_id"], "Winner differs from training-only objective")
            summary["experiments"][directory.name] = {"completed_candidates": len(report["results"]), "status": report["status"],
                                                        "best_cv_accuracy": best["cv"]["accuracy_mean"], "original_test_evaluated": False}
    predictions = pd.read_csv(canonical / "test_predictions.csv", dtype=str)
    accuracy = float(accuracy_score(predictions["observed"], predictions["predicted"]))
    require(np.isclose(accuracy, published["accuracy"], rtol=0, atol=1e-12), "Published accuracy differs from held-out predictions")
    summary["published_accuracy"] = accuracy
    summary["achieved"] = accuracy >= .6
    summary["interpretation"] = "Training CV improvements do not satisfy the goal. Completion requires an actual model with >=60% exact Borg accuracy verified on the original held-out task, without easier labels or denominators."
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
