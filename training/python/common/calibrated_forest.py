"""Portable imputation + forest + prior-Borg transition, without pickle."""
from __future__ import annotations

import numpy as np

from common.export_classifier import predict_json, predict_proba_json
from common.export_forest import export_random_forest


def export_calibrated_forest(pipeline, candidate, input_contract, validity):
    imputer, classifier = pipeline.steps[0][1], pipeline.steps[-1][1]
    if candidate["algorithm"] not in ("random_forest", "extra_trees") or len(pipeline.steps) != 2:
        raise ValueError("This portable exporter requires a median-imputer forest pipeline")
    indicators = imputer.indicator_.features_.tolist() if imputer.add_indicator else []
    transformed_names = list(candidate["features"]) + ["missing_" + candidate["features"][i] for i in indicators]
    return {"type": "calibrated_forest_json", "version": 1,
            "feature_order": candidate["features"], "target_mode": candidate["target_mode"],
            "native_labels": [f"Borg {i}" for i in range(11)], "input_contract": input_contract,
            "algorithm": candidate["algorithm"], "evaluation_validity": validity,
            "imputer": {"statistics": imputer.statistics_.tolist(), "indicator_features": indicators},
            "forest": export_random_forest(classifier, transformed_names, [str(c) for c in classifier.classes_])}


def transformed_features(payload, features):
    x = np.asarray(features, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(payload["feature_order"]) or np.isinf(x).any():
        raise ValueError("Feature matrix differs from calibrated model contract")
    names = payload["feature_order"]
    prior = x[:, names.index("prior_borg")]
    age = x[:, names.index("prior_age_minutes")]
    contract = payload["input_contract"]
    if (not np.isfinite(prior).all() or not np.isfinite(age).all()
            or np.any(prior != np.rint(prior)) or np.any((prior < 0) | (prior > 10))
            or np.any(age < contract["minimum_prior_age_minutes"])
            or np.any(age > contract["maximum_prior_age_minutes"])):
        raise ValueError("An observed previous Borg aged 1-15 minutes is required; current/future/stale reports cannot be imputed")
    missing = np.isnan(x)
    values = np.where(missing, np.asarray(payload["imputer"]["statistics"]), x)
    return np.column_stack((values, missing[:, payload["imputer"]["indicator_features"]].astype(float))), prior


def predict_calibrated_json(payload, features):
    transformed, previous = transformed_features(payload, features)
    values = predict_json(payload["forest"], transformed).astype(int)
    if payload["target_mode"] == "change_from_prior":
        values = np.clip(values + previous.astype(int), 0, 10)
    return np.asarray([f"Borg {value}" for value in values])


class JsonCalibratedPredictor:
    def __init__(self, payload):
        self.payload = payload

    def predict(self, features):
        return predict_calibrated_json(self.payload, features)
