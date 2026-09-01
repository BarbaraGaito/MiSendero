"""Cross-validated hyperparameter selection for the small-data RandomForest trainers.

The three `train.py` scripts used to hardcode `max_depth=4, min_samples_leaf=2,
n_estimators=200` as a guess. This runs a small, fixed grid through stratified
CV on the *real* training fold only (never the augmented rows, so a synthetic
point derived from a real row never leaks into a different CV split than that
row) and keeps whichever config has the best mean macro-F1, so the forest's
depth and leaf size reflect what the real data supports.
"""

from __future__ import annotations

from collections import Counter
from itertools import product
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score

PARAM_GRID: dict[str, list[Any]] = {
    "n_estimators": [150, 200, 300],
    "max_depth": [3, 4, 5, 6],
    "min_samples_leaf": [1, 2, 3],
}

# Falls back to these (the pipeline's original hardcoded values) when there
# are too few real rows per class for cross-validation to mean anything.
_FALLBACK_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "max_depth": 4,
    "min_samples_leaf": 2,
}


def select_hyperparameters(
    features: pd.DataFrame,
    labels: pd.Series,
    random_state: int = 42,
) -> dict[str, Any]:
    """Pick the grid entry with the best mean CV macro-F1 on real (features, labels).

    Returns a dict of the winning `n_estimators`/`max_depth`/`min_samples_leaf`,
    plus `"selection_method"` (`"cross_validated"` or `"fallback_too_few_rows"`)
    and `"cv_folds"`/`"cv_f1_macro_mean"` so the choice is auditable from
    `metrics.json` rather than a silent constant.
    """
    label_counts = Counter(labels)
    splits = min(5, min(label_counts.values())) if label_counts else 0

    if splits < 2:
        return {
            **_FALLBACK_PARAMS,
            "selection_method": "fallback_too_few_rows",
            "cv_folds": None,
            "cv_f1_macro_mean": None,
        }

    cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=random_state)

    best_params = dict(_FALLBACK_PARAMS)
    best_score = float("-inf")
    for n_estimators, max_depth, min_samples_leaf in product(
        PARAM_GRID["n_estimators"], PARAM_GRID["max_depth"], PARAM_GRID["min_samples_leaf"]
    ):
        candidate = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            class_weight="balanced",
            random_state=random_state,
        )
        scores = cross_val_score(candidate, features, labels, cv=cv, scoring="f1_macro")
        mean_score = float(scores.mean())
        if mean_score > best_score:
            best_score = mean_score
            best_params = {
                "n_estimators": n_estimators,
                "max_depth": max_depth,
                "min_samples_leaf": min_samples_leaf,
            }

    return {
        **best_params,
        "selection_method": "cross_validated",
        "cv_folds": int(splits),
        "cv_f1_macro_mean": float(best_score),
    }
