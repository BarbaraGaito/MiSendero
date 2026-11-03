"""Verify only original human-reported resistance RPE cells and genuine priors."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

import fetch_more_public_rpe_metadata as repository
from public_sources import ROOT,digest,group_key

DOCS = ROOT/"docs/fatigue-80-2026-10-25"
PAPER = "https://arxiv.org/html/2510.03197v1"


def verify():
    directory = repository.DIRECTORY
    receipt_path = directory/"resistance-archive-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["code_sha256"] == digest(Path(__file__).with_name("fetch_resistance_original_archive.py"))
    assert receipt["fixed_version_record_id"] == 17259404 and receipt["requested_concept_id"] == 17259403
    assert receipt["license"] == "CC BY4.0" and not receipt["downloaded_code_executed"] and not receipt["pretrained_weights_loaded"]
    archive_path = directory/receipt["local_filename"]
    assert archive_path.stat().st_size == receipt["bytes"] and digest(archive_path) == receipt["sha256"]
    assert digest(archive_path,"md5") == receipt["repository_md5"] == "580ac3dea08ec34dff9f74f51edbd624"
    with zipfile.ZipFile(archive_path) as archive:
        member = next(n for n in archive.namelist() if n.endswith("/Code/Preprocessing/rpes.csv"))
        prefix = member[:-len("Code/Preprocessing/rpes.csv")]
        original = archive.read(member)
        processed_member = prefix+"Code/Datasets/rep_dataset.csv"
        processed_bytes = archive.read(processed_member)
        reader_member = prefix+"Code/Preprocessing/preprocessing.py"
        reader = archive.read(reader_member)
        readme = archive.read(prefix+"README.md")
    # Read the authors' parser as text only; the second CSV line is a count
    # summary, not exertion observations, and must be skipped as documented.
    code_text = reader.decode("utf-8-sig")
    assert re.search(r"def read_rpes\(filename\):\s+df = pd.read_csv\(filename, skiprows=\[1\]\)",code_text)
    assert "Label files containing RPE values provided by participants" in readme.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(original.decode("utf-8-sig"))))
    sets = rows[0]
    assert len(rows) == 44 and len(sets) == len(set(sets)) == 69
    assert all(re.fullmatch(r"(A321|G998|P714|T417|T456)_(5|10|15)_\d+",key) for key in sets)
    people = sorted({key.split("_")[0] for key in sets})
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    fitting_people,reserved_people = {people[i] for i in fit},{people[i] for i in held}
    assert len(fitting_people) == 4 and len(reserved_people) == 1 and not fitting_people&reserved_people
    original_cells,by_set,lineage,counts = {},{},[],[]
    for column,key in enumerate(sets):
        person = key.split("_")[0]
        partition = "fitting" if person in fitting_people else "reserved"
        sequence = {}
        observed_rows = []
        for index,row in enumerate(rows[2:]):
            text = row[column].strip() if len(row)>column else ""
            if not text:
                continue
            value = float(Decimal(text))
            assert np.isfinite(value) and 1 <= value <= 10
            original_cells[key,index] = value
            sequence[index] = value
            observed_rows.append(index)
            lineage.append({"row_key":group_key(f"Resistance-original-RPE:{key}:{index}"),
                "group_key":group_key(f"Resistance-original-participant:{person}"),
                "sequence_key":group_key(f"Resistance-original-set:{key}"),"source_partition":partition,
                "original_person_id":person,"original_set_id":key,"repetition_index_zero_based":index,
                "original_csv_member":member,"original_csv_line":index+3,"original_csv_column":column+1,
                "original_rpe":value,"formula_or_imputation":False})
        assert observed_rows == list(range(len(observed_rows)))
        by_set[key] = sequence
        declared = int(rows[1][column])
        if declared != len(sequence):
            counts.append({"original_set_id":key,"declared_count_metadata":declared,"actual_original_rpe_cells":len(sequence),
                "difference":len(sequence)-declared})
    processed = list(csv.DictReader(io.StringIO(processed_bytes.decode("utf-8-sig"))))
    canonical = {}
    for row in processed:
        key,index = row["ID"],int(row["rep_num"])
        assert (key,index) not in canonical and key in by_set and index in by_set[key]
        value = float(Decimal(row["RPE"]))
        assert value == original_cells[key,index]
        canonical[key,index] = value
    assert len(original_cells) == len(canonical) == len(processed) == 1003 and set(original_cells) == set(canonical)
    assert sum(int(n) for n in rows[1]) == 1001
    assert counts == [{"original_set_id":"T417_10_1","declared_count_metadata":17,"actual_original_rpe_cells":18,"difference":1},
        {"original_set_id":"T417_10_2","declared_count_metadata":16,"actual_original_rpe_cells":17,"difference":1}]
    pairs = []
    for key,sequence in by_set.items():
        person = key.split("_")[0]
        for index,value in sequence.items():
            if index-1 not in sequence:
                continue
            pairs.append({"row_key":group_key(f"Resistance-original-RPE:{key}:{index}"),
                "group_key":group_key(f"Resistance-original-participant:{person}"),
                "sequence_key":group_key(f"Resistance-original-set:{key}"),"original_set_id":key,
                "repetition_index_zero_based":index,"source_partition":"fitting" if person in fitting_people else "reserved",
                "actual_current_rpe":value,"actual_prior_rpe":sequence[index-1],"actual_second_prior_rpe":sequence.get(index-2),
                "prior_row_key":group_key(f"Resistance-original-RPE:{key}:{index-1}"),
                "second_prior_row_key":None if index-2 not in sequence else group_key(f"Resistance-original-RPE:{key}:{index-2}")})
    assert len(pairs) == 934 and sum(p["actual_second_prior_rpe"] is not None for p in pairs) == 865
    partition_counts = {partition:{"people":len(fitting_people if partition == "fitting" else reserved_people),
        "original_reports":sum(r["source_partition"] == partition for r in lineage),
        "actual_adjacent_pairs":sum(r["source_partition"] == partition for r in pairs),
        "pairs_with_second_genuine_prior":sum(r["source_partition"] == partition and r["actual_second_prior_rpe"] is not None for r in pairs)}
        for partition in ("fitting","reserved")}
    assert partition_counts == {"fitting":{"people":4,"original_reports":930,"actual_adjacent_pairs":866,"pairs_with_second_genuine_prior":802},
        "reserved":{"people":1,"original_reports":73,"actual_adjacent_pairs":68,"pairs_with_second_genuine_prior":63}}
    report = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),"audit_code_sha256":digest(Path(__file__)),
        "public_dataset":"https://zenodo.org/records/17259404","paper":PAPER,"authors":["James Thomas","Johan Wahlstrom"],
        "license":"CC BY4.0","archive_receipt_sha256":digest(receipt_path),"original_archive_sha256":digest(archive_path),
        "original_annotation_member":member,"original_annotation_member_sha256":hashlib.sha256(original).hexdigest(),
        "canonical_rpe_crosscheck_member":processed_member,"canonical_rpe_crosscheck_member_sha256":hashlib.sha256(processed_bytes).hexdigest(),
        "original_reader_member":reader_member,"original_reader_member_sha256":hashlib.sha256(reader).hexdigest(),
        "original_manual_reports":1003,"original_sets":69,"original_people":5,"original_rpe_range":[1.,10.],
        "fractional_original_reports_preserved":sum(v != int(v) for v in original_cells.values()),
        "all1003reports_match_original_cells_bijectively":True,"actual_adjacent_pairs":934,"pairs_with_second_genuine_prior":865,
        "original_count_metadata_total":1001,"count_metadata_discrepancies_preserved":counts,
        "actual_response_values_changed_or_filled":0,"source_partition_counts":partition_counts,
        "whole_person_split":{"method":"GroupShuffleSplit20percent seed42 on all5original people before report/pair eligibility",
            "fitting_original_people":sorted(fitting_people),"reserved_original_people":sorted(reserved_people)},
        "auxiliary_ordered_history_eligible":True,"native_target_merge_approved":False,"exact_report_clocks_known":False,
        "new_sensor_join_approved":False,"generated_emg_labels_used_as_rpe_targets":False,"smote_or_jitter_samples_used":False,
        "downloaded_study_code_executed":False,"pretrained_weights_loaded":False,"model_fitting_started":False,
        "synthetic_rows":0,"imputed_targets":0,"native_targets_added":0,
        "instrument":"Resistance-study Borg CR10 as authored,reported1-10 after each repetition. Remains a separate original outcome; no conversion to native0-10 labels.",
        "timing":"Only actual repetition order within the original set. No assumed report ages,rest intervals or mapping to walking phases; each first report stays an observed prior rather than an invented baseline.",
        "scope":"Original manual rpes.csv numeric cells only,excluding the count metadata line; all1003values independently cross-checked against canonical ID/repetition/RPE columns without using its other features. Two count-metadata undercounts are recorded,not used to erase actual confirmed responses. No learned EMG labels,SMOTE/jitter examples,supplied weights or downloaded code execution. Whole-person source reservation fixed before eligibility; all original native487/179cases remain unchanged.",
        "original_response_lineage":lineage,"actual_pair_lineage":pairs}
    output = DOCS/"resistance-reported-rpe-verification.json"
    output.write_text(json.dumps(report,indent=2,ensure_ascii=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("verification","original_manual_reports","original_sets","original_people","actual_adjacent_pairs",
        "pairs_with_second_genuine_prior","source_partition_counts","count_metadata_discrepancies_preserved","model_fitting_started")}),flush=True)
    return report


if __name__ == "__main__":
    verify()
