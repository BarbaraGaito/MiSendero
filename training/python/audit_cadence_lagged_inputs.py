"""Independently verify original source cells and native past-minute inputs."""
import csv
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

import cadence_lagged_rpe as source
import fatigue_cadence_native_inputs as native
from public_sources import RAW, ROOT, digest, group_key


def us(value):
    return int(pd.Timestamp(value).value//1000)


def verify():
    fitting,reserved,manifest = source.load()
    combined = pd.concat([fitting,reserved]).set_index("row_key")
    with source.DATA.open(encoding="utf-8-sig",newline="") as stream:
        raw = list(csv.DictReader(stream))
    by_stage = {(int(row["ID"]),int(row["Stage"][1:])):i for i,row in enumerate(raw)}
    assert len(raw) == len(by_stage) == 1214
    people = sorted({int(row["ID"]) for row in raw})
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    assert manifest["source_split"]["fitting_original_ids"] == [people[i] for i in fit]
    assert manifest["source_split"]["reserved_original_ids"] == [people[i] for i in held]
    assert len(fit) == 124 and len(held) == 32
    observed = []
    for proof in manifest["lineage"]:
        current,prior = raw[proof["original_current_row"]],raw[proof["original_previous_row"]]
        person,stage = int(current["ID"]),int(current["Stage"][1:])
        assert int(prior["ID"]) == person and int(prior["Stage"][1:]) == stage-1
        assert by_stage[person,stage-1] == proof["original_previous_row"]
        assert prior["TermCode"].strip() in ("","NA")
        row = combined.loc[proof["row_key"]]
        assert row.prior_row_key == group_key(f"CADENCE-adult-original:{person}:T{stage-1}")
        assert proof["row_key"] == group_key(f"CADENCE-adult-original:{person}:T{stage}")
        assert row.group_key == group_key(f"CADENCE-adult-participant:{person}")
        assert row.rpe_native == float(current["RPE"]) and row.prior_rpe_native == float(prior["RPE"])
        lag,baseline = float(prior["HR_bpm"]),float(prior["RestHR_bpm"])
        np.testing.assert_allclose(row[source.FEATURES].to_numpy(float),[lag,baseline,lag-baseline,lag/baseline],rtol=0,atol=1e-12)
        partition = "fitting" if person in manifest["source_split"]["fitting_original_ids"] else "reserved"
        assert row.source_partition == proof["source_partition"] == partition
        assert proof["hr_input_row"] == proof["original_previous_row"] and not proof["current_bout_hr_used"]
        assert not proof["exact_report_clock_known"] and not proof["exact_prior_report_age_known"]
        observed.append(proof["row_key"])
    assert len(observed) == len(set(observed)) == 1057
    assert set(observed) == set(combined.index)
    assert len(fitting) == 851 and len(reserved) == 206
    assert not set(fitting.group_key)&set(reserved.group_key)
    excluded = []
    for index,row in enumerate(raw):
        if (int(row["ID"]),int(row["Stage"][1:])-1) not in by_stage:
            excluded.append(index)
    assert excluded == [row["original_row"] for row in manifest["excluded_current_rows"]]
    assert len(excluded) == 157
    assert set(source.FEATURES) == {"lag_hr_bpm","baseline_hr_bpm","hr_delta_baseline","hr_ratio_baseline"}
    assert manifest["older_cohort_rows_used"] == manifest["synthetic_rows"] == manifest["new_native_borg_targets"] == 0
    data,evidence = native.load()
    original,train,test,native_manifest,_ = native.native_inputs()
    assert data.row_key.tolist() == original.row_key.tolist() and len(data) == 666
    assert list(data) == ["row_key","group_key",*native.FEATURES]
    assert evidence["parent_native_dataset_sha256"] == native_manifest["dataset_sha256"]
    reports = pd.read_csv(RAW/"geofatigue/self_reported_fatigue_level.original.tab")
    reports["time"] = pd.to_datetime(reports.time,utc=True)
    sessions = json.loads((RAW/"geofatigue/session_metadata.json").read_text())
    grouped = {}
    for index,proof in enumerate(evidence["lineage"]):
        grouped.setdefault(tuple(proof["source_members"]),[]).append((index,proof))
    native_minutes = 0
    with zipfile.ZipFile(native.ARCHIVE) as archive:
        for members,observations in sorted(grouped.items()):
            samples = {}
            person = observations[0][1]["participant"]
            for member in members:
                records = csv.DictReader(io.StringIO(archive.read(member).decode("utf-8-sig")))
                for row in records:
                    assert row["participant_full_id"].endswith("-"+person)
                    if row["missing_value_reason"] not in ("","NA","NaN","null","NULL","nan"):
                        continue
                    try:
                        value = float(row["pulse_rate_bpm"])
                    except ValueError:
                        continue
                    if not np.isfinite(value) or not 30 <= value <= 240:
                        continue
                    timestamp = float(row["timestamp_unix"])
                    assert timestamp.is_integer()
                    time = int(timestamp)*1000
                    if time in samples:
                        assert abs(samples[time]-value) <= 1e-12
                    samples[time] = value
            for index,proof in observations:
                now = pd.Timestamp(proof["prediction_time_us"],unit="us",tz="UTC")
                matching = [s for s in sessions[person] if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"])]
                assert len(matching) == 1
                session = matching[0]
                tasks = [t for t in session["tasks"] if pd.Timestamp(t["start_time"]) <= now <= pd.Timestamp(t["end_time"])]
                assert len(tasks) == 1
                task = tasks[0]
                start = pd.Timestamp(task["start_time"])
                prior_tasks = [t for t in session["tasks"] if pd.Timestamp(t["end_time"]) <= start]
                previous_end = max([pd.Timestamp(t["end_time"]) for t in prior_tasks],default=pd.Timestamp(session["start_time"]))
                baseline_start = max(start-pd.Timedelta(minutes=5),previous_end,pd.Timestamp(session["start_time"]))
                assert us(start) == proof["task_start_us"] and baseline_start == pd.Timestamp(proof["baseline_start"])
                old = reports[reports.id.eq(person)&(reports.time >= pd.Timestamp(session["start_time"]))
                    &(reports.time >= now-pd.Timedelta(minutes=15))&(reports.time <= now-pd.Timedelta(minutes=1))].sort_values("time")
                assert len(old) and us(old.iloc[-1].time) == proof["prior_report_time_us"]
                prior = proof["prior_report_time_us"]
                eligible = sorted(t for t in samples if prior-120_000_000 <= t and t+60_000_000 <= prior)
                baseline = sorted(t for t in samples if us(baseline_start) <= t and t+60_000_000 <= us(start))
                lag = samples[eligible[-1]] if eligible else np.nan
                base = float(np.mean([samples[t] for t in baseline])) if baseline else np.nan
                expected = [lag,base,lag-base,lag/base if np.isfinite(base) and base > 0 else np.nan]
                np.testing.assert_allclose(data.iloc[index][native.FEATURES].to_numpy(float),expected,rtol=0,atol=1e-10,equal_nan=True)
                expected_lag_start = pd.Timestamp(eligible[-1],unit="us",tz="UTC").isoformat() if eligible else None
                assert proof["lag_hr_minute_start"] == expected_lag_start
                assert proof["baseline_observed_minute_starts"] == [pd.Timestamp(t,unit="us",tz="UTC").isoformat() for t in baseline]
                if eligible:
                    assert eligible[-1]+60_000_000 <= prior <= proof["prediction_time_us"]-60_000_000
                if baseline:
                    assert baseline[-1]+60_000_000 <= us(start) < proof["prediction_time_us"]
                native_minutes += len(baseline)+bool(eligible)
            print(f"Independently reconstructed HR inputs for{len(observations)} actual native cases",flush=True)
    assert len(train) == 487 and len(test) == 179 and not set(train.group_key)&set(test.group_key)
    result = {"version":1,"verification":"passed","audit_code_sha256":digest(Path(__file__)),
        "source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),
        "native_provenance_sha256":digest(native.DIRECTORY/"provenance.json"),
        "source_dataset_sha256":manifest["dataset_sha256"],"native_input_dataset_sha256":evidence["dataset_sha256"],
        "actual_source_current_prior_cells_verified":1057,"actual_source_fitting_targets":851,"actual_source_reserved_targets":206,
        "original_source_people_partitioned_before_eligibility":{"fitting":124,"reserved":32},
        "eligible_source_people":{"fitting":123,"reserved":32},"source_targets_remain_original_borg6to20":True,
        "current_bout_hr_excluded":True,"unknown_report_clocks_not_invented":True,"older_cohort_excluded":True,
        "actual_native_cases_independently_rebuilt":666,"native_observed_minute_visits_rebuilt":int(native_minutes),
        "original_native_training_cases":487,"original_native_test_cases":179,"native_cases_dropped":0,
        "native_missing_counts":evidence["missing_counts"],"native_cross_midnight_sessions":evidence["cross_midnight_sessions_combined"],
        "real_missing_prior_hr_recovered":evidence["previously_missing_prior_hr_recovered_from_real_data"],
        "current_native_targets_in_input_cache":False,"native_target_merge_approved":False,"model_fitting_started":False,
        "synthetic_values":0,"interpolated_inputs":0,
        "scope":"Only measured public source/native observations. Native lag HR ends before actual previous Borg; baseline minutes end before task start. Source uses completed preceding-bout HR and measured seated baseline, with original6-20 targets. Different baseline definitions retained explicitly. Whole-person source reservation and all original native487/179 cases preserved."}
    output = ROOT/"docs/fatigue-80-2026-10-25/cadence-lagged-input-verification.json"
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False),flush=True)
    return result


if __name__ == "__main__":
    verify()
