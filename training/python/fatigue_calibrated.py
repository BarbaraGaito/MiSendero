"""User-authorized prior-Borg calibration with strictly chronological inputs.

The previous Borg is an explicitly observed user input, not a sensor-derived
label. Its report must be 1-15 minutes older than the prediction. The target
remains the exact current native Borg value on the complete original cohort.
"""
from __future__ import annotations

import hashlib
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from fatigue_experiment import estimator_for
from fatigue_features import RESEARCH
from public_sources import OUTPUT, RAW, digest


def previous_reports(responses, prediction_time, session_start):
    return responses[(responses["time"] >= session_start)
                     & (responses["time"] >= prediction_time - pd.Timedelta(minutes=15))
                     & (responses["time"] <= prediction_time - pd.Timedelta(minutes=1))].sort_values("time")


def prepare():
    directory = RESEARCH / "multisensor-v1"
    frame = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
    manifest = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    require_hash = digest(directory / "dataset.csv") == manifest["dataset_sha256"]
    if not require_hash:
        raise ValueError("Base observations changed")
    original_provenance = json.loads((OUTPUT / "fatigue/provenance.json").read_text(encoding="utf-8"))
    responses = pd.read_csv(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
    responses["time"] = pd.to_datetime(responses["time"], utc=True)
    if responses.duplicated(["id", "time"]).any():
        raise ValueError("Ambiguous duplicate original Borg timestamps")
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    additions, evidence = [], []
    for i, row in enumerate(original_provenance["lineage"]):
        participant = "p" + re.search(r"/p(\d+)-", row["lineage"]["member"])[1]
        t = pd.Timestamp(row["lineage"]["label_time"])
        session = next(s for s in sessions[participant] if pd.Timestamp(s["start_time"]) <= t <= pd.Timestamp(s["end_time"]))
        task = next(task for task in session["tasks"] if pd.Timestamp(task["start_time"]) <= t <= pd.Timestamp(task["end_time"]))
        old = previous_reports(responses[responses["id"].eq(participant)], t, pd.Timestamp(session["start_time"]))
        values = {"prior_borg": np.nan, "prior_age_minutes": np.nan, "prior2_borg": np.nan,
                  "prior2_age_minutes": np.nan, "prior_borg_slope": np.nan,
                  "prior_in_current_task": np.nan, "prior_count_current_task": 0}
        previous_evidence = []
        if len(old):
            last = old.iloc[-1]
            values.update(prior_borg=float(last["borg_scale"]), prior_age_minutes=(t-last["time"]).total_seconds()/60,
                          prior_in_current_task=int(last["time"] >= pd.Timestamp(task["start_time"])),
                          prior_count_current_task=int((old["time"] >= pd.Timestamp(task["start_time"])).sum()))
            if len(old) >= 2:
                penultimate = old.iloc[-2]
                interval = (last["time"] - penultimate["time"]).total_seconds() / 60
                values.update(prior2_borg=float(penultimate["borg_scale"]), prior2_age_minutes=(t-penultimate["time"]).total_seconds()/60,
                              prior_borg_slope=(float(last["borg_scale"])-float(penultimate["borg_scale"]))/interval)
            previous_evidence = [{"response_time": r["time"].isoformat(), "observed_borg": float(r["borg_scale"])} for _, r in old.tail(2).iterrows()]
        additions.append(values)
        evidence.append({"row_key": row["row_key"], "group_key": row["group_key"], "prediction_time": t.isoformat(),
                         "previous_observed_reports": previous_evidence})
    added = pd.DataFrame(additions)
    frame = pd.concat([frame.drop(columns=["label"]), added, frame[["label"]]], axis=1)
    destination = RESEARCH / "calibrated-v1"
    destination.mkdir(exist_ok=True)
    frame.to_csv(destination / "dataset.csv", index=False)
    result = {**manifest, "dataset_sha256": digest(destination / "dataset.csv"), "parent_dataset_sha256": manifest["dataset_sha256"],
              "feature_code_sha256": digest(Path(__file__)), "features": [c for c in frame if c != "label"],
              "calibration_features": list(added), "calibration_lineage": evidence,
              "user_authorization": "User explicitly allowed a previous Borg self-report during the activity.",
              "input_contract": {"minimum_prior_age_minutes": 1, "maximum_prior_age_minutes": 15,
                                 "previous_report_is_observed_input": True, "current_or_future_response_permitted": False},
              "rows": len(frame), "missing_previous_report": int(added["prior_borg"].isna().sum()),
              "evaluation_scope": "Participant-disjoint model fitting with chronological observed Borg calibration feedback. This is not sensor-only inference."}
    (destination / "provenance.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared calibrated inputs for {len(frame)} unchanged responses; missing previous Borg={result['missing_previous_report']}", flush=True)
    return frame, result


def candidate_plan(manifest):
    prior = manifest["calibration_features"]
    context = ["elapsed_minutes", "cumulative_active_minutes", "task_order", "terrain_stairs", "terrain_flat_trail", "terrain_ramp"]
    sets = {"prior_context": prior + context,
            "prior_normalized_sensors": prior + [c for c in manifest["features"] if c.endswith(("delta_baseline", "ratio_baseline", "recent_slope", "history_std"))] + context,
            "prior_all_sensors": manifest["features"]}
    algorithms = [
        ("random_forest", {"n_estimators": 200, "min_samples_leaf": 2, "max_features": 1., "max_depth": 8}),
        ("random_forest", {"n_estimators": 200, "min_samples_leaf": 5, "max_features": 1., "max_depth": 5}),
        ("extra_trees", {"n_estimators": 200, "min_samples_leaf": 2, "max_features": 1., "max_depth": 8}),
        ("extra_trees", {"n_estimators": 200, "min_samples_leaf": 5, "max_features": 1., "max_depth": 5}),
        ("xgboost", {"n_estimators": 250, "max_depth": 2, "learning_rate": .05, "min_child_weight": 5, "reg_lambda": 10}),
        ("xgboost", {"n_estimators": 250, "max_depth": 4, "learning_rate": .05, "min_child_weight": 5, "reg_lambda": 10}),
    ]
    return [{"id": f"calibrated-{i:03d}", "feature_set": name, "features": columns,
             "algorithm": algorithm, "params": params, "target_mode": mode}
            for i, (name, columns, algorithm, params, mode) in enumerate(
                (name, cols, algorithm, params, mode) for name, cols in sets.items()
                for algorithm, params in algorithms for mode in ("absolute_borg", "change_from_prior"))]


def evaluate(frame, candidate):
    y = frame["label"].str.replace("Borg ", "", regex=False).astype(int)
    groups = frame["group_key"]
    prediction = np.empty(len(frame), dtype=int)
    folds = []
    if candidate["target_mode"] == "change_from_prior" and frame["prior_borg"].isna().any():
        raise ValueError("Transition model needs observed prior input for every evaluated response; do not drop uncalibrated rows")
    for train, validation in GroupKFold(n_splits=5).split(frame, y, groups):
        if set(groups.iloc[train]) & set(groups.iloc[validation]):
            raise AssertionError("Participant leakage in calibrated model fitting")
        target = y.iloc[train]
        if candidate["target_mode"] == "change_from_prior":
            target = target - frame.iloc[train]["prior_borg"].astype(int)
        estimator = estimator_for(candidate)
        with warnings.catch_warnings(record=True), threadpool_limits(limits=1):
            warnings.simplefilter("always", ConvergenceWarning)
            estimator.fit(frame.iloc[train][candidate["features"]], target.astype(str))
            values = estimator.predict(frame.iloc[validation][candidate["features"]]).astype(int)
        if candidate["target_mode"] == "change_from_prior":
            values = np.clip(values + frame.iloc[validation]["prior_borg"].to_numpy(dtype=int), 0, 10)
        prediction[validation] = values
        folds.append({"train_groups": sorted(set(groups.iloc[train])), "validation_groups": sorted(set(groups.iloc[validation])),
                      "accuracy": float(accuracy_score(y.iloc[validation], values)),
                      "copy_previous_borg_accuracy": float(accuracy_score(y.iloc[validation], frame.iloc[validation]["prior_borg"])),
                      "f1_macro": float(f1_score(y.iloc[validation], values, labels=list(range(11)), average="macro", zero_division=0))})
    return {"accuracy_mean": float(np.mean([f["accuracy"] for f in folds])),
            "accuracy_std": float(np.std([f["accuracy"] for f in folds])),
            "pooled_oof_accuracy": float(accuracy_score(y, prediction)),
            "oof_predictions": [f"Borg {value}" for value in prediction], "folds": folds}


def main():
    directory = RESEARCH / "calibrated-v1"
    if not (directory / "provenance.json").exists():
        prepare()
    manifest = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if digest(directory / "dataset.csv") != manifest["dataset_sha256"] or digest(Path(__file__)) != manifest["feature_code_sha256"]:
        raise ValueError("Calibrated feature snapshot/code changed; preserve previous report and rebuild")
    frame = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
    frame["row_key"] = [r["row_key"] for r in manifest["lineage"]]
    frame["group_key"] = [r["group_key"] for r in manifest["lineage"]]
    protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    training = frame[frame["row_key"].isin(protocol["train_row_keys"])].copy()
    require_no_test = not set(training["group_key"]) & set(protocol["test_groups"])
    if len(training) != len(protocol["train_row_keys"]) or not require_no_test:
        raise ValueError("Original held-out responses leaked into calibrated fitting")
    candidates = candidate_plan(manifest)
    report = {"version": 1, "objective": "exact_current_native_Borg_accuracy_with_user_authorized_past_report",
              "target_accuracy": .6, "test_evaluated": False, "dataset_sha256": manifest["dataset_sha256"],
              "plan": candidates, "plan_sha256": hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest(),
              "experiment_code_sha256": digest(Path(__file__)), "train_row_keys": training["row_key"].tolist(),
              "status": "running", "results": []}
    path = directory / "selection.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        for key in ("dataset_sha256", "plan_sha256", "experiment_code_sha256"):
            if old[key] != report[key]:
                raise ValueError("Calibrated search inputs changed; preserve previous evidence first")
        report = old
    done = {r["candidate"]["id"] for r in report["results"]}
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        cv = evaluate(training, candidate)
        report["results"].append({"candidate": candidate, "cv": cv})
        winner = max(report["results"], key=lambda r: r["cv"]["accuracy_mean"])
        report["winner_id"] = winner["candidate"]["id"]
        report["best_cv_accuracy"] = winner["cv"]["accuracy_mean"]
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']} {candidate['target_mode']}: CV accuracy={cv['accuracy_mean']:.4f}, best={report['best_cv_accuracy']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
