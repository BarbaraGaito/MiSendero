"""Actual CADENCE adult targets with strictly earlier completed-bout HR.

Keep original Borg6-20. Reserve source people before fitting. No current-bout
physiology, invented response clocks, gap filling, or older-cohort ID repairs.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

import fetch_cadence_cloud as source
from fatigue_features import RESEARCH
from public_sources import ROOT, digest, group_key

DIRECTORY = RESEARCH/"cadence-lagged-rpe-80-v1"
DOCS = ROOT/"docs/fatigue-80-2026-10-25"
DATA = source.DIRECTORY/"PMC7877025.1/12966_2021_1096_MOESM1_ESM.csv"
FEATURES = ["lag_hr_bpm","baseline_hr_bpm","hr_delta_baseline","hr_ratio_baseline"]


def dependencies():
    return {name:digest(path) for name,path in {
        "preparation_code":Path(__file__),"retrieval_code":Path(source.__file__),
        "eligibility_code":Path(__file__).with_name("audit_cadence_candidates.py"),
        "eligibility_review":DOCS/"cadence-eligibility.json","source_receipt":source.DIRECTORY/"receipt.json",
        "adult_table":DATA,"public_real_data_policy":DOCS/"public-real-data-policy.json"}.items()}


def checked_original():
    receipt = json.loads((source.DIRECTORY/"receipt.json").read_text())
    if receipt["code_sha256"] != digest(Path(source.__file__)):
        raise ValueError("Frozen public cloud source retrieval changed")
    for entry in receipt["files"]:
        path = source.DIRECTORY/entry["local_path"]
        if digest(path) != entry["sha256"] or ("repository_md5" in entry and digest(path,"md5") != entry["repository_md5"]):
            raise ValueError("Public CADENCE bytes differ from frozen repository hashes")
    audit = json.loads((DOCS/"cadence-eligibility.json").read_text())
    if audit["audit_code_sha256"] != digest(Path(__file__).with_name("audit_cadence_candidates.py")) or not audit["cohorts"]["adult"]["identity_stage_screen_passed"]:
        raise ValueError("Adult identity/scale eligibility evidence changed")
    if audit["cohorts"]["adult"]["data_sha256"] != digest(DATA) or audit["cohorts"]["older"]["identity_stage_screen_passed"]:
        raise ValueError("Original adult source changed or older identity failures were accepted")
    frame = pd.read_csv(DATA)
    frame["stage_number"] = frame.Stage.str.extract(r"^T([1-9][0-9]*)$",expand=False).astype(int)
    if len(frame) != 1214 or frame.ID.nunique() != 156 or frame.duplicated(["ID","stage_number"]).any():
        raise ValueError("Expected original adult rows and unique within-person stages")
    if not frame.TreadmillSpeed_MPH.eq(.5*frame.stage_number).all():
        raise ValueError("Observed stages disagree with prescribed treadmill order")
    return frame


def prepare():
    if (DIRECTORY/"provenance.json").exists() or (DIRECTORY/"dataset.csv").exists():
        raise ValueError("Preserve frozen source adapter before changing it")
    raw = checked_original()
    people = np.sort(raw.ID.unique())
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    fitting_ids,held_ids = people[fit].astype(int).tolist(),people[held].astype(int).tolist()
    if len(fitting_ids) != 124 or len(held_ids) != 32 or set(fitting_ids)&set(held_ids):
        raise ValueError("Frozen whole-person source reservation changed")
    lookup = {(int(row.ID),int(row.stage_number)):(index,row) for index,row in raw.iterrows()}
    records,lineage,excluded = [],[],[]
    for index,current in raw.iterrows():
        person,stage = int(current.ID),int(current.stage_number)
        old = lookup.get((person,stage-1))
        if old is None:
            excluded.append({"original_row":int(index),"person_id":person,"stage":stage,
                             "reason":"No original immediately preceding stage; no gap bridging or onset zero"})
            continue
        prior_index,prior = old
        if pd.notna(prior.TermCode):
            raise ValueError("A supposedly completed preceding bout has a termination marker; inspect original order")
        key = group_key(f"CADENCE-adult-original:{person}:T{stage}")
        prior_key = group_key(f"CADENCE-adult-original:{person}:T{stage-1}")
        group = group_key(f"CADENCE-adult-participant:{person}")
        lag,baseline = float(prior.HR_bpm),float(prior.RestHR_bpm)
        target,previous = float(current.RPE),float(prior.RPE)
        if not np.isfinite([lag,baseline,target,previous]).all() or baseline <= 0 or not 6 <= target <= 20 or not 6 <= previous <= 20:
            raise ValueError("Actual source physiology or original RPE is invalid")
        partition = "fitting" if person in fitting_ids else "reserved"
        records.append({"row_key":key,"prior_row_key":prior_key,"group_key":group,"source_domain":"cadence_adult_rpe6to20",
            "source_partition":partition,"stage_number":stage,"prior_stage_number":stage-1,
            "lag_hr_bpm":lag,"baseline_hr_bpm":baseline,"hr_delta_baseline":lag-baseline,"hr_ratio_baseline":lag/baseline,
            "prior_rpe_native":previous,"rpe_native":target})
        lineage.append({"row_key":key,"prior_row_key":prior_key,"group_key":group,"source_partition":partition,
            "original_current_row":int(index),"original_previous_row":int(prior_index),"published_person_id":person,
            "published_stage":str(current.Stage),"published_previous_stage":str(prior.Stage),
            "rpe_column":"RPE","hr_input_row":int(prior_index),"hr_input_column":"HR_bpm",
            "baseline_input_column":"RestHR_bpm","actual_current_rpe":target,"actual_previous_rpe":previous,
            "current_bout_hr_used":False,"exact_report_clock_known":False,"exact_prior_report_age_known":False})
    frame = pd.DataFrame(records)
    if len(frame) != 1057 or len(excluded) != 157 or not frame.row_key.is_unique:
        raise ValueError("Actual adjacent-stage source targets changed")
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY/"dataset.csv",index=False)
    fitting,reserved = frame.source_partition.eq("fitting"),frame.source_partition.eq("reserved")
    result = {"version":1,"dependencies_sha256":dependencies(),"dataset_sha256":digest(DIRECTORY/"dataset.csv"),
        "source":"https://pmc.ncbi.nlm.nih.gov/articles/PMC7877025/","doi":"10.1186/s12966-021-01096-w",
        "source_instrument":"Original Borg6-20, never rescaled to native0-10",
        "raw_actual_reports":1214,"raw_adult_people":156,"actual_adjacent_targets":len(frame),
        "fitting_actual_targets":int(fitting.sum()),"reserved_actual_targets":int(reserved.sum()),
        "fitting_people_with_eligible_targets":int(frame.loc[fitting,"group_key"].nunique()),
        "reserved_people_with_eligible_targets":int(frame.loc[reserved,"group_key"].nunique()),
        "source_split":{"method":"GroupShuffleSplit20percent,seed42,original156 people before target eligibility",
            "fitting_original_ids":fitting_ids,"reserved_original_ids":held_ids,
            "fitting_groups":[group_key(f"CADENCE-adult-participant:{person}") for person in fitting_ids],
            "reserved_groups":[group_key(f"CADENCE-adult-participant:{person}") for person in held_ids]},
        "features":FEATURES,"current_bout_hr_inputs":0,"older_cohort_rows_used":0,"synthetic_rows":0,
        "assumed_onset_rpe":0,"interpolated_targets":0,"invented_exact_report_ages":0,"new_native_borg_targets":0,
        "feature_definitions":{"lag_hr_bpm":"Original immediately preceding bout HR average over2:45-4:45, completed before the current bout response",
            "baseline_hr_bpm":"Original lowest observed seated-rest HR before the treadmill protocol",
            "hr_delta_baseline":"Measured lagged HR minus measured baseline HR",
            "hr_ratio_baseline":"Measured lagged HR divided by measured baseline HR"},
        "time_policy":"Known source stage order and completed previous bout establish past-only inputs. Exact response clocks/ages remain unknown. Nominal5min bouts/2min rests are protocol metadata, not invented measured timestamps. Prior RPE is retained only as original lineage, not a proposed cross-scale model predictor. Current-bout physiology is excluded.",
        "model_fitting_started_at_preparation":False,"native_target_merge_approved":False,
        "excluded_current_rows":excluded,"lineage":lineage}
    (DIRECTORY/"provenance.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({key:result[key] for key in ("actual_adjacent_targets","fitting_actual_targets","reserved_actual_targets",
        "fitting_people_with_eligible_targets","reserved_people_with_eligible_targets")}),flush=True)


def load():
    manifest = json.loads((DIRECTORY/"provenance.json").read_text())
    if manifest["dependencies_sha256"] != dependencies() or manifest["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen source inputs, split, code, public-data policy or eligibility evidence changed")
    checked_original()
    frame = pd.read_csv(DIRECTORY/"dataset.csv")
    fitting,reserved = frame[frame.source_partition.eq("fitting")].copy(),frame[frame.source_partition.eq("reserved")].copy()
    if set(fitting.group_key)&set(reserved.group_key) or len(fitting)+len(reserved) != 1057:
        raise ValueError("Source person boundary or actual source target count changed")
    return fitting,reserved,manifest


if __name__ == "__main__":
    prepare()
