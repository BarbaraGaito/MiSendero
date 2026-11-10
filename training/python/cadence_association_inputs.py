"""Original public CADENCE association targets and past-only native inputs.

Source task is retrospective concurrent physiology/RPE association, not a
claim that same-bout source HR is available before the source RPE response.
"""
from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import cadence_lagged_rpe as original_source
import fatigue_cadence_native_inputs as previous_native
from fatigue_dynamics import load_inputs as native_inputs
from fatigue_features import RESEARCH
from public_sources import ROOT, digest, group_key

SOURCE_DIRECTORY = RESEARCH/"cadence-association-source-80-v1"
NATIVE_DIRECTORY = RESEARCH/"cadence-association-native-80-v1"
REVIEW = ROOT/"docs/fatigue-80-2026-10-25/cadence-association-task-review.json"
SOURCE_FEATURES = ["hr_bpm","baseline_hr_bpm","hr_delta_baseline","hr_ratio_baseline"]
NATIVE_FEATURES = ["current_hr_bpm","prior_hr_bpm","baseline_hr_bpm","current_hr_delta_baseline",
                   "current_hr_ratio_baseline","prior_hr_delta_baseline","prior_hr_ratio_baseline"]


def dependencies():
    return {name:digest(path) for name,path in {
        "preparation_code":Path(__file__),"review":REVIEW,"review_code":Path(__file__).with_name("review_cadence_association_task.py"),
        "source_code":Path(original_source.__file__),"original_source_table":original_source.DATA,
        "original_source_provenance":original_source.DIRECTORY/"provenance.json",
        "native_pulse_code":Path(previous_native.__file__),"native_identity_code":Path(previous_native.identities.__file__),
        "original_native_physiology_provenance":previous_native.DIRECTORY/"provenance.json",
        "native_dynamics_provenance":RESEARCH/"dynamics-80-v1/provenance.json",
        "raw_native_archive":previous_native.ARCHIVE,"raw_reports":previous_native.identities.REPORTS,
        "session_metadata":previous_native.identities.SESSIONS,
        "public_real_data_policy":ROOT/"docs/fatigue-80-2026-10-25/public-real-data-policy.json"}.items()}


def checked_review():
    review = json.loads(REVIEW.read_text())
    if (review["review_code_sha256"] != digest(Path(__file__).with_name("review_cadence_association_task.py"))
        or not review["auxiliary_association_review_eligible"] or not review["all_native_used_minutes_completed_by_query"]
        or review["source_current_bout_hr_strictly_before_rpe_claim_approved"]
        or review["source_original_table_sha256"] != digest(original_source.DATA)
        or review["existing_native_input_provenance_sha256"] != digest(previous_native.DIRECTORY/"provenance.json")):
        raise ValueError("Retrospective source-task or causal native-input review changed")
    return review


def prepare():
    for directory in (SOURCE_DIRECTORY,NATIVE_DIRECTORY):
        if (directory/"provenance.json").exists() or (directory/"dataset.csv").exists():
            raise ValueError("Preserve frozen association inputs before another preparation")
    review = checked_review()
    raw = original_source.checked_original()
    _,_,old_source = original_source.load()
    fitting_ids = set(old_source["source_split"]["fitting_original_ids"])
    reserved_ids = set(old_source["source_split"]["reserved_original_ids"])
    if len(fitting_ids) != 124 or len(reserved_ids) != 32 or fitting_ids&reserved_ids:
        raise ValueError("Source whole-person reservation changed")
    source_rows,source_lineage = [],[]
    for index,row in raw.iterrows():
        person,stage = int(row.ID),int(row.stage_number)
        hr,baseline,target = float(row.HR_bpm),float(row.RestHR_bpm),float(row.RPE)
        if not np.isfinite([hr,baseline,target]).all() or not 30 <= hr <= 240 or not 30 <= baseline <= 240 or not 6 <= target <= 20:
            raise ValueError("Source physiology or unchanged source6-20 target is invalid")
        key = group_key(f"CADENCE-adult-original:{person}:T{stage}")
        group = group_key(f"CADENCE-adult-participant:{person}")
        if person not in fitting_ids|reserved_ids:
            raise ValueError("Original source person absent from the fixed reservation")
        partition = "fitting" if person in fitting_ids else "reserved"
        source_rows.append({"row_key":key,"group_key":group,"source_domain":"cadence_adult_concurrent_rpe6to20",
            "source_partition":partition,"stage_number":stage,"hr_bpm":hr,"baseline_hr_bpm":baseline,
            "hr_delta_baseline":hr-baseline,"hr_ratio_baseline":hr/baseline,"rpe_native":target})
        source_lineage.append({"row_key":key,"group_key":group,"source_partition":partition,"original_row":int(index),
            "published_person_id":person,"published_stage":str(row.Stage),"hr_column":"HR_bpm","baseline_column":"RestHR_bpm",
            "rpe_column":"RPE","actual_source_rpe6to20":target,"strictly_before_rpe_input_claim":False})
    source_frame = pd.DataFrame(source_rows)
    if len(source_frame) != 1214 or not source_frame.row_key.is_unique:
        raise ValueError("Original source association target count/identities changed")
    fitting = source_frame.source_partition.eq("fitting")
    if int(fitting.sum()) != 976 or int((~fitting).sum()) != 238:
        raise ValueError("Original source-person split or row eligibility changed")
    frame,train,test,native_manifest,_ = native_inputs()
    old_cache,old_native = previous_native.load()
    old_cache = old_cache.set_index("row_key")
    identities,_ = previous_native.identities.input_rows()
    identities = {r["row_key"]:r for r in identities if r["cohort"] == "canonical"}
    review_by_key = {r["row_key"]:r for r in review["native_lineage"]}
    grouped = defaultdict(list)
    for row in old_native["lineage"]:
        grouped[tuple(row["source_prefixes"])].append(row)
    prepared,lineage = {},{}
    minute = pd.Timedelta(minutes=1)
    with zipfile.ZipFile(previous_native.ARCHIVE) as archive:
        for prefixes,items in sorted(grouped.items()):
            signal,members = previous_native.read_pulse(archive,prefixes,items[0]["participant"])
            for row in items:
                key = row["row_key"]
                identity = identities[key]
                now = pd.Timestamp(identity["current_time_us"],unit="us",tz="UTC")
                start = pd.Timestamp(identity["current_lower_bound_us"],unit="us",tz="UTC")
                window = signal[(signal.index >= start)&(signal.index >= now-2*minute)&(signal.index+minute <= now)]
                current = float(window.iloc[-1]) if len(window) else np.nan
                expected = review_by_key[key]["current_hr_bpm"]
                if not np.isclose(current,np.nan if expected is None else expected,rtol=0,atol=1e-12,equal_nan=True):
                    raise ValueError("Rebuilt measured current HR differs from the reviewed actual minute")
                prior,baseline = float(old_cache.loc[key,"lag_hr_bpm"]),float(old_cache.loc[key,"baseline_hr_bpm"])
                prepared[key] = {"row_key":key,"group_key":row["group_key"],"current_hr_bpm":current,
                    "prior_hr_bpm":prior,"baseline_hr_bpm":baseline,"current_hr_delta_baseline":current-baseline,
                    "current_hr_ratio_baseline":current/baseline if np.isfinite(baseline) and baseline > 0 else np.nan,
                    "prior_hr_delta_baseline":prior-baseline,
                    "prior_hr_ratio_baseline":prior/baseline if np.isfinite(baseline) and baseline > 0 else np.nan}
                lineage[key] = {**row,"current_hr_minute_start":window.index[-1].isoformat() if len(window) else None,
                    "current_hr_minute_end":(window.index[-1]+minute).isoformat() if len(window) else None,
                    "current_hr_source_members":members,"original_snapshot_hr_last":review_by_key[key]["original_snapshot_hr_last"],
                    "newer_actual_current_minute_recovered":review_by_key[key]["newer_actual_current_minute_recovered"]}
    native_frame = pd.DataFrame([prepared[k] for k in frame.row_key])
    if len(native_frame) != 666 or not native_frame.row_key.is_unique or np.isinf(native_frame[NATIVE_FEATURES].to_numpy()).any():
        raise ValueError("Original native identities or past-only measured summaries changed")
    missing = native_frame[NATIVE_FEATURES].isna().sum().astype(int).to_dict()
    if missing != dict(zip(NATIVE_FEATURES,[0,3,8,8,8,11,11])):
        raise ValueError("Natural missing input counts changed; no cases may be filtered")
    if set(source_frame.group_key)&set(frame.group_key):
        raise ValueError("Source/native participant namespaces overlap")
    signature = dependencies()
    for directory,data in ((SOURCE_DIRECTORY,source_frame),(NATIVE_DIRECTORY,native_frame)):
        directory.mkdir(exist_ok=True)
        data.to_csv(directory/"dataset.csv",index=False)
    source_provenance = {"version":1,"dependencies_sha256":signature,"dataset_sha256":digest(SOURCE_DIRECTORY/"dataset.csv"),
        "actual_source_targets":1214,"fitting_actual_targets":976,"reserved_actual_targets":238,
        "fitting_people":124,"reserved_people":32,"source_split":old_source["source_split"],"features":SOURCE_FEATURES,
        "source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC7877025/","source_instrument":"Original Borg6-20, unchanged",
        "source_task":"Retrospective concurrent physiology/RPE association, not a source pre-response forecast",
        "strict_source_pretarget_hr_availability_claim":False,"exact_source_response_clocks_known":False,
        "synthetic_rows":0,"interpolated_targets":0,"native_borg_targets_added":0,"native_target_merge_approved":False,
        "older_cohort_rows_used":0,"model_fitting_started_at_preparation":False,"lineage":source_lineage}
    native_provenance = {"version":1,"dependencies_sha256":signature,"dataset_sha256":digest(NATIVE_DIRECTORY/"dataset.csv"),
        "original_native_dataset_sha256":native_manifest["dataset_sha256"],"original_cases":666,"original_training_cases":len(train),
        "original_test_cases":len(test),"features":NATIVE_FEATURES,"missing_counts":missing,
        "newer_actual_current_hr_minutes_recovered":sum(r["newer_actual_current_minute_recovered"] for r in lineage.values()),
        "original_native_features_overwritten":False,"current_native_borg_in_inputs":False,"synthetic_values":0,
        "native_cases_dropped":0,"interpolated_sensor_samples":0,"all_native_inputs_available_before_query":True,
        "context":"Current HR is last actually completed minute, within2min and current task. Prior HR is last actually completed minute within2min before the genuine earlier Borg. Baseline is original pre-task mean, unlike source lowest seated rest; definitions remain distinct. Cross-midnight files belong to the same actual person/session.",
        "model_fitting_started_at_preparation":False,"lineage":[lineage[k] for k in frame.row_key]}
    for directory,provenance in ((SOURCE_DIRECTORY,source_provenance),(NATIVE_DIRECTORY,native_provenance)):
        (directory/"provenance.json").write_text(json.dumps(provenance,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"source_actual_targets":1214,"source_fitting":976,"source_reserved":238,
        "native_original_cases":666,"native_missing_counts":missing,"newer_actual_current_hr_minutes":2}),flush=True)


def load():
    checked_review()
    expected = dependencies()
    manifests = {}
    frames = {}
    for name,directory in (("source",SOURCE_DIRECTORY),("native",NATIVE_DIRECTORY)):
        provenance = json.loads((directory/"provenance.json").read_text())
        if provenance["dependencies_sha256"] != expected or provenance["dataset_sha256"] != digest(directory/"dataset.csv"):
            raise ValueError("Frozen association source/native input snapshot changed")
        manifests[name],frames[name] = provenance,pd.read_csv(directory/"dataset.csv")
    source_frame,native_frame = frames["source"],frames["native"]
    fitting,reserved = source_frame[source_frame.source_partition.eq("fitting")].copy(),source_frame[source_frame.source_partition.eq("reserved")].copy()
    if len(fitting) != 976 or len(reserved) != 238 or set(fitting.group_key)&set(reserved.group_key) or len(native_frame) != 666:
        raise ValueError("Original source reservation or native case scope changed")
    return fitting,reserved,native_frame,manifests


if __name__ == "__main__":
    prepare()
