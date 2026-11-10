"""Verify original HIFT cells and preserve its session-level target distinction."""
import hashlib
import json
import re
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from openpyxl import load_workbook

from public_sources import digest

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT/"training/data/raw/fatigue-research/new-rpe-candidates-2026-10-27-v1"
DOCS = ROOT/"docs/fatigue-80-2026-10-25"
FILE = RAW/"files/hift/DB (1).xlsx"
NS = {"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def inspect():
    metadata = json.loads((RAW/"hift-metadata.json").read_text())
    expected = next(row for row in metadata["files"] if row["name"] == FILE.name)
    assert FILE.stat().st_size == expected["size"] == 16485
    assert hashlib.md5(FILE.read_bytes()).hexdigest() == expected["computed_md5"] == "6cf222762295ce5339f041c4f0999999"
    with zipfile.ZipFile(FILE) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        original = {}
        for cell in sheet.findall(".//m:sheetData/m:row/m:c",NS):
            value = cell.find("m:v",NS)
            if cell.get("t") in (None,"n") and value is not None and value.text is not None:
                original[cell.attrib["r"]] = float(value.text)
    workbook = load_workbook(FILE,read_only=True,data_only=True)
    ws = workbook["DB"]
    people = {ref:value for ref,value in original.items() if re.fullmatch(r"A\d+",ref) and int(ref[1:]) >= 2}
    assert len(people) == len(set(people.values())) == 28
    for ref,value in people.items():
        assert ws[ref].value == value
    targets = {}
    for name,column,hr_column in (("AMRAP","AN","AH"),("FOR_TIME","AO","AI"),("EMOM","AP","AJ")):
        cells = {column+ref[1:]:original[column+ref[1:]] for ref in people if column+ref[1:] in original}
        for ref,value in cells.items():
            assert ws[ref].value == value and 0 <= value <= 10
            assert hr_column+re.search(r"\d+",ref).group() in original
        targets[name] = {"actual_original_responses":len(cells),"missing_original_responses":len(people)-len(cells),
            "original_cells":cells,"matching_workout_mean_hr_available":len(cells)}
    assert [targets[k]["actual_original_responses"] for k in targets] == [28,28,25]
    review = DOCS/"hift-protocol-review.md"
    report = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "verification_code_sha256":digest(Path(__file__)),"original_workbook_sha256":digest(FILE),
        "original_metadata_sha256":digest(RAW/"hift-metadata.json"),"protocol_review_sha256":digest(review),
        "primary_article":"https://pmc.ncbi.nlm.nih.gov/articles/PMC12049098/",
        "primary_article_doi":"10.7717/peerj.19265","public_dataset_doi":"10.6084/m9.figshare.25858906.v1",
        "original_workbook_people":28,"article_and_repository_described_people":25,
        "actual_original_responses":81,"actual_original_cells_independently_checked_against_xlsx_xml":81,
        "workouts":targets,"original_missing_responses_preserved":3,
        "source_instrument":"Borg_CR10_session_RPE","source_response_minutes_after_workout":30,
        "source_question_references_whole_workout":True,"source_sensor_window":"whole_workout_mean_HR",
        "momentary_native_target_merge_eligible":False,"source_native_target_conversion":False,
        "genuine_within_workout_prior_rpe_available":False,"exact_session_clock_released":False,
        "original_rows_excluded_to_force_article_count":0,"model_fitting_started":False,"synthetic_rows":0,
        "decision":"Do not pool these81actual whole-workout CR10responses with momentary native Borgtargets. The source provides one delayed session report per modality; no within-workout history or minute-specific HRcanbe invented. Any future auxiliary task must retain the different target/window and all original28person identities,including3without EMOMresponses."}
    output = DOCS/"hift-protocol-eligibility.json"
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    path = DOCS/"current-research-status.json"
    status = json.loads(path.read_text())
    status["additional_public_candidate_inspections"][output.name] = digest(output)
    status["other_new_public_candidates"]["hift"].update(
        status="Primary protocol verified: delayed whole-workout CR10reported30minafterexercise,not momentary native Borg. OriginalXMLchecks81responses/28people,3missing EMOM;retain article25versusoriginal28discrepancy. No native target pooling or invented within-workout priors.",
        model_fitting_started=False,protocol_review=review.name,eligibility_verification=output.name,
        actual_original_responses=81,original_workbook_people=28,momentary_native_target_merge_eligible=False)
    for field in ("additional_scoped_verifications","additional_data_audits","additional_public_candidate_inspections"):
        assert all(digest(DOCS/name) == value for name,value in status[field].items())
    path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("verification","original_workbook_people","actual_original_responses",
        "source_response_minutes_after_workout","momentary_native_target_merge_eligible","model_fitting_started")}),flush=True)


if __name__ == "__main__":
    inspect()
