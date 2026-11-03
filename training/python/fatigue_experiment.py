"""Accuracy-oriented fatigue research with participant-disjoint training CV.

The original 179-response test is not evaluated by this search command. Native
Borg classes and the complete original active-task cohort remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from fatigue_features import RESEARCH
from public_sources import OUTPUT, digest


class EncodedXGBClassifier(ClassifierMixin, BaseEstimator):
    def __init__(self, config=None):
        self.config = config

    def fit(self, x, y):
        from xgboost import XGBClassifier
        self.classes_, encoded = np.unique(y, return_inverse=True)
        self.classifier_ = XGBClassifier(**self.config, random_state=42, n_jobs=1)
        self.classifier_.fit(x, encoded)
        return self

    def predict(self, x):
        return self.classes_[self.classifier_.predict(x).astype(int)]

    def predict_proba(self, x):
        return self.classifier_.predict_proba(x)


def plan(features):
    sets = {
        "original": ["hr_last", "elapsed_minutes"],
        "cardiovascular": [c for c in features if c.startswith(("hr_", "prv_", "respiration_")) or c == "elapsed_minutes"],
        "normalized": [c for c in features if c.endswith(("delta_baseline", "ratio_baseline", "recent_slope", "history_std")) or c in ("elapsed_minutes", "cumulative_active_minutes", "task_order", "terrain_stairs", "terrain_ramp", "terrain_flat_trail")],
        "all_sensors_context": features,
    }
    algorithms = [
        ("random_forest", {"n_estimators": 200, "min_samples_leaf": 2, "max_depth": None, "max_features": "sqrt"}),
        ("random_forest", {"n_estimators": 200, "min_samples_leaf": 8, "max_depth": None, "max_features": 1.}),
        ("extra_trees", {"n_estimators": 200, "min_samples_leaf": 2, "max_depth": None, "max_features": 0.7}),
        ("extra_trees", {"n_estimators": 200, "min_samples_leaf": 8, "max_depth": None, "max_features": 1.}),
        *[("xgboost", {"n_estimators": 300, "max_depth": depth, "learning_rate": 0.05,
                        "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 3, "reg_lambda": 5}) for depth in (2, 4, 6)],
        *[("hist_gradient_boosting", {"max_iter": 250, "max_leaf_nodes": leaves, "learning_rate": 0.05,
                                       "min_samples_leaf": 10, "l2_regularization": 5, "early_stopping": False}) for leaves in (7, 15)],
        ("svm", {"C": 1., "gamma": "scale"}), ("svm", {"C": 10., "gamma": "scale"}),
        ("svm", {"C": 100., "gamma": 0.01}),
        ("knn", {"n_neighbors": 7, "weights": "distance"}),
        ("knn", {"n_neighbors": 21, "weights": "distance"}),
        ("mlp", {"hidden_layer_sizes": [32, 16], "alpha": 1., "solver": "lbfgs", "max_iter": 1000}),
        ("mlp", {"hidden_layer_sizes": [64, 32], "alpha": 1., "solver": "adam", "max_iter": 1000}),
    ]
    return [{"id": f"multisensor-{i:03d}", "feature_set": name, "features": cols,
             "algorithm": algorithm, "params": params}
            for i, (name, cols, algorithm, params) in enumerate(
                (name, cols, algorithm, params) for name, cols in sets.items() for algorithm, params in algorithms)]


def estimator_for(candidate):
    algorithm, params = candidate["algorithm"], candidate["params"]
    if algorithm == "random_forest":
        model = RandomForestClassifier(**params, random_state=42, n_jobs=1)
    elif algorithm == "extra_trees":
        model = ExtraTreesClassifier(**params, random_state=42, n_jobs=1)
    elif algorithm == "hist_gradient_boosting":
        model = HistGradientBoostingClassifier(**params, random_state=42)
    elif algorithm == "xgboost":
        model = EncodedXGBClassifier(params)
    elif algorithm == "svm":
        model = SVC(**params, random_state=42)
    elif algorithm == "knn":
        model = KNeighborsClassifier(**params)
    elif algorithm == "mlp":
        model = MLPClassifier(**params, early_stopping=False, random_state=42)
    else:
        raise ValueError(f"Unknown research algorithm: {algorithm}")
    preprocessing = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)]
    if algorithm in ("svm", "knn", "mlp"):
        preprocessing.append(StandardScaler())
    return make_pipeline(*preprocessing, model)


def load_frame(directory):
    manifest = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if digest(directory / "dataset.csv") != manifest["dataset_sha256"]:
        raise ValueError("Research measurements changed after feature preparation")
    if digest(Path(__file__).with_name("fatigue_features.py")) != manifest["feature_code_sha256"]:
        raise ValueError("Feature code changed: rebuild causal features first")
    canonical = OUTPUT / "fatigue"
    if digest(canonical / "dataset.csv") != manifest["canonical_dataset_sha256"] or digest(canonical / "provenance.json") != manifest["canonical_provenance_sha256"]:
        raise ValueError("Canonical dataset or lineage changed")
    frame = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
    frame["row_key"] = [row["row_key"] for row in manifest["lineage"]]
    frame["group_key"] = [row["group_key"] for row in manifest["lineage"]]
    original = json.loads((canonical / "metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    training = frame[frame["row_key"].isin(original["train_row_keys"])].copy()
    if set(training["group_key"]) & set(original["test_groups"]) or len(training) != len(original["train_row_keys"]):
        raise ValueError("Research split changed or leaks held-out participants")
    return training, manifest


def cv_candidate(frame, candidate):
    x, y, groups = frame[candidate["features"]], frame["label"], frame["group_key"]
    labels = sorted(y.unique())
    predictions = np.empty(len(frame), dtype=object)
    folds, convergence = [], 0
    for train, validation in GroupKFold(n_splits=5).split(x, y, groups):
        if set(groups.iloc[train]) & set(groups.iloc[validation]):
            raise AssertionError("Participant leakage")
        clf = estimator_for(candidate)
        with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
            warnings.simplefilter("always", ConvergenceWarning)
            clf.fit(x.iloc[train], y.iloc[train])
            predicted = clf.predict(x.iloc[validation])
        convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
        predictions[validation] = predicted
        folds.append({"train_groups": sorted(set(groups.iloc[train])), "validation_groups": sorted(set(groups.iloc[validation])),
                      "accuracy": float(accuracy_score(y.iloc[validation], predicted)),
                      "f1_macro": float(f1_score(y.iloc[validation], predicted, labels=labels, average="macro", zero_division=0))})
    return {"accuracy_mean": float(np.mean([f["accuracy"] for f in folds])),
            "accuracy_std": float(np.std([f["accuracy"] for f in folds])),
            "pooled_oof_accuracy": float(accuracy_score(y, predictions)),
            "f1_macro_mean": float(np.mean([f["f1_macro"] for f in folds])),
            "folds": folds, "oof_predictions": predictions.tolist(), "convergence_warnings": convergence}


def search(directory, *, limit=None):
    frame, manifest = load_frame(directory)
    candidates = plan(manifest["features"])
    fingerprint = hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest()
    report_path = directory / "selection-v1.json"
    report = {"version": 1, "objective": "exact_Borg_accuracy", "target_accuracy": 0.6,
              "test_evaluated": False, "seed": 42, "plan": candidates, "plan_sha256": fingerprint,
              "dataset_sha256": manifest["dataset_sha256"], "experiment_code_sha256": digest(Path(__file__)),
              "train_row_keys": frame["row_key"].tolist(), "train_groups": sorted(set(frame["group_key"])),
              "status": "running", "results": []}
    if report_path.exists():
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        for key in ("dataset_sha256", "plan_sha256", "experiment_code_sha256", "train_row_keys"):
            if existing[key] != report[key]:
                raise ValueError("Research plan/code/data changed; archive the previous report before restarting")
        report = existing
    done = {r["candidate"]["id"] for r in report["results"]}
    for candidate in candidates[:limit] if limit else candidates:
        if candidate["id"] in done:
            continue
        cv = cv_candidate(frame, candidate)
        report["results"].append({"candidate": candidate, "cv": cv})
        winner = max(report["results"], key=lambda r: r["cv"]["accuracy_mean"])
        report["winner_id"] = winner["candidate"]["id"]
        report["best_cv_accuracy"] = winner["cv"]["accuracy_mean"]
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']}: CV accuracy={cv['accuracy_mean']:.4f}; best={report['best_cv_accuracy']:.4f}", flush=True)
    report["status"] = "complete" if len(report["results"]) == len(candidates) else "partial"
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=RESEARCH / "multisensor-v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    search(args.directory, limit=args.limit)


if __name__ == "__main__":
    main()
