"""Nested grouped transfer using real WorkerFatigue and STS Borg responses.

A sensor-only continuous teacher uses actual native Borg, including real 0.5
STS ratings. Its prediction is a feature for a prior-Borg classifier on the
original walking task. Inner cross-fitting prevents a target label entering
its own teacher feature. Validation denominators never include extra sources.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_dynamics_experiment import DynamicsClassifier, plan as dynamics_plan
from fatigue_features import RESEARCH
from fatigue_transfer import load_external as load_worker
from public_sources import digest

DIRECTORY = RESEARCH / "auxiliary-transfer-80-v1"
SENSOR_FEATURES = ["hr_last", "hr_history_mean", "elapsed_minutes"]


def extra_sources():
    worker, worker_split = load_worker()
    sts_directory = RESEARCH / "sts-v1"
    manifest = json.loads((sts_directory / "provenance.json").read_text(encoding="utf-8"))
    if digest(sts_directory / "dataset.csv") != manifest["dataset_sha256"] or digest(Path(__file__).with_name("sts_fatigue.py")) != manifest["feature_code_sha256"]:
        raise ValueError("Audited sparse STS responses changed")
    sts = pd.read_csv(sts_directory / "dataset.csv", dtype={"label": str})
    sts = pd.concat([sts, pd.DataFrame({"row_key": [r["row_key"] for r in manifest["lineage"]], "group_key": [r["group_key"] for r in manifest["lineage"]]})], axis=1)
    train, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(sts, groups=sts["group_key"]))
    if set(sts.iloc[train]["group_key"]) & set(sts.iloc[test]["group_key"]):
        raise AssertionError("STS external holdout leakage")
    split = {"dataset_sha256": manifest["dataset_sha256"], "train_row_keys": sts.iloc[train]["row_key"].tolist(),
             "test_row_keys": sts.iloc[test]["row_key"].tolist(), "train_groups": sorted(set(sts.iloc[train]["group_key"])),
             "test_groups": sorted(set(sts.iloc[test]["group_key"]))}
    external = pd.concat([worker[SENSOR_FEATURES + ["label", "row_key", "group_key"]], sts.iloc[train][SENSOR_FEATURES + ["label", "row_key", "group_key"]]], ignore_index=True)
    return external, {"worker": worker_split, "sts": split}


def teacher_plan():
    configs = [("random_forest", {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 8}),
               ("hist_gradient_boosting", {"max_iter": 150, "max_leaf_nodes": 7, "learning_rate": .05, "l2_regularization": 10}),
               ("svr", {"C": 10., "gamma": "scale", "epsilon": .1})]
    return [{"id": f"teacher-{i:03d}", "algorithm": algorithm, "params": params, "external_weight": weight}
            for i, (algorithm, params, weight) in enumerate((a, p, w) for a, p in configs for w in (0., .25, 1.))]


def fit_teacher(target_train, external, config):
    data = target_train[SENSOR_FEATURES + ["label", "group_key"]]
    weights = np.ones(len(data))
    if config["external_weight"] > 0:
        if set(data["group_key"]) & set(external["group_key"]):
            raise AssertionError("Source participant namespace collision")
        data = pd.concat([data, external[SENSOR_FEATURES + ["label", "group_key"]]], ignore_index=True)
        weights = np.r_[weights, np.full(len(external), config["external_weight"])]
    if config["algorithm"] == "random_forest":
        estimator = RandomForestRegressor(**config["params"], random_state=42, n_jobs=1)
    elif config["algorithm"] == "hist_gradient_boosting":
        estimator = HistGradientBoostingRegressor(**config["params"], random_state=42)
    else:
        estimator = SVR(**config["params"])
    pipeline = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), estimator)
    # Native fractional Borg cells remain real regression targets. They are
    # neither rounded nor converted into another supervision scale.
    target = data["label"].str.removeprefix("Borg ").astype(float)
    with threadpool_limits(limits=1):
        pipeline.fit(data[SENSOR_FEATURES], target, **{pipeline.steps[-1][0] + "__sample_weight": weights})
    return pipeline


def add_teacher(frame, scores):
    return frame.assign(teacher_expected_borg=np.clip(scores, 0, 10),
                        teacher_difference_from_prior=np.clip(scores, 0, 10) - frame["prior_borg"].to_numpy(float))


def student_plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    compact = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    candidates = []
    for name, features in (("prior_teacher", prior), ("dynamics_teacher", compact)):
        for algorithm, params in (("logistic", {"C": .1, "max_iter": 3000}),
                                  ("mlp", {"hidden_layer_sizes": [8], "solver": "lbfgs", "alpha": 10., "max_iter": 1500}),
                                  ("mlp", {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 10., "max_iter": 1500})):
            candidates.append({"id": f"student-{len(candidates):03d}", "feature_set": name,
                               "features": features + ["teacher_expected_borg", "teacher_difference_from_prior"],
                               "algorithm": algorithm, "params": params, "target_mode": "change_from_prior"})
    return candidates


def select():
    _, train, _, manifest, _ = load_inputs()
    external, splits = extra_sources()
    teachers, students = teacher_plan(), student_plan(manifest)
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
                 "classifier_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py")),
                 "external_splits": splits, "teachers": teachers, "students": students, "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "objective": "exact_native_Borg_accuracy_on_original_487_training_responses", "test_used_for_selection": False,
              "external_test_used": False, "nested_teacher_cross_fitting": True, "previous_benchmark_results_are_published": True,
              "harmonization": "HR bpm and elapsed minutes only. Study measurement methods differ (chest instantaneous vs wrist minute means); no HRV, acceleration-site or Borg-scale conversion. Study-specific windows are not made into equivalent recent-window features."}
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if any(previous[k] != v for k, v in signature.items()):
            raise ValueError("Frozen transfer inputs changed; preserve the previous version")
        report = previous
    done = {r["candidate"]["id"] for r in report["results"]}
    outer = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for teacher_index, config in enumerate(teachers):
        ids = [f"transfer-{teacher_index}-{student['id']}" for student in students]
        if all(identifier in done for identifier in ids):
            continue
        predictions = {identifier: np.empty(len(train), dtype=object) for identifier in ids}
        convergence = {identifier: 0 for identifier in ids}
        for fit, val in outer:
            fitting, validation = train.iloc[fit], train.iloc[val]
            if set(fitting["group_key"]) & set(validation["group_key"]):
                raise AssertionError("Outer transfer fold leaked walking participants")
            # Each meta-training teacher feature excludes that row's entire
            # participant. Validation features use the teacher trained on all
            # outer-fit people plus the sealed external training split only.
            fitted_scores = np.empty(len(fitting))
            for inner_fit, inner_val in GroupKFold(n_splits=3).split(fitting, groups=fitting["group_key"]):
                if set(fitting.iloc[inner_fit]["group_key"]) & set(fitting.iloc[inner_val]["group_key"]):
                    raise AssertionError("Inner teacher cross-fit leaked participants")
                fitted = fit_teacher(fitting.iloc[inner_fit], external, config)
                fitted_scores[inner_val] = fitted.predict(fitting.iloc[inner_val][SENSOR_FEATURES])
            teacher = fit_teacher(fitting, external, config)
            validation_scores = teacher.predict(validation[SENSOR_FEATURES])
            meta_fit, meta_val = add_teacher(fitting, fitted_scores), add_teacher(validation, validation_scores)
            for identifier, student in zip(ids, students):
                with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                    warnings.simplefilter("always", ConvergenceWarning)
                    model = DynamicsClassifier(student).fit(meta_fit)
                    predictions[identifier][val] = model.predict(meta_val)
                convergence[identifier] += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
        for identifier, student in zip(ids, students):
            if identifier in done:
                continue
            values = predictions[identifier]
            scores = [float(accuracy_score(train.iloc[val]["label"], values[val])) for _, val in outer]
            report["results"].append({"candidate": {"id": identifier, "teacher": config, "student": student},
                                      "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                                      "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(train["label"], values)),
                                      "oof_predictions": values.tolist(), "convergence_warnings": convergence[identifier]})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        content = json.dumps(report, indent=2, allow_nan=False) + "\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Teacher {teacher_index+1}/{len(teachers)} {config['algorithm']} external_weight={config['external_weight']}: {len(report['results'])}/{len(teachers)*len(students)} nested candidates, best exact CV={best['accuracy_mean']:.4f}; extra fitting rows={len(external)}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    select()
