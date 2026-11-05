"""Causal feedback dynamics for the >=80% exact native-Borg research goal.

The original cohort, native targets and participant holdout are unchanged.
Past self-reports are user-authorized observations; current/future responses
cannot enter the predictors. No report is interpolated into a training label.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_features import MINUTE, RESEARCH
from public_sources import OUTPUT, RAW, digest, verify_source_snapshot

DIRECTORY = RESEARCH / "dynamics-80-v1"
CONTEXT = ["elapsed_minutes", "cumulative_active_minutes", "task_order", "terrain_stairs", "terrain_ramp", "terrain_flat_trail"]


def feedback_dynamics(reports, tasks, session_start, now, current_task):
    """Only same-person reports that are >=1 minute old in this session."""
    past = reports[(reports["time"] >= session_start) & (reports["time"] <= now - MINUTE)].sort_values("time")
    start = pd.Timestamp(current_task["start_time"])
    current = past[(past["time"] >= start) & past["task_label"].eq(current_task["label"])]
    elapsed = (now - start).total_seconds() / 60
    values = {}
    for prefix, rows in (("task_feedback", current), ("all_feedback", past[past["task"].eq(1)])):
        borg = rows["borg_scale"].to_numpy(float)
        times = (rows["time"] - start).dt.total_seconds().to_numpy() / 60
        increments, intervals = np.diff(borg), np.diff(times)
        rates = increments / intervals if len(intervals) else np.array([])
        positive = np.flatnonzero(increments > 0)
        values.update({f"{prefix}_count": len(rows), f"{prefix}_first": borg[0] if len(borg) else np.nan,
                       f"{prefix}_total_rise": borg[-1] - borg[0] if len(borg) else np.nan,
                       f"{prefix}_zero_fraction": float(np.mean(increments == 0)) if len(increments) else np.nan,
                       f"{prefix}_positive_fraction": float(np.mean(increments > 0)) if len(increments) else np.nan,
                       f"{prefix}_rate_mean": float(np.mean(rates)) if len(rates) else np.nan,
                       f"{prefix}_rate_median": float(np.median(rates)) if len(rates) else np.nan,
                       f"{prefix}_rate_std": float(np.std(rates)) if len(rates) else np.nan,
                       f"{prefix}_since_last_increase": elapsed - times[positive[-1] + 1] if len(positive) else np.nan,
                       f"{prefix}_linear_extrapolation": borg[-1] + (elapsed - times[-1]) * rates[-1] if len(rates) else np.nan})
        for lag in range(1, 5):
            values[f"{prefix}_delta_{lag}"] = increments[-lag] if len(increments) >= lag else np.nan
            values[f"{prefix}_interval_{lag}"] = intervals[-lag] if len(intervals) >= lag else np.nan
        for lag in range(1, 7):
            values[f"{prefix}_borg_{lag}"] = borg[-lag] if len(borg) >= lag else np.nan
            values[f"{prefix}_age_{lag}"] = elapsed - times[-lag] if len(times) >= lag else np.nan
    # Compare a known earlier task with the present elapsed time. The lookup
    # includes only completed tasks and actual earlier reports, never a future
    # label from the present task or an extrapolated supervision target.
    similar = []
    completed_rises, completed_rates = [], []
    for task in sorted(tasks, key=lambda t: t["start_time"]):
        if pd.Timestamp(task["end_time"]) > now - MINUTE:
            continue
        task_start = pd.Timestamp(task["start_time"])
        old = past[(past["time"] >= task_start) & (past["time"] <= pd.Timestamp(task["end_time"]))
                   & past["task_label"].eq(task["label"])]
        if len(old):
            minutes = (old["time"] - task_start).dt.total_seconds() / 60
            nearest = old.iloc[int(np.argmin(np.abs(minutes.to_numpy() - elapsed)))]
            similar.append(float(nearest["borg_scale"]))
            rise = float(old.iloc[-1]["borg_scale"] - old.iloc[0]["borg_scale"])
            duration = (old.iloc[-1]["time"] - old.iloc[0]["time"]).total_seconds() / 60
            completed_rises.append(rise)
            if duration > 0:
                completed_rates.append(rise / duration)
    values.update(previous_task_at_similar_elapsed_mean=float(np.mean(similar)) if similar else np.nan,
                  previous_task_at_similar_elapsed_last=similar[-1] if similar else np.nan,
                  completed_task_rise_mean=float(np.mean(completed_rises)) if completed_rises else np.nan,
                  completed_task_rate_mean=float(np.mean(completed_rates)) if completed_rates else np.nan)
    return values, past


def complete_signal_at(signal, report_time):
    samples = signal[(signal.index + MINUTE <= report_time) & (signal.index >= report_time - 3 * MINUTE)].dropna()
    return float(samples.iloc[-1]) if len(samples) else np.nan


def physiological_calibration(past, signal, current_value, now, current_task):
    paired = past.copy()
    paired["observed_hr"] = [complete_signal_at(signal, t) for t in paired["time"]]
    pairs = paired[paired["observed_hr"].notna() & paired["task"].eq(1)]
    local = pairs[(pairs["time"] >= pd.Timestamp(current_task["start_time"]))
                  & pairs["task_label"].eq(current_task["label"])]
    result = {}
    for prefix, data in (("session_hr_borg", pairs), ("task_hr_borg", local)):
        x, y = data["observed_hr"].to_numpy(float), data["borg_scale"].to_numpy(float)
        variance = float(np.sum((x - x.mean()) ** 2)) if len(x) else 0
        # Fixed shrinkage prevents division by tiny HR variation. It does not
        # fit a calibration using any current or future response.
        slope = float(np.sum((x - x.mean()) * (y - y.mean())) / (variance + 100)) if len(x) >= 2 else np.nan
        prediction = float(y.mean() + slope * (current_value - x.mean())) if len(x) >= 2 else np.nan
        result.update({f"{prefix}_count": len(data), f"{prefix}_slope": slope,
                       f"{prefix}_prediction": prediction,
                       f"{prefix}_hr_range": float(np.ptp(x)) if len(x) else np.nan})
    for lag in range(1, 5):
        result[f"feedback_hr_{lag}"] = float(paired.iloc[-lag]["observed_hr"]) if len(paired) >= lag else np.nan
        result[f"feedback_hr_change_{lag}"] = current_value - result[f"feedback_hr_{lag}"]
    return result


def prepare():
    verify_source_snapshot("fatigue")
    parent = RESEARCH / "calibrated-session-v1"
    manifest = json.loads((parent / "provenance.json").read_text(encoding="utf-8"))
    if digest(parent / "dataset.csv") != manifest["dataset_sha256"]:
        raise ValueError("Parent causal observation snapshot changed")
    frame = pd.read_csv(parent / "dataset.csv", dtype={"label": str})
    original = json.loads((OUTPUT / "fatigue/provenance.json").read_text(encoding="utf-8"))
    reports = pd.read_csv(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
    reports["time"] = pd.to_datetime(reports["time"], utc=True)
    if reports.duplicated(["id", "time"]).any():
        raise ValueError("Ambiguous original feedback")
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    additions, evidence, cached = [], [], {}
    with zipfile.ZipFile(RAW / "geofatigue/Physiological Data.zip") as archive:
        for i, item in enumerate(original["lineage"]):
            member = item["lineage"]["member"]
            participant = "p" + re.search(r"/p(\d+)-", member)[1]
            now = pd.Timestamp(item["lineage"]["label_time"])
            matches = [(s, t) for s in sessions[participant] for t in s["tasks"]
                       if pd.Timestamp(t["start_time"]) <= now <= pd.Timestamp(t["end_time"])]
            if len(matches) != 1:
                raise ValueError("Response must belong to exactly one task")
            session, task = matches[0]
            row, past = feedback_dynamics(reports[reports["id"].eq(participant)], session["tasks"], pd.Timestamp(session["start_time"]), now, task)
            if member not in cached:
                raw = pd.read_csv(io.BytesIO(archive.read(member)))
                values = pd.to_numeric(raw["pulse_rate_bpm"], errors="coerce")
                valid = values.between(30, 240) & (raw["missing_value_reason"].isna() | raw["missing_value_reason"].eq(""))
                cached[member] = pd.Series(values.where(valid).to_numpy(), index=pd.to_datetime(raw["timestamp_unix"], unit="ms", utc=True)).sort_index()
            row.update(physiological_calibration(past, cached[member], float(frame.iloc[i]["hr_last"]), now, task))
            additions.append(row)
            evidence.append({"row_key": item["row_key"], "prediction_time": now.isoformat(),
                             "earliest_feedback": past["time"].min().isoformat(), "latest_feedback": past["time"].max().isoformat(),
                             "original_feedback_count": len(past), "hr_member": member})
    added = pd.DataFrame(additions)
    if set(added) & set(frame):
        raise ValueError("New dynamics names collide with original predictors")
    combined = pd.concat([frame.drop(columns=["label"]), added, frame[["label"]]], axis=1)
    if len(combined) != 666 or combined["label"].tolist() != frame["label"].tolist():
        raise ValueError("Original native task/cohort changed")
    DIRECTORY.mkdir(exist_ok=True)
    data_path, provenance_path = DIRECTORY / "dataset.csv", DIRECTORY / "provenance.json"
    if data_path.exists() or provenance_path.exists():
        raise ValueError("Dynamics snapshot exists; preserve it before preparing a new version")
    combined.to_csv(data_path, index=False)
    updated = {**manifest, "version": 1, "parent_dataset_sha256": manifest["dataset_sha256"],
               "dataset_sha256": digest(data_path), "feature_code_sha256": digest(Path(__file__)),
               "features": [c for c in combined if c != "label"], "dynamics_features": list(added),
               "dynamics_lineage": evidence, "target_accuracy": .8,
               "dynamics_policy": "Same-session actual reports <= prediction minus one minute. Physiology uses completed minutes <= each prior report. No participant IDs, absolute timestamps, current/future Borg, interpolated labels or cohort exclusions."}
    provenance_path.write_text(json.dumps(updated, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Prepared {len(combined)} unchanged native responses with {len(added.columns)} causal feedback-dynamics features", flush=True)


def load_inputs():
    manifest = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if digest(DIRECTORY / "dataset.csv") != manifest["dataset_sha256"] or digest(Path(__file__)) != manifest["feature_code_sha256"]:
        raise ValueError("Frozen dynamics features/code changed")
    frame = pd.read_csv(DIRECTORY / "dataset.csv", dtype={"label": str})
    frame = pd.concat([frame, pd.DataFrame({"row_key": [r["row_key"] for r in manifest["lineage"]],
                                           "group_key": [r["group_key"] for r in manifest["lineage"]]})], axis=1)
    protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    train = frame[frame["row_key"].isin(protocol["train_row_keys"])].copy()
    test = frame[frame["row_key"].isin(protocol["test_row_keys"])].copy()
    if len(train) != 487 or len(test) != 179 or set(train["group_key"]) & set(test["group_key"]):
        raise ValueError("Original participant holdout changed")
    return frame, train, test, manifest, protocol


if __name__ == "__main__":
    prepare()
