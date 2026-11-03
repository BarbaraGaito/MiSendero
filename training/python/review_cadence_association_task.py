"""Review a retrospective source task separately from native causal inference.

An external concurrent HR/RPE association is not a source forecasting claim.
It can only produce computed representations from actual past native sensors;
source labels never become native labels and native test people never supervise it.
"""
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
from public_sources import ROOT, digest


def require(value, reason):
    if not value:
        raise ValueError(reason)


def review():
    raw = source.checked_original()
    old_fitting,old_reserved,source_manifest = source.load()
    fitting_ids = set(source_manifest["source_split"]["fitting_original_ids"])
    reserved_ids = set(source_manifest["source_split"]["reserved_original_ids"])
    fitting,reserved = raw[raw.ID.isin(fitting_ids)],raw[raw.ID.isin(reserved_ids)]
    require(len(fitting) == 976 and len(reserved) == 238 and len(fitting_ids) == 124 and len(reserved_ids) == 32
            and not fitting_ids&reserved_ids and len(raw) == 1214,"Original source person reservation changed")
    require(np.isfinite(raw[["HR_bpm","RestHR_bpm","RPE"]].to_numpy(float)).all()
            and raw.HR_bpm.between(30,240).all() and raw.RestHR_bpm.between(30,240).all()
            and raw.RPE.between(6,20).all(),"Source measured physiology or original6-20 targets changed")
    # Compare the current and lagged association on the identical851 fitting
    # targets, not on either reserved cohort and not across different row sets.
    lineages = [r for r in source_manifest["lineage"] if r["source_partition"] == "fitting"]
    current_indices = [r["original_current_row"] for r in lineages]
    require([r["row_key"] for r in lineages] == old_fitting.row_key.tolist(),"Matched source diagnostic order changed")
    current = raw.loc[current_indices]
    np.testing.assert_array_equal(current.RPE.to_numpy(float),old_fitting.rpe_native.to_numpy(float))
    source_diagnostics = {"same_fitting_targets":851,
        "concurrent_current_hr_current_rpe_pearson":float(np.corrcoef(current.HR_bpm,old_fitting.rpe_native)[0,1]),
        "earlier_bout_hr_current_rpe_pearson":float(np.corrcoef(old_fitting.lag_hr_bpm,old_fitting.rpe_native)[0,1]),
        "reserved_targets_used":0,"model_fitting_performed":False}
    frame,train,test,native_source_manifest,_ = load_inputs()
    cache,native_manifest = physiology.load()
    cache = cache.set_index("row_key")
    native = frame.set_index("row_key")
    original_members = {}
    for row in native_source_manifest["lineage"]:
        members = [name for name in row["sensor_members"] if name.endswith("_pulse-rate.csv")]
        require(len(members) == 1,"Original native HR member is ambiguous")
        original_members[row["row_key"]] = members[0]
    identities,_ = physiology.identities.input_rows()
    identities = {r["row_key"]:r for r in identities if r["cohort"] == "canonical"}
    grouped = defaultdict(list)
    for row in native_manifest["lineage"]:
        grouped[tuple(row["source_prefixes"])].append(row)
    minute = pd.Timedelta(minutes=1)
    lineage = []
    old_file_cache = {}
    with zipfile.ZipFile(physiology.ARCHIVE) as archive:
        for prefixes,items in sorted(grouped.items()):
            signal,members = physiology.read_pulse(archive,prefixes,items[0]["participant"])
            for row in items:
                identity = identities[row["row_key"]]
                now = pd.Timestamp(identity["current_time_us"],unit="us",tz="UTC")
                start = pd.Timestamp(identity["current_lower_bound_us"],unit="us",tz="UTC")
                window = signal[(signal.index >= start)&(signal.index >= now-2*minute)&(signal.index+minute <= now)]
                current_hr = float(window.iloc[-1]) if len(window) else np.nan
                original_hr = float(native.loc[row["row_key"],"hr_last"])
                original_member = original_members[row["row_key"]]
                require(original_member in members,"Original current HR came from a different participant/session")
                if len(prefixes) == 1:
                    old_signal = signal
                else:
                    if original_member not in old_file_cache:
                        prefix = original_member.split("/digital_biomarkers/")[0]
                        old_file_cache[original_member] = physiology.read_pulse(archive,(prefix,),row["participant"])[0]
                    old_signal = old_file_cache[original_member]
                old_window = old_signal[(old_signal.index >= start)&(old_signal.index >= now-2*minute)&(old_signal.index+minute <= now)]
                original_rebuilt = float(old_window.iloc[-1]) if len(old_window) else np.nan
                require(np.isclose(original_rebuilt,original_hr,rtol=0,atol=1e-12,equal_nan=True),
                        "Original-file completed-minute reconstruction differs from the frozen native predictor")
                newer_actual_minute = bool(len(window) and len(old_window) and window.index[-1] > old_window.index[-1])
                changed_value = not bool(np.isclose(current_hr,original_hr,rtol=0,atol=1e-12,equal_nan=True))
                if changed_value:
                    require(len(prefixes) > 1 and newer_actual_minute,
                            "Current HR changed without a newer actual past minute from the same cross-midnight session")
                if len(window):
                    require(window.index[-1]+minute <= now and window.index[-1] >= start,"Native current HR includes future or wrong-task measurements")
                baseline = float(cache.loc[row["row_key"],"baseline_hr_bpm"])
                prior = float(cache.loc[row["row_key"],"lag_hr_bpm"])
                lineage.append({"row_key":row["row_key"],"group_key":row["group_key"],"prediction_time":now.isoformat(),
                    "current_hr_minute_start":window.index[-1].isoformat() if len(window) else None,
                    "current_hr_minute_end":(window.index[-1]+minute).isoformat() if len(window) else None,
                    "current_hr_bpm":current_hr if np.isfinite(current_hr) else None,"source_members":members,
                    "original_hr_member":original_member,"original_snapshot_hr_last":original_hr if np.isfinite(original_hr) else None,
                    "original_hr_minute_start":old_window.index[-1].isoformat() if len(old_window) else None,
                    "original_hr_minute_end":(old_window.index[-1]+minute).isoformat() if len(old_window) else None,
                    "newer_actual_current_minute_recovered":newer_actual_minute,"current_hr_value_changed":changed_value,
                    "current_hr_and_baseline_available":bool(np.isfinite([current_hr,baseline]).all()),
                    "current_prior_hr_and_baseline_available":bool(np.isfinite([current_hr,prior,baseline]).all())})
    require(len(lineage) == 666 and len({r["row_key"] for r in lineage}) == 666,"Native current-HR review changed original cases")
    by_key = {r["row_key"]:r for r in lineage}
    availability = {name:{"original_cases":len(part),"past_complete_current_hr":sum(by_key[k]["current_hr_bpm"] is not None for k in part.row_key),
        "current_hr_and_baseline":sum(by_key[k]["current_hr_and_baseline_available"] for k in part.row_key),
        "current_prior_hr_and_baseline":sum(by_key[k]["current_prior_hr_and_baseline_available"] for k in part.row_key)}
        for name,part in (("all",frame),("fitting",train),("reserved",test))}
    policy = source.DOCS/"public-real-data-policy.json"
    result = {"version":1,"reviewed_at":datetime.now(timezone.utc).isoformat(),"status":"retrospective_auxiliary_task_review_completed",
        "review_code_sha256":digest(Path(__file__)),"source_original_table_sha256":digest(source.DATA),
        "existing_source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),
        "existing_native_input_provenance_sha256":digest(physiology.DIRECTORY/"provenance.json"),
        "source_eligibility_sha256":digest(source.DOCS/"cadence-eligibility.json"),"public_real_data_policy_sha256":digest(policy),
        "reader_code_sha256":{name:digest(path) for name,path in {"source":Path(source.__file__),"native_pulse":Path(physiology.__file__),
            "native_identity":Path(physiology.identities.__file__)}.items()},"raw_archive_sha256":digest(physiology.ARCHIVE),
        "source_actual_original_targets":1214,"source_fitting_targets":976,"source_reserved_targets":238,
        "source_fitting_people":124,"source_reserved_people":32,"source_person_split_changed":False,
        "source_target_instrument":"Original observed Borg6-20, no conversion to native0-10",
        "source_target_task":"Retrospective concurrent association of recorded same-bout HR/restingHR with source RPE; not a source real-time forecast",
        "source_current_bout_hr_strictly_before_rpe_claim_approved":False,"exact_source_response_clocks_known":False,
        "auxiliary_association_review_eligible":True,"source_only_fitting_required":True,
        "source_diagnostic_on_identical_fitting_targets":source_diagnostics,"native_measured_input_availability":availability,
        "native_current_hr_original_values_independently_compared":True,"all_native_used_minutes_completed_by_query":True,
        "native_newer_current_minutes_recovered":sum(r["newer_actual_current_minute_recovered"] for r in lineage),
        "native_current_hr_values_changed_from_newer_observed_minutes":sum(r["current_hr_value_changed"] for r in lineage),
        "frozen_original_native_features_modified":False,
        "native_input_case_count":666,"native_cases_removed":0,"new_native_targets":0,"synthetic_rows":0,
        "model_fitting_started":False,"versioned_adapter_and_independent_raw_input_audit_required":True,
        "rationale":[
            "The earlier lagged studies asked source functions to forecast a later bout's RPE. Uncertain source report clocks correctly prohibit claiming that same-bout averagedHR is an available pre-RPE forecasting input.",
            "A separate retrospective source association task can learn from actual concurrent public physiology and its original source instrument. This does not prove a causal effect or make that association an operational source forecaster.",
            "A future native model may only query the frozen association function with native sensor measurements completed before the native prediction time. No source RPE or current native Borg can enter a native query.",
            "Computed source-scale states and their differences would remain representations, not new observations or converted native labels. Only original native fitting people may calibrate their relationship to native Borg.",
            "This task change needs a separate frozen data adapter and independent raw-cell/native-window verification. The earlier source pre-RPE timing exclusion and different source/native baseline definitions remain valid.",
            "Source reserved people remain unused for fitting or selection. Model usefulness and hyperparameters must be assessed on original native participant CV, with every original native case retained."
        ],"native_lineage":lineage}
    output = ROOT/"docs/fatigue-80-2026-10-25/cadence-association-task-review.json"
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({key:result[key] for key in ("status","source_actual_original_targets","source_fitting_targets","source_reserved_targets",
        "source_diagnostic_on_identical_fitting_targets","native_measured_input_availability","model_fitting_started")}),flush=True)
    return result


if __name__ == "__main__":
    review()
