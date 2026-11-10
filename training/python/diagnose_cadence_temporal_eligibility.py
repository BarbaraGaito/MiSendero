"""Screen real two-antecedent physiology; no model fitting or target changes."""
from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import cadence_lagged_rpe as source
import fatigue_cadence_native_inputs as physiology
from fatigue_dynamics import load_inputs
from public_sources import RAW, ROOT, digest, group_key


def require(value, reason):
    if not value:
        raise ValueError(reason)


def screen():
    original = source.checked_original()
    fitting,reserved,source_manifest = source.load()
    partition = {r.row_key:r.source_partition for _,r in pd.concat([fitting,reserved]).iterrows()}
    lookup = {(int(r.ID),int(r.stage_number)):(i,r) for i,r in original.iterrows()}
    source_proof = []
    for index,current in original.iterrows():
        person,stage = int(current.ID),int(current.stage_number)
        if (person,stage-1) not in lookup or (person,stage-2) not in lookup:
            continue
        previous_index,previous = lookup[person,stage-1]
        older_index,older = lookup[person,stage-2]
        require(pd.isna(previous.TermCode) and pd.isna(older.TermCode),"A source antecedent was not a completed bout")
        values = [float(previous.HR_bpm),float(older.HR_bpm),float(previous.RestHR_bpm),
                  float(current.RPE),float(previous.RPE),float(older.RPE)]
        require(np.isfinite(values).all() and all(6 <= value <= 20 for value in values[-3:]),
                "Source original measurements or source-native RPE scale changed")
        key = group_key(f"CADENCE-adult-original:{person}:T{stage}")
        require(key in partition,"Temporal source target is outside the existing person reservation")
        source_proof.append({"row_key":key,"group_key":group_key(f"CADENCE-adult-participant:{person}"),
            "source_partition":partition[key],"original_current_row":int(index),"original_previous_row":int(previous_index),
            "original_second_previous_row":int(older_index),"current_rpe6to20":float(current.RPE),
            "previous_rpe6to20":float(previous.RPE),"second_previous_rpe6to20":float(older.RPE),
            "observed_prior_hr_bpm":float(previous.HR_bpm),"observed_second_prior_hr_bpm":float(older.HR_bpm),
            "past_hr_change_bpm":float(previous.HR_bpm-older.HR_bpm),"source_rpe_change":float(current.RPE-previous.RPE)})
    require(len(source_proof) == 901,"Original consecutive source triplet count changed")
    source_counts = {part:sum(r["source_partition"] == part for r in source_proof) for part in ("fitting","reserved")}
    source_people = {part:len({r["group_key"] for r in source_proof if r["source_partition"] == part}) for part in source_counts}
    frame,train,test,manifest,_ = load_inputs()
    native_cache,native_manifest = physiology.load()
    native_cache = native_cache.set_index("row_key")
    raw_reports = pd.read_csv(RAW/"geofatigue/self_reported_fatigue_level.original.tab")
    raw_reports["time"] = pd.to_datetime(raw_reports.time,utc=True)
    require(not raw_reports.duplicated(["id","time"]).any(),"Ambiguous original native responses")
    reports = raw_reports.set_index(["id","time"])
    identities,_ = physiology.identities.input_rows()
    identities = {r["row_key"]:r for r in identities if r["cohort"] == "canonical"}
    histories = {r["row_key"]:r for r in manifest["calibration_lineage"]}
    rows = {r.row_key:r for _,r in frame.iterrows()}
    grouped = defaultdict(list)
    for proof in native_manifest["lineage"]:
        grouped[tuple(proof["source_prefixes"])].append(proof)
    native_proof = []
    minute = pd.Timedelta(minutes=1)
    with zipfile.ZipFile(physiology.ARCHIVE) as archive:
        for prefixes,items in sorted(grouped.items()):
            signal,members = physiology.read_pulse(archive,prefixes,items[0]["participant"])
            for prepared in items:
                key = prepared["row_key"]
                history = histories[key]["previous_observed_reports"]
                identity,native = identities[key],rows[key]
                now = pd.Timestamp(identity["current_time_us"],unit="us",tz="UTC")
                require(pd.Timestamp(histories[key]["prediction_time"]) == now,"Native prediction clock changed")
                previous = history[-1]
                previous_time = pd.Timestamp(previous["response_time"])
                require(previous_time == pd.Timestamp(identity["prior_time_us"],unit="us",tz="UTC")
                        and previous["observed_borg"] == native.prior_borg,"First genuine prior changed")
                observed = reports.loc[(identity["participant"],previous_time),"borg_scale"]
                require(float(observed) == float(native.prior_borg),"First prior does not match original measured response")
                old_time,old_hr,old_minute_start = None,np.nan,None
                if len(history) == 2:
                    old_time = pd.Timestamp(history[0]["response_time"])
                    age = (now-old_time).total_seconds()/60
                    require(old_time < previous_time and 1 <= age <= 15
                            and old_time >= pd.Timestamp(identity["prior_lower_bound_us"],unit="us",tz="UTC")
                            and abs(age-native.prior2_age_minutes) < 1e-10
                            and history[0]["observed_borg"] == native.prior2_borg,
                            "Second prior is not the original actual same-session1-15minute response")
                    observed_old = reports.loc[(identity["participant"],old_time),"borg_scale"]
                    require(float(observed_old) == float(native.prior2_borg),"Second prior was inferred or relabeled")
                    window = signal[(signal.index >= old_time-2*minute)&(signal.index+minute <= old_time)]
                    if len(window):
                        old_hr,old_minute_start = float(window.iloc[-1]),window.index[-1]
                        require(old_minute_start+minute <= old_time < previous_time < now,"Second-prior HR includes future signal")
                else:
                    require(len(history) == 1 and pd.isna(native.prior2_borg),"A missing second prior was invented or dropped")
                latest_hr = float(native_cache.loc[key,"lag_hr_bpm"])
                base = float(native_cache.loc[key,"baseline_hr_bpm"])
                native_proof.append({"row_key":key,"group_key":identity["group_key"],"prior2_response_available":old_time is not None,
                    "prediction_time":now.isoformat(),"prior_response_time":previous_time.isoformat(),
                    "second_prior_response_time":old_time.isoformat() if old_time is not None else None,
                    "second_prior_hr_minute_start":old_minute_start.isoformat() if old_minute_start is not None else None,
                    "second_prior_hr_minute_end":(old_minute_start+minute).isoformat() if old_minute_start is not None else None,
                    "both_past_hr_measured":bool(np.isfinite([latest_hr,old_hr]).all()),
                    "both_past_hr_and_baseline_measured":bool(np.isfinite([latest_hr,old_hr,base]).all()),
                    "second_prior_hr_bpm":old_hr if np.isfinite(old_hr) else None,"source_members":members})
    require(len(native_proof) == 666 and len({r["row_key"] for r in native_proof}) == 666
            and sum(r["prior2_response_available"] for r in native_proof) == 623,"Original native cases/prior availability changed")
    by_key = {r["row_key"]:r for r in native_proof}
    counts = {name:{"original_cases":len(part),"actual_second_prior_responses":sum(by_key[k]["prior2_response_available"] for k in part.row_key),
        "both_past_hr_measured":sum(by_key[k]["both_past_hr_measured"] for k in part.row_key),
        "both_past_hr_and_baseline_measured":sum(by_key[k]["both_past_hr_and_baseline_measured"] for k in part.row_key)}
        for name,part in (("all",frame),("fitting",train),("reserved",test))}
    result = {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"status":"eligibility_screen_completed",
        "code_sha256":digest(Path(__file__)),"source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),
        "native_physiology_provenance_sha256":digest(physiology.DIRECTORY/"provenance.json"),
        "native_dynamics_provenance_sha256":digest(physiology.RESEARCH/"dynamics-80-v1/provenance.json"),
        "raw_native_reports_sha256":digest(RAW/"geofatigue/self_reported_fatigue_level.original.tab"),
        "raw_archive_sha256":digest(physiology.ARCHIVE),"public_real_data_policy_sha256":digest(source.DOCS/"public-real-data-policy.json"),
        "reader_code_sha256":{name:digest(path) for name,path in {"source":Path(source.__file__),
            "native_pulse":Path(physiology.__file__),"native_identity":Path(physiology.identities.__file__)}.items()},
        "source_actual_three_stage_targets":901,"source_partitions":source_counts,"source_eligible_people_by_partition":source_people,
        "source_original_current_rpe_range":[min(r["current_rpe6to20"] for r in source_proof),max(r["current_rpe6to20"] for r in source_proof)],
        "source_observed_rpe_change_range":[min(r["source_rpe_change"] for r in source_proof),max(r["source_rpe_change"] for r in source_proof)],
        "native_actual_input_availability":counts,"original_native_cases_dropped":0,"new_native_targets":0,"synthetic_values":0,
        "source_current_bout_hr_used":False,"invented_exact_source_clocks":0,"model_fitting_started":False,
        "independent_input_audit_still_required_before_model_fitting":True,"source_scale_conversion_approved":False,
        "source_time_policy":"Two completed immediately preceding bouts only; exact source report times remain unknown. Use raw measured HR differences, not slopes per invented minute. Source RPE changes remain differences on original6-20, never native0-10 labels.",
        "native_time_policy":"Two original same-session Borg responses1-15min before prediction; each associated HR is an actual completed minute ending by that response. Missing priors/minutes stay missing; retain all native cases. Baseline contexts still differ across studies.",
        "scope":"Input eligibility screen only, reusing the frozen original pulse reader with its code pinned. No predictor/target dataset or model has been fitted. An independent raw-cell/window audit is needed before any future temporal transfer study.",
        "source_lineage":source_proof,"native_lineage":native_proof}
    output = ROOT/"docs/fatigue-80-2026-10-25/cadence-temporal-eligibility.json"
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","source_actual_three_stage_targets","source_partitions",
        "source_eligible_people_by_partition","native_actual_input_availability","model_fitting_started")}),flush=True)
    return result


if __name__ == "__main__":
    screen()
