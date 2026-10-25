"""Recompute the search report from saved train-only out-of-fold predictions."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold

from common.selection import candidate_plan, plan_sha256


def audit_selection(report, features, labels, groups, inputs):
    plan = candidate_plan()
    if (report["inputs"] != inputs or report["candidate_plan_sha256"] != plan_sha256(plan)
            or report["candidate_count"] != len(plan) or report["test_used_for_selection"] is not False
            or report["objective"] != "grouped_training_cv_f1_macro_mean"
            or [r["candidate"] for r in report["results"]] != plan):
        raise ValueError("Selection inputs, objective or frozen candidate plan changed")
    partitions = list(GroupKFold(n_splits=min(5, groups.nunique())).split(features, labels, groups))
    vocabulary = sorted(labels.unique())
    for result in report["results"]:
        cv = result["cv"]
        predictions = np.asarray(cv["oof_predictions"], dtype=str)
        if len(predictions) != len(labels) or not set(predictions) <= set(vocabulary):
            raise ValueError("Selection OOF predictions differ from training rows/labels")
        folds, scores, accuracies = [], [], []
        for train, validation in partitions:
            folds.append({"train_groups": sorted(set(groups.iloc[train])),
                          "validation_groups": sorted(set(groups.iloc[validation]))})
            scores.append(f1_score(labels.iloc[validation], predictions[validation],
                                   labels=vocabulary, average="macro", zero_division=0))
            accuracies.append(accuracy_score(labels.iloc[validation], predictions[validation]))
        if cv["partitions"] != folds or cv["folds"] != len(folds):
            raise ValueError("Selection CV partitions differ from training-only GroupKFold")
        for key, value in {"f1_macro_mean": np.mean(scores), "f1_macro_std": np.std(scores),
                           "accuracy_mean": np.mean(accuracies), "accuracy_std": np.std(accuracies)}.items():
            if not np.isclose(cv[key], value, atol=1e-12, rtol=0):
                raise ValueError("Selection CV metric differs from saved OOF predictions")
        if not np.allclose(cv["f1_macro_by_fold"], scores, atol=1e-12, rtol=0):
            raise ValueError("Selection fold scores differ from saved OOF predictions")
    best = max(report["results"], key=lambda r: r["cv"]["f1_macro_mean"])
    legacy = max((r for r in report["results"] if r["candidate"].get("legacy")),
                 key=lambda r: r["cv"]["f1_macro_mean"])
    gain = best["cv"]["f1_macro_mean"] - legacy["cv"]["f1_macro_mean"]
    if (report["winner_id"] != best["candidate"]["id"]
            or report["legacy_winner_id"] != legacy["candidate"]["id"]
            or not np.isclose(report["cv_gain_over_legacy"], gain, atol=1e-12, rtol=0)):
        raise ValueError("Winner was not selected using training-only CV F1")
    return best
