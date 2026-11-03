"""Independently check each expanded source pair against original survey cells."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import fatigue_worker_survey_priors as study
from public_sources import ROOT, digest


def validate():
    data, provenance = study.load()
    sources, manifests, splits = study.parent.source_inputs()
    original = sources["worker"].set_index("row_key",drop=False)
    survey = pd.read_excel(study.SURVEY)
    lineage = {r["row_key"]:r for r in manifests["worker"]["lineage"]}
    old, _ = study.parent.load_sources()
    assert data.row_key.is_unique and len(data) == 302
    assert provenance["synthetic_sensor_rows"] == provenance["synthetic_targets"] == provenance["assumed_zero_priors"] == provenance["invented_survey_timestamps"] == 0
    assert provenance["new_native_borg_targets"] == provenance["new_independent_questionnaire_measurements"] == 0
    assert provenance["used_for_new_model_fitting"] is False
    baseline_values, newly_usable, prior_without_sensor_row = [], 0, 0
    for row in data[data.source_domain.eq("worker")].itertuples():
        current = original.loc[row.row_key]
        evidence = lineage[row.row_key]
        sheet = survey.iloc[evidence["questionnaire_worksheet_row"]-2]
        rep = int(re.search(r"\[REP ([1-5])\]",evidence["questionnaire_column"])[1])
        previous_column = study.BASELINE_COLUMN if rep == 1 else f"What is your physical fatigue level currently [REP {rep-1}] ?"
        assert row.borg_native == current.borg_native == sheet[evidence["questionnaire_column"]]
        assert row.prior_borg == sheet[previous_column] and 0 <= row.prior_borg <= 10
        assert row.group_key == current.group_key and row.group_key not in splits["worker"]["test_groups"]
        np.testing.assert_allclose([row.hr_last,row.hr_history_mean],[current.hr_last,current.hr_history_mean],rtol=0,atol=1e-12,equal_nan=True)
        if rep == 1:
            baseline_values.append(row.prior_borg)
        elif row.prior_row_key not in set(original.index):
            prior_without_sensor_row += 1
        newly_usable += int(row.row_key not in set(old.row_key))
    pd.testing.assert_frame_equal(data[data.source_domain.eq("sts")].reset_index(drop=True),old[old.source_domain.eq("sts")].reset_index(drop=True))
    for name in ("worker","sts"):
        part = data[data.source_domain.eq(name)]
        assert not set(part.row_key) & set(splits[name]["test_row_keys"])
        assert not set(part.group_key) & set(splits[name]["test_groups"])
    counts = {str(k):v for k,v in pd.Series(baseline_values).value_counts().sort_index().to_dict().items()}
    assert len(baseline_values) == 51 and sum(v > 0 for v in baseline_values) == 39
    assert newly_usable == 53 and prior_without_sensor_row == 2
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "source_dataset_sha256":provenance["dataset_sha256"],"source_provenance_sha256":digest(study.DIRECTORY/"provenance.json"),
        "original_public_survey_sha256":digest(study.SURVEY),"actual_source_targets_with_real_prior":302,
        "source_counts":{"worker":253,"sts":49},"additional_usable_existing_targets":53,
        "actual_pre_experiment_priors_checked":51,"nonzero_pre_experiment_priors":39,"pre_experiment_prior_counts":counts,
        "previous_real_survey_present_despite_missing_previous_sensor_case":2,
        "all_current_source_borg_values_unchanged":True,"external_reserved_people_excluded":True,
        "synthetic_rows":0,"assumed_zero_priors":0,"invented_survey_timestamps":0,
        "new_native_borg_targets":0,"new_independent_questionnaire_measurements":0,"used_for_new_model_fitting":False,
        "scope":"Original observed public questionnaire cells only. Earlier pre-experiment and repetition reports are inputs, not assumed zeros or fabricated timestamps. This preparation extends source pair eligibility; no model improvement or new native test result is claimed."}


if __name__ == "__main__":
    result=validate()
    path=ROOT/"docs/fatigue-80-2026-10-25/worker-survey-prior-verification.json"
    path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"real_source_pairs_verified":302,"additional_existing_source_targets_usable":53,"nonzero_baselines_preserved":39,"new_native_borg_targets":0}))
