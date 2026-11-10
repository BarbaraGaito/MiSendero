"""Audit original WorkerFatigue Borg responses before cross-study transfer.

One row is produced per published post-repetition questionnaire response.
Interpolated targets and repeated per-sample targets are never observations.
Sessions with any disagreement between sensor labels and the original survey
are excluded in full, rather than choosing only the labels that happen to agree.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_features import MINUTE, RESEARCH, ROOT, causal_statistics
from fetch_fatigue_extra import DESTINATION
from public_sources import digest, group_key

SENSOR_COLUMNS = {"hr": ("HR_Processed", 30, 240), "respiration": ("RR", 3, 80),
                  "temperature": ("Temperature", 5, 45)}


def completed_minute_means(frame, column, lower, upper):
    times = pd.to_timedelta(frame["Time"], unit="ms")
    values = pd.to_numeric(frame[column], errors="coerce")
    values = values.where(values.between(lower, upper))
    data = pd.DataFrame({"time": times, "value": values}).dropna()
    data["minute"] = data["time"].dt.floor("min")
    records = {}
    for minute, rows in data.groupby("minute"):
        # Source files are published at 2 Hz. Reject partial or sparse bins.
        if (len(rows) >= 110 and rows["time"].min() <= minute + pd.Timedelta(seconds=2)
                and rows["time"].max() >= minute + pd.Timedelta(seconds=58)):
            records[minute] = float(rows["value"].mean())
    if not records:
        return pd.Series([], index=pd.TimedeltaIndex([]), dtype=float)
    return pd.Series(records, dtype=float).sort_index()


def prepare_worker():
    receipt = json.loads((DESTINATION / "download-receipt.json").read_text(encoding="utf-8"))
    for entry in receipt["files"]:
        if digest(ROOT / entry["path"]) != entry["sha256"]:
            raise ValueError("WorkerFatigue source snapshot changed")
    survey_path = DESTINATION / "USER FORM RESPONSE.xlsx"
    survey = pd.read_excel(survey_path)
    survey["worksheet_row"] = np.arange(len(survey)) + 2
    survey = survey.dropna(subset=["Test"]).copy()
    survey["Test"] = survey["Test"].str.strip()
    if survey["Test"].duplicated().any():
        raise ValueError("Original questionnaire contains duplicate session identifiers")
    survey = survey.set_index("Test")
    members = json.loads((DESTINATION / "processed-members.json").read_text(encoding="utf-8"))
    sessions = defaultdict(dict)
    exclusions = []
    for member in members:
        match = re.search(r"/(Rep([1-5])|Initial_Rest)_(P\d+[CZ]\d+S\d+)\.csv$", member)
        if not match:
            continue
        stage, repetition, session = match.groups()
        path = DESTINATION / "processed" / member
        columns = ["Time", *[v[0] for v in SENSOR_COLUMNS.values()], "Physical Fatigue - Final"]
        data = pd.read_csv(path, usecols=columns)
        if stage in sessions[session]:
            raise ValueError("Duplicate processed session/repetition")
        sessions[session][stage] = {"data": data, "member": member, "sha256": digest(path)}
    canonical_manifest = json.loads((RESEARCH / "multisensor-v1/provenance.json").read_text(encoding="utf-8"))
    feature_names = canonical_manifest["features"]
    observations, lineage = [], []
    session_audit = []
    for session, segments in sorted(sessions.items()):
        repetitions = sorted((name for name in segments if name.startswith("Rep")), key=lambda name: int(name[3:]))
        if not repetitions:
            continue
        problems = []
        if session not in survey.index:
            problems.append("No unambiguous matching original questionnaire session ID")
        if "Initial_Rest" not in segments or "Rep1" not in segments:
            problems.append("Missing original pre-task baseline or first repetition")
        ratings = {}
        for stage in repetitions:
            values = segments[stage]["data"]["Physical Fatigue - Final"].dropna().unique()
            if len(values) != 1 or not 0 <= values[0] <= 10 or not float(values[0]).is_integer():
                problems.append(f"{stage}: nonconstant, missing or noninteger target; no interpolation permitted")
                continue
            rating = float(values[0])
            if session in survey.index:
                expected = survey.loc[session, f"What is your physical fatigue level currently [REP {int(stage[3:])}] ?"]
                if pd.isna(expected) or float(expected) != rating:
                    problems.append(f"{stage}: processed response disagrees with original questionnaire")
            ratings[stage] = rating
        session_audit.append({"session_key": group_key("WorkerFatigue-session:" + session),
                              "observed_repetitions": len(repetitions), "accepted": not problems, "reasons": problems})
        if problems:
            exclusions.append({"session": session, "reasons": problems})
            continue
        first = segments["Rep1"]["data"]
        task_start = pd.Timedelta(milliseconds=float(first["Time"].min()))
        baseline = segments["Initial_Rest"]["data"]
        baseline_start = max(pd.Timedelta(milliseconds=float(baseline["Time"].min())), task_start - 5 * MINUTE)
        all_data = pd.concat([segments["Initial_Rest"]["data"], *[segments[name]["data"] for name in repetitions]], ignore_index=True)
        all_data = all_data[["Time", *[v[0] for v in SENSOR_COLUMNS.values()]]]
        duplicate_times = all_data["Time"].duplicated(keep=False)
        if duplicate_times.any():
            # Manual segmentation can include an identical boundary sample in
            # both adjacent files. Collapse only identical sensor observations.
            duplicates = all_data[duplicate_times].groupby("Time").nunique(dropna=False)
            if (duplicates > 1).any().any():
                exclusions.append({"session": session, "reasons": ["Conflicting sensor readings at overlapping segment timestamps"]})
                continue
            all_data = all_data.drop_duplicates("Time")
        series = {name: completed_minute_means(all_data, column, lower, upper)
                  for name, (column, lower, upper) in SENSOR_COLUMNS.items()}
        participant = re.match(r"P(\d+)", session)[1]
        for stage in repetitions:
            data = segments[stage]["data"]
            response_endpoint = pd.Timedelta(milliseconds=float(data["Time"].max()))
            features = {name: np.nan for name in feature_names}
            features["elapsed_minutes"] = (response_endpoint - task_start).total_seconds() / 60
            preceding = [f"Rep{i}" for i in range(1, int(stage[3:]) + 1)]
            if all(name in segments for name in preceding):
                features["cumulative_active_minutes"] = sum((segments[name]["data"]["Time"].max() - segments[name]["data"]["Time"].min()) / 60000 for name in preceding)
            for name, signal in series.items():
                features.update({f"{name}_{key}": value for key, value in causal_statistics(signal, response_endpoint, task_start, baseline_start).items()})
            if all(pd.isna(features[f"{name}_last"]) for name in SENSOR_COLUMNS):
                exclusions.append({"session": session, "stage": stage, "reasons": ["No complete recent common-sensor minute"]})
                continue
            row_key = group_key(f"WorkerFatigue:{session}:{stage}")
            observations.append({**features, "label": f"Borg {ratings[stage]:g}"})
            lineage.append({"row_key": row_key, "group_key": group_key("WorkerFatigue-participant:" + participant),
                            "sensor_member": segments[stage]["member"], "sensor_file_sha256": segments[stage]["sha256"],
                            "questionnaire_worksheet_row": int(survey.loc[session, "worksheet_row"]),
                            "questionnaire_column": f"What is your physical fatigue level currently [REP {int(stage[3:])}] ?",
                            "published_borg": ratings[stage], "repetition_end_elapsed_ms": float(data["Time"].max()),
                            "response_alignment": "Published rating after repetition; use only complete sensor minutes preceding repetition end, not invented survey timestamps."})
    frame = pd.DataFrame(observations)
    if frame.empty:
        raise ValueError("No auditable original Borg responses with compatible sensors")
    directory = RESEARCH / "worker-v1"
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory / "dataset.csv", index=False)
    manifest = {"version": 1, "source": receipt, "features": feature_names, "rows": len(frame),
                "participants": len({row["group_key"] for row in lineage}),
                "dataset_sha256": digest(directory / "dataset.csv"), "adapter_code_sha256": digest(Path(__file__)),
                "original_survey_sha256": digest(survey_path), "lineage": lineage,
                "session_audit": session_audit, "exclusions": exclusions,
                "synthetic_rows": 0, "interpolated_targets": 0, "rest_labels_added": 0,
                "harmonization": "Common HR bpm, respiration breaths/min and temperature Celsius only; minute means require >=110 valid 2-Hz samples and near-complete minute coverage. No HRV-to-RMSSD or chest-to-wrist acceleration conversion; unavailable features remain missing. Median imputation belongs inside training folds.",
                "label_definition": "Exact original integer modified Borg 0-10 after each repetition, independently checked against original questionnaire. Entire sessions rejected on any label mismatch."}
    (directory / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(frame)} independent questionnaire responses from {manifest['participants']} additional participants; excluded {sum(not s['accepted'] for s in session_audit)} inconsistent/unverifiable sessions", flush=True)
    return frame, manifest


if __name__ == "__main__":
    prepare_worker()
