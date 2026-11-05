"""Measured pre-first-task session baselines; no targets or extra cases."""
from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import cadence_association_inputs as association
from fatigue_dynamics import load_inputs
from public_sources import RAW, ROOT, digest

DIRECTORY = association.NATIVE_DIRECTORY.parent/"native-session-rest-inputs-80-v1"
DIAGNOSTIC = ROOT/"docs/fatigue-80-2026-10-25/cadence-baseline-context-diagnostic.json"
FEATURES = ["session_rest_mean_hr_bpm","session_rest_lowest_minute_hr_bpm"]


def dependencies():
    return {name:digest(path) for name,path in {"preparation_code":Path(__file__),"baseline_context_diagnostic":DIAGNOSTIC,
        "baseline_context_code":Path(__file__).with_name("diagnose_cadence_baseline_context.py"),
        "association_preparation_code":Path(association.__file__),"association_native_provenance":association.NATIVE_DIRECTORY/"provenance.json",
        "native_reader_code":Path(association.previous_native.__file__),"native_identity_code":Path(association.previous_native.identities.__file__),
        "session_metadata":RAW/"geofatigue/session_metadata.json","raw_archive":association.previous_native.ARCHIVE,
        "public_real_data_policy":ROOT/"docs/fatigue-80-2026-10-25/public-real-data-policy.json"}.items()}


def prepare():
    if (DIRECTORY/"dataset.csv").exists() or (DIRECTORY/"provenance.json").exists():
        raise ValueError("Preserve the frozen measured session-rest input cache")
    diagnostic = json.loads(DIAGNOSTIC.read_text())
    if diagnostic["code_sha256"] != digest(Path(__file__).with_name("diagnose_cadence_baseline_context.py")) or diagnostic["status"] != "actual_baseline_context_screen_completed":
        raise ValueError("Measured baseline-context evidence changed")
    _,_,_,manifests = association.load()
    frame,train,test,native_manifest,_ = load_inputs()
    sessions = json.loads((RAW/"geofatigue/session_metadata.json").read_text())
    identities,_ = association.previous_native.identities.input_rows()
    identities = {r["row_key"]:r for r in identities if r["cohort"] == "canonical"}
    grouped = defaultdict(list)
    for row in manifests["native"]["lineage"]:
        grouped[tuple(row["source_prefixes"])].append(row)
    prepared,lineage = {},{}
    minute = pd.Timedelta(minutes=1)
    available_sessions,total_minutes = 0,0
    with zipfile.ZipFile(association.previous_native.ARCHIVE) as archive:
        for prefixes,rows in sorted(grouped.items()):
            person = rows[0]["participant"]
            now = pd.Timestamp(identities[rows[0]["row_key"]]["current_time_us"],unit="us",tz="UTC")
            matching = [s for s in sessions[person] if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"])]
            if len(matching) != 1:
                raise ValueError("Session-rest baseline belongs to an ambiguous session")
            session = matching[0]
            session_start = pd.Timestamp(session["start_time"])
            first_task = min(pd.Timestamp(t["start_time"]) for t in session["tasks"])
            lower = max(session_start,first_task-5*minute)
            signal,members = association.previous_native.read_pulse(archive,prefixes,person)
            baseline = signal[(signal.index >= lower)&(signal.index+minute <= first_task)]
            mean = float(baseline.mean()) if len(baseline) else np.nan
            lowest = float(baseline.min()) if len(baseline) else np.nan
            total_minutes += len(baseline)
            available_sessions += int(len(baseline)>0)
            for row in rows:
                key = row["row_key"]
                query = pd.Timestamp(identities[key]["current_time_us"],unit="us",tz="UTC")
                if not session_start <= first_task < query:
                    raise ValueError("A candidate session-rest baseline uses future measurements")
                prepared[key] = {"row_key":key,"group_key":row["group_key"],FEATURES[0]:mean,FEATURES[1]:lowest}
                lineage[key] = {"row_key":key,"group_key":row["group_key"],"participant":person,
                    "source_prefixes":list(prefixes),"source_members":members,"prediction_time":query.isoformat(),
                    "session_start":session_start.isoformat(),"first_task_start":first_task.isoformat(),"baseline_lower_bound":lower.isoformat(),
                    "actual_observed_minute_starts":[t.isoformat() for t in baseline.index],
                    "latest_observed_minute_end":(baseline.index[-1]+minute).isoformat() if len(baseline) else None}
    data = pd.DataFrame([prepared[key] for key in frame.row_key])
    if len(data) != 666 or not data.row_key.is_unique or data[FEATURES].notna().sum().to_dict() != dict.fromkeys(FEATURES,636):
        raise ValueError("Original native case count or natural baseline availability changed")
    if len(grouped) != 44 or available_sessions != 42:
        raise ValueError("Original observed native sessions changed")
    DIRECTORY.mkdir(exist_ok=True)
    data.to_csv(DIRECTORY/"dataset.csv",index=False)
    provenance = {"version":1,"dependencies_sha256":dependencies(),"dataset_sha256":digest(DIRECTORY/"dataset.csv"),
        "original_native_dataset_sha256":native_manifest["dataset_sha256"],"features":FEATURES,"original_cases":666,
        "original_training_cases":len(train),"original_test_cases":len(test),"actual_sessions":44,"sessions_with_observed_baseline":42,
        "actual_complete_baseline_minutes_across_sessions":total_minutes,"natural_missing_counts":data[FEATURES].isna().sum().astype(int).to_dict(),
        "native_current_targets_in_cache":False,"native_cases_dropped":0,"synthetic_rows":0,"interpolated_minutes":0,
        "original_features_overwritten":False,"new_model_fitting_started_at_preparation":False,
        "definition":"Mean and lowest actual completed minute in the5min window ending before the first task, bounded by original session start. The same known preexercise baseline may be reused for later queries from that same person/session; it is not a new fitting row. No posture equivalence with CADENCE seated rest is assumed. All natural missing baselines and original cases retained.",
        "lineage":[lineage[key] for key in frame.row_key]}
    (DIRECTORY/"provenance.json").write_text(json.dumps(provenance,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({key:provenance[key] for key in ("original_cases","actual_sessions","sessions_with_observed_baseline",
        "actual_complete_baseline_minutes_across_sessions","natural_missing_counts")}),flush=True)


def load():
    manifest = json.loads((DIRECTORY/"provenance.json").read_text())
    if manifest["dependencies_sha256"] != dependencies() or manifest["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen actual session-rest inputs changed")
    data = pd.read_csv(DIRECTORY/"dataset.csv")
    if len(data) != 666 or data.row_key.tolist() != [r["row_key"] for r in manifest["lineage"]]:
        raise ValueError("Original native session-rest case identities changed")
    return data,manifest


if __name__ == "__main__":
    prepare()
