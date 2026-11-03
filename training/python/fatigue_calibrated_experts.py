"""Learn separate initial-task and within-task Borg transitions, using all rows.

The gate is known before prediction: whether the previous user report was
at or before the current task started. Neither branch drops difficult responses.
Model combinations are ranked on original participant-disjoint training CV.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.naive_bayes import CategoricalNB, GaussianNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from fatigue_calibrated_ensemble import load_inputs
from fatigue_features import RESEARCH
from public_sources import digest


INITIAL_FEATURES = ["elapsed_minutes", "hr_last", "hr_delta_baseline", "hr_ratio_baseline", "hr_change_after_prior",
                    "cumulative_active_minutes", "task_order", "terrain_stairs", "terrain_flat_trail", "terrain_ramp",
                    "prior_borg", "prior2_borg", "prior_history_mean", "prior_history_std"]
LATER_FEATURES = ["prior_borg", "prior2_borg", "prior_age_minutes", "prior_borg_slope", "prior_history_mean",
                 "prior_history_std", "prior_count_current_task", "elapsed_minutes", "hr_change_after_prior",
                 "hr_change_per_minute_after_prior", "hr_delta_baseline", "hr_recent_slope"]


def categorical_features(frame):
    """Fixed predictor bins; no fatigue target is coarsened or generated."""
    def encode(values, boundaries):
        values = np.asarray(values, dtype=float)
        encoded = np.digitize(np.nan_to_num(values, nan=0.), boundaries)
        encoded[~np.isfinite(values)] = len(boundaries) + 1
        return encoded
    direction = np.where(frame["prior2_borg"].notna(), np.sign(frame["prior_borg"]-frame["prior2_borg"]) + 1, 3).astype(int)
    return np.column_stack((encode(frame["prior_borg"], np.arange(.5, 10, 1)),
                            encode(frame["prior2_borg"], np.arange(.5, 10, 1)), direction,
                            encode(frame["elapsed_minutes"], [2.5, 7.5, 12.5, 17.5, 22.5, 30]),
                            encode(frame["prior_age_minutes"], [2, 4, 6, 8, 10, 12, 15]),
                            encode(frame["prior_count_current_task"], [.5, 1.5, 2.5, 3.5, 4.5]),
                            encode(frame["hr_change_after_prior"], [-50, -30, -15, -5, 5, 15, 30, 50])))


def model(config):
    kind = config["algorithm"]
    params = config.get("params", {})
    if kind == "majority":
        return DummyClassifier(strategy="most_frequent")
    if kind == "extra_trees":
        classifier = ExtraTreesClassifier(n_estimators=200, random_state=42, n_jobs=1, **params)
    elif kind == "random_forest":
        classifier = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=1, **params)
    elif kind == "gaussian_nb":
        classifier = GaussianNB(**params)
    elif kind == "logistic":
        classifier = LogisticRegression(max_iter=3000, random_state=42, **params)
    elif kind == "svm":
        classifier = SVC(random_state=42, **params)
    elif kind == "categorical_nb":
        return CategoricalNB(min_categories=[12, 12, 4, 8, 9, 7, 10], **params)
    else:
        raise ValueError("Unknown calibrated expert")
    stages = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)]
    if kind in ("gaussian_nb", "logistic", "svm"):
        stages.append(StandardScaler())
    return make_pipeline(*stages, classifier)


def fit_predict(train, test, targets, config, features):
    if not len(test):
        return np.array([], dtype=int)
    if not len(train):
        raise ValueError("An expert cannot fit without observed training responses")
    classifier = model(config)
    if config["algorithm"] == "categorical_nb":
        x_train, x_test = categorical_features(train), categorical_features(test)
    elif config["algorithm"] == "majority":
        x_train, x_test = np.zeros((len(train), 1)), np.zeros((len(test), 1))
    else:
        x_train, x_test = train[features], test[features]
    if len(np.unique(targets)) < 2:
        return np.full(len(test), np.asarray(targets)[0], dtype=int)
    with threadpool_limits(limits=1):
        classifier.fit(x_train, targets)
        return classifier.predict(x_test).astype(int)


def main():
    _, target, _, manifest, _ = load_inputs()
    initial_configs = [
        {"algorithm": "majority"},
        {"algorithm": "extra_trees", "params": {"max_depth": 3, "min_samples_leaf": 3, "max_features": 1.}},
        {"algorithm": "extra_trees", "params": {"max_depth": 6, "min_samples_leaf": 2, "max_features": .7}},
        {"algorithm": "random_forest", "params": {"max_depth": 4, "min_samples_leaf": 4, "max_features": 1.}},
        {"algorithm": "logistic", "params": {"C": .1}},
        {"algorithm": "svm", "params": {"C": 1., "gamma": "scale"}},
    ]
    later_configs = [
        {"algorithm": "extra_trees", "params": {"max_depth": 3, "min_samples_leaf": 2, "max_features": 1.}},
        {"algorithm": "extra_trees", "params": {"max_depth": 6, "min_samples_leaf": 4, "max_features": 1.}},
        {"algorithm": "random_forest", "params": {"max_depth": 5, "min_samples_leaf": 4, "max_features": 1.}},
        {"algorithm": "categorical_nb", "params": {"alpha": .1}},
        {"algorithm": "categorical_nb", "params": {"alpha": 1.}},
        {"algorithm": "categorical_nb", "params": {"alpha": 5.}},
        {"algorithm": "gaussian_nb", "params": {"var_smoothing": .01}},
        {"algorithm": "gaussian_nb", "params": {"var_smoothing": .1}},
        {"algorithm": "logistic", "params": {"C": .1}},
        {"algorithm": "logistic", "params": {"C": 1.}},
        {"algorithm": "svm", "params": {"C": 1., "gamma": "scale"}},
        {"algorithm": "svm", "params": {"C": 10., "gamma": "scale"}},
    ]
    directory = RESEARCH / "calibrated-experts-v1"
    directory.mkdir(exist_ok=True)
    path = directory / "selection.json"
    configurations = {"initial": initial_configs, "later": later_configs,
                      "initial_features": INITIAL_FEATURES, "later_features": LATER_FEATURES}
    report = {"version": 1, "objective": "exact_native_Borg_accuracy_with_observed_prior_feedback",
              "target_accuracy": .6, "test_evaluated": False, "dataset_sha256": manifest["dataset_sha256"],
              "code_sha256": digest(Path(__file__)), "plan": configurations,
              "plan_sha256": hashlib.sha256(json.dumps(configurations, sort_keys=True).encode()).hexdigest(),
              "train_row_keys": target["row_key"].tolist(), "status": "running", "results": []}
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old["code_sha256"] != report["code_sha256"] or old["dataset_sha256"] != report["dataset_sha256"]:
            raise ValueError("Expert experiment changed; preserve previous evidence first")
        if old["status"] == "complete":
            print(f"Expert search already complete: best CV accuracy={old['best_cv_accuracy']:.4f}")
            return
    truth = target["label"].str.replace("Borg ", "", regex=False).astype(int)
    folds = list(GroupKFold(n_splits=5).split(target, truth, target["group_key"]))
    initial_predictions = np.zeros((len(initial_configs), len(target)), dtype=int)
    later_predictions = np.zeros((len(later_configs), len(target)), dtype=int)
    for fold_index, (train_idx, validation_idx) in enumerate(folds):
        training, validation = target.iloc[train_idx], target.iloc[validation_idx]
        if set(training["group_key"]) & set(validation["group_key"]):
            raise AssertionError("Expert training leaked target participants")
        train_initial = training["prior_age_minutes"].ge(training["elapsed_minutes"])
        validate_initial = validation["prior_age_minutes"].ge(validation["elapsed_minutes"])
        for i, config in enumerate(initial_configs):
            selected_train = training[train_initial]
            selected_test = validation[validate_initial]
            predicted = fit_predict(selected_train, selected_test,
                truth.loc[selected_train.index], config, INITIAL_FEATURES)
            initial_predictions[i, validation_idx[validate_initial.to_numpy()]] = predicted
        for i, config in enumerate(later_configs):
            selected_train = training[~train_initial]
            selected_test = validation[~validate_initial]
            delta = truth.loc[selected_train.index] - selected_train["prior_borg"].astype(int)
            predicted = fit_predict(selected_train, selected_test, delta, config, LATER_FEATURES)
            values = np.clip(predicted + selected_test["prior_borg"].to_numpy(dtype=int), 0, 10)
            later_predictions[i, validation_idx[~validate_initial.to_numpy()]] = values
        print(f"Calibrated experts: completed training-only fold {fold_index+1}/5", flush=True)
    gate = target["prior_age_minutes"].ge(target["elapsed_minutes"]).to_numpy()
    for i, first in enumerate(initial_configs):
        for j, later in enumerate(later_configs):
            values = np.where(gate, initial_predictions[i], later_predictions[j])
            scores = [float(accuracy_score(truth.iloc[validation], values[validation])) for _, validation in folds]
            report["results"].append({"candidate": {"id": f"experts-{i:02d}-{j:02d}", "initial": first, "later": later},
                                      "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                                      "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(truth, values)),
                                      "oof_predictions": [f"Borg {v}" for v in values]})
    best = max(report["results"], key=lambda row: row["accuracy_mean"])
    report.update(status="complete", winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Best calibrated experts: {best['candidate']}; exact native CV accuracy={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    main()
