"""Recover genuine WorkerFatigue earlier survey cells, never assumed zeros."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import fatigue_source_transitions as parent
from public_sources import ROOT, digest, group_key

DIRECTORY = parent.baseline.RESEARCH/"source-survey-prior-transitions-80-v1"
SURVEY = ROOT/"training/data/raw/fatigue-research/worker-fatigue/USER FORM RESPONSE.xlsx"
BASELINE_COLUMN = "What is your physical fatigue level currently [Pre-experiment] ?"


def build():
    sources, manifests, splits = parent.source_inputs()
    existing, previous_provenance = parent.load_sources()
    if digest(SURVEY) != manifests["worker"]["original_survey_sha256"]:
        raise ValueError("Original public physical-fatigue questionnaire changed")
    survey = pd.read_excel(SURVEY)
    lineage = {r["row_key"]:r for r in manifests["worker"]["lineage"]}
    allowed = sources["worker"]
    if allowed.row_key.tolist() != splits["worker"]["train_row_keys"] or set(allowed.group_key) & set(splits["worker"]["test_groups"]):
        raise ValueError("A held-out WorkerFatigue person/report entered the real-prior table")
    by_cell = {(lineage[key]["questionnaire_worksheet_row"], lineage[key]["questionnaire_column"]):key for key in allowed.row_key}
    rows, evidence = [], []
    old = existing[existing.source_domain.eq("worker")].set_index("row_key")
    for current in allowed.itertuples():
        record = lineage[current.row_key]
        sheetrow, current_col = record["questionnaire_worksheet_row"], record["questionnaire_column"]
        rep = int(re.search(r"\[REP ([1-5])\]", current_col)[1])
        prior_col = BASELINE_COLUMN if rep == 1 else current_col.replace(f"[REP {rep}]", f"[REP {rep-1}]")
        original = survey.iloc[sheetrow-2]
        session = re.search(r"_(P\d+[CZ]\d+S\d+)\.csv$", record["sensor_member"])[1]
        if str(original["Test"]).strip() != session:
            raise ValueError("Original prior survey belongs to a different source session")
        target, previous = pd.to_numeric(original[current_col],errors="coerce"), pd.to_numeric(original[prior_col],errors="coerce")
        if not np.isfinite([target,previous]).all() or not 0 <= target <= 10 or not 0 <= previous <= 10:
            raise ValueError("A source physical-fatigue survey is missing or outside original CR10; no filling permitted")
        if target != current.borg_native or target != record["published_borg"]:
            raise ValueError("The observed current source Borg changed")
        prior_key = by_cell.get((sheetrow,prior_col), group_key(f"WorkerFatigue-original-survey:{sheetrow}:{prior_col}"))
        if current.row_key in old.index:
            if previous != old.loc[current.row_key,"prior_borg"] or prior_key != old.loc[current.row_key,"prior_row_key"]:
                raise ValueError("A previously verified actual prior changed")
        rows.append({"source_domain":"worker","row_key":current.row_key,"prior_row_key":prior_key,
            "group_key":current.group_key,"prior_borg":float(previous),"borg_native":float(target),
            "hr_last":current.hr_last,"hr_history_mean":current.hr_history_mean})
        evidence.append({"current_row_key":current.row_key,"worksheet_row":int(sheetrow),"source_session":session,
            "current_column":current_col,"prior_column":prior_col,"current_borg":float(target),"prior_borg":float(previous),
            "prior_row_key":prior_key,"prior_is_pre_experiment_survey":rep == 1,
            "timing":"Published pre-experiment survey precedes repetition one; each later actual survey follows the preceding repetition. Exact survey times/ages are not invented."})
    sts = existing[existing.source_domain.eq("sts")]
    data = pd.concat([pd.DataFrame(rows),sts],ignore_index=True)[existing.columns]
    if len(data) != 302 or not data.row_key.is_unique or len(rows) != 253 or len(sts) != 49:
        raise ValueError("Expanded real-prior source counts changed")
    return data, evidence, splits, previous_provenance


def prepare():
    data, lineage, splits, old = build()
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY/"dataset.csv"
    if path.exists():
        raise ValueError("Preserve the frozen original-survey-prior snapshot before preparing another version")
    data.to_csv(path,index=False)
    baseline = [r for r in lineage if r["prior_is_pre_experiment_survey"]]
    provenance = {"version":1,"code_sha256":digest(Path(__file__)),"dataset_sha256":digest(path),
        "original_public_survey_sha256":digest(SURVEY),"parent_provenance_sha256":digest(parent.SOURCE_DIRECTORY/"provenance.json"),
        "parent_code_sha256":digest(Path(parent.__file__)),"actual_source_targets":302,
        "counts":{"worker":253,"sts":49},"participants":data.group_key.nunique(),
        "additional_real_current_targets_with_an_observed_prior":53,"genuine_pre_experiment_prior_cells":len(baseline),
        "pre_experiment_prior_value_counts":{str(k):v for k,v in pd.Series([r["prior_borg"] for r in baseline]).value_counts().sort_index().to_dict().items()},
        "worker_original_survey_pair_lineage":lineage,"external_splits":{name:splits[name] for name in ("worker","sts")},
        "synthetic_sensor_rows":0,"synthetic_targets":0,"assumed_zero_priors":0,"invented_survey_timestamps":0,
        "new_independent_questionnaire_measurements":0,"new_native_borg_targets":0,"native_target_merge":False,
        "features":parent.FEATURES,"used_for_new_model_fitting":False,
        "policy":"Recover previous Borg from actual original public questionnaire cells. Nonzero pre-experiment Borg is retained. Missing preceding sensor rows do not erase a real earlier survey cell. Earlier survey time is known only by protocol order, so no source age/time is assigned. Actual current targets are the same already audited original source reports, not fabricated extra observations. Original native 487/179 cases stay unchanged."}
    (DIRECTORY/"provenance.json").write_text(json.dumps(provenance,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"actual_source_targets_with_real_prior":302,"additional_eligible_existing_targets":53,
        "genuine_baseline_priors":len(baseline),"baseline_value_counts":provenance["pre_experiment_prior_value_counts"],"new_native_targets":0}),flush=True)


def load():
    provenance=json.loads((DIRECTORY/"provenance.json").read_text())
    if (digest(Path(__file__)) != provenance["code_sha256"] or digest(DIRECTORY/"dataset.csv") != provenance["dataset_sha256"]
            or digest(SURVEY) != provenance["original_public_survey_sha256"] or digest(Path(parent.__file__)) != provenance["parent_code_sha256"]
            or digest(parent.SOURCE_DIRECTORY/"provenance.json") != provenance["parent_provenance_sha256"]):
        raise ValueError("Frozen original-survey-prior source changed")
    return pd.read_csv(DIRECTORY/"dataset.csv"), provenance


if __name__ == "__main__":
    prepare()
