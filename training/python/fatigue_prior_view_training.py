"""Report-balanced training with genuine observed-history input augmentation."""
from __future__ import annotations

import importlib.metadata
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from fatigue_dynamics import load_inputs
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from fatigue_prior_views import DIRECTORY as VIEW_DIRECTORY, load as load_views
from fatigue_probability import validate_calibration
from fatigue_warm_sgd import core_candidate
from public_sources import digest

DIRECTORY = RESEARCH / "prior-view-augmentation-80-v1"


def fitting_views(frame, pool, policy, mass):
    if policy not in ("prefix", "subsets") or not 0 < mass < 1 or not frame["row_key"].is_unique:
        raise ValueError("Unique fitting reports and a valid input-view policy/mass required")
    selected = pool[pool["target_row_key"].isin(frame["row_key"])].copy()
    if policy == "prefix":
        selected = selected[selected["prefix_only"]].copy()
    original = frame.set_index("row_key")
    if len(selected):
        expected = original.loc[selected["target_row_key"]]
        if (not np.array_equal(expected["group_key"].to_numpy(), selected["group_key"].to_numpy())
                or not np.array_equal(expected["label"].to_numpy(), selected["label"].to_numpy())
                or selected["view_key"].duplicated().any()):
            raise ValueError("An alternative view changed its original person/target or duplicated a view")
    counts = selected["target_row_key"].value_counts()
    canonical_weight = np.asarray([1.-mass if key in counts else 1. for key in frame["row_key"]])
    alternate_weight = np.asarray([mass/counts[key] for key in selected["target_row_key"]])
    weights = np.r_[canonical_weight, alternate_weight]
    data = pd.concat([frame, selected.rename(columns={"target_row_key": "original_target_key"})], ignore_index=True)
    roots = [*frame["row_key"], *selected["target_row_key"]]
    total = pd.Series(weights).groupby(roots).sum().reindex(frame["row_key"])
    np.testing.assert_allclose(total, np.ones(len(frame)), rtol=0, atol=1e-12)
    if not np.isclose(weights.sum(), len(frame)) or not np.all(weights > 0):
        raise ValueError("Input views changed the total weight of original reports")
    return data, weights, selected["view_key"].tolist()


class PriorViewBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame, pool, core_specification):
        validate_calibration(frame)
        if self.candidate["algorithm"] == "control":
            self.base = DynamicsClassifier(core_specification).fit(frame)
            self.fit_summary = {"unique_actual_targets": len(frame), "alternative_input_views": 0, "total_report_weight": float(len(frame))}
            return self
        data, weights, keys = fitting_views(frame, pool, self.candidate["view_policy"], self.candidate["view_mass"])
        validate_calibration(data)
        columns = self.candidate["features"]
        # The imputer learns from unique real query rows; views must not move
        # its median simply because one report offers more history subsets.
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True).fit(frame[columns])
        values = self.imputer.transform(data[columns])
        self.scaler = StandardScaler().fit(values, sample_weight=weights)
        target = data["label"].str.removeprefix("Borg ").to_numpy(int)
        if self.candidate["target_mode"] == "change_from_prior":
            target = target-data["prior_borg"].to_numpy(int)
        self.model = MLPClassifier(**self.candidate["params"], random_state=42, early_stopping=False)
        with threadpool_limits(limits=1):
            self.model.fit(self.scaler.transform(values), target.astype(str), sample_weight=weights)
        self.fit_summary = {"unique_actual_targets": len(frame), "alternative_input_views": len(keys), "total_report_weight": float(weights.sum())}
        return self

    def predict(self, frame):
        validate_calibration(frame)
        if self.candidate["algorithm"] == "control":
            return self.base.predict(frame)
        values = self.scaler.transform(self.imputer.transform(frame[self.candidate["features"]]))
        predicted = self.model.predict(values).astype(int)
        if self.candidate["target_mode"] == "change_from_prior":
            predicted = predicted+frame["prior_borg"].to_numpy(int)
        return np.asarray([f"Borg {i}" for i in np.clip(predicted, 0, 10)])


def plan(manifest):
    features = core_candidate(manifest)["features"]
    candidates = [{"id": "prior-view-000", "algorithm": "control", "features": features, "feature_set": "incumbent_control"}]
    models = [(shape, alpha, mode) for shape, alpha, mode in
              (([16, 8], 3., "change_from_prior"), ([16, 8], 10., "change_from_prior"), ([16, 8], 30., "change_from_prior"),
               ([8], 10., "change_from_prior"), ([16, 8], 10., "absolute_borg"))]
    for policy in ("prefix", "subsets"):
        for shape, alpha, mode in models:
            for mass in (.1, .3, .6):
                candidates.append({"id": f"prior-view-{len(candidates):03d}", "algorithm": "mlp", "feature_set": "observed_history_views",
                    "features": features, "view_policy": policy, "view_mass": mass, "target_mode": mode,
                    "params": {"hidden_layer_sizes": shape, "solver": "lbfgs", "alpha": alpha, "max_iter": 1000}})
    return candidates


def fingerprint(manifest, view_manifest):
    helpers = ("fatigue_prior_views.py", "fatigue_dynamics_experiment.py", "fatigue_probability.py", "fatigue_warm_sgd.py")
    return {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
            "view_dataset_sha256": view_manifest["dataset_sha256"], "view_provenance_sha256": digest(VIEW_DIRECTORY / "provenance.json"),
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "software_versions": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scikit-learn", "joblib")}}


def select():
    _, train, _, manifest, _ = load_inputs()
    pool, view_manifest = load_views()
    signature = {**fingerprint(manifest, view_manifest), "plan": plan(manifest), "core_candidate": core_candidate(manifest),
                 "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "new_observed_targets": 0, "synthetic_borg_targets": 0, "interpolated_targets": 0,
              "evaluation_denominator": 487, "test_denominator": 179, "minimum_cv_for_new_test_evaluation": .65,
              "input_view_pool_size": len(pool), "evaluation_uses_original_complete_history": True,
              "policy": "Report-balanced alternative observed-history input views are fitting-only. Each actual target retains total weight one. Each outer fold filters all alternative views by original fitting target/person before parsing their labels. Imputation fits only unique canonical fitting rows. Validation and test use their unchanged original queries."}
    if path.exists():
        report = json.loads(path.read_text())
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen prior-view training study changed")
    else:
        path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in signature["plan"]:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted, evidence, convergence = np.empty(len(train), dtype=object), [], 0
        for fit, val in folds:
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise ValueError("Prior-view outer fold leaked participants")
            with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                warnings.simplefilter("always", ConvergenceWarning)
                model = PriorViewBorg(candidate).fit(train.iloc[fit], pool, signature["core_candidate"])
                predicted[val] = model.predict(train.iloc[val])
            convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
            evidence.append({"fit_row_keys": train.iloc[fit]["row_key"].tolist(), "validation_row_keys": train.iloc[val]["row_key"].tolist(), **model.fit_summary})
        if candidate["algorithm"] == "control":
            original = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
            expected = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["id"] == "alternative-023")
            np.testing.assert_array_equal(predicted, expected)
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(),
            "convergence_warnings": convergence, "folds": evidence})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(signature["plan"]) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Observed-prior views {len(report['results'])}/{len(signature['plan'])}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
