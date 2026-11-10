"""Verify original EMAP CR10 cells without executing study code or imputation."""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import openpyxl
from sklearn.model_selection import GroupShuffleSplit

import fetch_exercise_rpe_candidates as source
from public_sources import ROOT, digest, group_key

RAW_WORKBOOK = "Data_and_codebook/Data_during_exercise_EMAP.xlsx"
MERGED = "Data_and_codebook/emap_all.csv"
CODEBOOK = "Data_and_codebook/Codebook/Codebook_during_exercise_EMAP.xls"
DATA_MANAGEMENT = "R_Scripts/Data_management/DataM_during_exercise_EMAP.Rmd"
DESCRIPTIVE = "Data_analyses/Descriptive_analyses_EMAP_2.Rmd"
ANALYSIS = "Data_analyses/Data_analyses_EMAP_MVPA_2.Rmd"
QUESTIONNAIRE = "Materials/Questionnaires/During_exercise_questionnaire_EMAP.docx"
PREDICATES = [(3823,974654949),(3827,None),(3884,190964604),(3889,372571339),(3906,1067502624),
              (3907,138062464),(3932,440981825),(3939,1616603526),(3940,1668215102),(3682,None)]
EXCLUDED_IDS = {3863,3864,3870,3871,3889,3893}


def numeric(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and np.isfinite(value)


def verify():
    directory = source.DIRECTORY
    inventory = json.loads((directory/"inventory.json").read_text())
    receipt = json.loads((directory/"files-receipt.json").read_text())
    context = json.loads((directory/"reader-context-receipt.json").read_text())
    assert inventory["record"] == 19387250 and inventory["license"]["id"] == "cc-by-4.0"
    assert inventory["code_sha256"] == receipt["code_sha256"] == digest(Path(source.__file__))
    assert inventory["metadata_sha256"] == digest(directory/"metadata.json")
    assert receipt["inventory_sha256"] == context["source_inventory_sha256"] == digest(directory/"inventory.json")
    assert context["code_sha256"] == digest(Path(__file__).with_name("fetch_exercise_rpe_reader_context.py"))
    for entry in receipt["files"]:
        path = directory/"files"/entry["filename"]
        assert path.stat().st_size == entry["bytes"] and digest(path,"md5") == entry["repository_md5"] and digest(path) == entry["sha256"]
    analysis_path = directory/"files"/context["analysis_context"]["filename"]
    assert analysis_path.stat().st_size == context["analysis_context"]["bytes"]
    assert digest(analysis_path) == context["analysis_context"]["sha256"] and digest(analysis_path,"md5") == context["analysis_context"]["repository_md5"]
    reader = context["isolated_xls_reader"]
    wheel = directory/reader["relative_path"]
    assert digest(wheel) == reader["sha256"] == reader["published_sha256"]
    assert not context["training_environment_modified"] and not context["downloaded_study_code_executed"]
    sys.path.insert(0,str(wheel))
    import xlrd
    assert xlrd.__version__ == "2.0.2"
    archive = zipfile.ZipFile(directory/"files/Data_and_codebook.zip")
    scripts = zipfile.ZipFile(directory/"files/Data_management_R_Scripts.zip")
    analyses = zipfile.ZipFile(analysis_path)
    materials = zipfile.ZipFile(directory/"files/Materials.zip")
    management_text = scripts.read(DATA_MANAGEMENT).decode("utf-8-sig")
    assert 'read_excel("Data_during_exercise_EMAP.xlsx")' in management_text
    for stage in range(1,5):
        assert f'"Rated_Perceived_Exertion_T{stage}"' in management_text and f'"RPE{stage}"' in management_text
    assert not re.search(r"\bmice\s*\(",management_text)
    descriptions = {}
    for name in (DESCRIPTIVE,ANALYSIS):
        text = analyses.read(name).decode("utf-8-sig")
        found = [(int(person),int(seed) if seed else None) for person,seed in re.findall(
            r"filter\(!\(record_id == (\d+)(?: & seed == (\d+))?\)\)",text)]
        assert found == PREDICATES
        excluded = re.search(r"excluded_record_ids\s*<-\s*c\(([^)]+)\)",text)
        assert excluded and {int(v.strip()) for v in excluded[1].split(",")} == EXCLUDED_IDS
        descriptions[name] = text
    assert re.search(r"\bmice\s*\(",descriptions[ANALYSIS])
    merged = list(csv.DictReader(io.StringIO(archive.read(MERGED).decode("utf-8-sig"))))
    assert len(merged) == 128
    # R's ID-only dplyr filters discard unidentified rows. For a matching ID
    # with an unavailable seed, its ID+seed predicate is NA and filter drops it.
    selected = [r for r in merged if r["record_id"] not in ("NA","")]
    missing_identifiers = len(merged)-len(selected)
    for person,seed in PREDICATES:
        kept = []
        for row in selected:
            if int(row["record_id"]) != person:
                kept.append(row)
            elif seed is not None and row["seed"] not in ("NA","") and int(Decimal(row["seed"])) != seed:
                kept.append(row)
        selected = kept
    selected = [r for r in selected if int(r["record_id"]) not in EXCLUDED_IDS]
    cohort = {int(r["record_id"]):r for r in selected}
    assert len(selected) == len(cohort) == 109 and missing_identifiers == 2
    codebook = xlrd.open_workbook(file_contents=archive.read(CODEBOOK)).sheet_by_name("Codebook")
    assert codebook.nrows == 5 and codebook.cell_value(3,1) == "Perceived exertion from T1 to T4"
    assert codebook.cell_value(1,1) == "Affective response (valence) from T1 to T4"
    questionnaire_zip = zipfile.ZipFile(io.BytesIO(materials.read(QUESTIONNAIRE)))
    questionnaire = ET.fromstring(questionnaire_zip.read("word/document.xml"))
    qtext = " ".join(node.text or "" for node in questionnaire.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
    assert "CR10" in qtext and "Aucun effort" in qtext and "Effort maximal" in qtext
    raw_bytes = archive.read(RAW_WORKBOOK)
    workbook = openpyxl.load_workbook(io.BytesIO(raw_bytes),read_only=False,data_only=False)
    assert workbook.sheetnames == ["Feuil1"]
    sheet = workbook.active
    header = [sheet.cell(1,i).value for i in range(1,12)]
    assert header == ["ID","FeelingScale_T1","FeelingScale_T2","FeelingScale_T3","FeelingScale_T4","FS_Mean",
        "Rated_Perceived_Exertion_T1","Rated_Perceived_Exertion_T2","Rated_Perceived_Exertion_T3","Rated_Perceived_Exertion_T4","RPE_Mean"]
    identified = {}
    aggregate_formulas = 0
    orphan_responses = 0
    for cells in sheet.iter_rows(min_row=2,max_col=11):
        aggregate_formulas += sum(cells[i].data_type == "f" for i in (5,10))
        if cells[0].value is None:
            orphan_responses += int(any(cell.value is not None for cell in cells[6:10]))
            continue
        person = int(str(cells[0].value).strip())
        assert person not in identified
        identified[person] = cells
    assert len(identified) == 282 and orphan_responses == 0
    all_raw_cells = sum(numeric(cell.value) for cells in identified.values() for cell in cells[6:10])
    raw_people_with_responses = sum(any(numeric(cell.value) for cell in cells[6:10]) for cells in identified.values())
    assert all_raw_cells == 431 and raw_people_with_responses == 108
    ns = {"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as xlsx:
        root = ET.fromstring(xlsx.read("xl/worksheets/sheet1.xml"))
    xml_cells = {c.attrib["r"]:c for c in root.findall(".//m:sheetData/m:row/m:c",ns)}
    people = sorted(cohort)
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    fitting_ids,reserved_ids = {people[i] for i in fit},{people[i] for i in held}
    assert len(fitting_ids) == 87 and len(reserved_ids) == 22 and not fitting_ids&reserved_ids
    responses,lineage,pairs = {},[],[]
    presence = Counter()
    for person in people:
        cells = identified.get(person)
        measured = {}
        for stage in range(1,5):
            cell = cells[5+stage] if cells is not None else None
            value = cell.value if cell is not None else None
            csv_value = cohort[person][f"RPE{stage}"]
            if value is None:
                assert csv_value in ("NA","")
                continue
            assert numeric(value) and 0 <= value <= 10 and cell.data_type != "f"
            assert float(csv_value) == float(value)
            xml = xml_cells[cell.coordinate]
            assert xml.find("m:f",ns) is None and xml.attrib.get("t","n") == "n"
            assert float(Decimal(xml.find("m:v",ns).text)) == float(value)
            measured[stage] = float(value)
            lineage.append({"row_key":group_key(f"EMAP-original-response:{person}:T{stage}"),
                "group_key":group_key(f"EMAP-original-participant:{person}"),"published_person_id":person,
                "source_partition":"fitting" if person in fitting_ids else "reserved","questionnaire_slot":stage,
                "raw_sheet":"Feuil1","original_cell":cell.coordinate,"observed_rpe":float(value),"formula_or_imputation":False})
        responses[person] = measured
        presence["".join("1" if i in measured else "0" for i in range(1,5))] += 1
        for stage in range(2,5):
            if stage in measured and stage-1 in measured:
                pairs.append({"group_key":group_key(f"EMAP-original-participant:{person}"),"published_person_id":person,
                    "source_partition":"fitting" if person in fitting_ids else "reserved","current_slot":stage,
                    "actual_current_rpe":measured[stage],"actual_prior_rpe":measured[stage-1],
                    "actual_second_prior_rpe":measured.get(stage-2)})
    assert len(lineage) == 407 and len(pairs) == 305
    assert dict(presence) == {"1111":101,"1110":1,"0000":7}
    stage_counts = {stage:sum(stage in measured for measured in responses.values()) for stage in range(1,5)}
    assert stage_counts == {1:102,2:102,3:102,4:101}
    by_partition = {partition:{"cohort_people":len(fitting_ids if partition == "fitting" else reserved_ids),
        "people_with_actual_responses":len({r["group_key"] for r in lineage if r["source_partition"] == partition}),
        "actual_rpe_cells":sum(r["source_partition"] == partition for r in lineage),
        "actual_adjacent_pairs":sum(r["source_partition"] == partition for r in pairs)} for partition in ("fitting","reserved")}
    import hashlib
    payload_hashes = {"raw_workbook":hashlib.sha256(raw_bytes).hexdigest(),"merged_original_csv":hashlib.sha256(archive.read(MERGED)).hexdigest(),
        "codebook":hashlib.sha256(archive.read(CODEBOOK)).hexdigest(),"management_script":hashlib.sha256(scripts.read(DATA_MANAGEMENT)).hexdigest(),
        "descriptive_script":hashlib.sha256(analyses.read(DESCRIPTIVE)).hexdigest(),"analysis_script":hashlib.sha256(analyses.read(ANALYSIS)).hexdigest(),
        "questionnaire":hashlib.sha256(materials.read(QUESTIONNAIRE)).hexdigest()}
    result = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),"audit_code_sha256":digest(Path(__file__)),
        "source":inventory["record_url"],"paper":source.PAPER,"license":"CC BY4.0","inventory_sha256":digest(directory/"inventory.json"),
        "original_file_receipt_sha256":digest(directory/"files-receipt.json"),"reader_context_receipt_sha256":digest(directory/"reader-context-receipt.json"),
        "original_member_sha256":payload_hashes,"published_cohort_people_reproduced":109,"raw_workbook_identified_rows":282,
        "raw_people_with_any_rpe":108,"raw_individual_rpe_cells":431,"published_cohort_people_with_actual_rpe":102,
        "actual_published_cohort_rpe_cells":407,"actual_adjacent_rpe_pairs":305,"actual_pairs_with_two_genuine_priors":sum(r["actual_second_prior_rpe"] is not None for r in pairs),
        "observed_zero_cells_preserved":sum(r["observed_rpe"] == 0 for r in lineage),
        "fractional_observed_cells_preserved":sum(r["observed_rpe"] != int(r["observed_rpe"]) for r in lineage),
        "cohort_rpe_presence_patterns":dict(presence),"observed_rpe_cells_by_slot":stage_counts,
        "aggregate_mean_formula_cells_ignored":aggregate_formulas,"raw_workbook_unidentified_rows_not_counted":sheet.max_row-1-len(identified),
        "cohort_source_partition":by_partition,"source_split":{"method":"GroupShuffleSplit20percent,seed42,109 published cohort people before response/pair eligibility",
            "fitting_original_ids":sorted(fitting_ids),"reserved_original_ids":sorted(reserved_ids)},
        "native_target_merge_approved":False,"auxiliary_ordered_rpe_history_review_eligible":True,"concurrent_native_sensor_join_approved":False,
        "exact_report_clocks_known":False,"exact_prior_ages_invented":0,"imputed_or_mean_targets_used":0,"synthetic_rows":0,
        "downloaded_study_code_executed":False,"model_fitting_started":False,
        "instrument":"Original questionnaire explicitly names CR10 and anchors0=no effort,10=maximal effort. Raw RPE fields remain separate from affective Feeling Scale and aggregate means.",
        "timing":"Use only recorded slot order T1-T4. The original questionnaire describes warm-up/main/cooldown and a no-cooldown alternative; the article describes active-session structural points. Do not invent exact clocks, gaps or hard-map these phases to a native walking task.",
        "scope":"Only direct numeric individual response cells cross-checked by original XML and non-imputed merged CSV after reproducing published cohort filters from scripts read as text. All MICE objects/standardized imputed outputs, aggregate means and later-week accelerometer data are excluded from target/current-sensor use. Source reservation fixed before response eligibility; native487/179 cases and labels unchanged.",
        "response_lineage":lineage,"adjacent_pair_lineage":pairs}
    output = ROOT/"docs/fatigue-80-2026-10-25/exercise-rpe-original-verification.json"
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({key:result[key] for key in ("verification","published_cohort_people_reproduced","actual_published_cohort_rpe_cells",
        "actual_adjacent_rpe_pairs","actual_pairs_with_two_genuine_priors","cohort_source_partition","aggregate_mean_formula_cells_ignored",
        "fractional_observed_cells_preserved","model_fitting_started")}),flush=True)
    return result


if __name__ == "__main__":
    verify()
