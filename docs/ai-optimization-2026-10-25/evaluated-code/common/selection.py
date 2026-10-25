"""Reproducible train-only search for small, grouped tabular datasets.

The candidate list is fixed before any holdout predictions. Scaling and class
weights are fitted again inside each fold. Neural nets never reserve random
rows for early stopping (that would split a participant across partitions).
"""
from __future__ import annotations

import hashlib
import json
import warnings

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold, ParameterSampler
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from threadpoolctl import threadpool_limits

SEED = 42
SEARCH_VERSION = 1


def candidate_plan():
    # Keep the exact four previous configurations as eligible incumbents.
    plan = [{"algorithm": "random_forest", "params": {
        "n_estimators": 150, "max_depth": depth, "min_samples_leaf": leaf,
        "class_weight": "balanced", "max_features": "sqrt"}, "legacy": True}
        for depth in (4, 8) for leaf in (2, 5)]
    space = {"max_depth": [3, 5, 8, 12, None], "min_samples_leaf": [1, 2, 4, 8],
             "max_features": ["sqrt", 0.7, 1.0], "class_weight": [None, "balanced"]}
    for algorithm in ("random_forest", "extra_trees"):
        for params in ParameterSampler(space, n_iter=24, random_state=SEED):
            plan.append({"algorithm": algorithm, "params": {"n_estimators": 150, **params}})
    for c in (0.01, 0.1, 1.0, 10.0):
        plan.append({"algorithm": "logistic_regression", "params": {"C": c}})
    for alpha in (0.0001, 0.001, 0.01, 0.1):
        for average in (False, True):
            plan.append({"algorithm": "sgd", "params": {"alpha": alpha, "average": average}})
    for solver in ("lbfgs", "adam", "sgd"):
        for hidden in ([8], [16, 8]):
            for alpha in (0.01, 1.0):
                plan.append({"algorithm": "mlp", "params": {
                    "solver": solver, "hidden_layer_sizes": hidden, "alpha": alpha}})
    for i, item in enumerate(plan):
        item["id"] = f"candidate-{i:03d}"
    return plan


def plan_sha256(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def make_estimator(candidate):
    algorithm, params = candidate["algorithm"], candidate["params"]
    if algorithm in ("random_forest", "extra_trees"):
        cls = RandomForestClassifier if algorithm == "random_forest" else ExtraTreesClassifier
        return cls(**params, random_state=SEED, n_jobs=1)
    if algorithm == "logistic_regression":
        classifier = LogisticRegression(**params, class_weight="balanced", max_iter=2000, random_state=SEED)
    elif algorithm == "sgd":
        classifier = SGDClassifier(**params, loss="log_loss", class_weight="balanced",
                                   max_iter=3000, tol=1e-5, early_stopping=False, random_state=SEED)
    elif algorithm == "mlp":
        classifier = MLPClassifier(**params, max_iter=1000, early_stopping=False,
                                   learning_rate_init=0.01, random_state=SEED)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    return Pipeline([("scale", StandardScaler()), ("classifier", classifier)])


def fit_candidate(estimator, candidate, features, labels):
    # Weight only observed training rows, without duplicating or synthesizing.
    kwargs = {}
    if candidate["algorithm"] == "mlp":
        kwargs["classifier__sample_weight"] = compute_sample_weight("balanced", labels)
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
        warnings.simplefilter("always", ConvergenceWarning)
        estimator.fit(features, np.asarray(labels, dtype=str), **kwargs)
    return sum(issubclass(w.category, ConvergenceWarning) for w in caught)


def cross_validate_candidate(features, labels, groups, candidate):
    if not (len(features) == len(labels) == len(groups)) or groups.nunique() < 2:
        raise ValueError("Insufficient or mismatched grouped training observations")
    folds, scores, accuracies, convergences = [], [], [], 0
    vocabulary = sorted(labels.unique())  # Train labels only, fixed across folds.
    oof = np.empty(len(labels), dtype=object)
    for train, validation in GroupKFold(n_splits=min(5, groups.nunique())).split(features, labels, groups):
        if set(groups.iloc[train]) & set(groups.iloc[validation]):
            raise AssertionError("CV group leakage")
        estimator = make_estimator(candidate)
        convergences += fit_candidate(estimator, candidate, features.iloc[train], labels.iloc[train])
        prediction = estimator.predict(features.iloc[validation])
        oof[validation] = prediction
        score = float(f1_score(labels.iloc[validation], prediction, labels=vocabulary,
                               average="macro", zero_division=0))
        scores.append(score)
        accuracies.append(float(accuracy_score(labels.iloc[validation], prediction)))
        folds.append({"train_groups": sorted(set(groups.iloc[train])),
                      "validation_groups": sorted(set(groups.iloc[validation]))})
    return {"folds": len(folds), "f1_macro_mean": float(np.mean(scores)),
            "f1_macro_std": float(np.std(scores)), "f1_macro_by_fold": scores,
            "accuracy_mean": float(np.mean(accuracies)), "accuracy_std": float(np.std(accuracies)),
            "convergence_warnings": convergences, "partitions": folds,
            "oof_predictions": oof.tolist()}


def select_candidate(features, labels, groups, progress=None):
    plan = candidate_plan()
    results = []
    for candidate in plan:
        cv = cross_validate_candidate(features, labels, groups, candidate)
        results.append({"candidate": candidate, "cv": cv})
        if progress and (len(results) % 10 == 0 or len(results) == len(plan)):
            progress(len(results), len(plan), max(r["cv"]["f1_macro_mean"] for r in results))
    # Stable first-candidate tie break; holdout accuracy never enters selection.
    winner = max(results, key=lambda r: r["cv"]["f1_macro_mean"])
    legacy = max((r for r in results if r["candidate"].get("legacy")),
                 key=lambda r: r["cv"]["f1_macro_mean"])
    report = {"version": SEARCH_VERSION, "seed": SEED, "objective": "grouped_training_cv_f1_macro_mean",
              "candidate_plan_sha256": plan_sha256(plan), "candidate_count": len(plan),
              "test_used_for_selection": False, "scaling_fit_within_fold": True,
              "early_stopping": False, "winner_id": winner["candidate"]["id"],
              "legacy_winner_id": legacy["candidate"]["id"],
              "cv_gain_over_legacy": winner["cv"]["f1_macro_mean"] - legacy["cv"]["f1_macro_mean"],
              "interpretation": "Selection CV is optimized and is not an unbiased generalization estimate; use the fixed holdout for descriptive comparison.",
              "results": results}
    return winner["candidate"], winner["cv"], report
