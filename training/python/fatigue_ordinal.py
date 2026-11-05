"""Ordinal regression research, evaluated by exact native Borg accuracy.

Continuous predictions are rounded to the original integer scale; neither
bands nor tolerance-based matches count toward the 60-percent objective.
"""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from fatigue_experiment import load_frame, plan
from fatigue_features import RESEARCH
from fatigue_transfer import load_external
from public_sources import digest


def candidates_for(features):
    sets = {row["feature_set"]: row["features"] for row in plan(features)
            if row["feature_set"] in ("original", "normalized", "all_sensors_context")}
    algorithms = [
        ("random_forest", {"n_estimators": 200, "min_samples_leaf": 3, "max_features": 0.7}),
        ("random_forest", {"n_estimators": 200, "min_samples_leaf": 10, "max_features": 1.}),
        ("extra_trees", {"n_estimators": 200, "min_samples_leaf": 3, "max_features": 0.7}),
        ("extra_trees", {"n_estimators": 200, "min_samples_leaf": 10, "max_features": 1.}),
        ("hist_gradient_boosting", {"max_iter": 250, "max_leaf_nodes": 7, "min_samples_leaf": 15,
                                    "learning_rate": 0.05, "l2_regularization": 5, "loss": "squared_error"}),
        ("hist_gradient_boosting", {"max_iter": 250, "max_leaf_nodes": 7, "min_samples_leaf": 15,
                                    "learning_rate": 0.05, "l2_regularization": 5, "loss": "absolute_error"}),
        ("xgboost", {"n_estimators": 300, "max_depth": 3, "learning_rate": 0.05,
                     "min_child_weight": 5, "reg_lambda": 5, "subsample": 0.8}),
        ("svr", {"C": 1., "gamma": "scale", "epsilon": 0.5}),
        ("svr", {"C": 10., "gamma": "scale", "epsilon": 0.5}),
        ("mlp", {"hidden_layer_sizes": [32, 16], "alpha": 5., "solver": "lbfgs", "max_iter": 1000}),
    ]
    return [{"id": f"ordinal-{i:03d}", "features": cols, "feature_set": name,
             "algorithm": algorithm, "params": params, "external_weight": weight}
            for i, (name, cols, algorithm, params, weight) in enumerate(
                (name, cols, algorithm, params, weight) for name, cols in sets.items()
                for algorithm, params in algorithms for weight in (0., 1.))]


def estimator_for(candidate):
    algorithm, params = candidate["algorithm"], candidate["params"]
    if algorithm == "random_forest":
        estimator = RandomForestRegressor(**params, n_jobs=1, random_state=42)
    elif algorithm == "extra_trees":
        estimator = ExtraTreesRegressor(**params, n_jobs=1, random_state=42)
    elif algorithm == "hist_gradient_boosting":
        estimator = HistGradientBoostingRegressor(**params, early_stopping=False, random_state=42)
    elif algorithm == "xgboost":
        from xgboost import XGBRegressor
        estimator = XGBRegressor(**params, n_jobs=1, random_state=42)
    elif algorithm == "svr":
        estimator = SVR(**params)
    elif algorithm == "mlp":
        estimator = MLPRegressor(**params, early_stopping=False, random_state=42)
    else:
        raise ValueError("Unknown ordinal estimator")
    steps = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)]
    if algorithm in ("svr", "mlp"):
        steps.append(StandardScaler())
    return make_pipeline(*steps, estimator)


def evaluate(target, external, candidate):
    import pandas as pd
    truth = target["label"].str.replace("Borg ", "", regex=False).astype(float)
    prediction = np.empty(len(target), dtype=int)
    folds, convergence = [], 0
    for train, validation in GroupKFold(n_splits=5).split(target, truth, target["group_key"]):
        training = target.iloc[train]
        weights = np.ones(len(training))
        if candidate["external_weight"]:
            training = pd.concat([training, external], ignore_index=True)
            weights = np.r_[weights, np.full(len(external), candidate["external_weight"])]
        if set(training["group_key"]) & set(target.iloc[validation]["group_key"]):
            raise AssertionError("Participant leakage in ordinal fitting")
        y_train = training["label"].str.replace("Borg ", "", regex=False).astype(float)
        estimator = estimator_for(candidate)
        kwargs = {estimator.steps[-1][0] + "__sample_weight": weights}
        with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
            warnings.simplefilter("always", ConvergenceWarning)
            estimator.fit(training[candidate["features"]], y_train, **kwargs)
            values = estimator.predict(target.iloc[validation][candidate["features"]])
        convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite ordinal prediction")
        rounded = np.clip(np.rint(values), 0, 10).astype(int)
        prediction[validation] = rounded
        folds.append({"train_groups": sorted(set(target.iloc[train]["group_key"])),
                      "validation_groups": sorted(set(target.iloc[validation]["group_key"])),
                      "accuracy": float(accuracy_score(truth.iloc[validation], rounded)),
                      "mae": float(mean_absolute_error(truth.iloc[validation], values))})
    return {"accuracy_mean": float(np.mean([r["accuracy"] for r in folds])),
            "accuracy_std": float(np.std([r["accuracy"] for r in folds])),
            "pooled_oof_accuracy": float(accuracy_score(truth, prediction)),
            "oof_predictions": [f"Borg {i}" for i in prediction], "folds": folds,
            "convergence_warnings": convergence}


def main():
    target, manifest = load_frame(RESEARCH / "multisensor-v1")
    external, external_split = load_external()
    candidates = candidates_for(manifest["features"])
    directory = RESEARCH / "ordinal-v1"
    directory.mkdir(exist_ok=True)
    path = directory / "selection.json"
    plan_sha = hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest()
    report = {"version": 1, "objective": "exact_native_integer_Borg_accuracy", "target_accuracy": 0.6,
              "test_evaluated": False, "tolerance_matches_count_as_accuracy": False,
              "plan": candidates, "plan_sha256": plan_sha, "experiment_code_sha256": digest(Path(__file__)),
              "dataset_sha256": manifest["dataset_sha256"], "external_split": external_split,
              "train_row_keys": target["row_key"].tolist(), "status": "running", "results": []}
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        for key in ("plan_sha256", "experiment_code_sha256", "dataset_sha256", "external_split"):
            if report[key] != old[key]:
                raise ValueError("Ordinal research inputs changed; preserve previous results first")
        report = old
    completed = {r["candidate"]["id"] for r in report["results"]}
    for candidate in candidates:
        if candidate["id"] in completed:
            continue
        cv = evaluate(target, external, candidate)
        report["results"].append({"candidate": candidate, "cv": cv})
        winner = max(report["results"], key=lambda r: r["cv"]["accuracy_mean"])
        report["winner_id"] = winner["candidate"]["id"]
        report["best_cv_accuracy"] = winner["cv"]["accuracy_mean"]
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']} external={candidate['external_weight']}: exact CV accuracy={cv['accuracy_mean']:.4f}, best={report['best_cv_accuracy']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
