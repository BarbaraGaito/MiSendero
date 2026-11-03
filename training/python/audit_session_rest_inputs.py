"""Independently reconstruct every measured pre-first-task baseline window."""
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import fatigue_session_rest_inputs as prepared
from audit_cadence_association_inputs import read_original_member, us
from fatigue_dynamics import load_inputs
from public_sources import RAW, ROOT, digest


def verify():
    data,manifest = prepared.load()
    original,train,test,canonical,_ = load_inputs()
    assert data.row_key.tolist() == original.row_key.tolist() and len(data) == 666
    assert list(data) == ["row_key","group_key",*prepared.FEATURES]
    assert "label" not in data and manifest["original_native_dataset_sha256"] == canonical["dataset_sha256"]
    sessions = json.loads((RAW/"geofatigue/session_metadata.json").read_text())
    identities,prefixes = {},defaultdict(set)
    for row in canonical["lineage"]:
        members = [name for name in row["sensor_members"] if name.endswith("_pulse-rate.csv")]
        assert len(members) == 1
        member = members[0]
        person = "p"+re.search(r"/p(\d+)-",member)[1]
        now = pd.Timestamp(row["response_time"])
        matches = [s for s in sessions[person] if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"])]
        assert len(matches) == 1
        session = matches[0]
        session_key = person,us(session["start_time"])
        prefixes[session_key].add(member.split("/digital_biomarkers/")[0])
        identities[row["row_key"]] = person,now,session,session_key
    grouped = defaultdict(list)
    for index,proof in enumerate(manifest["lineage"]):
        person,now,session,session_key = identities[proof["row_key"]]
        assert proof["participant"] == person and pd.Timestamp(proof["prediction_time"]) == now
        assert proof["source_prefixes"] == sorted(prefixes[session_key])
        grouped[tuple(proof["source_members"])].append((index,proof))
    sessions_count,available_sessions,unique_minutes,case_minute_visits = 0,0,0,0
    with zipfile.ZipFile(prepared.association.previous_native.ARCHIVE) as archive:
        names = archive.namelist()
        for members,items in sorted(grouped.items()):
            person = items[0][1]["participant"]
            expected_members = sorted(name for name in names if name.endswith("_pulse-rate.csv")
                and any(name.startswith(prefix+"/digital_biomarkers/aggregated_per_minute/") for prefix in items[0][1]["source_prefixes"]))
            assert list(members) == expected_members
            samples = {}
            for member in members:
                for time,value in read_original_member(archive,member,person).items():
                    if time in samples:
                        assert abs(samples[time]-value) <= 1e-12
                    samples[time] = value
            window_signature = None
            for index,proof in items:
                key = proof["row_key"]
                person,now,session,_ = identities[key]
                first_task = min(pd.Timestamp(task["start_time"]) for task in session["tasks"])
                lower = max(pd.Timestamp(session["start_time"]),first_task-pd.Timedelta(minutes=5))
                eligible = sorted(t for t in samples if us(lower) <= t and t+60_000_000 <= us(first_task))
                expected_mean = float(np.mean([samples[t] for t in eligible])) if eligible else np.nan
                expected_minimum = float(np.min([samples[t] for t in eligible])) if eligible else np.nan
                np.testing.assert_allclose(data.iloc[index][prepared.FEATURES].to_numpy(float),[expected_mean,expected_minimum],rtol=0,atol=1e-10,equal_nan=True)
                assert data.iloc[index].row_key == key and data.iloc[index].group_key == original.iloc[index].group_key
                assert pd.Timestamp(proof["session_start"]) == pd.Timestamp(session["start_time"])
                assert pd.Timestamp(proof["first_task_start"]) == first_task and pd.Timestamp(proof["baseline_lower_bound"]) == lower
                assert first_task < now
                assert proof["actual_observed_minute_starts"] == [pd.Timestamp(t,unit="us",tz="UTC").isoformat() for t in eligible]
                assert proof["latest_observed_minute_end"] == (pd.Timestamp(eligible[-1]+60_000_000,unit="us",tz="UTC").isoformat() if eligible else None)
                if eligible:
                    assert eligible[-1]+60_000_000 <= us(first_task) < us(now)
                if window_signature is None:
                    window_signature = tuple(eligible)
                    unique_minutes += len(eligible)
                    available_sessions += int(bool(eligible))
                else:
                    assert tuple(eligible) == window_signature
                case_minute_visits += len(eligible)
            sessions_count += 1
    assert sessions_count == manifest["actual_sessions"] == 44
    assert available_sessions == manifest["sessions_with_observed_baseline"] == 42
    assert unique_minutes == manifest["actual_complete_baseline_minutes_across_sessions"]
    assert data[prepared.FEATURES].isna().sum().astype(int).to_dict() == manifest["natural_missing_counts"] == dict.fromkeys(prepared.FEATURES,30)
    assert len(train) == manifest["original_training_cases"] == 487 and len(test) == manifest["original_test_cases"] == 179
    assert not set(train.group_key)&set(test.group_key)
    assert not manifest["native_current_targets_in_cache"] and not manifest["original_features_overwritten"]
    assert manifest["native_cases_dropped"] == manifest["synthetic_rows"] == manifest["interpolated_minutes"] == 0
    result = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),"audit_code_sha256":digest(Path(__file__)),
        "raw_csv_reader_code_sha256":digest(Path(__file__).with_name("audit_cadence_association_inputs.py")),
        "input_provenance_sha256":digest(prepared.DIRECTORY/"provenance.json"),"input_dataset_sha256":manifest["dataset_sha256"],
        "original_native_cases_independently_verified":666,"original_training_cases":487,"original_test_cases":179,
        "actual_sessions":sessions_count,"sessions_with_observed_preexercise_baseline":available_sessions,
        "actual_complete_minutes_across_unique_sessions":unique_minutes,"baseline_minute_case_visits_verified":case_minute_visits,
        "natural_missing_baselines_per_feature":30,"all_used_minutes_completed_before_first_task_and_query":True,
        "current_native_borg_in_cache":False,"participant_ids_are_model_features":False,"native_case_filtering":False,
        "original_native_features_overwritten":False,"synthetic_values":0,"new_model_fitting_started":False,
        "scope":"Actual mean/minimum pre-first-task pulse from the original same-person/session raw CSVs. Repeated use of a known session baseline adds no fitting observations. No assumed rest posture, generated minutes, target conversion, missing-case removal, future data or changed native487/179 cases."}
    output = ROOT/"docs/fatigue-80-2026-10-25/session-rest-input-verification.json"
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False),flush=True)
    return result


if __name__ == "__main__":
    verify()
