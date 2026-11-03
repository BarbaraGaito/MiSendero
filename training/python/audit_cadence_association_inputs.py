"""Independent raw-cell and completed-minute audit of association inputs."""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

import cadence_association_inputs as prepared
from fatigue_dynamics import load_inputs
from public_sources import RAW, ROOT, digest, group_key


def us(value):
    return int(pd.Timestamp(value).value//1000)


def read_original_member(archive,member,person):
    samples = {}
    for row in csv.DictReader(io.StringIO(archive.read(member).decode("utf-8-sig"))):
        assert row["participant_full_id"].endswith("-"+person)
        if row["missing_value_reason"] not in ("","NA","NaN","null","NULL","nan"):
            continue
        try:
            value = float(row["pulse_rate_bpm"])
        except ValueError:
            continue
        if not np.isfinite(value) or not 30 <= value <= 240:
            continue
        stamp = Decimal(row["timestamp_unix"])*1000
        assert stamp == int(stamp)
        time = int(stamp)
        if time in samples:
            assert abs(samples[time]-value) <= 1e-12
        samples[time] = value
    return samples


def verify():
    fitting,reserved,native,manifests = prepared.load()
    source_manifest,native_manifest = manifests["source"],manifests["native"]
    source = pd.concat([fitting,reserved]).set_index("row_key")
    with prepared.original_source.DATA.open(encoding="utf-8-sig",newline="") as stream:
        raw = list(csv.DictReader(stream))
    people = sorted({int(r["ID"]) for r in raw})
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    fit_ids,held_ids = {people[i] for i in fit},{people[i] for i in held}
    assert len(raw) == len(source) == 1214 and len(people) == 156 and len(fit_ids) == 124 and len(held_ids) == 32
    assert source_manifest["source_split"]["fitting_original_ids"] == [people[i] for i in fit]
    assert source_manifest["source_split"]["reserved_original_ids"] == [people[i] for i in held]
    assert not set(fitting.group_key)&set(reserved.group_key) and len(fitting) == 976 and len(reserved) == 238
    observed = []
    for proof in source_manifest["lineage"]:
        actual = raw[proof["original_row"]]
        person,stage = int(actual["ID"]),int(actual["Stage"][1:])
        key = group_key(f"CADENCE-adult-original:{person}:T{stage}")
        row = source.loc[key]
        assert key == proof["row_key"] and row.group_key == proof["group_key"] == group_key(f"CADENCE-adult-participant:{person}")
        hr,baseline,target = float(actual["HR_bpm"]),float(actual["RestHR_bpm"]),float(actual["RPE"])
        assert row.rpe_native == proof["actual_source_rpe6to20"] == target and 6 <= target <= 20
        np.testing.assert_allclose(row[prepared.SOURCE_FEATURES].to_numpy(float),[hr,baseline,hr-baseline,hr/baseline],rtol=0,atol=1e-12)
        assert row.source_partition == proof["source_partition"] == ("fitting" if person in fit_ids else "reserved")
        assert row.stage_number == stage and not proof["strictly_before_rpe_input_claim"]
        observed.append(key)
    assert len(set(observed)) == 1214 and set(observed) == set(source.index)
    assert not source_manifest["strict_source_pretarget_hr_availability_claim"] and not source_manifest["exact_source_response_clocks_known"]
    assert source_manifest["synthetic_rows"] == source_manifest["interpolated_targets"] == source_manifest["native_borg_targets_added"] == 0
    assert not source_manifest["native_target_merge_approved"] and source_manifest["older_cohort_rows_used"] == 0
    original,train,test,canonical_manifest,_ = load_inputs()
    assert len(native) == 666 and native.row_key.tolist() == original.row_key.tolist()
    assert list(native) == ["row_key","group_key",*prepared.NATIVE_FEATURES] and "label" not in native
    assert native_manifest["original_native_dataset_sha256"] == canonical_manifest["dataset_sha256"]
    reports = pd.read_csv(RAW/"geofatigue/self_reported_fatigue_level.original.tab")
    reports["time"] = pd.to_datetime(reports.time,utc=True)
    assert not reports.duplicated(["id","time"]).any()
    sessions = json.loads((RAW/"geofatigue/session_metadata.json").read_text())
    original_rows = {r["row_key"]:r for r in canonical_manifest["lineage"]}
    identities,expected_prefixes = {},defaultdict(set)
    for key,row in original_rows.items():
        members = [name for name in row["sensor_members"] if name.endswith("_pulse-rate.csv")]
        assert len(members) == 1
        member = members[0]
        person = "p"+re.search(r"/p(\d+)-",member)[1]
        now = pd.Timestamp(row["response_time"])
        matches = [(s,t) for s in sessions[person] for t in s["tasks"]
                   if pd.Timestamp(t["start_time"]) <= now <= pd.Timestamp(t["end_time"])]
        assert len(matches) == 1
        session,task = matches[0]
        session_key = person,us(session["start_time"])
        expected_prefixes[session_key].add(member.split("/digital_biomarkers/")[0])
        identities[key] = person,now,session,task,session_key,member
    grouped = defaultdict(list)
    for index,proof in enumerate(native_manifest["lineage"]):
        person,_,_,_,session_key,_ = identities[proof["row_key"]]
        assert proof["participant"] == person and proof["source_prefixes"] == sorted(expected_prefixes[session_key])
        grouped[tuple(proof["current_hr_source_members"])].append((index,proof))
    minute_visits,changed,newer = 0,0,0
    with zipfile.ZipFile(prepared.previous_native.ARCHIVE) as archive:
        all_names = archive.namelist()
        for members,items in sorted(grouped.items()):
            person = items[0][1]["participant"]
            prefixes = items[0][1]["source_prefixes"]
            expected_members = sorted(name for name in all_names if name.endswith("_pulse-rate.csv")
                and any(name.startswith(prefix+"/digital_biomarkers/aggregated_per_minute/") for prefix in prefixes))
            assert list(members) == expected_members and len(members) == len(prefixes)
            by_member = {member:read_original_member(archive,member,person) for member in members}
            samples = {}
            for values in by_member.values():
                for t,value in values.items():
                    if t in samples:
                        assert abs(samples[t]-value) <= 1e-12
                    samples[t] = value
            for index,proof in items:
                key = proof["row_key"]
                person,now,session,task,_,old_member = identities[key]
                start = pd.Timestamp(task["start_time"])
                previous_tasks = [t for t in session["tasks"] if pd.Timestamp(t["end_time"]) <= start]
                previous_end = max([pd.Timestamp(t["end_time"]) for t in previous_tasks],default=pd.Timestamp(session["start_time"]))
                baseline_start = max(start-pd.Timedelta(minutes=5),previous_end,pd.Timestamp(session["start_time"]))
                assert us(now) == proof["prediction_time_us"] and us(start) == proof["task_start_us"]
                assert baseline_start == pd.Timestamp(proof["baseline_start"])
                past = reports[reports.id.eq(person)&(reports.time >= pd.Timestamp(session["start_time"]))
                    &(reports.time >= now-pd.Timedelta(minutes=15))&(reports.time <= now-pd.Timedelta(minutes=1))].sort_values("time")
                assert len(past)
                prior = past.iloc[-1]
                assert us(prior.time) == proof["prior_report_time_us"] and float(prior.borg_scale) == original.iloc[index].prior_borg
                assert abs((now-prior.time).total_seconds()/60-original.iloc[index].prior_age_minutes) <= 1e-10
                current_times = sorted(t for t in samples if max(us(start),us(now)-120_000_000) <= t and t+60_000_000 <= us(now))
                prior_times = sorted(t for t in samples if us(prior.time)-120_000_000 <= t and t+60_000_000 <= us(prior.time))
                baseline_times = sorted(t for t in samples if us(baseline_start) <= t and t+60_000_000 <= us(start))
                current = samples[current_times[-1]] if current_times else np.nan
                old = samples[prior_times[-1]] if prior_times else np.nan
                baseline = float(np.mean([samples[t] for t in baseline_times])) if baseline_times else np.nan
                expected = [current,old,baseline,current-baseline,current/baseline if np.isfinite(baseline) else np.nan,
                            old-baseline,old/baseline if np.isfinite(baseline) else np.nan]
                np.testing.assert_allclose(native.iloc[index][prepared.NATIVE_FEATURES].to_numpy(float),expected,rtol=0,atol=1e-10,equal_nan=True)
                assert native.iloc[index].row_key == key and native.iloc[index].group_key == original.iloc[index].group_key
                assert proof["current_hr_minute_start"] == (pd.Timestamp(current_times[-1],unit="us",tz="UTC").isoformat() if current_times else None)
                assert proof["lag_hr_minute_start"] == (pd.Timestamp(prior_times[-1],unit="us",tz="UTC").isoformat() if prior_times else None)
                assert proof["baseline_observed_minute_starts"] == [pd.Timestamp(t,unit="us",tz="UTC").isoformat() for t in baseline_times]
                original_times = sorted(t for t in by_member[old_member] if max(us(start),us(now)-120_000_000) <= t and t+60_000_000 <= us(now))
                original_hr = by_member[old_member][original_times[-1]] if original_times else np.nan
                assert np.isclose(original_hr,original.iloc[index].hr_last,rtol=0,atol=1e-12,equal_nan=True)
                is_newer = bool(current_times and original_times and current_times[-1] > original_times[-1])
                assert is_newer == proof["newer_actual_current_minute_recovered"]
                if not np.isclose(current,original_hr,rtol=0,atol=1e-12,equal_nan=True):
                    assert len(prefixes) > 1 and is_newer
                    changed += 1
                newer += int(is_newer)
                if current_times:
                    assert current_times[-1]+60_000_000 <= us(now)
                if prior_times:
                    assert prior_times[-1]+60_000_000 <= us(prior.time) <= us(now)-60_000_000
                if baseline_times:
                    assert baseline_times[-1]+60_000_000 <= us(start) < us(now)
                minute_visits += len(baseline_times)+bool(current_times)+bool(prior_times)
    assert changed == newer == native_manifest["newer_actual_current_hr_minutes_recovered"] == 2
    assert len(train) == 487 and len(test) == 179 and not set(train.group_key)&set(test.group_key)
    assert native[prepared.NATIVE_FEATURES].isna().sum().astype(int).to_dict() == native_manifest["missing_counts"]
    assert native_manifest["native_cases_dropped"] == native_manifest["synthetic_values"] == native_manifest["interpolated_sensor_samples"] == 0
    result = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),"audit_code_sha256":digest(Path(__file__)),
        "source_provenance_sha256":digest(prepared.SOURCE_DIRECTORY/"provenance.json"),
        "native_provenance_sha256":digest(prepared.NATIVE_DIRECTORY/"provenance.json"),
        "source_dataset_sha256":source_manifest["dataset_sha256"],"native_dataset_sha256":native_manifest["dataset_sha256"],
        "source_task_review_sha256":digest(prepared.REVIEW),"source_current_physiology_rpe_cells_independently_verified":1214,
        "source_fitting_actual_targets":976,"source_reserved_actual_targets":238,"source_fitting_people":124,"source_reserved_people":32,
        "source_original6to20_targets_unchanged":True,"source_task_is_retrospective_association":True,
        "source_strict_pretarget_hr_forecasting_claim_approved":False,"source_exact_report_clocks_not_invented":True,
        "actual_native_cases_independently_rebuilt":666,"actual_native_minute_visits_verified":int(minute_visits),
        "original_training_cases":487,"original_test_cases":179,"native_pulse_at_query_completed_by_query":True,
        "native_prior_pulse_completed_by_genuine_prior":True,"native_baseline_completed_before_task":True,
        "native_missing_counts":native_manifest["missing_counts"],"newer_actual_current_minutes_recovered":2,
        "native_input_cache_contains_current_borg_or_ids_as_predictors":False,"native_original_features_overwritten":False,
        "source_labels_became_native_labels":False,"native_cases_dropped":0,"synthetic_values":0,"model_fitting_started":False,
        "scope":"All source1214 original concurrent HR/RPE6-20 records and all native666 original cases verified from raw cells/minutes. Source association has no claimed pre-RPE forecasting chronology. Any future native query may only use actual measurements completed by that query, with genuine earlier Borg as authorized. Separate source/native instruments and baseline definitions, whole-person reservation, natural missing values and original487/179 native targets remain fixed."}
    output = ROOT/"docs/fatigue-80-2026-10-25/cadence-association-input-verification.json"
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False),flush=True)
    return result


if __name__ == "__main__":
    verify()
