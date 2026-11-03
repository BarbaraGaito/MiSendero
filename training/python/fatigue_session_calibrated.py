"""Causal within-session Borg scale calibration, including older real feedback.

A recent report remains mandatory. Older reports describe personal scale usage;
they do not replace a fresh assessment or supply the current/future target.
The original complete cohort and participant holdout remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import ParameterSampler

from fatigue_calibrated import evaluate
from fatigue_features import RESEARCH
from public_sources import OUTPUT, RAW, digest, verify_source_snapshot

DIRECTORY = RESEARCH / "calibrated-session-v1"


def session_history_features(responses, tasks, session_start, prediction_time):
    past = responses[(responses["time"] >= session_start)
                     & (responses["time"] <= prediction_time - pd.Timedelta(minutes=1))].sort_values("time")
    active = past[past["task_label"].isin(["flat_trail", "stairs", "ramp"])]
    older = past[past["time"] < prediction_time - pd.Timedelta(minutes=15)]
    result = {}
    for prefix, rows in (("session", past), ("session_active", active), ("session_older", older)):
        values = rows["borg_scale"].to_numpy(dtype=float)
        result.update({f"{prefix}_count": len(values), f"{prefix}_mean": float(np.mean(values)) if len(values) else np.nan,
                       f"{prefix}_std": float(np.std(values)) if len(values) else np.nan,
                       f"{prefix}_max": float(np.max(values)) if len(values) else np.nan,
                       f"{prefix}_last": float(values[-1]) if len(values) else np.nan})
    completed = []
    for task in sorted(tasks, key=lambda row: row["start_time"]):
        start, end = pd.Timestamp(task["start_time"]), pd.Timestamp(task["end_time"])
        if end > prediction_time - pd.Timedelta(minutes=1):
            continue
        observed = past[(past["time"] > start) & (past["time"] <= end) & past["task_label"].eq(task["label"])]
        if len(observed):
            completed.append((float(observed.iloc[0]["borg_scale"]), float(observed.iloc[-1]["borg_scale"])))
    result.update(completed_task_count=len(completed),
                  completed_first_borg_mean=float(np.mean([row[0] for row in completed])) if completed else np.nan,
                  completed_last_borg_mean=float(np.mean([row[1] for row in completed])) if completed else np.nan,
                  last_completed_first_borg=completed[-1][0] if completed else np.nan,
                  last_completed_last_borg=completed[-1][1] if completed else np.nan)
    return result, past


def prepare():
    verify_source_snapshot("fatigue")
    parent = RESEARCH / "calibrated-v2"
    manifest = json.loads((parent / "provenance.json").read_text(encoding="utf-8"))
    if digest(parent / "dataset.csv") != manifest["dataset_sha256"]:
        raise ValueError("Parent calibration observations changed")
    frame = pd.read_csv(parent / "dataset.csv", dtype={"label": str})
    original = json.loads((OUTPUT / "fatigue/provenance.json").read_text(encoding="utf-8"))
    responses = pd.read_csv(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
    responses["time"] = pd.to_datetime(responses["time"], utc=True)
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    additions, evidence = [], []
    for row in original["lineage"]:
        participant = "p" + re.search(r"/p(\d+)-", row["lineage"]["member"])[1]
        t = pd.Timestamp(row["lineage"]["label_time"])
        session = next(s for s in sessions[participant] if pd.Timestamp(s["start_time"]) <= t <= pd.Timestamp(s["end_time"]))
        values, past = session_history_features(responses[responses["id"].eq(participant)], session["tasks"], pd.Timestamp(session["start_time"]), t)
        additions.append(values)
        evidence.append({"row_key": row["row_key"], "prediction_time": t.isoformat(),
                         "past_reports": [{"time": r["time"].isoformat(), "borg": float(r["borg_scale"]), "task_label": r["task_label"]} for _, r in past.iterrows()]})
    added = pd.DataFrame(additions)
    frame = pd.concat([frame.drop(columns=["label"]), added, frame[["label"]]], axis=1)
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY / "dataset.csv", index=False)
    updated = {**manifest, "features": [c for c in frame if c != "label"], "session_features": list(added),
               "dataset_sha256": digest(DIRECTORY / "dataset.csv"), "parent_dataset_sha256": manifest["dataset_sha256"],
               "feature_code_sha256": digest(Path(__file__)), "session_history_lineage": evidence,
               "session_history_policy": "Observed reports from the same session strictly at least one minute before prediction; recent mandatory report still 1-15 minutes old. Older history is optional personal scale calibration. No future/current ratings or cross-session feedback.",
               "user_authorized_previous_Borg_feedback": True}
    (DIRECTORY / "provenance.json").write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared personal scale history for all {len(frame)} original observed responses", flush=True)


def plan(manifest):
    prior, history = manifest["calibration_features"], manifest["session_features"]
    compact = prior + ["hr_last", "elapsed_minutes", "hr_change_after_prior"]
    context = ["cumulative_active_minutes", "task_order", "terrain_stairs", "terrain_ramp", "terrain_flat_trail"]
    normalized = [c for c in manifest["features"] if not c.startswith("raw_") and c.endswith(("delta_baseline", "ratio_baseline", "recent_slope"))]
    sets = {"past_session_scale": compact + history,
            "past_active_scale_context": compact + context + [c for c in history if c.startswith(("session_active", "completed", "last_completed"))],
            "past_scale_physiology": list(dict.fromkeys(compact + history + context + normalized))}
    space = {"max_depth": [3, 5, 8, None], "min_samples_leaf": [2, 5, 10], "max_features": [.7, 1.]}
    params = list(ParameterSampler(space, n_iter=6, random_state=42))
    return [{"id": f"session-{i:03d}", "feature_set": name, "features": cols, "algorithm": algorithm,
             "params": {"n_estimators": 200, **parameters}, "target_mode": mode}
            for i, (name, cols, algorithm, parameters, mode) in enumerate(
                (name, cols, algorithm, parameters, mode) for name, cols in sets.items()
                for algorithm in ("random_forest", "extra_trees") for parameters in params
                for mode in ("absolute_borg", "change_from_prior"))]


def main():
    if not (DIRECTORY / "provenance.json").exists():
        prepare()
    manifest = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if digest(DIRECTORY / "dataset.csv") != manifest["dataset_sha256"] or digest(Path(__file__)) != manifest["feature_code_sha256"]:
        raise ValueError("Session calibration snapshot changed; preserve old version before rebuilding")
    frame = pd.read_csv(DIRECTORY / "dataset.csv", dtype={"label": str})
    frame = pd.concat([frame, pd.DataFrame({"row_key": [r["row_key"] for r in manifest["lineage"]], "group_key": [r["group_key"] for r in manifest["lineage"]]})], axis=1)
    protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    train = frame[frame["row_key"].isin(protocol["train_row_keys"])]
    if len(train) != len(protocol["train_row_keys"]) or set(train["group_key"]) & set(protocol["test_groups"]):
        raise ValueError("Original held-out participants leaked into session-model fitting")
    candidates = plan(manifest)
    report = {"version": 1, "objective": "exact_native_Borg_accuracy_with_causal_personal_history", "target_accuracy": .6,
              "test_used_for_selection": False, "previous_benchmark_evaluations_are_published": True,
              "plan": candidates, "plan_sha256": hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest(),
              "dataset_sha256": manifest["dataset_sha256"], "experiment_code_sha256": digest(Path(__file__)),
              "train_row_keys": train["row_key"].tolist(), "status": "running", "results": []}
    path = DIRECTORY / "selection.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        for key in ("plan_sha256", "dataset_sha256", "experiment_code_sha256"):
            if old[key] != report[key]:
                raise ValueError("Session search changed; archive the prior version first")
        report = old
    done = {r["candidate"]["id"] for r in report["results"]}
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        cv = evaluate(train, candidate)
        report["results"].append({"candidate": candidate, "cv": cv})
        best = max(report["results"], key=lambda row: row["cv"]["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["cv"]["accuracy_mean"])
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']} {candidate['target_mode']}: CV accuracy={cv['accuracy_mean']:.4f}, best={report['best_cv_accuracy']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
