"""Count original exercise workbook cells without inventing its codebook."""
from __future__ import annotations

import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl

import fetch_light_exercise as source
from public_sources import ROOT, digest


def require(value, reason):
    if not value:
        raise ValueError(reason)


def numeric(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool)


def validate():
    inventory_path,receipt_path = source.DIRECTORY/"inventory.json",source.DIRECTORY/"files-receipt.json"
    inventory,receipt = json.loads(inventory_path.read_text()),json.loads(receipt_path.read_text())
    require(inventory["doi"] == "10.17632/kcff3z6wjb.1" and inventory["license"]["short_name"] == "CC BY 4.0"
            and inventory["code_sha256"] == receipt["code_sha256"] == digest(Path(source.__file__))
            and receipt["inventory_sha256"] == digest(inventory_path) and receipt["publisher_hashes_verified"],
            "Original public source metadata/retrieval changed")
    for entry in inventory["metadata"]:
        require(digest(source.DIRECTORY/entry["path"]) == entry["sha256"],"Original metadata bytes changed")
    require(len(inventory["files"]) == len(receipt["files"]) == 1,"Unexpected source files")
    entry = receipt["files"][0]
    path = source.DIRECTORY/"files"/entry["filename"]
    require(entry["filename"] == "PATimeSeries.xlsx" and path.stat().st_size == entry["bytes"] == 56853
            and digest(path) == entry["sha256"] == entry["published_sha256"],"Original workbook bytes/checksum changed")
    workbook = openpyxl.load_workbook(path,read_only=False,data_only=False)
    require(workbook.sheetnames == ["PATimeSeries"],"Unexpected sheets; inspect source codebook before proceeding")
    sheet = workbook.active
    header = [cell.value for cell in sheet[1]]
    expected = ["CODE","Place","Group","Sex","Age","Weight","Height"]+[
        f"T{i}{suffix}" for i in range(1,49) for suffix in ("K1","E1","P1","K2","E2","P2","B")]
    require(header == expected,"Original abbreviated session fields changed")
    populated = [row for row in sheet.iter_rows(min_row=2) if any(cell.value is not None for cell in row)]
    values = [[cell.value for cell in row] for row in populated]
    require(len(values) == 24 and len({r[0] for r in values}) == 24 and all(r[0] is not None for r in values),
            "Expected24 actual distinct coded rows, not formatted blank worksheet rows")
    slots = [{suffix:row[7+(session-1)*7+offset] for offset,suffix in enumerate(("K1","E1","P1","K2","E2","P2","B"))}
             for row in values for session in range(1,49)]
    counts = {field:{"numeric":sum(numeric(r[field]) for r in slots),"blank":sum(r[field] is None for r in slots),
                     "spreadsheet_error":sum(r[field] == "#NULL!" for r in slots),
                     "other_nonnumeric":sum(not numeric(r[field]) and r[field] not in (None,"#NULL!") for r in slots)}
              for field in ("K1","E1","P1","K2","E2","P2","B")}
    b_values = [r["B"] for r in slots if numeric(r["B"])]
    require(len(slots) == 1152 and counts["B"] == {"numeric":1121,"blank":0,"spreadsheet_error":31,"other_nonnumeric":0},
            "Original B cell counts changed")
    ns = {"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        b_cells = [cell for cell in root.findall(".//m:sheetData/m:row/m:c",ns)
                   if re.match(r"[A-Z]+",cell.attrib["r"]).group() in {openpyxl.utils.get_column_letter(i+1) for i,k in enumerate(header) if re.fullmatch(r"T\d+B",k)}
                   and int(re.search(r"\d+$",cell.attrib["r"]).group()) > 1]
        raw_numeric = [float(cell.find("m:v",ns).text) for cell in b_cells
                       if cell.attrib.get("t","n") == "n" and cell.find("m:v",ns) is not None]
        raw_errors = [cell.find("m:v",ns).text for cell in b_cells if cell.attrib.get("t") == "e"]
        require(Counter(raw_numeric) == Counter(b_values) and raw_errors == ["#NULL!"]*31,
                "Independent original XML B counts differ from workbook reader")
        bundled_documentation = [name for name in archive.namelist() if "comment" in name.lower() or name.lower().endswith((".pdf",".docx",".txt"))]
    formula_cells = sum(cell.data_type == "f" for row in populated for cell in row)
    require(formula_cells == 0,"Inspect computed workbook cells before treating them as observed")
    state = json.JSONDecoder().raw_decode((source.DIRECTORY/"page.html").read_text(encoding="utf-8").split("window.INITIAL_STATE = ",1)[1])[0]
    description = state["dataset"]["snapshot"]
    report = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "audit_code_sha256":digest(Path(__file__)),"inventory_sha256":digest(inventory_path),"receipt_sha256":digest(receipt_path),
        "workbook_sha256":digest(path),"source":source.PAGE,"license":"CC BY4.0","formatted_sheet_rows_including_header":sheet.max_row,
        "actual_coded_participant_rows":24,"formatted_blank_rows_excluded_from_counts":sheet.max_row-1-len(populated),
        "session_slots_per_coded_row":48,"potential_person_session_slots":1152,"field_cell_counts":counts,
        "numeric_B_cells":len(b_values),"B_observed_range":[min(b_values),max(b_values)],
        "B_observed_counts":dict(sorted(Counter(str(v) for v in b_values).items())),"original_spreadsheet_error_B_cells":31,
        "numeric_P1_and_P2_with_numeric_B":sum(all(numeric(r[k]) for k in ("P1","P2","B")) for r in slots),
        "formula_cells_in_actual_rows":formula_cells,"independent_original_xml_counts_match":True,
        "bundled_codebook_or_comments":bundled_documentation,"source_related_links":description["related_links"],
        "training_approved":False,"native_target_merge_approved":False,"used_for_training":False,"synthetic_rows":0,
        "limitations":[
            "The repository describes pre/post exercise pulse, feeling/arousal and post-session Borg but supplies only abbreviated column names and no codebook or linked article.",
            "B spans2-7. That observed range does not establish whether the instrument is CR10, a brief seven-category Borg or another coding. Do not relabel it as native0-10 or source6-20.",
            "P1/P2 plausibly denote pre/post pulse from their repeated layout, but bpm units, measurement procedure and timing relative to B are not explicitly documented for these columns.",
            "T1-T48 are session slots, not measured dates or one-minute histories. Do not invent timestamps or use these as a recent Borg prior in a walk.",
            "Preserve31 original B spreadsheet errors as unavailable outcomes; never replace them by zero or imputed labels.",
            "The sheet has15 formatted empty rows beyond24 actual coded rows. These are not additional participants or observations."
        ],
        "decision":"Retain original verified public data for review only. No fitting until instrument and predictor semantics/chronology are established by source documentation; no invented mappings or labels."}
    output = ROOT/"docs/fatigue-80-2026-10-25/light-exercise-eligibility.json"
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,allow_nan=False),flush=True)
    return report


if __name__ == "__main__":
    validate()
