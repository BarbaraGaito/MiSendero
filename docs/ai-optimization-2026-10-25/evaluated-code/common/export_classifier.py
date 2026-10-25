"""Plain JSON research artifacts for forests, scaled linear models and MLPs.

No pickle loading is required to audit predictions. These files are not bundled
into the mobile application and never grant deployment approval.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit, softmax
from sklearn.pipeline import Pipeline

from common.export_forest import export_random_forest


def export_classifier(estimator, features, algorithm, validity):
    metadata = {"algorithm": algorithm, "evaluation_validity": validity}
    if algorithm in ("random_forest", "extra_trees"):
        return export_random_forest(estimator, features, list(estimator.classes_), metadata)
    if not isinstance(estimator, Pipeline):
        raise ValueError("Scaled classifier pipeline required")
    scaler, classifier = estimator.named_steps["scale"], estimator.named_steps["classifier"]
    payload = {"type": "scaled_classifier_json", "version": 1,
               "feature_order": list(features), "classes": list(estimator.classes_), **metadata,
               "scaler": {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}}
    if algorithm == "mlp":
        payload["network"] = {"coefs": [v.tolist() for v in classifier.coefs_],
                              "intercepts": [v.tolist() for v in classifier.intercepts_],
                              "activation": classifier.activation, "out_activation": classifier.out_activation_}
    elif algorithm in ("sgd", "logistic_regression"):
        payload["linear"] = {"coef": classifier.coef_.tolist(), "intercept": classifier.intercept_.tolist(),
                             "multiclass": "ovr" if algorithm == "sgd" else "multinomial"}
    else:
        raise ValueError(f"Unsupported classifier export: {algorithm}")
    return payload


def predict_proba_json(payload, features):
    x = np.asarray(features, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(payload["feature_order"]) or not np.isfinite(x).all():
        raise ValueError("Finite feature matrix matching exported feature order required")
    if payload["type"] == "random_forest_json":
        # sklearn trees compare float32 inputs against double thresholds.
        x = x.astype(np.float32)
        total = np.zeros((len(x), len(payload["classes"])))
        for tree in payload["trees"]:
            for row_index, row in enumerate(x):
                node = 0
                while tree["left"][node] != -1:
                    node = tree["left"][node] if float(row[tree["feature"][node]]) <= tree["threshold"][node] else tree["right"][node]
                total[row_index] += tree["value"][node]
        return total / len(payload["trees"])
    x = (x - payload["scaler"]["mean"]) / payload["scaler"]["scale"]
    if "linear" in payload:
        linear = payload["linear"]
        scores = x @ np.asarray(linear["coef"]).T + linear["intercept"]
        if scores.shape[1] == 1:
            p = expit(scores[:, 0])
            return np.column_stack((1 - p, p))
        if linear["multiclass"] == "multinomial":
            return softmax(scores, axis=1)
        probabilities = expit(scores)
        return probabilities / probabilities.sum(axis=1, keepdims=True)
    network = payload["network"]
    activations = {"relu": lambda a: np.maximum(a, 0), "tanh": np.tanh,
                   "logistic": expit, "identity": lambda a: a, "softmax": lambda a: softmax(a, axis=1)}
    for i, (weights, intercepts) in enumerate(zip(network["coefs"], network["intercepts"])):
        x = x @ np.asarray(weights) + intercepts
        activation = network["out_activation"] if i == len(network["coefs"]) - 1 else network["activation"]
        x = activations[activation](x)
    return np.column_stack((1 - x[:, 0], x[:, 0])) if x.shape[1] == 1 else x


def predict_json(payload, features):
    return np.asarray(payload["classes"])[predict_proba_json(payload, features).argmax(axis=1)]
