"""Portable median imputation, scaling and calibrated neural-network inference."""
import numpy as np
from sklearn.pipeline import Pipeline

from common.calibrated_forest import transformed_features
from common.export_classifier import export_classifier, predict_proba_json


def export_calibrated_network(trained, validity, contract):
    candidate = trained.candidate
    if candidate["algorithm"] != "mlp":
        raise ValueError("A fitted calibrated MLP is required")
    imputer, scaler, network = [step[1] for step in trained.model.steps]
    indicators = imputer.indicator_.features_.tolist()
    names = list(candidate["features"]) + ["missing_" + candidate["features"][i] for i in indicators]
    scaled = Pipeline([("scale", scaler), ("classifier", network)])
    classifier = export_classifier(scaled, names, "mlp", validity)
    return {"type": "calibrated_classifier_json", "version": 1, "algorithm": "mlp",
            "feature_order": candidate["features"], "target_mode": candidate["target_mode"],
            "input_contract": contract, "evaluation_validity": validity,
            "native_labels": [f"Borg {i}" for i in range(11)],
            "imputer": {"statistics": imputer.statistics_.tolist(), "indicator_features": indicators},
            "classifier": classifier}


def predict_head_proba(payload, features):
    transformed, _ = transformed_features(payload, features)
    return predict_proba_json(payload["classifier"], transformed)


def predict_calibrated_network(payload, features):
    transformed, prior = transformed_features(payload, features)
    probabilities = predict_proba_json(payload["classifier"], transformed)
    values = np.asarray(payload["classifier"]["classes"], dtype=int)[probabilities.argmax(axis=1)]
    if payload["target_mode"] == "change_from_prior":
        values = np.clip(values + prior.astype(int), 0, 10)
    return np.asarray([f"Borg {value}" for value in values])
