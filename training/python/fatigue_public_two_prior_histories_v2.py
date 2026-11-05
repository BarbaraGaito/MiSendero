"""Recover every available real Worker second prior directly from original cells.

The first chain-only snapshot left two genuine responses unavailable because
their intermediate current pair was absent from the prepared fitting table.
Preserve that snapshot and read the original survey cells for this version.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

import fatigue_public_two_prior_histories as previous
from public_sources import digest,group_key

DIRECTORY = previous.DIRECTORY.parent/"public-two-prior-histories-80-v2"
PRIOR,SECOND = previous.PRIOR,previous.SECOND


def dependencies():
    return {name:digest(path) for name,path in {
        "preparation_code":Path(__file__),"previous_chain_preparation_code":Path(previous.__file__),
        "previous_chain_provenance":previous.DIRECTORY/"provenance.json",
        "previous_chain_dataset":previous.DIRECTORY/"dataset.csv",
        "original_worker_survey":previous.parent.previous.SURVEY,
        "original_worker_pair_provenance":previous.parent.previous.DIRECTORY/"provenance.json",
        "original_emap_review":previous.parent.REVIEW,
        "parent_source_input_audit":previous.parent.DOCS/"emap-history-input-verification.json",
        "public_real_data_policy":previous.parent.DOCS/"public-real-data-policy.json"}.items()}


def build():
    old,_ = previous.load()
    output = old.copy()
    original_proof = json.loads((previous.parent.previous.DIRECTORY/"provenance.json").read_text())
    survey = previous.parent.previous.SURVEY
    if digest(survey) != original_proof["original_public_survey_sha256"]:
        raise ValueError("Original public questionnaire changed")
    sheet = openpyxl.load_workbook(survey,data_only=False).worksheets[0]
    columns = {cell.value:cell.column for cell in sheet[1]}
    lineage = {r["current_row_key"]:r for r in original_proof["worker_original_survey_pair_lineage"]}
    by_cell = {(r["worksheet_row"],r["current_column"]):r["current_row_key"] for r in lineage.values()}
    extra,evidence = [],[]
    for index in output.index[output.source_domain.eq("worker")]:
        row = output.loc[index]
        info = lineage[row.row_key]
        repetition = int(re.search(r"\[REP ([1-5])\]",info["current_column"])[1])
        if repetition == 1:
            if np.isfinite(row[SECOND]):
                raise ValueError("Second prior invented before the original pre-experiment questionnaire")
            continue
        second_column = (previous.parent.previous.BASELINE_COLUMN if repetition == 2 else
            info["current_column"].replace(f"[REP {repetition}]",f"[REP {repetition-2}]"))
        cell = sheet.cell(info["worksheet_row"],columns[second_column])
        if cell.data_type == "f" or cell.value is None:
            raise ValueError("A purported actual second prior is missing or a formula")
        value = float(cell.value)
        if not np.isfinite(value) or not 0 <= value <= 10:
            raise ValueError("Original source second prior is outside unscaled CR10")
        key = by_cell.get((info["worksheet_row"],second_column),
            group_key(f"WorkerFatigue-original-survey:{info['worksheet_row']}:{second_column}"))
        if np.isfinite(row[SECOND]):
            if row[SECOND] != value or row.public_ordered_second_prior_row_key != key:
                raise ValueError("Previously observed chain second prior differs from its original cell")
        else:
            extra.append({"row_key":row.row_key,"worksheet_row":info["worksheet_row"],"current_repetition":repetition,
                "actual_second_prior":value,"original_second_prior_column":second_column,"original_cell":cell.coordinate})
        output.loc[index,SECOND] = value
        output.loc[index,"public_ordered_second_prior_row_key"] = key
        evidence.append({"row_key":row.row_key,"group_key":row.group_key,"worksheet_row":info["worksheet_row"],
            "current_repetition":repetition,"original_second_prior_column":second_column,
            "original_second_prior_cell":cell.coordinate,"actual_second_prior":value,"second_prior_row_key":key})
    if len(evidence) != 202 or len(extra) != 2:
        raise ValueError("Direct original-cell recovery counts changed")
    preserved = [name for name in old.columns if name not in (SECOND,"public_ordered_second_prior_row_key")]
    pd.testing.assert_frame_equal(output[preserved],old[preserved])
    observed = old[SECOND].notna()
    np.testing.assert_array_equal(output.loc[observed,SECOND],old.loc[observed,SECOND])
    if len(output) != 607 or output[SECOND].notna().sum() != 405:
        raise ValueError("Actual current targets or available second-prior counts changed")
    return output,evidence,extra


def prepare():
    if (DIRECTORY/"dataset.csv").exists() or (DIRECTORY/"provenance.json").exists():
        raise ValueError("Preserve this frozen direct-cell source version before changing preparation")
    frame,lineage,extra = build()
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY/"dataset.csv",index=False)
    report = {"version":2,"dependencies_sha256":dependencies(),"dataset_sha256":digest(DIRECTORY/"dataset.csv"),
        "actual_current_pairs_preserved":607,"actual_fitting_current_pairs":550,"reserved_emap_current_pairs":57,
        "worker_second_priors_recovered_from_original_cells":202,"previous_chain_worker_second_priors_preserved":200,
        "additional_raw_cells_beyond_chain":extra,"emap_actual_second_priors_preserved":203,"sts_unavailable_second_priors_preserved":49,
        "actual_second_priors":405,"fitting_actual_second_priors":367,"reserved_actual_second_priors":38,
        "naturally_unavailable_second_priors":202,"new_independent_current_observations":0,
        "original_current_targets_and_other_columns_preserved":True,"source_targets_pooled_across_instruments":False,
        "common_history_features":[PRIOR,SECOND],"worker_original_second_prior_lineage":lineage,
        "synthetic_rows":0,"imputed_targets":0,"second_priors_filled_when_unobserved":0,
        "invented_source_times_or_sensor_joins":0,"native_targets_added":0,"model_fitting_started_at_preparation":False,
        "scope":"Same607original current pairs,550fitting/57reserved. Direct original-cell extraction recovers202actual Worker second priors,including2not recoverable from the earlier pair-chain snapshot;200already observed values and203EMAPsecond priors are preserved. All current labels, other original columns and source partitions unchanged. Separate source outcomes only; no new current measurements, generated examples, imputed targets or guessed clocks/phases/sensors."}
    (DIRECTORY/"provenance.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"actual_current_pairs":607,"actual_fitting_pairs":550,"worker_actual_second_priors":202,
        "additional_original_cells_beyond_chain":2,"actual_second_priors":405,"fitting_actual_second_priors":367,
        "new_current_observations":0,"model_fitting_started":False}),flush=True)
    return report


def load():
    report = json.loads((DIRECTORY/"provenance.json").read_text())
    if report["dependencies_sha256"] != dependencies() or report["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen direct original-cell history snapshot changed")
    expected,_,_ = build()
    frame = pd.read_csv(DIRECTORY/"dataset.csv")
    pd.testing.assert_frame_equal(frame,expected,check_dtype=False,rtol=0,atol=1e-12)
    return frame,report


if __name__ == "__main__":
    prepare()
