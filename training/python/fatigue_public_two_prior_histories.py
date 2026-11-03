"""Recover genuine second priors from original public pairs without adding targets."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import fatigue_emap_history_inputs as parent
from public_sources import digest

DIRECTORY = parent.DIRECTORY.parent/"public-two-prior-histories-80-v1"
PRIOR = "public_ordered_actual_prior_rpe"
SECOND = "public_ordered_actual_second_prior_rpe"


def dependencies():
    return {name:digest(path) for name,path in {
        "preparation_code":Path(__file__),"parent_preparation_code":Path(parent.__file__),
        "parent_source_provenance":parent.DIRECTORY/"provenance.json",
        "parent_source_dataset":parent.DIRECTORY/"dataset.csv",
        "parent_source_input_audit":parent.DOCS/"emap-history-input-verification.json",
        "original_worker_survey":parent.previous.SURVEY,
        "original_worker_pair_provenance":parent.previous.DIRECTORY/"provenance.json",
        "original_emap_review":parent.REVIEW,
        "public_real_data_policy":parent.DOCS/"public-real-data-policy.json"}.items()}


def build():
    original,_ = parent.load()
    output = original.copy()
    lookup = original.set_index("row_key")
    second,keys,lineage = [],[],[]
    for row in original.itertuples():
        value,key,origin = np.nan,None,"no_observed_second_prior_in_the_original_snapshot"
        if row.source_domain == "emap":
            if np.isfinite(row.prior2_borg):
                value,key,origin = float(row.prior2_borg),row.prior2_row_key,"original_EMAP_individual_response_cell"
        elif row.prior_row_key in lookup.index:
            previous = lookup.loc[row.prior_row_key]
            if (previous.source_domain != row.source_domain or previous.group_key != row.group_key
                or previous.source_partition != row.source_partition or previous.borg_native != row.prior_borg):
                raise ValueError("A preceding source pair belongs to another person/session or has inconsistent observed RPE")
            value,key,origin = float(previous.prior_borg),previous.prior_row_key,"original_previous_pair_prior_survey_cell"
        if np.isfinite(value) and not 0 <= value <= 10:
            raise ValueError("Original second CR10 response is outside its unchanged scale")
        second.append(value)
        keys.append(key)
        lineage.append({"row_key":row.row_key,"group_key":row.group_key,"source_domain":row.source_domain,
            "source_partition":row.source_partition,"actual_prior_rpe":float(row.prior_borg),
            "actual_second_prior_rpe":None if np.isnan(value) else value,
            "prior_row_key":row.prior_row_key,"second_prior_row_key":key,"origin":origin})
    output[PRIOR] = original.prior_borg.to_numpy(float)
    output[SECOND] = second
    output["public_ordered_second_prior_row_key"] = keys
    pd.testing.assert_frame_equal(output[original.columns],original)
    if len(output) != 607 or not output.row_key.is_unique:
        raise ValueError("Original source current targets were replicated or dropped")
    counts = output.groupby("source_domain")[SECOND].count().astype(int).to_dict()
    if counts != {"emap":203,"sts":0,"worker":200}:
        raise ValueError("Actual second-prior recovery counts changed")
    return output,lineage


def prepare():
    if (DIRECTORY/"dataset.csv").exists() or (DIRECTORY/"provenance.json").exists():
        raise ValueError("Preserve this frozen original-history snapshot before changing preparation")
    frame,lineage = build()
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY/"dataset.csv",index=False)
    counts = {domain:{partition:{"actual_current_targets":len(part),"observed_second_priors":int(part[SECOND].notna().sum()),
        "naturally_unavailable_second_priors":int(part[SECOND].isna().sum())} for partition,part in data.groupby("source_partition")}
        for domain,data in frame.groupby("source_domain")}
    report = {"version":1,"dependencies_sha256":dependencies(),"dataset_sha256":digest(DIRECTORY/"dataset.csv"),
        "actual_current_targets_including_reserved":607,"actual_fitting_current_targets":550,"reserved_emap_current_targets":57,
        "source_counts":counts,"actual_second_priors":403,"additional_genuine_worker_second_priors":200,
        "fitting_actual_second_priors":365,"reserved_actual_second_priors":38,
        "original_columns_and_targets_preserved":True,"new_independent_current_observations":0,
        "source_targets_pooled_across_instruments":False,"common_history_features":[PRIOR,SECOND],
        "synthetic_rows":0,"imputed_targets":0,"second_priors_filled_when_unobserved":0,
        "invented_source_times_or_sensor_joins":0,"native_targets_added":0,"model_fitting_started_at_preparation":False,
        "lineage":lineage,
        "scope":"Same607original current pairs,550fitting/57EMAPreserved. Recover200genuine Worker second priors through verified previous-pair survey-cell lineage; preserve203actual EMAPsecond priors and49STS unavailable second priors. Original columns/targets remain unchanged. The common two-history view supports separate source-outcome tasks without clock/phase/sensor assumptions. No new current responses, generated examples, missing-history fabrication or imputed labels."}
    (DIRECTORY/"provenance.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"actual_current_targets":607,"actual_fitting_targets":550,"additional_genuine_worker_second_priors":200,
        "actual_second_priors":403,"fitting_actual_second_priors":365,"new_current_observations":0,"counts":counts}),flush=True)
    return report


def load():
    report = json.loads((DIRECTORY/"provenance.json").read_text())
    if report["dependencies_sha256"] != dependencies() or report["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen original source second-prior preparation changed")
    expected,_ = build()
    frame = pd.read_csv(DIRECTORY/"dataset.csv")
    pd.testing.assert_frame_equal(frame,expected,check_dtype=False,rtol=0,atol=1e-12)
    return frame,report


if __name__ == "__main__":
    prepare()
