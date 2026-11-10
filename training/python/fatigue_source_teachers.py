"""Source-specific auxiliary predictions without mixing outcome definitions.

External teachers never fit any GeoFatigue target. OxBioZ post-trial RPE stays
in its own teacher, as do original STS and WorkerFatigue Borg responses. All
external participant holdouts remain sealed. Only predicted covariates, not
extra target labels, enter the original walking classifier.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from fatigue_auxiliary_transfer import extra_sources
from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from oxbioz_fatigue import DIRECTORY as OX_DIRECTORY, load as load_ox
from public_sources import digest

DIRECTORY = RESEARCH / "source-specific-transfer-80-v1"
SENSOR_FEATURES = ["hr_last", "hr_history_mean"]
SOURCES = ("worker", "sts", "oxbioz_post_trial")


def external_inputs():
    known, known_splits = extra_sources()
    sources = {}
    for name in ("worker", "sts"):
        allowed = set(known_splits[name]["train_row_keys"])
        data = known[known["row_key"].isin(allowed)].copy()
        data["borg_native"] = data["label"].str.removeprefix("Borg ").astype(float)
        sources[name] = data
    ox, provenance = load_ox()
    fit, held = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(ox, groups=ox["group_key"]))
    if set(ox.iloc[fit]["group_key"]) & set(ox.iloc[held]["group_key"]):
        raise ValueError("OxBioZ participant holdout overlaps fitting")
    sources["oxbioz_post_trial"] = ox.iloc[fit].copy()
    splits = {**known_splits, "oxbioz_post_trial": {"dataset_sha256": provenance["dataset_sha256"],
                "train_row_keys": ox.iloc[fit]["row_key"].tolist(), "test_row_keys": ox.iloc[held]["row_key"].tolist(),
                "train_groups": sorted(set(ox.iloc[fit]["group_key"])), "test_groups": sorted(set(ox.iloc[held]["group_key"]))}}
    for name, frame in sources.items():
        if set(frame["row_key"]) != set(splits[name]["train_row_keys"]) or set(frame["row_key"]) & set(splits[name]["test_row_keys"]):
            raise ValueError("Auxiliary teacher consumes a reserved external report")
    return sources, splits


def fit_teacher(frame, algorithm):
    estimator = {"ridge": lambda: Ridge(alpha=10.), "svr": lambda: SVR(C=10., gamma="scale", epsilon=.1),
                 "random_forest": lambda: RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=3, random_state=42, n_jobs=1)}[algorithm]()
    model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), estimator)
    # All original fractional ratings are continuous targets, with no rounding.
    with threadpool_limits(limits=1):
        model.fit(frame[SENSOR_FEATURES], frame["borg_native"].to_numpy(float))
    return model


def add_teacher_features(frame, teachers):
    output = frame.copy()
    for source, teacher in teachers.items():
        predicted = teacher.predict(frame[SENSOR_FEATURES])
        output[source + "_external_estimate"] = predicted
        output[source + "_estimate_minus_prior"] = predicted - frame["prior_borg"].to_numpy(float)
    return output


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    student_configs = [("logistic", {"C": .1, "max_iter": 3000}),
                       ("mlp", {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 10., "max_iter": 1500}),
                       ("svm", {"C": 10., "gamma": "scale"})]
    recipes = []
    for algorithm in ("control", "ridge", "svr", "random_forest"):
        sets = [("sensor_control", [])] if algorithm == "control" else [
            ("known_sources", ["worker", "sts"]), ("oxbioz_only", ["oxbioz_post_trial"]), ("all_sources", list(SOURCES))]
        for name, sources in sets:
            features = prior + SENSOR_FEATURES if algorithm == "control" else prior + [f for s in sources for f in (s + "_external_estimate", s + "_estimate_minus_prior")]
            for classifier, params in student_configs:
                recipes.append({"id": f"source-teachers-{len(recipes):03d}", "teacher_algorithm": algorithm,
                                "feature_set": name, "features": features, "algorithm": classifier,
                                "params": params, "target_mode": "change_from_prior"})
    return recipes


def select():
    frame, train, _, manifest, _ = load_inputs()
    sources, splits = external_inputs()
    recipes = plan(manifest)
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
                 "classifier_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py")),
                 "external_loader_code_sha256": digest(Path(__file__).with_name("fatigue_auxiliary_transfer.py")),
                 "oxbioz_provenance_sha256": digest(OX_DIRECTORY / "provenance.json"),
                 "plan": recipes, "external_splits": splits, "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "external_test_used": False, "teachers_use_geofatigue_labels": False,
              "previous_benchmark_results_are_published": True, "original_momentary_target_merge": False,
              "fitting_reports_per_source": {k: len(v) for k, v in sources.items()},
              "note": "Post-trial OxBioZ outcomes are kept in a separate source-only regressor. Its predictions are auxiliary covariates, never observed momentary Borg or extra evaluation cases. HR units match bpm, but windows, alignment and outcome contexts differ across studies."}
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if any(previous.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve frozen source-specific transfer before changing its inputs")
        report = previous
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for teacher_algorithm in ("control", "ridge", "svr", "random_forest"):
        candidates = [c for c in recipes if c["teacher_algorithm"] == teacher_algorithm]
        if all(any(r["candidate"] == c for r in report["results"]) for c in candidates):
            continue
        if teacher_algorithm == "control":
            transformed = frame
        else:
            teachers = {name: fit_teacher(data, teacher_algorithm) for name, data in sources.items()}
            joblib.dump(teachers, DIRECTORY / (teacher_algorithm + "-teachers.joblib"))
            transformed = add_teacher_features(frame, teachers)
        targets = transformed.loc[train.index]
        for candidate in candidates:
            if any(r["candidate"] == candidate for r in report["results"]):
                continue
            predictions = np.empty(len(train), dtype=object)
            for fit, val in folds:
                if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                    raise ValueError("Walking classifier leaked validation participants")
                with threadpool_limits(limits=1):
                    model = DynamicsClassifier(candidate).fit(targets.iloc[fit])
                    predictions[val] = model.predict(targets.iloc[val])
            scores = [float(accuracy_score(train.iloc[val]["label"], predictions[val])) for _, val in folds]
            report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                      "pooled_oof_accuracy": float(accuracy_score(train["label"], predictions)), "oof_predictions": predictions.tolist()})
            best = max(report["results"], key=lambda r: r["accuracy_mean"])
            report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                          status="complete" if len(report["results"]) == len(recipes) else "running")
            path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            print(f"Source-specific transfer {len(report['results'])}/{len(recipes)}: current CV={np.mean(scores):.6f}, best CV={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
