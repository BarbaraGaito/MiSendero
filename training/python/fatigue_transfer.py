"""Train-only cross-study transfer on exact observed Borg 0-10 responses.

The target remains accuracy on the original GeoFatigue task. Extra-source
participants augment fitting only; they cannot make the original validation
score look better by contributing easier examples to its denominator.
"""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.utils.class_weight import compute_sample_weight
from threadpoolctl import threadpool_limits

from fatigue_experiment import EncodedXGBClassifier, estimator_for, load_frame, plan
from fatigue_features import RESEARCH
from public_sources import digest


class WeightedXGB(EncodedXGBClassifier):
    def fit(self, x, y, sample_weight=None):
        from xgboost import XGBClassifier
        self.classes_, encoded = np.unique(y, return_inverse=True)
        self.classifier_ = XGBClassifier(**self.config, random_state=42, n_jobs=1)
        self.classifier_.fit(x, encoded, sample_weight=sample_weight)
        return self


def load_external():
    directory = RESEARCH / "worker-v1"
    manifest = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if digest(directory / "dataset.csv") != manifest["dataset_sha256"]:
        raise ValueError("Audited additional observations changed")
    if digest(Path(__file__).with_name("worker_fatigue.py")) != manifest["adapter_code_sha256"]:
        raise ValueError("External adapter changed; rebuild its audit first")
    frame = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
    frame["group_key"] = [row["group_key"] for row in manifest["lineage"]]
    frame["row_key"] = [row["row_key"] for row in manifest["lineage"]]
    train, test = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(frame, groups=frame["group_key"]))
    if set(frame.iloc[train]["group_key"]) & set(frame.iloc[test]["group_key"]):
        raise AssertionError("Additional-source participant leakage")
    return frame.iloc[train].copy(), {"dataset_sha256": manifest["dataset_sha256"],
        "train_row_keys": frame.iloc[train]["row_key"].tolist(), "test_row_keys": frame.iloc[test]["row_key"].tolist(),
        "train_groups": sorted(set(frame.iloc[train]["group_key"])), "test_groups": sorted(set(frame.iloc[test]["group_key"]))}


def transfer_plan(features):
    candidates = []
    for base in plan(features):
        if base["feature_set"] != "normalized" or base["algorithm"] in ("knn", "mlp"):
            continue
        for weight in (0., 0.25, 1.):
            candidates.append({**base, "id": f"transfer-{len(candidates):03d}", "external_weight": weight})
    return candidates


def evaluate(target, external, candidate):
    groups, y = target["group_key"], target["label"]
    predictions = np.empty(len(target), dtype=object)
    folds, convergence = [], 0
    for train, validation in GroupKFold(n_splits=5).split(target, y, groups):
        training = target.iloc[train]
        weights = np.ones(len(training))
        if candidate["external_weight"] > 0:
            training = pd.concat([training, external], ignore_index=True)
            weights = np.concatenate([weights, np.full(len(external), candidate["external_weight"])])
        if set(training["group_key"]) & set(target.iloc[validation]["group_key"]):
            raise AssertionError("Cross-study fold leaked target participants")
        model = estimator_for(candidate)
        if candidate["algorithm"] == "xgboost":
            model.steps[-1] = ("weightedxgb", WeightedXGB(candidate["params"]))
        fit_kwargs = {model.steps[-1][0] + "__sample_weight": weights}
        with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(training[candidate["features"]], training["label"], **fit_kwargs)
            predicted = model.predict(target.iloc[validation][candidate["features"]])
        convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
        predictions[validation] = predicted
        folds.append({"target_train_groups": sorted(set(target.iloc[train]["group_key"])),
                      "external_train_groups": sorted(set(external["group_key"])) if candidate["external_weight"] > 0 else [],
                      "validation_groups": sorted(set(target.iloc[validation]["group_key"])),
                      "accuracy": float(accuracy_score(y.iloc[validation], predicted)),
                      "f1_macro": float(f1_score(y.iloc[validation], predicted, labels=[f"Borg {i}" for i in range(11)], average="macro", zero_division=0))})
    return {"accuracy_mean": float(np.mean([row["accuracy"] for row in folds])),
            "accuracy_std": float(np.std([row["accuracy"] for row in folds])),
            "pooled_oof_accuracy": float(accuracy_score(y, predictions)), "oof_predictions": predictions.tolist(),
            "folds": folds, "convergence_warnings": convergence}


def main():
    target, manifest = load_frame(RESEARCH / "multisensor-v1")
    external, external_split = load_external()
    candidates = transfer_plan(manifest["features"])
    plan_sha = hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest()
    directory = RESEARCH / "transfer-v1"
    directory.mkdir(exist_ok=True)
    report_path = directory / "selection.json"
    report = {"version": 1, "objective": "exact_native_Borg_accuracy_on_original_target_participants",
              "target_accuracy": 0.6, "target_test_evaluated": False, "external_test_evaluated": False,
              "plan": candidates, "plan_sha256": plan_sha, "experiment_code_sha256": digest(Path(__file__)),
              "target_dataset_sha256": manifest["dataset_sha256"], "external_split": external_split,
              "target_train_row_keys": target["row_key"].tolist(), "status": "running", "results": []}
    if report_path.exists():
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        for key in ("plan_sha256", "experiment_code_sha256", "target_dataset_sha256", "external_split"):
            if report[key] != existing[key]:
                raise ValueError("Transfer inputs changed; preserve previous evidence before a new run")
        report = existing
    completed = {row["candidate"]["id"] for row in report["results"]}
    print(f"Fitting with {len(target)} target responses + {len(external)} external responses; external holdout {len(external_split['test_row_keys'])} responses remains sealed", flush=True)
    for candidate in candidates:
        if candidate["id"] in completed:
            continue
        cv = evaluate(target, external, candidate)
        report["results"].append({"candidate": candidate, "cv": cv})
        winner = max(report["results"], key=lambda r: r["cv"]["accuracy_mean"])
        report["winner_id"] = winner["candidate"]["id"]
        report["best_cv_accuracy"] = winner["cv"]["accuracy_mean"]
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['algorithm']} external_weight={candidate['external_weight']}: CV accuracy={cv['accuracy_mean']:.4f}, best={report['best_cv_accuracy']:.4f}", flush=True)
    report["status"] = "complete"
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
