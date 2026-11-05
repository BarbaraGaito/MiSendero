"""Transfer actual walking SPE histories through separate conditional heads.

The four walking conditions retain independent SPE heads. Existing public
Worker/STS teachers are optional. Native targets never include source labels.
"""
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

import fatigue_combined_walking_sources as source
import fatigue_survey_prior_teachers as parent
from public_sources import digest

DIRECTORY = source.DIRECTORY.parent/"walking-source-teachers-80-v1"
FEATURES = ["prior_spe", "prior2_spe", "nominal_elapsed_minutes"]
OUTPUTS = [f"walking_spe_{condition}_{kind}" for condition in source.walking.CONDITIONS for kind in ("estimate", "change")]
_RUNTIME = None


def plan():
    controls = (0, 1, 2, 3, 10, 11, 12, 13, 14, 15)
    result = [{"id": f"walking-teacher-{i:03d}", "algorithm": "previous_real_control",
        "parent_candidate_id": f"survey-teacher-{old:03d}"} for i, old in enumerate(controls)]
    for algorithm in ("ridge", "svr", "random_forest"):
        for existing in (False, True):
            for member in ("core", "cat"):
                result.append({"id": f"walking-teacher-{len(result):03d}", "algorithm": "separate_walking_spe_heads",
                    "teacher_algorithm": algorithm, "include_existing_borg_teachers": existing, "member": member,
                    "walking_head_features": FEATURES, "native_targets_unchanged": True})
    return result


def load_inputs():
    parents = parent.load_inputs()
    combined, provenance = source.load()
    _, train, test, _, old, _, _, _ = parents
    pd.testing.assert_frame_equal(combined[combined.source_domain.isin(["worker", "sts"])][old.columns].reset_index(drop=True), old.reset_index(drop=True), check_dtype=False, rtol=0, atol=1e-12)
    if len(combined) != 458 or set(combined.group_key) & set(pd.concat([train, test]).group_key):
        raise ValueError("Combined public source or native person namespaces changed")
    previous = json.loads((parent.DIRECTORY/"selection.json").read_text())
    if previous["status"] != "complete" or previous["train_row_keys"] != train.row_key.tolist() or previous["test_used_for_selection"]:
        raise ValueError("Frozen actual-source controls changed")
    return parents, combined, provenance, previous


def fingerprint(inputs):
    return {"code_sha256": digest(Path(__file__)), "parent_signature": parent.fingerprint(inputs[0]),
        "combined_provenance_sha256": digest(source.DIRECTORY/"provenance.json"),
        "source_dataset_sha256": inputs[2]["dataset_sha256"], "previous_selection_sha256": digest(parent.DIRECTORY/"selection.json"),
        "public_real_data_policy_sha256": digest(parent.native.POLICY),
        "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in
            ("fatigue_combined_walking_sources.py", "walking_spe_transitions.py", "fatigue_survey_prior_teachers.py")},
        "worker_processes": 2}


def fit_walking_teachers(combined, algorithm, observer=None):
    data = combined[combined.source_domain.eq("walking_spe")]
    if len(data) != 156 or data.group_key.nunique() != 1 or data[["hr_last", "hr_history_mean", "borg_native"]].notna().any().any():
        raise ValueError("Walking must remain SPE-only with one conservative cohort and no guessed HR/native Borg")
    teachers = {}
    for condition in source.walking.CONDITIONS:
        part = data[data.source_condition.eq(condition)]
        if len(part) != 39 or part.sequence_key.nunique() != 13:
            raise ValueError("Original condition-specific SPE sequences changed")
        current, prior = part.spe_native.to_numpy(float), part.prior_spe.to_numpy(float)
        estimator = {"ridge": lambda: Ridge(alpha=10.), "svr": lambda: SVR(C=10., gamma="scale", epsilon=.1),
            "random_forest": lambda: RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=3, random_state=42, n_jobs=1)}[algorithm]()
        model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), estimator)
        if observer is not None:
            observer(condition, part[FEATURES].copy(), current.copy(), prior.copy())
        with threadpool_limits(limits=1):
            model.fit(part[FEATURES], current-prior)
        teachers[condition] = model
    return teachers


def query_source_features(frame):
    return pd.DataFrame({"prior_spe": frame.prior_borg, "prior2_spe": frame.prior2_borg,
                         "nominal_elapsed_minutes": frame.elapsed_minutes}, index=frame.index)


def add_features(frame, walking_teachers, existing_teachers):
    parent.parent.baseline.validate_calibration(frame)
    output = parent.parent.add_features(frame, existing_teachers)
    inputs = query_source_features(frame)
    with threadpool_limits(limits=1):
        for condition, teacher in walking_teachers.items():
            delta = teacher.predict(inputs)
            if not np.isfinite(delta).all():
                raise ValueError("Nonfinite walking SPE source representation")
            output[f"walking_spe_{condition}_change"] = delta
            output[f"walking_spe_{condition}_estimate"] = np.clip(frame.prior_borg.to_numpy()+delta, 0, 10)
    return output


class WalkingSourceBorg:
    def __init__(self, candidate, walking_teachers, existing_teachers):
        self.candidate = candidate
        self.walking_teachers = walking_teachers
        self.existing_teachers = existing_teachers if candidate["include_existing_borg_teachers"] else {}

    def fit(self, frame, specifications, observer=None):
        c = self.candidate
        self.input_features = list(dict.fromkeys(specifications[c["member"]]["features"]+parent.parent.FEATURES+
            ["prior2_borg", "elapsed_minutes"]))
        generated = OUTPUTS+(parent.parent.OUTPUTS if self.existing_teachers else [])
        recipe = {**specifications[c["member"]], "id": c["id"], "features": self.input_features+generated}
        data = add_features(frame, self.walking_teachers, self.existing_teachers)
        if observer is not None:
            observer(data[recipe["features"]].copy(), data.label.copy())
        with threadpool_limits(limits=1):
            self.model = (parent.parent.baseline.DynamicsClassifier(recipe) if c["member"] == "core"
                          else parent.parent.baseline.CatBoostBorg(recipe)).fit(data)
        return self

    def predict(self, frame):
        return self.model.predict(add_features(frame, self.walking_teachers, self.existing_teachers))


def read_teachers(signature):
    walking, existing = {}, {}
    for algorithm in ("ridge", "svr", "random_forest"):
        path = DIRECTORY/"teachers"/(algorithm+".joblib")
        metadata = json.loads(path.with_suffix(".json").read_text())
        if metadata["signature"] != signature or metadata["algorithm"] != algorithm or metadata["model_sha256"] != digest(path):
            raise ValueError("Frozen walking source heads changed")
        walking[algorithm] = joblib.load(path)
        path = parent.DIRECTORY/"teachers"/(algorithm+".joblib")
        metadata = json.loads(path.with_suffix(".json").read_text())
        if metadata["signature"] != signature["parent_signature"] or metadata["model_sha256"] != digest(path):
            raise ValueError("Previously verified Worker/STS teachers changed")
        existing[algorithm] = joblib.load(path)
    return walking, existing


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    signature = fingerprint(inputs)
    _RUNTIME = inputs, signature, read_teachers(signature)


def compute_fold(job):
    candidate, number, fit, val = job
    inputs, signature, (walking, existing) = _RUNTIME
    train, specifications = inputs[0][1], inputs[0][3]["member_specifications"]
    fitting, validation = train.iloc[fit], train.iloc[val]
    if set(fitting.group_key) & set(validation.group_key):
        raise ValueError("Native fitting and validation people overlap")
    algorithm = candidate["teacher_algorithm"]
    model = WalkingSourceBorg(candidate, walking[algorithm], existing[algorithm]).fit(fitting, specifications)
    return {"signature": signature, "candidate": candidate, "fold_number": number,
        "fit_row_keys": fitting.row_key.tolist(), "validation_row_keys": validation.row_key.tolist(),
        "actual_walking_source_targets": 156, "actual_existing_source_targets": 302 if candidate["include_existing_borg_teachers"] else 0,
        "predicted": model.predict(validation).tolist()}


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report, indent=2, allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload, encoding="utf-8")
    path.write_text(payload, encoding="utf-8")


def select():
    inputs = load_inputs()
    parents, combined, _, previous = inputs
    train, test = parents[1:3]
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("teachers", "folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature, "version": 1, "status": "running", "plan": plan(), "results": [],
        "target_accuracy": .8, "train_row_keys": train.row_key.tolist(), "evaluation_denominator": len(train), "test_denominator": len(test),
        "test_used_for_selection": False, "previous_benchmark_results_are_published": True, "minimum_cv_for_new_test_evaluation": .65,
        "combined_actual_source_targets": 458, "new_walking_actual_source_targets": 156, "new_native_borg_targets": 0,
        "synthetic_training_rows": 0, "walking_sensor_join_performed": False, "walking_person_holdout_claimed": False,
        "source_preparation_used_for_fitting_in_this_study": True,
        "policy": "Actual public source pairs only. Four separate walking-condition SPE heads use previous measured SPE and published nominal elapsed minutes, never guessed HR or participant identities. Native Borg/prior2/elapsed are numeric query inputs to frozen source functions; their outputs are computed features, not observed Borg labels or a scale conversion. Source preprocessing sees no native data/labels. Existing Worker/STS fitting teachers retain reserved people. Walking is one auxiliary cohort with no independent source-person validation claim. Original487/179 native participant cohorts, exact targets and missing cases retained; no artificial histories, masks, rows or validation stopping."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k, v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen walking-source study changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    for algorithm in ("ridge", "svr", "random_forest"):
        path = DIRECTORY/"teachers"/(algorithm+".joblib")
        if path.with_suffix(".json").exists():
            saved = json.loads(path.with_suffix(".json").read_text())
            if saved["signature"] != signature or saved["algorithm"] != algorithm or saved["model_sha256"] != digest(path):
                raise ValueError("Saved walking source heads changed")
        else:
            teachers = fit_walking_teachers(combined, algorithm)
            joblib.dump(teachers, path)
            metadata = {"signature": signature, "algorithm": algorithm, "model_sha256": digest(path), "actual_walking_targets": 156,
                "targets_per_condition": {condition: 39 for condition in source.walking.CONDITIONS}, "native_targets_used_for_fitting": 0}
            path.with_suffix(".json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
        print(f"Walking SPE source heads ready:{algorithm},156 actual targets", flush=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    jobs = []
    for candidate in plan()[10:]:
        for number, (fit, val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist():
                    raise ValueError("Frozen walking-source native fold changed")
            else:
                jobs.append((candidate, number, fit, val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2, initializer=worker_initialize) as pool:
            futures = [pool.submit(compute_fold, job) for job in jobs]
            for future in as_completed(futures):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
                print(f"Walking-source native fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete", flush=True)
    for candidate in plan():
        if any(row["candidate"] == candidate for row in report["results"]):
            continue
        if candidate["algorithm"] == "previous_real_control":
            old = next(row for row in previous["results"] if row["candidate"]["id"] == candidate["parent_candidate_id"])
            predicted, details = np.asarray(old["oof_predictions"]), []
        else:
            predicted, details = np.empty(len(train), dtype=object), []
            for number, (_, val) in enumerate(folds):
                saved = json.loads((DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
                predicted[val] = saved["predicted"]
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val].label, predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train.label, predicted)), "oof_predictions": predicted.tolist(), "folds": details})
        winner = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"], best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Walking-source recipe {candidate['id']}:CV={np.mean(scores):.6f}", flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
