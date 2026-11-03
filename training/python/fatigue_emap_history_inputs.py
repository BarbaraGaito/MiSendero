"""Prepare actual ordered EMAP CR10 histories alongside separate Worker/STS rows."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

import fatigue_worker_survey_priors as previous
import fetch_exercise_rpe_candidates as original
from fatigue_features import RESEARCH
from public_sources import ROOT, digest, group_key

DIRECTORY = RESEARCH/"emap-ordered-history-inputs-80-v1"
DOCS = ROOT/"docs/fatigue-80-2026-10-25"
REVIEW = DOCS/"exercise-rpe-original-verification.json"
WORKBOOK_MEMBER = "Data_and_codebook/Data_during_exercise_EMAP.xlsx"
TARGET_COLUMNS = {"emap":"current_rpe","worker":"borg_native","sts":"borg_native"}
FEATURES = {"emap":["prior_borg","prior2_borg"],"worker":["prior_borg"],"sts":["prior_borg"]}


def dependencies():
    return {name:digest(path) for name,path in {
        "preparation_code":Path(__file__),"original_review":REVIEW,
        "original_review_code":Path(__file__).with_name("audit_exercise_rpe_originals.py"),
        "original_archive":original.DIRECTORY/"files/Data_and_codebook.zip",
        "original_file_receipt":original.DIRECTORY/"files-receipt.json",
        "previous_source_provenance":previous.DIRECTORY/"provenance.json",
        "previous_source_preparation":Path(previous.__file__),
        "previous_source_audit":DOCS/"worker-survey-prior-verification.json",
        "public_real_data_policy":DOCS/"public-real-data-policy.json"}.items()}


def build():
    review = json.loads(REVIEW.read_text())
    if (review["verification"] != "passed" or review["audit_code_sha256"] != digest(Path(__file__).with_name("audit_exercise_rpe_originals.py"))
        or not review["auxiliary_ordered_rpe_history_review_eligible"] or review["imputed_or_mean_targets_used"] != 0
        or review["actual_adjacent_rpe_pairs"] != 305 or review["native_target_merge_approved"]):
        raise ValueError("Original public individual CR10 review changed")
    archive_path = original.DIRECTORY/"files/Data_and_codebook.zip"
    receipt = json.loads((original.DIRECTORY/"files-receipt.json").read_text())
    entry = next(r for r in receipt["files"] if r["filename"] == archive_path.name)
    if digest(archive_path) != entry["sha256"] or digest(archive_path,"md5") != entry["repository_md5"]:
        raise ValueError("Original public source archive changed")
    with zipfile.ZipFile(archive_path) as archive:
        payload = archive.read(WORKBOOK_MEMBER)
    if hashlib.sha256(payload).hexdigest() != review["original_member_sha256"]["raw_workbook"]:
        raise ValueError("Original individual-response workbook changed")
    sheet = openpyxl.load_workbook(io.BytesIO(payload),data_only=False)["Feuil1"]
    cells = {int(str(row[0].value).strip()):row for row in sheet.iter_rows(min_row=2,max_col=11) if row[0].value is not None}
    fitting = set(review["source_split"]["fitting_original_ids"])
    reserved = set(review["source_split"]["reserved_original_ids"])
    if len(fitting) != 87 or len(reserved) != 22 or fitting&reserved:
        raise ValueError("Original whole-person split changed")
    observed = {}
    for item in review["response_lineage"]:
        cell = cells[item["published_person_id"]][5+item["questionnaire_slot"]]
        if cell.coordinate != item["original_cell"] or cell.data_type == "f" or cell.value != item["observed_rpe"]:
            raise ValueError("A raw individual response differs from its independent audit")
        observed[item["published_person_id"],item["questionnaire_slot"]] = float(cell.value)
    if len(observed) != 407:
        raise ValueError("Original observed individual responses missing")
    rows,lineage = [],[]
    for pair in review["adjacent_pair_lineage"]:
        person,slot = pair["published_person_id"],pair["current_slot"]
        target,prior = observed[person,slot],observed[person,slot-1]
        second = observed.get((person,slot-2),np.nan)
        if target != pair["actual_current_rpe"] or prior != pair["actual_prior_rpe"]:
            raise ValueError("Actual source ordered pair changed")
        expected_second = pair["actual_second_prior_rpe"]
        if not ((expected_second is None and np.isnan(second)) or expected_second == second):
            raise ValueError("Second actual prior changed or was filled")
        key = group_key(f"EMAP-original-response:{person}:T{slot}")
        row = {"source_domain":"emap","source_partition":"fitting" if person in fitting else "reserved",
            "row_key":key,"group_key":group_key(f"EMAP-original-participant:{person}"),
            "prior_row_key":group_key(f"EMAP-original-response:{person}:T{slot-1}"),
            "prior2_row_key":None if np.isnan(second) else group_key(f"EMAP-original-response:{person}:T{slot-2}"),
            "current_slot":slot,"prior_borg":prior,"prior2_borg":second,"current_rpe":target}
        rows.append(row)
        lineage.append({**pair,"row_key":key,"current_cell":cells[person][5+slot].coordinate,
            "prior_cell":cells[person][4+slot].coordinate,
            "second_prior_cell":None if np.isnan(second) else cells[person][3+slot].coordinate})
    emap = pd.DataFrame(rows)
    old,old_manifest = previous.load()
    old = old.assign(source_partition="fitting")
    for domain,split in old_manifest["external_splits"].items():
        part = old[old.source_domain.eq(domain)]
        if set(part.group_key)&set(split["test_groups"]) or set(part.row_key)&set(split["test_row_keys"]):
            raise ValueError("Reserved previous-source people entered fitting")
    if len(emap) != 305 or len(old) != 302 or set(emap.row_key)&set(old.row_key) or set(emap.group_key)&set(old.group_key):
        raise ValueError("Public source sizes or namespaces changed")
    frame = pd.concat([old,emap],ignore_index=True,sort=False)
    if len(frame) != 607 or not frame.row_key.is_unique:
        raise ValueError("Actual source target duplicated or dropped")
    return frame,lineage,old_manifest


def prepare():
    if (DIRECTORY/"dataset.csv").exists() or (DIRECTORY/"provenance.json").exists():
        raise ValueError("Preserve this frozen actual-source adapter before changing preparation")
    frame,lineage,old_manifest = build()
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY/"dataset.csv",index=False)
    counts = {domain:{partition:{"actual_pairs":len(part),"people":part.group_key.nunique()}
        for partition,part in data.groupby("source_partition")} for domain,data in frame.groupby("source_domain")}
    report = {"version":1,"dependencies_sha256":dependencies(),"dataset_sha256":digest(DIRECTORY/"dataset.csv"),
        "actual_combined_pairs_including_reserved":607,"actual_fitting_pairs":550,"reserved_emap_pairs":57,
        "source_counts":counts,"source_feature_columns":FEATURES,"source_target_columns":TARGET_COLUMNS,
        "source_instruments":{"emap":"Original individual CR10 perceived exertion0-10",
            "worker":"Original physical-fatigue Borg CR10","sts":"Original fractional Borg CR10"},
        "emap_pair_lineage":lineage,"previous_external_splits":old_manifest["external_splits"],
        "source_targets_pooled_across_instruments":False,"new_native_borg_targets":0,
        "exact_source_report_times_or_ages_invented":0,"synthetic_rows":0,"imputed_or_mean_targets":0,
        "new_source_sensor_joins":0,"source_model_fitting_started_at_preparation":False,
        "policy":"Actual measured pairs only;607total including57 EMAPreserved,550fitting(248EMAP/253Worker/49STS). Published109person EMAPcohort whole-person split fixed before response eligibility. Each outcome remains a separate source head with original unscaled target. EMAPuses only genuine prior/second-prior CR10 in recorded order; no exact clocks, phases or HR inferred. Worker/STS use actual prior Borg alone; their original HR columns are preserved but not shared with EMAP. All native487/179 exact labels/cases remain unchanged; no imputed targets, mean/formula responses, synthetic examples or fabricated missing histories."}
    (DIRECTORY/"provenance.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"actual_pairs":607,"fitting_pairs":550,"reserved_emap_pairs":57,"counts":counts,"native_targets_added":0}),flush=True)
    return report


def load():
    report = json.loads((DIRECTORY/"provenance.json").read_text())
    if report["dependencies_sha256"] != dependencies() or report["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen source preparation, raw cells or audit changed")
    expected,_,_ = build()
    frame = pd.read_csv(DIRECTORY/"dataset.csv")
    pd.testing.assert_frame_equal(frame,expected,check_dtype=False,rtol=0,atol=1e-12)
    if frame[frame.source_domain.eq("emap")][["borg_native","hr_last","hr_history_mean"]].notna().any().any():
        raise ValueError("EMAPreceived a fabricated HR join or native target")
    return frame,report


if __name__ == "__main__":
    prepare()
