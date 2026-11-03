"""Independently rebuild prepared EMAP pairs from numeric original XLSX XML."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

import fatigue_emap_history_inputs as source
from fatigue_catboost import load_inputs as native_inputs
from public_sources import digest, group_key


def verify():
    provenance_path = source.DIRECTORY/"provenance.json"
    provenance = json.loads(provenance_path.read_text())
    assert provenance["dependencies_sha256"] == source.dependencies()
    assert provenance["dataset_sha256"] == digest(source.DIRECTORY/"dataset.csv")
    review = json.loads(source.REVIEW.read_text())
    assert review["verification"] == "passed" and review["audit_code_sha256"] == digest(Path(__file__).with_name("audit_exercise_rpe_originals.py"))
    with zipfile.ZipFile(source.original.DIRECTORY/"files/Data_and_codebook.zip") as archive:
        workbook_bytes = archive.read(source.WORKBOOK_MEMBER)
    assert hashlib.sha256(workbook_bytes).hexdigest() == review["original_member_sha256"]["raw_workbook"]
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as workbook:
        xml = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    namespace = {"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    raw = {cell.attrib["r"]:cell for cell in xml.findall(".//s:sheetData/s:row/s:c",namespace)}
    all_responses = {}
    by_response = {}
    for line in review["response_lineage"]:
        cell = raw[line["original_cell"]]
        assert cell.find("s:f",namespace) is None and cell.attrib.get("t","n") == "n"
        value = float(Decimal(cell.find("s:v",namespace).text))
        assert value == line["observed_rpe"] and 0 <= value <= 10
        person,slot = line["published_person_id"],line["questionnaire_slot"]
        all_responses[person,slot] = value
        by_response[person,slot] = line
    ids = sorted(review["source_split"]["fitting_original_ids"]+review["source_split"]["reserved_original_ids"])
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(ids,groups=ids))
    fit_ids,held_ids = {ids[i] for i in fit},{ids[i] for i in held}
    assert fit_ids == set(review["source_split"]["fitting_original_ids"]) and held_ids == set(review["source_split"]["reserved_original_ids"])
    expected = []
    for person in ids:
        for slot in range(2,5):
            if (person,slot) not in all_responses or (person,slot-1) not in all_responses:
                continue
            second = all_responses.get((person,slot-2),np.nan)
            expected.append({"source_domain":"emap","source_partition":"fitting" if person in fit_ids else "reserved",
                "row_key":group_key(f"EMAP-original-response:{person}:T{slot}"),
                "group_key":group_key(f"EMAP-original-participant:{person}"),
                "prior_row_key":group_key(f"EMAP-original-response:{person}:T{slot-1}"),
                "prior2_row_key":None if np.isnan(second) else group_key(f"EMAP-original-response:{person}:T{slot-2}"),
                "current_slot":slot,"prior_borg":all_responses[person,slot-1],"prior2_borg":second,
                "current_rpe":all_responses[person,slot]})
    frame = pd.read_csv(source.DIRECTORY/"dataset.csv")
    emap = frame[frame.source_domain.eq("emap")].reset_index(drop=True)
    expected = pd.DataFrame(expected)
    pd.testing.assert_frame_equal(emap[expected.columns],expected,check_dtype=False,rtol=0,atol=0)
    old = pd.read_csv(source.previous.DIRECTORY/"dataset.csv")
    pd.testing.assert_frame_equal(frame[frame.source_domain.isin(["worker","sts"])][old.columns].reset_index(drop=True),old,check_dtype=False,rtol=0,atol=1e-12)
    assert len(frame) == 607 and len(emap) == 305 and frame.row_key.is_unique
    assert len(emap[emap.source_partition.eq("fitting")]) == 248 and len(emap[emap.source_partition.eq("reserved")]) == 57
    assert set(emap[emap.source_partition.eq("fitting")].group_key).isdisjoint(emap[emap.source_partition.eq("reserved")].group_key)
    assert emap.group_key.nunique() == 102 and emap.prior2_borg.isna().sum() == 102
    assert not emap[["hr_last","hr_history_mean","borg_native"]].notna().any().any()
    assert not frame[frame.source_domain.ne("emap")].current_rpe.notna().any()
    assert provenance["synthetic_rows"] == provenance["imputed_or_mean_targets"] == provenance["new_native_borg_targets"] == 0
    assert provenance["exact_source_report_times_or_ages_invented"] == provenance["new_source_sensor_joins"] == 0
    assert not provenance["source_targets_pooled_across_instruments"]
    native_frame,native_train,native_test,_,_ = native_inputs()
    assert (len(native_frame),len(native_train),len(native_test)) == (666,487,179)
    assert not set(native_frame.group_key)&set(frame.group_key)
    report = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "audit_code_sha256":digest(Path(__file__)),"source_provenance_sha256":digest(provenance_path),
        "source_original_review_sha256":digest(source.REVIEW),"source_preparation_code_sha256":digest(Path(source.__file__)),
        "actual_original_response_cells_checked":407,"actual_emap_pairs_independently_rebuilt":305,
        "emap_fitting_pairs":248,"emap_reserved_pairs":57,"emap_fitting_people":83,"emap_reserved_people":19,
        "emap_pairs_with_second_genuine_prior":203,"naturally_missing_second_priors":102,
        "previous_worker_sts_pairs_preserved":302,"total_fitting_pairs_across_separate_tasks":550,
        "all_original_fractional_targets_and_zero_responses_preserved":True,
        "whole_person_split_independently_reproduced_before_eligibility":True,
        "source_targets_pooled_across_instruments":False,"synthetic_rows":0,"imputed_or_mean_targets":0,
        "invented_source_clocks_or_sensor_joins":0,"native_targets_added":0,"source_model_fitting_started":False,
        "scope":"Independent numeric XML reconstruction of305 original EMAPordered pairs with frozen whole-person reservation; previous302 Worker/STS rows preserved cell-for-cell. Only measured individual CR10 responses supervise separate source tasks. No invented times, native phase equivalence, accelerometer/HRjoin, MICE/formula targets or synthetic examples."}
    output = source.DOCS/"emap-history-input-verification.json"
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(report),flush=True)
    return report


if __name__ == "__main__":
    verify()
