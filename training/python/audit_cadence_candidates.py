"""Review original CADENCE identities, scales and temporal eligibility.

No model fitting, scale conversion, ID repair or new report timestamps.
"""
import csv
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

import fetch_cadence_cloud as source
from public_sources import ROOT, digest

FILES = {"adult":("PMC7877025.1/12966_2021_1096_MOESM1_ESM.csv", "PMC7877025.1/12966_2021_1096_MOESM2_ESM.xlsx"),
         "older":("PMC10688086.1/12966_2023_1543_MOESM2_ESM.xlsx", "PMC10688086.1/12966_2023_1543_MOESM3_ESM.xlsx")}
STATIC = ["Age_years","Sex","HeightCMAvg","WeightKGAvg","RestHR_bpm"]


def review():
    root = source.DIRECTORY
    receipt = json.loads((root/"receipt.json").read_text())
    dictionary = json.loads((root/"older-dictionary-receipt.json").read_text())
    assert receipt["code_sha256"] == digest(Path(source.__file__))
    assert dictionary["code_sha256"] == digest(Path(__file__).with_name("fetch_cadence_dictionary.py"))
    assert dictionary["article_metadata_sha256"] == digest(root/"PMC10688086.1.json")
    assert dictionary["sha256"] == digest(root/dictionary["local_path"])
    assert dictionary["repository_md5"] == digest(root/dictionary["local_path"],"md5")
    for entry in receipt["files"]:
        assert entry["sha256"] == digest(root/entry["local_path"])
        if "repository_md5" in entry:
            assert entry["repository_md5"] == digest(root/entry["local_path"],"md5")
    cohorts = {}
    for name,(data_name, dictionary_name) in FILES.items():
        data_path, dictionary_path = root/data_name, root/dictionary_name
        if data_path.suffix == ".csv":
            with data_path.open(encoding="utf-8-sig",newline="") as stream:
                original_rows = list(csv.DictReader(stream))
            frame = pd.read_csv(data_path)
            assert len(original_rows) == len(frame)
            np.testing.assert_array_equal([float(row["RPE"]) for row in original_rows],frame.RPE.to_numpy())
        else:
            book = load_workbook(data_path,read_only=True,data_only=True)
            rows = list(book[book.sheetnames[0]].values)
            columns = list(rows[0])
            original_rows = [dict(zip(columns,row)) for row in rows[1:] if row[0] is not None]
            book.close()
            frame = pd.read_excel(data_path)
            assert len(original_rows) == len(frame)
            np.testing.assert_array_equal([row["RPE"] for row in original_rows],frame.RPE.to_numpy())
        definitions = pd.read_excel(dictionary_path).set_index("Variable")
        assert all(column in frame for column in ["ID","Stage","RPE","HR_bpm",*STATIC])
        assert "6 to 20 Borg scale" in definitions.loc["RPE","Description"]
        assert "last minute" in definitions.loc["RPE","Description"]
        assert "2:45" in definitions.loc["HR_bpm","Description"] and "4:45" in definitions.loc["HR_bpm","Description"]
        assert frame[["ID","Stage","RPE","HR_bpm",*STATIC]].notna().all().all()
        assert np.isfinite(frame.RPE).all() and frame.RPE.between(6,20).all() and frame.HR_bpm.between(20,250).all()
        assert frame.RPE.eq(frame.RPE.round()).all()
        stage = frame.Stage.str.extract(r"^T([1-9][0-9]*)$",expand=False)
        assert stage.notna().all()
        frame = frame.assign(stage_number=stage.astype(int))
        duplicate = frame[frame.duplicated(["ID","Stage"],keep=False)]
        inconsistent = frame.groupby("ID")[STATIC].nunique(dropna=False).gt(1).any(axis=1)
        inconsistent_ids = inconsistent[inconsistent].index.astype(int).tolist()
        missing_predecessor = 0
        adjacent = 0
        for _, person in frame.groupby("ID"):
            stages = person.stage_number.tolist()
            for current in stages:
                if current <= 1:
                    continue
                if stages.count(current) == 1 and stages.count(current-1) == 1:
                    adjacent += 1
                else:
                    missing_predecessor += 1
        valid = duplicate.empty and not inconsistent_ids
        article = "PMC7877025.1" if name == "adult" else "PMC10688086.1"
        protocol = (root/article/(article+".txt")).read_text(encoding="utf-8")
        assert "2-minute" in protocol or "2-min" in protocol
        assert "last minute" in protocol and "6 to 20" in protocol
        cohorts[name] = {"data_path":data_name,"data_sha256":digest(data_path),"dictionary_path":dictionary_name,
            "dictionary_sha256":digest(dictionary_path),"article_text_sha256":digest(root/article/(article+".txt")),
            "original_rows":len(frame),"identifier_count":int(frame.ID.nunique()),"columns":list(frame.drop(columns="stage_number")),
            "original_rpe_cells_verified":len(original_rows),"rpe_range":[float(frame.RPE.min()),float(frame.RPE.max())],
            "age_range":[float(frame.Age_years.min()),float(frame.Age_years.max())],
            "duplicate_id_stage_rows":len(duplicate),"duplicate_id_stage_extra_rows":int(frame.duplicated(["ID","Stage"]).sum()),
            "ids_with_inconsistent_static_fields":inconsistent_ids,
            "adjacent_stage_target_rows_before_eligibility_filter":adjacent,
            "target_rows_without_unique_immediate_prior":missing_predecessor,
            "identity_stage_screen_passed":valid,"cohort_approved_for_preparation_review":valid,
            "cohort_used_for_fitting":False,"invented_or_repaired_identifiers":0,
            "decision":"Eligible for a separately audited, source-only lagged-input adapter; reserve source people before fitting." if valid else
                "Exclude the entire older cohort from fitting until source identity inconsistencies are resolved. Do not infer replacements from age/sex, row position or numerical similarity."}
    assert cohorts["adult"]["original_rows"] == 1214 and cohorts["adult"]["identifier_count"] == 156
    assert cohorts["adult"]["identity_stage_screen_passed"]
    assert cohorts["older"]["original_rows"] == 550 and cohorts["older"]["identifier_count"] == 97
    assert not cohorts["older"]["identity_stage_screen_passed"]
    result = {"version":1,"verification":"passed","audit_code_sha256":digest(Path(__file__)),
        "repository_receipt_sha256":digest(root/"receipt.json"),"older_dictionary_receipt_sha256":digest(root/"older-dictionary-receipt.json"),
        "source":"NIH NLM NCBI PMC Article Datasets on AWS", "article_dois":[v["doi"] for v in receipt["versions"]],
        "cohorts":cohorts,"current_bout_hr_as_past_only_predictor_approved":False,
        "temporal_reason":"HR averages cover2:45-4:45 of a five-minute bout, while RPE is asked during4:00-5:00. Without exact response timestamps, some current-bout HR can follow the response. Use a completed previous bout only, never assert current-bout averages are strictly past.",
        "potential_lagged_input_policy":"Under the regular five-minute-bout/two-minute-rest protocol, adjacent last-minute RPE reports are6-8 minutes apart. The paper also permits early termination: allowing a current response anywhere from0-5 minutes widens protocol-derived bounds to2-8 minutes, with the previous completed-bout HR average ending at least2.25 minutes before the earliest current response. These are conditional protocol bounds, not measured timestamps or an observed exact7-minute age. Verify previous-bout completion/within-person adjacency before an adapter; keep exact age unknown and invent no clock or onset RPE.",
        "target_scale":"Original Borg6-20, observed values6-16; separate auxiliary outcome only, no rescaling or relabeling as native0-10 Borg.",
        "native_target_merge_approved":False,"model_fitting_started":False,"synthetic_rows":0,"source_people_split_not_yet_prepared":True,
        "policy":"Only original measured public cells. Adult identity/chronology may support a source-only lagged-input task after a frozen whole-person split and independent adapter audit. Older identity failures cannot be fixed by fabricating people or joining mismatched rows. No source-target conversion, fake clocks, native target changes or test tuning."}
    path = ROOT/"docs/fatigue-80-2026-10-25/cadence-eligibility.json"
    path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False),flush=True)
    return result


if __name__ == "__main__":
    review()
