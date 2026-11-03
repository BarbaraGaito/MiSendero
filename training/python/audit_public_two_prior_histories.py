"""Independently verify recovered second priors against original questionnaire cells."""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import openpyxl
import pandas as pd

import fatigue_public_two_prior_histories as source
from public_sources import digest,group_key


def verify():
    frame = pd.read_csv(source.DIRECTORY/"dataset.csv")
    provenance_path = source.DIRECTORY/"provenance.json"
    provenance = json.loads(provenance_path.read_text())
    assert provenance["dependencies_sha256"] == source.dependencies()
    assert provenance["dataset_sha256"] == digest(source.DIRECTORY/"dataset.csv")
    parent = pd.read_csv(source.parent.DIRECTORY/"dataset.csv")
    pd.testing.assert_frame_equal(frame[parent.columns],parent,check_dtype=False,rtol=0,atol=0)
    assert len(frame) == 607 and frame.row_key.is_unique
    worker_proof = json.loads((source.parent.previous.DIRECTORY/"provenance.json").read_text())
    survey_path = source.parent.previous.SURVEY
    assert digest(survey_path) == worker_proof["original_public_survey_sha256"]
    sheet = openpyxl.load_workbook(survey_path,data_only=False).worksheets[0]
    columns = {cell.value:cell.column for cell in sheet[1]}
    worker_lineage = {r["current_row_key"]:r for r in worker_proof["worker_original_survey_pair_lineage"]}
    by_cell = {(r["worksheet_row"],r["current_column"]):r["current_row_key"] for r in worker_lineage.values()}
    verified_worker = 0
    for row in frame[frame.source_domain.eq("worker")].itertuples():
        info = worker_lineage[row.row_key]
        number = int(re.search(r"\[REP ([1-5])\]",info["current_column"])[1])
        current_cell = sheet.cell(info["worksheet_row"],columns[info["current_column"]])
        prior_cell = sheet.cell(info["worksheet_row"],columns[info["prior_column"]])
        assert current_cell.data_type != "f" and prior_cell.data_type != "f"
        assert float(Decimal(str(current_cell.value))) == row.borg_native
        assert float(Decimal(str(prior_cell.value))) == row.prior_borg == getattr(row,source.PRIOR)
        if number == 1:
            assert np.isnan(getattr(row,source.SECOND)) and pd.isna(row.public_ordered_second_prior_row_key)
            continue
        second_column = (source.parent.previous.BASELINE_COLUMN if number == 2 else
            info["current_column"].replace(f"[REP {number}]",f"[REP {number-2}]"))
        cell = sheet.cell(info["worksheet_row"],columns[second_column])
        assert cell.data_type != "f" and cell.value is not None
        value = float(Decimal(str(cell.value)))
        expected_key = by_cell.get((info["worksheet_row"],second_column),
            group_key(f"WorkerFatigue-original-survey:{info['worksheet_row']}:{second_column}"))
        assert 0 <= value <= 10 and getattr(row,source.SECOND) == value
        assert row.public_ordered_second_prior_row_key == expected_key
        verified_worker += 1
    assert verified_worker == 200
    review = json.loads(source.parent.REVIEW.read_text())
    assert review["audit_code_sha256"] == digest(Path(__file__).with_name("audit_exercise_rpe_originals.py"))
    with zipfile.ZipFile(source.parent.original.DIRECTORY/"files/Data_and_codebook.zip") as archive:
        payload = archive.read(source.parent.WORKBOOK_MEMBER)
    import hashlib
    assert hashlib.sha256(payload).hexdigest() == review["original_member_sha256"]["raw_workbook"]
    with zipfile.ZipFile(io.BytesIO(payload)) as workbook:
        root = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    namespace = {"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cells = {cell.attrib["r"]:cell for cell in root.findall(".//s:sheetData/s:row/s:c",namespace)}
    observed = {}
    current_lookup = {}
    for info in review["response_lineage"]:
        person,slot = info["published_person_id"],info["questionnaire_slot"]
        cell = cells[info["original_cell"]]
        assert cell.find("s:f",namespace) is None and cell.attrib.get("t","n") == "n"
        value = float(Decimal(cell.find("s:v",namespace).text))
        assert value == info["observed_rpe"]
        observed[person,slot] = value
        current_lookup[info["row_key"]] = (person,slot)
    verified_emap = 0
    for row in frame[frame.source_domain.eq("emap")].itertuples():
        person,slot = current_lookup[row.row_key]
        assert observed[person,slot] == row.current_rpe
        assert observed[person,slot-1] == row.prior_borg == getattr(row,source.PRIOR)
        if (person,slot-2) not in observed:
            assert np.isnan(getattr(row,source.SECOND)) and pd.isna(row.public_ordered_second_prior_row_key)
            continue
        assert getattr(row,source.SECOND) == observed[person,slot-2]
        assert row.public_ordered_second_prior_row_key == group_key(f"EMAP-original-response:{person}:T{slot-2}")
        verified_emap += 1
    assert verified_emap == 203
    sts = frame[frame.source_domain.eq("sts")]
    assert len(sts) == 49 and sts[source.SECOND].isna().all()
    np.testing.assert_array_equal(sts[source.PRIOR],sts.prior_borg)
    np.testing.assert_array_equal(frame[source.PRIOR],frame.prior_borg)
    assert frame[source.SECOND].notna().sum() == 403
    fitting,reserved = frame[frame.source_partition.eq("fitting")],frame[frame.source_partition.eq("reserved")]
    assert len(fitting) == 550 and len(reserved) == 57 and set(fitting.group_key).isdisjoint(reserved.group_key)
    assert fitting[source.SECOND].notna().sum() == 365 and reserved[source.SECOND].notna().sum() == 38
    assert not provenance["source_targets_pooled_across_instruments"] and provenance["original_columns_and_targets_preserved"]
    assert provenance["synthetic_rows"] == provenance["imputed_targets"] == provenance["second_priors_filled_when_unobserved"] == 0
    assert provenance["native_targets_added"] == provenance["new_independent_current_observations"] == 0
    result = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "audit_code_sha256":digest(Path(__file__)),"source_preparation_code_sha256":digest(Path(source.__file__)),
        "source_provenance_sha256":digest(provenance_path),"parent_source_provenance_sha256":digest(source.parent.DIRECTORY/"provenance.json"),
        "original_worker_survey_sha256":digest(survey_path),"original_emap_review_sha256":digest(source.parent.REVIEW),
        "original_current_pairs_preserved":607,"original_fitting_pairs_preserved":550,"original_reserved_emap_pairs_preserved":57,
        "worker_second_priors_independently_verified_from_original_cells":200,
        "emap_second_priors_independently_verified_from_original_xml":203,"sts_unavailable_second_priors_preserved":49,
        "observed_second_priors":403,"fitting_observed_second_priors":365,"reserved_observed_second_priors":38,
        "naturally_unavailable_second_priors":204,"all_original_source_columns_and_targets_preserved":True,
        "source_targets_pooled_across_instruments":False,"new_independent_current_observations":0,
        "native_targets_added":0,"synthetic_rows":0,"invented_source_times_or_sensor_joins":0,"model_fitting_started":False,
        "scope":"Direct original questionnaire-cell verification of200recovered Worker second priors and independent original XMLverification of203EMAPsecond priors. All607original current pairs,550fitting/57reserved and distinct original outcomes remain unchanged;204second priors unavailable in the snapshot stay missing. Compatible measured history inputs only; no generated rows, assumed zero baselines, imputed labels, native target merge or source clock/phase/sensor invention."}
    output = source.parent.DOCS/"public-two-prior-history-verification.json"
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result),flush=True)
    return result


if __name__ == "__main__":
    verify()
