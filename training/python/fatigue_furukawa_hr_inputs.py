"""Prepare original experiment2 Borg points with strictly preceding HR samples."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import audit_furukawa_original_rpe as original
from public_sources import digest,group_key

DIRECTORY = original.ROOT/"training/data/fatigue-research/furukawa-pre-report-hr-inputs-80-v1"
DOCS = original.DOCS
AUDIT = DOCS/"furukawa-original-rpe-verification.json"
FEATURES = ["hr_last_before_report","hr_recent_60s_mean","hr_history_mean",
    "hr_first_pre_report_mean","prior_report_hr_recent_mean","hr_recent_minus_prior_report_mean"]


def dependencies():
    return {"preparation_code":digest(Path(__file__)),"original_annotation_audit":digest(AUDIT),
        "original_annotation_audit_code":digest(Path(original.__file__)),"protocol_review":digest(original.REVIEW),
        "public_real_data_policy":digest(DOCS/"public-real-data-policy.json")}


def build():
    proof = json.loads(AUDIT.read_text())
    if (proof["verification"] != "passed" or proof["audit_code_sha256"] != digest(Path(original.__file__))
        or proof["protocol_review_sha256"] != digest(original.REVIEW) or not proof["auxiliary_pre_report_hr_task_eligible"]
        or proof["native_target_merge_approved"] or proof["synthetic_rows"] != 0):
        raise ValueError("Independent original experiment2 HR/RPE audit changed")
    rpe,rpe_file = original.read_original("rpe")
    hr,hr_file = original.read_original("hr")
    if proof["original_files"]["rpe"] != rpe_file or proof["original_files"]["hr"] != hr_file:
        raise ValueError("Original experiment2 source identity changed")
    fitting,reserved = set(proof["whole_person_split"]["fitting_original_people"]),set(proof["whole_person_split"]["reserved_original_people"])
    rows,lineage = [],[]
    for condition in sorted(rpe):
        target,measurements = rpe[condition],hr[condition]
        for person in original.PEOPLE:
            if person not in fitting|reserved:
                raise ValueError("Unassigned original source participant")
            first_points = [v[person] for t,v in measurements["values"].items() if 0 <= t < 60]
            first_mean = float(np.mean(first_points))
            for number,stamp in enumerate((60,180,300)):
                times = sorted(t for t in measurements["values"] if t < stamp)
                recent = [t for t in times if t >= stamp-60]
                prior = (60,180,300)[number-1] if number else None
                second = (60,180,300)[number-2] if number > 1 else None
                prior_times = [] if prior is None else [t for t in measurements["values"] if prior-60 <= t < prior]
                prior_mean = float(np.mean([measurements["values"][t][person] for t in prior_times])) if prior_times else np.nan
                recent_mean = float(np.mean([measurements["values"][t][person] for t in recent]))
                row_key = group_key(f"Furukawa2023-original-exp2:{condition}:{person}:RPE:{stamp}")
                rows.append({"row_key":row_key,"group_key":group_key(f"Furukawa2023-original-exp2-person:{person}"),
                    "sequence_key":group_key(f"Furukawa2023-original-exp2-condition:{condition}:person:{person}"),
                    "source_domain":"furukawa_exp2_original_points","source_partition":"fitting" if person in fitting else "reserved",
                    "original_person_header":person,"original_condition":condition,"elapsed_seconds":stamp,
                    "original_rpe_points":target["values"][stamp][person],"original_rpe_cell":target["coordinates"][stamp][person],
                    "prior_rpe_points":np.nan if prior is None else target["values"][prior][person],
                    "second_prior_rpe_points":np.nan if second is None else target["values"][second][person],
                    "prior_rpe_elapsed_seconds":np.nan if prior is None else prior,
                    "second_prior_rpe_elapsed_seconds":np.nan if second is None else second,
                    "prior_rpe_age_minutes":np.nan if prior is None else (stamp-prior)/60,
                    "hr_last_before_report":measurements["values"][times[-1]][person],"hr_recent_60s_mean":recent_mean,
                    "hr_history_mean":float(np.mean([measurements["values"][t][person] for t in times])),
                    "hr_first_pre_report_mean":first_mean,"prior_report_hr_recent_mean":prior_mean,
                    "hr_recent_minus_prior_report_mean":recent_mean-prior_mean,
                    "hr_recent_samples":len(recent),"hr_history_samples":len(times),"hr_last_elapsed_seconds":times[-1]})
                lineage.append({"row_key":row_key,"original_rpe_sheet":target["original_sheet"],"original_rpe_cell":target["coordinates"][stamp][person],
                    "original_hr_sheet":measurements["original_sheet"],"strictly_preceding_hr_cells":[measurements["coordinates"][t][person] for t in times],
                    "hr_recent_60s_cells":[measurements["coordinates"][t][person] for t in recent],
                    "prior_report_hr_recent_cells":[measurements["coordinates"][t][person] for t in sorted(prior_times)],
                    "maximum_hr_elapsed_seconds":times[-1],"current_rpe_elapsed_seconds":stamp})
    frame = pd.DataFrame(rows)
    if len(frame) != 336 or not frame.row_key.is_unique or frame.source_partition.eq("fitting").sum() != 252:
        raise ValueError("Original experiment2 source cases changed")
    return frame,lineage,proof


def prepare():
    if (DIRECTORY/"dataset.csv").exists() or (DIRECTORY/"provenance.json").exists():
        raise ValueError("Preserve the frozen original HR/RPE preparation before changing it")
    frame,lineage,proof = build()
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY/"dataset.csv",index=False)
    provenance = {"version":1,"dependencies_sha256":dependencies(),"dataset_sha256":digest(DIRECTORY/"dataset.csv"),
        "original_target_column":"original_rpe_points","actual_source_responses":336,"actual_source_fitting_targets":252,
        "actual_source_fitting_people":12,"reserved_source_targets":84,"reserved_source_people":4,
        "source_fitting_actual_adjacent_pairs":168,"source_fitting_actual_second_priors":84,
        "source_actual_hr_features":FEATURES,"whole_person_split":proof["whole_person_split"],"response_lineage":lineage,
        "original_outcome_points_preserved_separately":True,"original_scale_not_converted_to_native_borg":True,
        "first_pre_report_hr_is_during_running_not_rest":True,"source_rest_hr_or_individual_age_assumed":False,
        "all_hr_timestamps_strictly_before_current_rpe":True,"new_native_targets":0,"synthetic_rows":0,
        "interpolated_or_imputed_sensor_points":0,"step_frequency_native_mapping_used":False,"model_fitting_started_at_preparation":False,
        "scope":"Experiment2only336original reported Borg-point cells and actually earlier HRpoint samples,252fitting/84reserved by12/4original people. Original target,prior andsecond-prior points retain their scale. No cross-condition/experiment histories,imputed samples,supplied learned labels,source age/rest invention or native label conversion. HRfirst-minute reference is observed during running,not a rest measurement. Source targets remain separate from native487/179cases."}
    (DIRECTORY/"provenance.json").write_text(json.dumps(provenance,indent=2,ensure_ascii=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:provenance[k] for k in ("actual_source_responses","actual_source_fitting_targets","reserved_source_targets","source_fitting_actual_adjacent_pairs","source_fitting_actual_second_priors","new_native_targets","synthetic_rows","model_fitting_started_at_preparation")}),flush=True)
    return provenance


def load():
    provenance = json.loads((DIRECTORY/"provenance.json").read_text())
    if provenance["dependencies_sha256"] != dependencies() or provenance["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen original pre-report HR source preparation changed")
    frame = pd.read_csv(DIRECTORY/"dataset.csv")
    expected,_,_ = build()
    pd.testing.assert_frame_equal(frame,expected,check_dtype=False,rtol=0,atol=1e-12)
    return frame,provenance


if __name__ == "__main__":
    prepare()
