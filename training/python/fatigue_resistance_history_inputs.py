"""Combine genuine original resistance histories with the existing public pairs."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

import fatigue_public_two_prior_histories_v2 as previous
import fetch_more_public_rpe_metadata as repository
from public_sources import ROOT,digest,group_key

DIRECTORY = previous.DIRECTORY.parent/"resistance-expanded-history-inputs-80-v1"
DOCS = ROOT/"docs/fatigue-80-2026-10-25"
AUDIT = DOCS/"resistance-reported-rpe-verification.json"
PRIOR,SECOND = previous.PRIOR,previous.SECOND
TARGETS = {"emap":"current_rpe","worker":"borg_native","sts":"borg_native","resistance":"original_resistance_rpe"}


def dependencies():
    return {name:digest(path) for name,path in {
        "preparation_code":Path(__file__),"previous_preparation_code":Path(previous.__file__),
        "previous_provenance":previous.DIRECTORY/"provenance.json",
        "previous_source_input_audit":DOCS/"public-two-prior-history-v2-verification.json",
        "original_resistance_annotation_audit":AUDIT,
        "original_resistance_annotation_audit_code":Path(__file__).with_name("audit_resistance_reported_rpe.py"),
        "original_resistance_archive_receipt":repository.DIRECTORY/"resistance-archive-receipt.json",
        "public_real_data_policy":DOCS/"public-real-data-policy.json"}.items()}


def build():
    proof = json.loads(AUDIT.read_text())
    if (proof["verification"] != "passed" or proof["audit_code_sha256"] != digest(Path(__file__).with_name("audit_resistance_reported_rpe.py"))
        or not proof["auxiliary_ordered_history_eligible"] or proof["native_target_merge_approved"]
        or proof["synthetic_rows"] != 0 or proof["original_manual_reports"] != 1003):
        raise ValueError("Independent original manually reported RPE review changed")
    receipt = json.loads((repository.DIRECTORY/"resistance-archive-receipt.json").read_text())
    archive_path = repository.DIRECTORY/receipt["local_filename"]
    if digest(archive_path) != receipt["sha256"] or digest(archive_path) != proof["original_archive_sha256"]:
        raise ValueError("Fixed original resistance archive changed")
    with zipfile.ZipFile(archive_path) as archive:
        payload = archive.read(proof["original_annotation_member"])
    if hashlib.sha256(payload).hexdigest() != proof["original_annotation_member_sha256"]:
        raise ValueError("Original manual RPE CSV changed")
    data = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))
    fitting = set(proof["whole_person_split"]["fitting_original_people"])
    reserved = set(proof["whole_person_split"]["reserved_original_people"])
    rows = []
    for column,set_id in enumerate(data[0]):
        person = set_id.split("_")[0]
        if person not in fitting|reserved:
            raise ValueError("Original source person is absent from its pre-eligibility whole-person split")
        sequence = {index:float(row[column]) for index,row in enumerate(data[2:]) if len(row)>column and row[column].strip()}
        for index,current in sequence.items():
            if index-1 not in sequence:
                continue
            rows.append({"source_domain":"resistance","source_partition":"fitting" if person in fitting else "reserved",
                "row_key":group_key(f"Resistance-original-RPE:{set_id}:{index}"),
                "group_key":group_key(f"Resistance-original-participant:{person}"),
                "sequence_key":group_key(f"Resistance-original-set:{set_id}"),"original_set_id":set_id,
                "original_repetition_index_zero_based":index,"original_resistance_rpe":current,
                PRIOR:sequence[index-1],SECOND:sequence.get(index-2,np.nan),
                "prior_row_key":group_key(f"Resistance-original-RPE:{set_id}:{index-1}"),
                "public_ordered_second_prior_row_key":None if index-2 not in sequence else group_key(f"Resistance-original-RPE:{set_id}:{index-2}"),
                "original_rpe_csv_line":index+3,"original_rpe_csv_column":column+1})
    additional = pd.DataFrame(rows)
    old,manifest = previous.load()
    if len(additional) != 934 or set(additional.row_key)&set(old.row_key) or set(additional.group_key)&set(old.group_key):
        raise ValueError("Original resistance current targets were duplicated or source namespaces collide")
    frame = pd.concat([old,additional],ignore_index=True,sort=False)
    if len(frame) != 1541 or not frame.row_key.is_unique:
        raise ValueError("Original source current pairs were changed during combination")
    pd.testing.assert_frame_equal(frame[frame.source_domain.ne("resistance")][old.columns].reset_index(drop=True),old,check_dtype=False,rtol=0,atol=0)
    return frame,proof,manifest


def prepare():
    if (DIRECTORY/"dataset.csv").exists() or (DIRECTORY/"provenance.json").exists():
        raise ValueError("Preserve this frozen real-source expansion before changing preparation")
    frame,proof,old = build()
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY/"dataset.csv",index=False)
    fitting,reserved = frame[frame.source_partition.eq("fitting")],frame[frame.source_partition.eq("reserved")]
    counts = {domain:{partition:{"actual_pairs":len(part),"people":part.group_key.nunique(),"actual_second_priors":int(part[SECOND].notna().sum())}
        for partition,part in data.groupby("source_partition")} for domain,data in frame.groupby("source_domain")}
    if len(fitting) != 1416 or len(reserved) != 125 or fitting[SECOND].notna().sum() != 1169:
        raise ValueError("Expanded actual-source fit/reserved history counts changed")
    report = {"version":1,"dependencies_sha256":dependencies(),"dataset_sha256":digest(DIRECTORY/"dataset.csv"),
        "actual_source_pairs_including_stored_reserved":1541,"actual_source_fitting_targets":1416,
        "existing_source_fitting_targets_preserved":550,"additional_resistance_fitting_targets":866,
        "additional_resistance_fitting_people":4,"additional_resistance_reserved_targets":68,"additional_resistance_reserved_people":1,
        "stored_reserved_targets":125,"source_counts":counts,"source_fitting_actual_second_priors":1169,
        "source_current_target_columns":TARGETS,"common_measured_history_features":[PRIOR,SECOND],
        "original_manual_resistance_reports":1003,"original_manual_resistance_sets":69,
        "original_resistance_report_verification_sha256":digest(AUDIT),"resistance_source_split":proof["whole_person_split"],
        "source_outcomes_must_remain_separate":True,"native_target_merge":False,"new_native_borg_targets":0,
        "synthetic_rows":0,"imputed_targets":0,"invented_source_ages_or_phase_mapping":0,"new_sensor_joins":0,
        "model_fitting_started_at_preparation":False,
        "scope":"Union of607previous actual source pairs and934original resistance adjacent pairs. Existing550fitting/57EMAPreserved preserved; new866resistance fitting/68reserved fixed by whole original person before pair eligibility. Current labels are direct original manual cells,not supplied learned EMG labels or SMOTE/jitter rows. Resistance1-10 outcomes remain a separate source head; no native0-10 label conversion. Only actual within-set previous/second-previous reports,with natural missing second history. No inferred ages,rest times,sensor alignment or walking-phase equivalence; original native487/179cases unchanged."}
    (DIRECTORY/"provenance.json").write_text(json.dumps(report,indent=2,ensure_ascii=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"actual_combined_fitting_targets":1416,"previous_fitting_targets_preserved":550,
        "additional_resistance_fitting_targets":866,"new_resistance_reserved_targets":68,"source_fitting_actual_second_priors":1169,
        "new_native_targets":0,"model_fitting_started":False}),flush=True)
    return report


def load():
    report = json.loads((DIRECTORY/"provenance.json").read_text())
    if report["dependencies_sha256"] != dependencies() or report["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen original resistance-history source expansion changed")
    expected,_,_ = build()
    frame = pd.read_csv(DIRECTORY/"dataset.csv")
    pd.testing.assert_frame_equal(frame,expected,check_dtype=False,rtol=0,atol=1e-12)
    return frame,report


if __name__ == "__main__":
    prepare()
