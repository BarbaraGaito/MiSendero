"""Train-only comparison of participant-balanced losses for exact Borg.

The 86-response pilot participant is otherwise much more influential than
participants with 11-20 reports. Weighting changes fitting loss only: every
original validation/test response and native label retains unit evaluation
weight. No participant identifier is a predictor and no row is resampled.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_dynamics_experiment import plan as dynamics_plan
from fatigue_features import RESEARCH
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = RESEARCH / "participant-weighting-80-v1"


def fitting_weights(groups, power):
    if not np.isfinite(power) or power < 0:
        raise ValueError("Nonnegative finite weighting strength required")
    values = np.asarray(groups)
    if len(values) == 0:
        raise ValueError("Observed fitting participants required")
    _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    weights = counts[inverse].astype(float) ** (-power)
    return weights / weights.mean()


class ParticipantWeightedBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame):
        validate_calibration(frame)
        c = self.candidate
        classifier = MLPClassifier(hidden_layer_sizes=(16, 8), solver="lbfgs", alpha=c["alpha"], max_iter=1000,
                                   random_state=42, early_stopping=False)
        self.model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), classifier)
        target = frame["label"].str.removeprefix("Borg ").astype(int) - frame["prior_borg"].astype(int)
        self.fitting_group_counts = {str(k): int(v) for k, v in frame.groupby("group_key").size().items()}
        self.fitting_weight_sum = float(len(frame))
        extra = {} if c["participant_weight_power"] == 0 else {
            "mlpclassifier__sample_weight": fitting_weights(frame["group_key"], c["participant_weight_power"])}
        self.model.fit(frame[c["features"]], target.astype(str), **extra)
        return self

    def predict(self, frame):
        validate_calibration(frame)
        delta = self.model.predict(frame[self.candidate["features"]]).astype(int)
        return np.asarray([f"Borg {value}" for value in np.clip(delta + frame["prior_borg"].to_numpy(int), 0, 10)])


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    compact = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    candidates = []
    for name, features in (("prior_context", prior), ("compact_dynamics", compact)):
        for alpha in (1., 10., 100.):
            for power in (0., .5, 1., 2.):
                candidates.append({"id": f"participant-weight-{len(candidates):03d}", "features": features,
                                   "feature_set": name, "alpha": alpha, "participant_weight_power": power,
                                   "hidden_layer_sizes": [16, 8], "solver": "lbfgs", "max_iter": 1000,
                                   "target_mode": "change_from_prior", "random_state": 42})
    return candidates


def select():
    _, train, _, manifest, _ = load_inputs()
    candidates = plan(manifest)
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
                 "plan": candidates, "train_row_keys": train["row_key"].tolist(),
                 "dynamics_plan_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py"))}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "synthetic_rows": 0, "resampled_rows": 0, "evaluation_weighting": "unit_weight_per_original_response"}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the frozen participant-weighting study before changing inputs")
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in candidates:
        if any(row["candidate"] == candidate for row in report["results"]):
            continue
        predicted = np.empty(len(train), dtype=object)
        evidence = []
        for fit, val in folds:
            fitting_groups, validation_groups = set(train.iloc[fit]["group_key"]), set(train.iloc[val]["group_key"])
            if fitting_groups & validation_groups:
                raise ValueError("Participant balancing leaked validation people")
            with threadpool_limits(limits=1):
                model = ParticipantWeightedBorg(candidate).fit(train.iloc[fit])
            predicted[val] = model.predict(train.iloc[val])
            evidence.append({"fit_group_counts": model.fitting_group_counts, "fit_weight_sum": model.fitting_weight_sum,
                             "validation_groups": sorted(validation_groups)})
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)),
                                  "oof_predictions": predicted.tolist(), "folds": evidence})
        best = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"Participant-weighted fitting {len(report['results'])}/{len(candidates)}: unit-weight exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)
    control = next(row for row in report["results"] if row["candidate"]["feature_set"] == "prior_context"
                   and row["candidate"]["alpha"] == 10. and row["candidate"]["participant_weight_power"] == 0.)
    incumbent = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text(encoding="utf-8"))
    original = next(row for row in incumbent["results"] if row["candidate"]["id"] == "alternative-023")
    np.testing.assert_array_equal(control["oof_predictions"], original["oof_predictions"])
    print("Unweighted control exactly reproduces all 487 incumbent OOF decisions", flush=True)


if __name__ == "__main__":
    select()
