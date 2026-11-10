"""Grouped fitting with extra actual feedback; canonical evaluation unchanged."""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_dynamics_experiment import plan as dynamics_plan
from fatigue_extra_feedback import DIRECTORY as EXTRA_DIRECTORY, load as load_extra
from fatigue_features import RESEARCH
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = RESEARCH / "augmented-observed-feedback-80-v1"


def fitting_rows(original, extra, weight):
    if not np.isfinite(weight) or weight < 0:
        raise ValueError("Finite nonnegative extra-observation weight required")
    if weight == 0:
        return original.copy(), None, []
    eligible = extra[extra["group_key"].isin(set(original["group_key"]))].copy()
    if eligible["row_key"].duplicated().any() or set(eligible["row_key"]) & set(original["row_key"]):
        raise ValueError("Duplicate actual fitting outcomes")
    combined = pd.concat([original, eligible], ignore_index=True)
    weights = np.r_[np.ones(len(original)), np.full(len(eligible), weight)]
    return combined, weights, eligible["row_key"].tolist()


class AugmentedFeedbackBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, original, extra):
        c = self.candidate
        data, weights, keys = fitting_rows(original, extra, c["extra_weight"])
        validate_calibration(data)
        target = data["label"].str.removeprefix("Borg ").astype(int)
        if c["target_mode"] == "change_from_prior":
            target = target - data["prior_borg"].astype(int)
        if c["algorithm"] == "mlp":
            self.model = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True),
                StandardScaler(), MLPClassifier(hidden_layer_sizes=(16, 8), solver="lbfgs", alpha=c["alpha"],
                    max_iter=1000, random_state=42, early_stopping=False))
            extra_args = {} if weights is None else {"mlpclassifier__sample_weight": weights}
            self.model.fit(data[c["features"]], target.astype(str), **extra_args)
        else:
            self.model = CatBoostClassifier(iterations=c["iterations"], depth=c["depth"], l2_leaf_reg=c["l2_leaf_reg"],
                learning_rate=.03, loss_function="MultiClass", boosting_type="Ordered", grow_policy="SymmetricTree",
                random_seed=42, thread_count=4, task_type="CPU", border_count=128, bootstrap_type="Bayesian",
                bagging_temperature=1., random_strength=1., nan_mode="Min", use_best_model=False, allow_writing_files=False, verbose=False)
            args = {} if weights is None else {"sample_weight": weights}
            self.model.fit(data[c["features"]], target.to_numpy(), cat_features=["current_terrain"], **args)
        self.extra_fitting_row_keys = keys
        self.actual_fitting_rows = len(data)
        return self

    def predict(self, frame):
        validate_calibration(frame)
        values = np.asarray(self.model.predict(frame[self.candidate["features"]])).reshape(-1).astype(int)
        if self.candidate["target_mode"] == "change_from_prior":
            values = np.clip(values + frame["prior_borg"].to_numpy(int), 0, 10)
        return np.asarray([f"Borg {i}" for i in values])


def inputs():
    frame, train, test, manifest, protocol = load_inputs()
    extra, extra_manifest = load_extra()
    for data in (frame, train, test, extra):
        data["current_terrain"] = np.asarray(["stairs", "ramp", "flat_trail"])[data[["terrain_stairs", "terrain_ramp", "terrain_flat_trail"]].to_numpy().argmax(axis=1)]
    return frame, train, test, manifest, protocol, extra, extra_manifest


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    compact = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    candidates = []
    for name, features in (("prior_context", prior), ("compact_dynamics", compact)):
        for alpha in (1., 10., 100.):
            for mode in ("absolute_borg", "change_from_prior"):
                for weight in (0., .5, 1.):
                    candidates.append({"id": f"observed-extra-{len(candidates):03d}", "algorithm": "mlp", "feature_set": name,
                                       "features": features, "alpha": alpha, "target_mode": mode, "extra_weight": weight})
    source = RESEARCH / "catboost-80-v1/selection.json"
    frozen = json.loads(source.read_text(encoding="utf-8"))
    if frozen["status"] != "complete":
        raise ValueError("Freeze the original CatBoost study before planning its augmentation comparison")
    best = max(frozen["results"], key=lambda row: row["accuracy_mean"])["candidate"]
    for weight in (0., .5, 1.):
        candidates.append({**best, "id": f"observed-extra-{len(candidates):03d}", "algorithm": "catboost", "extra_weight": weight})
    return candidates


def select():
    _, train, _, manifest, _, extra, extra_manifest = inputs()
    candidates = plan(manifest)
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"], "extra_dataset_sha256": extra_manifest["dataset_sha256"],
                 "extra_provenance_sha256": digest(EXTRA_DIRECTORY / "provenance.json"), "plan": candidates,
                 "catboost_selection_sha256": digest(RESEARCH / "catboost-80-v1/selection.json"),
                 "train_row_keys": train["row_key"].tolist(), "extra_preparation_code_sha256": digest(Path(__file__).with_name("fatigue_extra_feedback.py"))}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [], "test_used_for_selection": False,
              "previous_benchmark_results_are_published": True, "extra_actual_report_pool": len(extra), "synthetic_rows": 0,
              "evaluation_denominator": 487, "test_denominator": 179, "evaluation_weighting": "unit_weight_per_original_response",
              "policy": "Extra actual outcomes enter fitting only for the fitting participants of each fold. No rest outcomes, interpolated targets or assumed onset zeros. Original validation/test cases remain unchanged."}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the frozen actual-feedback augmentation study before changing inputs")
    path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in candidates:
        if any(row["candidate"] == candidate for row in report["results"]):
            continue
        predicted = np.empty(len(train), dtype=object)
        evidence, convergence = [], 0
        for fit, val in folds:
            fit_groups, val_groups = set(train.iloc[fit]["group_key"]), set(train.iloc[val]["group_key"])
            if fit_groups & val_groups:
                raise ValueError("Augmentation leaked validation people")
            with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                warnings.simplefilter("always", ConvergenceWarning)
                model = AugmentedFeedbackBorg(candidate).fit(train.iloc[fit], extra)
            convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
            predicted[val] = model.predict(train.iloc[val])
            evidence.append({"fit_groups": sorted(fit_groups), "validation_groups": sorted(val_groups),
                             "original_fitting_rows": len(fit), "extra_fitting_row_keys": model.extra_fitting_row_keys,
                             "actual_fitting_rows": model.actual_fitting_rows})
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(),
                                  "folds": evidence, "convergence_warnings": convergence})
        best = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print(f"Actual additional feedback {len(report['results'])}/{len(candidates)}: exact unchanged CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)
    incumbent = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(row["oof_predictions"] for row in incumbent["results"] if row["candidate"]["id"] == "alternative-023")
    control = next(row["oof_predictions"] for row in report["results"] if row["candidate"]["algorithm"] == "mlp" and row["candidate"]["feature_set"] == "prior_context"
                   and row["candidate"]["alpha"] == 10. and row["candidate"]["target_mode"] == "change_from_prior" and row["candidate"]["extra_weight"] == 0.)
    np.testing.assert_array_equal(control, expected)
    source = json.loads((RESEARCH / "catboost-80-v1/selection.json").read_text())
    expected = max(source["results"], key=lambda row: row["accuracy_mean"])["oof_predictions"]
    control = next(row["oof_predictions"] for row in report["results"] if row["candidate"]["algorithm"] == "catboost" and row["candidate"]["extra_weight"] == 0.)
    np.testing.assert_array_equal(control, expected)
    print("Both original unaugmented model controls reproduce all 487 native OOF decisions", flush=True)


if __name__ == "__main__":
    select()
