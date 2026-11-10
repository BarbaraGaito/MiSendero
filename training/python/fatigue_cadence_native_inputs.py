"""Measured native lagged HR/baseline inputs; preserve all original cases.

Join both original day folders when a real session crosses UTC midnight.
No current target, source-inferred HR, interpolation or missing-case filtering.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import fatigue_physiology_pairs as identities
from fatigue_dynamics import load_inputs as native_inputs
from fatigue_features import RESEARCH
from public_sources import RAW, ROOT, digest, verify_source_snapshot

DIRECTORY = RESEARCH/"cadence-native-physiology-80-v1"
FEATURES = ["lag_hr_bpm","baseline_hr_bpm","hr_delta_baseline","hr_ratio_baseline"]
ARCHIVE = RAW/"geofatigue/Physiological Data.zip"


def dependencies():
    return {name:digest(path) for name,path in {"preparation_code":Path(__file__),"identity_code":Path(identities.__file__),
        "native_dynamics_code":Path(__file__).with_name("fatigue_dynamics.py"),
        "multisensor_provenance":RESEARCH/"multisensor-v1/provenance.json", "original_archive":ARCHIVE,
        "raw_reports":RAW/"geofatigue/self_reported_fatigue_level.original.tab",
        "session_metadata":RAW/"geofatigue/session_metadata.json",
        "real_public_data_policy":ROOT/"docs/fatigue-80-2026-10-25/public-real-data-policy.json"}.items()}


def read_pulse(archive,prefixes,person):
    members = sorted(name for name in archive.namelist() if name.endswith("_pulse-rate.csv")
        and any(name.startswith(prefix+"/digital_biomarkers/aggregated_per_minute/") for prefix in prefixes))
    if len(members) != len(prefixes):
        raise ValueError("Expected one original pulse file per actual participant/day prefix")
    rows = []
    for member in members:
        data = pd.read_csv(io.BytesIO(archive.read(member)))
        values = pd.to_numeric(data.pulse_rate_bpm,errors="coerce")
        people = data.participant_full_id.dropna().unique()
        if len(people) != 1 or not str(people[0]).endswith("-"+person):
            raise ValueError("Pulse-rate file belongs to another participant")
        valid = values.between(30,240)&(data.missing_value_reason.isna()|data.missing_value_reason.eq(""))
        rows.append(pd.DataFrame({"time":pd.to_datetime(data.timestamp_unix,unit="ms",utc=True),"value":values.where(valid)}))
    data = pd.concat(rows,ignore_index=True).sort_values("time",kind="stable")
    duplicate = data[data.time.duplicated(keep=False)]
    for _,part in duplicate.groupby("time"):
        if not np.allclose(part.value.to_numpy(),part.value.iloc[0],rtol=0,atol=1e-12,equal_nan=True):
            raise ValueError("Conflicting original HR observations at the same minute")
    data = data.drop_duplicates("time").dropna(subset=["value"])
    return pd.Series(data.value.to_numpy(),index=data.time),members


def measured_features(signal,identity,baseline_start):
    prior = pd.Timestamp(identity["prior_time_us"],unit="us",tz="UTC")
    task_start = pd.Timestamp(identity["current_lower_bound_us"],unit="us",tz="UTC")
    minute = pd.Timedelta(minutes=1)
    old = signal[(signal.index >= prior-2*minute)&(signal.index+minute <= prior)]
    baseline = signal[(signal.index >= pd.Timestamp(baseline_start))&(signal.index+minute <= task_start)]
    lag = float(old.iloc[-1]) if len(old) else np.nan
    base = float(baseline.mean()) if len(baseline) else np.nan
    values = {"lag_hr_bpm":lag,"baseline_hr_bpm":base,"hr_delta_baseline":lag-base,
              "hr_ratio_baseline":lag/base if np.isfinite(base) and base > 0 else np.nan}
    proof = {"prior_report_time_us":identity["prior_time_us"],"prediction_time_us":identity["current_time_us"],
        "task_start_us":identity["current_lower_bound_us"],"baseline_start":baseline_start,
        "lag_hr_minute_start":old.index[-1].isoformat() if len(old) else None,
        "lag_hr_minute_end":(old.index[-1]+minute).isoformat() if len(old) else None,
        "baseline_observed_minute_starts":[t.isoformat() for t in baseline.index],
        "latest_baseline_minute_end":(baseline.index[-1]+minute).isoformat() if len(baseline) else None}
    return values,proof


def prepare():
    if (DIRECTORY/"provenance.json").exists() or (DIRECTORY/"dataset.csv").exists():
        raise ValueError("Preserve frozen native physiological inputs before changes")
    verify_source_snapshot("fatigue")
    frame,train,test,manifest,_ = native_inputs()
    rows,_ = identities.input_rows()
    rows = [r for r in rows if r["cohort"] == "canonical"]
    if frame.row_key.tolist() != [r["row_key"] for r in rows] or len(rows) != 666:
        raise ValueError("Original native input identities changed")
    source_manifest = json.loads((RESEARCH/"multisensor-v1/provenance.json").read_text())
    baseline_by_key = {r["row_key"]:r["baseline_start"] for r in source_manifest["lineage"]}
    grouped = defaultdict(list)
    for index,row in enumerate(rows):
        grouped[tuple(row["source_prefixes"])].append((index,row))
    output,lineage = [None]*666,[None]*666
    with zipfile.ZipFile(ARCHIVE) as archive:
        for number,(prefixes,items) in enumerate(sorted(grouped.items()),1):
            signal,members = read_pulse(archive,prefixes,items[0][1]["participant"])
            for index,row in items:
                features,proof = measured_features(signal,row,baseline_by_key[row["row_key"]])
                output[index] = {"row_key":row["row_key"],"group_key":row["group_key"],**features}
                lineage[index] = {"row_key":row["row_key"],"group_key":row["group_key"],"participant":row["participant"],
                    "source_prefixes":list(prefixes),"source_members":members,**proof}
            print(f"Real native HR session{number}/{len(grouped)}",flush=True)
    data = pd.DataFrame(output)
    if not data.row_key.is_unique or np.isinf(data[FEATURES].to_numpy()).any():
        raise ValueError("Invalid native case identity or physiological summary")
    DIRECTORY.mkdir(exist_ok=True)
    data.to_csv(DIRECTORY/"dataset.csv",index=False)
    result = {"version":1,"dependencies_sha256":dependencies(),"dataset_sha256":digest(DIRECTORY/"dataset.csv"),
        "parent_native_dataset_sha256":manifest["dataset_sha256"],"features":FEATURES,"original_cases":666,
        "original_training_cases":len(train),"original_test_cases":len(test),"missing_counts":data[FEATURES].isna().sum().astype(int).to_dict(),
        "previously_missing_prior_hr_recovered_from_real_data":int((frame.prior_hr_at_report.isna()&data.lag_hr_bpm.notna()).sum()),
        "previously_missing_baseline_hr_recovered_from_real_data":int((frame.hr_baseline_mean.isna()&data.baseline_hr_bpm.notna()).sum()),
        "cross_midnight_sessions_combined":sum(len(prefixes)>1 for prefixes in grouped),
        "current_borg_in_inputs":False,"synthetic_values":0,"interpolated_minutes":0,"native_cases_dropped":0,
        "feature_definition":"Lag HR is the last actual complete minute ending by the genuine earlier Borg report,within2min. Baseline is the actual mean of complete pre-task minutes from the original published baseline start. Both are past-only; daily files from one session are joined without manufacturing missing samples.",
        "cross_source_context":"CADENCE baseline is lowest seated-rest HR; native baseline is a pre-task mean. Same bpm units, differing aggregation/context retained explicitly. These are inputs to a source representation, not a claim of identical assays or equivalent Borg scales.",
        "lineage":lineage}
    (DIRECTORY/"provenance.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({key:result[key] for key in ("original_cases","missing_counts","previously_missing_prior_hr_recovered_from_real_data",
        "previously_missing_baseline_hr_recovered_from_real_data")}),flush=True)


def load():
    manifest = json.loads((DIRECTORY/"provenance.json").read_text())
    if manifest["dependencies_sha256"] != dependencies() or manifest["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen native physiology/source data changed")
    frame = pd.read_csv(DIRECTORY/"dataset.csv")
    if len(frame) != 666 or frame.row_key.tolist() != [r["row_key"] for r in manifest["lineage"]]:
        raise ValueError("Native input row identities changed")
    return frame,manifest


if __name__ == "__main__":
    prepare()
