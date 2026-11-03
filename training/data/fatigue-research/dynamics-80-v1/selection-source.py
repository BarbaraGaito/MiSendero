"""Immutable train-only grouped search for the >=80% exact Borg objective."""
from __future__ import annotations

import argparse
import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from fatigue_dynamics import CONTEXT, DIRECTORY, load_inputs
from fatigue_experiment import EncodedXGBClassifier
from fatigue_probability import validate_calibration
from public_sources import digest


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    dynamics = manifest["dynamics_features"]
    compact_names = ["task_feedback_first", "task_feedback_total_rise", "task_feedback_count", "task_feedback_rate_mean",
                     "task_feedback_rate_median", "task_feedback_since_last_increase", "task_feedback_zero_fraction",
                     "task_feedback_linear_extrapolation", "task_feedback_delta_1", "task_feedback_interval_1",
                     "task_feedback_delta_2", "task_feedback_interval_2", "all_feedback_rate_mean",
                     "all_feedback_positive_fraction", "completed_task_rise_mean", "completed_task_rate_mean",
                     "previous_task_at_similar_elapsed_mean", "previous_task_at_similar_elapsed_last"]
    physiology = ["hr_last", "hr_delta_baseline", "hr_ratio_baseline", "hr_recent_slope", "hr_history_mean",
                  "hr_change_after_prior", "hr_change_per_minute_after_prior", "eda_delta_baseline", "eda_recent_slope",
                  "temperature_delta_baseline", "acceleration_history_mean", "steps_history_mean", "met_history_mean",
                  "raw_pulse_rmssd_ms", "raw_pulse_sdnn_ms", "screening_sleep_hours"]
    sets = {"compact_dynamics": prior + compact_names,
            "complete_feedback": list(dict.fromkeys(prior + dynamics + manifest["session_features"])),
            "feedback_physiology": list(dict.fromkeys(prior + dynamics + manifest["session_features"] + physiology))}
    configs = [
        *[("random_forest", {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": leaf, "max_features": 1.}) for leaf in (2, 5, 10)],
        *[("extra_trees", {"n_estimators": 200, "max_depth": None, "min_samples_leaf": leaf, "max_features": 1.}) for leaf in (2, 5, 10)],
        *[("xgboost", {"n_estimators": 200, "max_depth": depth, "learning_rate": .05, "min_child_weight": 5, "reg_lambda": 10}) for depth in (2, 3)],
        *[("hist_gradient_boosting", {"max_iter": 150, "max_leaf_nodes": leaves, "learning_rate": .05, "l2_regularization": 10, "min_samples_leaf": 10}) for leaves in (5, 10)],
        *[("svm", {"C": c, "gamma": "scale"}) for c in (.1, 1., 10.)],
        *[("logistic", {"C": c, "max_iter": 3000}) for c in (.01, .1, 1.)],
        *[("mlp", {"hidden_layer_sizes": shape, "solver": "lbfgs", "alpha": alpha, "max_iter": 1500}) for shape, alpha in (([8], 10.), ([16, 8], 1.), ([16, 8], 10.), ([16, 8], 100.), ([32, 16], 100.))],
    ]
    candidates = [{"id": "dynamics-000", "feature_set": "incumbent_control", "features": prior, "algorithm": "mlp",
                   "params": {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}, "target_mode": "change_from_prior"}]
    for name, features in sets.items():
        for algorithm, params in configs:
            for mode in ("absolute_borg", "change_from_prior"):
                candidates.append({"id": f"dynamics-{len(candidates):03d}", "feature_set": name, "features": features,
                                   "algorithm": algorithm, "params": params, "target_mode": mode})
    return candidates


class DynamicsClassifier:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame):
        validate_calibration(frame)
        c = self.candidate
        models = {"random_forest": RandomForestClassifier, "extra_trees": ExtraTreesClassifier,
                  "hist_gradient_boosting": HistGradientBoostingClassifier, "mlp": MLPClassifier,
                  "svm": SVC, "logistic": LogisticRegression}
        if c["algorithm"] == "xgboost":
            classifier = EncodedXGBClassifier(c["params"])
        else:
            extra = {"n_jobs": 1} if c["algorithm"] in ("random_forest", "extra_trees") else {}
            if c["algorithm"] == "mlp":
                extra["early_stopping"] = False
            classifier = models[c["algorithm"]](**c["params"], random_state=42, **extra)
        stages = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)]
        if c["algorithm"] in ("mlp", "svm", "logistic"):
            stages.append(StandardScaler())
        self.model = make_pipeline(*stages, classifier)
        target = frame["label"].str.removeprefix("Borg ").astype(int)
        if c["target_mode"] == "change_from_prior":
            target = target - frame["prior_borg"].astype(int)
        self.model.fit(frame[c["features"]], target.astype(str))
        return self

    def predict(self, frame):
        validate_calibration(frame)
        values = self.model.predict(frame[self.candidate["features"]]).astype(int)
        if self.candidate["target_mode"] == "change_from_prior":
            values = np.clip(values + frame["prior_borg"].to_numpy(dtype=int), 0, 10)
        return np.asarray([f"Borg {i}" for i in values])


def select():
    _, train, _, manifest, _ = load_inputs()
    candidates = plan(manifest)
    signature = {"dataset_sha256": manifest["dataset_sha256"], "code_sha256": digest(Path(__file__)),
                 "feature_code_sha256": manifest["feature_code_sha256"], "plan": candidates,
                 "plan_sha256": hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest(),
                 "train_row_keys": train["row_key"].tolist()}
    report = {**signature, "version": 1, "target_accuracy": .8, "objective": "exact_native_Borg_accuracy_on_unchanged_cohort",
              "status": "running", "test_used_for_selection": False, "previous_benchmark_results_are_published": True, "results": []}
    path = DIRECTORY / "selection.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if any(old[k] != v for k, v in signature.items()):
            raise ValueError("Dynamics experiment inputs changed; preserve the previous version")
        report = old
    done = {r["candidate"]["id"] for r in report["results"]}
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        predictions = np.empty(len(train), dtype=object)
        scores, convergence = [], 0
        for fit, val in folds:
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise AssertionError("Dynamics CV leaked participant data")
            with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                warnings.simplefilter("always", ConvergenceWarning)
                model = DynamicsClassifier(candidate).fit(train.iloc[fit])
                predicted = model.predict(train.iloc[val])
            convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
            predictions[val] = predicted
            scores.append(float(accuracy_score(train.iloc[val]["label"], predicted)))
        result = {"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                  "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(train["label"], predictions)),
                  "oof_predictions": predictions.tolist(), "convergence_warnings": convergence}
        report["results"].append(result)
        best = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(path)
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']} {candidate['target_mode']}: CV={result['accuracy_mean']:.4f}, best={best['accuracy_mean']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    # Canonical module keeps any later local serialized artifact importable.
    import fatigue_dynamics_experiment as module
    module.select()
