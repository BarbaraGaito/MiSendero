"""Participant-held-out training CV of causal waveform features; no test fit."""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from fatigue_experiment import EncodedXGBClassifier
from fatigue_features import RESEARCH
from public_sources import OUTPUT, digest


def load_target():
    directory = RESEARCH / "raw-v1"
    manifest = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if digest(directory / "dataset.csv") != manifest["dataset_sha256"]:
        raise ValueError("Raw-derived predictor snapshot changed")
    if digest(Path(__file__).with_name("fatigue_raw_features.py")) != manifest["feature_code_sha256"]:
        raise ValueError("Raw feature code changed; rebuild first")
    if digest(OUTPUT / "fatigue/dataset.csv") != manifest["canonical_dataset_sha256"]:
        raise ValueError("Original task changed")
    frame = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
    frame["row_key"] = [r["row_key"] for r in manifest["lineage"]]
    frame["group_key"] = [r["group_key"] for r in manifest["lineage"]]
    protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    target = frame[frame["row_key"].isin(protocol["train_row_keys"])].copy()
    if len(target) != len(protocol["train_row_keys"]) or set(target["group_key"]) & set(protocol["test_groups"]):
        raise ValueError("Original held-out cohort changed")
    return target, manifest


def candidate_plan(manifest):
    context = ["elapsed_minutes", "cumulative_active_minutes", "task_order", "terrain_stairs", "terrain_flat_trail", "terrain_ramp"]
    sets = {"raw_context": [*manifest["raw_features"], *context],
            "all_features": manifest["features"],
            "raw_relative": [name for name in manifest["features"] if name.endswith(("delta_baseline", "ratio_baseline")) or name.startswith("raw_pulse_") or name in context or name == "screening_sleep_hours"]}
    algorithms = [
        ("random_forest", {"n_estimators": 250, "min_samples_leaf": 2, "max_features": .5}, None),
        ("random_forest", {"n_estimators": 250, "min_samples_leaf": 6, "max_features": 1.}, None),
        ("extra_trees", {"n_estimators": 250, "min_samples_leaf": 2, "max_features": .7}, None),
        ("extra_trees", {"n_estimators": 250, "min_samples_leaf": 6, "max_features": 1.}, None),
        ("random_forest", {"n_estimators": 250, "min_samples_leaf": 3, "max_features": 1.}, 30),
        ("extra_trees", {"n_estimators": 250, "min_samples_leaf": 3, "max_features": 1.}, 30),
        ("hist_gradient_boosting", {"max_iter": 200, "max_leaf_nodes": 7, "min_samples_leaf": 15,
                                    "learning_rate": .05, "l2_regularization": 10, "early_stopping": False}, None),
        *[("xgboost", {"n_estimators": 300, "max_depth": depth, "learning_rate": .05,
                         "min_child_weight": 5, "reg_lambda": 10, "subsample": .8, "colsample_bytree": .8}, None) for depth in (3, 5)],
        ("svm", {"C": .3, "gamma": "scale"}, None),
        ("svm", {"C": 1., "gamma": "scale"}, None),
        ("svm", {"C": 10., "gamma": "scale"}, None),
        ("svm", {"C": 1., "gamma": "scale"}, 30),
        ("logistic_regression", {"C": .1, "max_iter": 3000}, None),
        ("logistic_regression", {"C": 1., "max_iter": 3000}, None),
    ]
    return [{"id": f"waveform-{i:03d}", "feature_set": name, "features": columns,
             "algorithm": algorithm, "params": params, "select_k": k}
            for i, (name, columns, algorithm, params, k) in enumerate(
                (name, cols, algorithm, params, k) for name, cols in sets.items() for algorithm, params, k in algorithms)]


def estimator_for(candidate):
    algorithm, params = candidate["algorithm"], candidate["params"]
    if algorithm == "random_forest":
        estimator = RandomForestClassifier(**params, n_jobs=1, random_state=42)
    elif algorithm == "extra_trees":
        estimator = ExtraTreesClassifier(**params, n_jobs=1, random_state=42)
    elif algorithm == "hist_gradient_boosting":
        estimator = HistGradientBoostingClassifier(**params, random_state=42)
    elif algorithm == "xgboost":
        estimator = EncodedXGBClassifier(params)
    elif algorithm == "svm":
        estimator = SVC(**params, random_state=42)
    elif algorithm == "logistic_regression":
        estimator = LogisticRegression(**params, random_state=42)
    else:
        raise ValueError("Unknown waveform estimator")
    steps = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)]
    if candidate["select_k"]:
        steps.append(SelectKBest(f_classif, k=min(candidate["select_k"], len(candidate["features"])) ))
    if algorithm in ("svm", "logistic_regression"):
        steps.append(StandardScaler())
    return make_pipeline(*steps, estimator)


def evaluate(frame, candidate):
    y, groups = frame["label"], frame["group_key"]
    prediction = np.empty(len(frame), dtype=object)
    folds, convergences = [], 0
    for train, validation in GroupKFold(n_splits=5).split(frame, y, groups):
        if set(groups.iloc[train]) & set(groups.iloc[validation]):
            raise AssertionError("Waveform participant leakage")
        estimator = estimator_for(candidate)
        with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
            warnings.simplefilter("always", ConvergenceWarning)
            estimator.fit(frame.iloc[train][candidate["features"]], y.iloc[train])
            values = estimator.predict(frame.iloc[validation][candidate["features"]])
        convergences += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
        prediction[validation] = values
        folds.append({"train_groups": sorted(set(groups.iloc[train])), "validation_groups": sorted(set(groups.iloc[validation])),
                      "accuracy": float(accuracy_score(y.iloc[validation], values)),
                      "f1_macro": float(f1_score(y.iloc[validation], values, labels=sorted(y.unique()), average="macro", zero_division=0))})
    return {"accuracy_mean": float(np.mean([r["accuracy"] for r in folds])),
            "accuracy_std": float(np.std([r["accuracy"] for r in folds])),
            "pooled_oof_accuracy": float(accuracy_score(y, prediction)), "folds": folds,
            "oof_predictions": prediction.tolist(), "convergence_warnings": convergences}


def main():
    target, manifest = load_target()
    candidates = candidate_plan(manifest)
    plan_sha = hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest()
    path = RESEARCH / "raw-v1/selection.json"
    report = {"version": 1, "objective": "exact_native_Borg_accuracy", "target_accuracy": .6,
              "test_evaluated": False, "plan": candidates, "plan_sha256": plan_sha,
              "dataset_sha256": manifest["dataset_sha256"], "experiment_code_sha256": digest(Path(__file__)),
              "train_row_keys": target["row_key"].tolist(), "status": "running", "results": []}
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        for key in ("plan_sha256", "dataset_sha256", "experiment_code_sha256"):
            if old[key] != report[key]:
                raise ValueError("Waveform experiment changed; preserve previous results first")
        report = old
    done = {r["candidate"]["id"] for r in report["results"]}
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        cv = evaluate(target, candidate)
        report["results"].append({"candidate": candidate, "cv": cv})
        winner = max(report["results"], key=lambda r: r["cv"]["accuracy_mean"])
        report["winner_id"] = winner["candidate"]["id"]
        report["best_cv_accuracy"] = winner["cv"]["accuracy_mean"]
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']} k={candidate['select_k']}: CV accuracy={cv['accuracy_mean']:.4f}, best={report['best_cv_accuracy']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
