"""Exploratory nested person-held-out evaluation of end-of-hike RPE.

This follow-up was designed after inspecting the initial HARDMIN benchmark.
It is not an untouched external test, nor a fatigue validation.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import time

import numpy as np
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from evaluate_hardmin_hiking import (
    ROOT, SOURCE_SHA256, bootstrap, get_observations, scores, subject_rows, workbook,
)

OUTPUT = ROOT / "docs/fatigue-trekking-evaluation-2026-10-22/hardmin-nested-results.json"
CANDIDATES = [("constant_median", "raw", None)] + [
    ("ridge", feature_set, alpha)
    for feature_set in ("raw", "pulse_change_and_elapsed") for alpha in (1.0, 10.0, 100.0)
]


def minutes(value: object) -> float:
    if isinstance(value, time):
        return 60 * value.hour + value.minute + value.second / 60
    parts = str(value).strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Unexpected lap-time format: {value!r}")
    hour, minute, second = map(float, parts)
    if hour < 0 or not 0 <= minute < 60 or not 0 <= second < 60:
        raise ValueError("Invalid lap time")
    return 60 * hour + minute + second / 60


def feature_matrices(book, rows: list[dict]) -> dict[str, np.ndarray]:
    timing = {condition: subject_rows(book[f"Performance-{condition}"])
              for condition in ("np", "wp")}
    raw = np.array([row["hr"] for row in rows])
    context = []
    for row in rows:
        baseline, first, second, third = row["hr"]
        laps = timing[row["condition"]][row["person"]][1:4]
        elapsed = sum(minutes(value) for value in laps)
        if not 0 < elapsed < 24 * 60:
            raise ValueError("Invalid elapsed time to third checkpoint")
        context.append([baseline, first, second, third, first - baseline,
                        second - baseline, third - baseline, third - first, elapsed])
    return {"raw": raw, "pulse_change_and_elapsed": np.array(context)}


def predict(candidate: tuple, xtrain, ytrain, xtest) -> np.ndarray:
    kind, _, alpha = candidate
    model = DummyRegressor(strategy="median") if kind == "constant_median" else make_pipeline(
        StandardScaler(), Ridge(alpha=alpha))
    model.fit(xtrain, ytrain)
    return np.clip(model.predict(xtest), 6, 20)


def absolute_uncertainty(rows: list[dict]) -> dict:
    people = sorted({row["person"] for row in rows}, key=int)
    by_person = {person: [row for row in rows if row["person"] == person] for person in people}
    rng = np.random.default_rng(42)
    accuracy, mae = [], []
    for _ in range(10000):
        sample = [row for person in rng.choice(people, len(people), replace=True)
                  for row in by_person[person]]
        errors = [abs(row["observed"] - row["predicted"]) for row in sample]
        accuracy.append(sum(error == 0 for error in errors) / len(errors))
        mae.append(sum(errors) / len(errors))
    return {"unit": "participant", "resamples": 10000, "seed": 42,
            "exact_accuracy_95pct": np.quantile(accuracy, [.025, .975]).tolist(),
            "mae_points_95pct": np.quantile(mae, [.025, .975]).tolist(),
            "scope": "Exploratory percentile intervals of fixed out-of-fold predictions; not all training or source-selection uncertainty"}


def evaluate(rows: list[dict], matrices: dict[str, np.ndarray]) -> dict:
    people = np.array([row["person"] for row in rows])
    y = np.array([row["rpe"] for row in rows])
    predictions = np.zeros(len(rows))
    baseline = np.zeros(len(rows))
    folds = []
    for person in sorted(set(people), key=int):
        train = np.flatnonzero(people != person)
        test = np.flatnonzero(people == person)
        if set(people[train]) & set(people[test]):
            raise ValueError("Outer participant leakage")
        inner = list(GroupKFold(n_splits=4).split(train, y[train], groups=people[train]))
        candidate_scores = []
        for candidate in CANDIDATES:
            feature_set = candidate[1]
            errors = []
            for inner_train, inner_test in inner:
                fit_ids, valid_ids = train[inner_train], train[inner_test]
                if set(people[fit_ids]) & set(people[valid_ids]):
                    raise ValueError("Inner participant leakage")
                pred = predict(candidate, matrices[feature_set][fit_ids], y[fit_ids],
                               matrices[feature_set][valid_ids])
                errors.extend(np.abs(pred - y[valid_ids]).tolist())
            candidate_scores.append(float(np.mean(errors)))
        # Ties prefer the first, simplest candidate. Outer outcomes never select a candidate.
        selected = int(np.argmin(candidate_scores))
        candidate = CANDIDATES[selected]
        predictions[test] = predict(candidate, matrices[candidate[1]][train], y[train],
                                    matrices[candidate[1]][test])
        baseline[test] = np.median(y[train])
        folds.append({"held_out_person": str(person), "selected": list(candidate),
                      "inner_mae": candidate_scores[selected]})
    rounded = np.rint(predictions).astype(int)
    rounded_baseline = np.rint(baseline).astype(int)
    per_visit = [{"person": row["person"], "condition": row["condition"],
                  "observed": int(y[i]), "predicted": int(rounded[i]),
                  "continuous_prediction": float(predictions[i]),
                  "baseline": int(rounded_baseline[i])} for i, row in enumerate(rows)]
    return {"source": "https://doi.org/10.26255/heal.mjhj-gsm4",
            "source_sha256": SOURCE_SHA256,
            "task": "Borg 6-20 exertion reported after hike, predicted at third checkpoint",
            "status": "Exploratory follow-up after initial source evaluation; not an untouched external test or a fatigue detector",
            "protocol": "Outer leave-one-person-out (17); inner 4-fold GroupKFold on training people; selection by continuous MAE; both visits stay together",
            "candidate_pool": [list(c) for c in CANDIDATES],
            "features": {"raw": "HR at start and three checkpoints",
                         "pulse_change_and_elapsed": "Raw HR; checkpoint minus starting HR; third minus first HR; sum of first three lap times. No final lap, endpoint HR, lab measurements or answers as inputs."},
            "people": len(set(people)), "visits": len(rows),
            "selected_counts": dict(Counter(str(f["selected"]) for f in folds)),
            "model": {**scores(y, rounded), "continuous_mae": float(np.mean(abs(y - predictions)))},
            "median_baseline": {**scores(y, rounded_baseline), "continuous_mae": float(np.mean(abs(y - baseline)))},
            "uncertainty_rounded_predictions": bootstrap(per_visit),
            "absolute_uncertainty": absolute_uncertainty(per_visit),
            "folds": folds, "predictions": per_visit}


def main() -> None:
    book = workbook()
    try:
        rows = get_observations(book)
        result = evaluate(rows, feature_matrices(book, rows))
    finally:
        book.close()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("people", "visits", "selected_counts", "model", "median_baseline", "uncertainty_rounded_predictions")}, indent=2))


if __name__ == "__main__":
    main()
