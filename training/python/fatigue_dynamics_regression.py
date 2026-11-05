"""Grouped train-only ordinal/continuous Borg models, scored by exact integers.

Regression learns the original observed values (or their change from actual
prior Borg). Only predictions are rounded; no target is binned/interpolated.
The original 179-response test is not evaluated by this search.
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
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_dynamics_experiment import plan as classifier_plan
from fatigue_features import RESEARCH
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = RESEARCH / "dynamics-regression-80-v1"


def plan(manifest):
    compact = next(c["features"] for c in classifier_plan(manifest) if c["feature_set"] == "compact_dynamics")
    sets = {"prior_context": manifest["calibration_features"] + CONTEXT,
            "compact_dynamics": compact,
            "compact_physiology": compact + ["hr_last", "hr_change_after_prior", "hr_delta_baseline", "task_hr_borg_prediction", "session_hr_borg_prediction"]}
    configs = [
        *[("svr", {"C": c, "epsilon": epsilon, "gamma": "scale"}) for c in (.1, 1., 10., 100.) for epsilon in (.05, .25)],
        *[("ridge", {"alpha": alpha}) for alpha in (1., 10., 100.)],
        *[("polynomial_ridge", {"alpha": alpha}) for alpha in (10., 100., 1000.)],
        ("random_forest", {"n_estimators": 200, "max_depth": 6, "min_samples_leaf": 5, "max_features": 1.}),
        ("extra_trees", {"n_estimators": 200, "max_depth": None, "min_samples_leaf": 5, "max_features": 1.}),
        *[("hist_gradient_boosting", {"loss": loss, "max_leaf_nodes": 7, "max_iter": 200, "learning_rate": .05, "l2_regularization": 10, "min_samples_leaf": 10}) for loss in ("squared_error", "absolute_error")],
        *[("mlp", {"hidden_layer_sizes": shape, "solver": "lbfgs", "alpha": alpha, "max_iter": 1500}) for shape, alpha in (([8], 1.), ([8], 10.), ([16, 8], 10.), ([16, 8], 100.))],
    ]
    return [{"id": f"continuous-{i:03d}", "feature_set": name, "features": features,
             "algorithm": algorithm, "params": params, "target_mode": mode}
            for i, (name, features, algorithm, params, mode) in enumerate(
                (name, features, algorithm, params, mode) for name, features in sets.items()
                for algorithm, params in configs for mode in ("absolute_borg", "change_from_prior"))]


class ContinuousBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame):
        c = self.candidate
        validate_calibration(frame)
        constructors = {"svr": SVR, "ridge": Ridge, "polynomial_ridge": Ridge, "random_forest": RandomForestRegressor,
                        "extra_trees": ExtraTreesRegressor, "hist_gradient_boosting": HistGradientBoostingRegressor, "mlp": MLPRegressor}
        extras = {"random_state": 42} if c["algorithm"] not in ("svr", "ridge", "polynomial_ridge") else {}
        if c["algorithm"] in ("random_forest", "extra_trees"):
            extras["n_jobs"] = 1
        if c["algorithm"] == "mlp":
            extras["early_stopping"] = False
        stages = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)]
        if c["algorithm"] in ("svr", "ridge", "polynomial_ridge", "mlp"):
            stages.append(StandardScaler())
        if c["algorithm"] == "polynomial_ridge":
            stages.extend([PolynomialFeatures(degree=2, include_bias=False), StandardScaler()])
        stages.append(constructors[c["algorithm"]](**c["params"], **extras))
        self.model = make_pipeline(*stages)
        target = frame["label"].str.removeprefix("Borg ").astype(int)
        if c["target_mode"] == "change_from_prior":
            target = target - frame["prior_borg"].astype(int)
        self.model.fit(frame[c["features"]], target)
        return self

    def predict(self, frame):
        validate_calibration(frame)
        value = self.model.predict(frame[self.candidate["features"]])
        if self.candidate["target_mode"] == "change_from_prior":
            value = value + frame["prior_borg"].to_numpy(float)
        return np.asarray([f"Borg {i}" for i in np.clip(np.floor(value + .5), 0, 10).astype(int)])


def select():
    _, train, _, manifest, _ = load_inputs()
    candidates = plan(manifest)
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"], "plan": candidates,
                 "plan_sha256": hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest(),
                 "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "objective": "exact_native_Borg_accuracy_on_unchanged_cohort",
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True, "status": "running", "results": []}
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if any(previous[k] != v for k, v in signature.items()):
            raise ValueError("Continuous search inputs changed; preserve previous run")
        report = previous
    done = {r["candidate"]["id"] for r in report["results"]}
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        predicted = np.empty(len(train), dtype=object)
        scores, convergence = [], 0
        for fit, val in folds:
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise AssertionError("Continuous model leaked validation participants")
            with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                warnings.simplefilter("always", ConvergenceWarning)
                model = ContinuousBorg(candidate).fit(train.iloc[fit])
                values = model.predict(train.iloc[val])
            convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
            predicted[val] = values
            scores.append(float(accuracy_score(train.iloc[val]["label"], values)))
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                                  "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)),
                                  "oof_predictions": predicted.tolist(), "convergence_warnings": convergence})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        content = json.dumps(report, indent=2, allow_nan=False) + "\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']} {candidate['target_mode']}: exact CV={scores and np.mean(scores):.4f}, best={best['accuracy_mean']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import fatigue_dynamics_regression as module
    module.select()
