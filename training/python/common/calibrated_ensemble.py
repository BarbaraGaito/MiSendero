"""Aggregate native Borg predictions; no tolerance matches or label bands."""
import numpy as np

from common.calibrated_forest import predict_calibrated_json


def aggregate_borg(values, method):
    values = np.asarray(values, dtype=int)
    if values.ndim != 2 or np.any((values < 0) | (values > 10)):
        raise ValueError("An ensemble requires exact integer Borg predictions")
    if method == "rounded_mean":
        return np.rint(values.mean(axis=0)).astype(int)
    if method == "rounded_median":
        return np.rint(np.median(values, axis=0)).astype(int)
    if method != "majority_vote":
        raise ValueError("Unknown calibrated ensemble aggregation")
    scores = np.zeros((values.shape[1], 11), dtype=int)
    for member in values:
        scores[np.arange(len(member)), member] += 1
    maximum = scores.max(axis=1)
    result = np.full(values.shape[1], -1, dtype=int)
    # Members are ordered by training CV accuracy; the first agreeing member
    # resolves ties without consulting the current or held-out response.
    for member in values:
        choose = (result < 0) & (scores[np.arange(len(member)), member] == maximum)
        result[choose] = member[choose]
    return result


def predict_ensemble_json(payload, frame):
    values = []
    for member in payload["members"]:
        prediction = predict_calibrated_json(member, frame[member["feature_order"]])
        values.append([int(label.removeprefix("Borg ")) for label in prediction])
    return np.asarray([f"Borg {value}" for value in aggregate_borg(values, payload["aggregation"])])
