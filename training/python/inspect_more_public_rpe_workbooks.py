"""Inventory original public workbook structure before target/timing eligibility."""
import json
import re
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl

import fetch_more_public_rpe_metadata as source
from public_sources import ROOT,digest


def inspect():
    directory = source.DIRECTORY
    receipt_path = directory/"original-files-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["code_sha256"] == digest(Path(__file__).with_name("fetch_more_public_rpe_files.py"))
    files = []
    for entry in receipt["files"]:
        path = directory/"files"/entry["source"]/entry["filename"]
        assert path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"] and digest(path,"md5") == entry["repository_md5"]
        item = {"source":entry["source"],"filename":entry["filename"],"sha256":digest(path),"license":entry["license"]}
        if path.suffix.lower() == ".xlsx":
            workbook = openpyxl.load_workbook(path,read_only=False,data_only=False)
            sheets = []
            for sheet in workbook:
                labels,formulas = [],0
                for row in sheet:
                    for cell in row:
                        formulas += int(cell.data_type == "f")
                        if isinstance(cell.value,str) and re.search(r"rpe|borg|exertion|\bPSE\b",cell.value,re.I):
                            labels.append({"cell":cell.coordinate,"text":cell.value[:250]})
                preview = []
                for row in sheet.iter_rows(min_row=1,max_row=min(sheet.max_row,6)):
                    present = [{"cell":cell.coordinate,"value":str(cell.value)[:100],"type":cell.data_type} for cell in row if cell.value is not None]
                    preview.append(present[:35])
                sheets.append({"name":sheet.title,"rows":sheet.max_row,"columns":sheet.max_column,"formula_cells":formulas,
                    "rpe_related_cells":labels[:100],"first_six_rows_nonempty_cells":preview})
            item["sheets"] = sheets
        elif path.suffix.lower() == ".docx":
            with zipfile.ZipFile(path) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
            item["original_table_context"] = " ".join(n.text or "" for n in document.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
        files.append(item)
    report = {"version":1,"inspected_at":datetime.now(timezone.utc).isoformat(),"inspection_code_sha256":digest(Path(__file__)),
        "original_file_receipt_sha256":digest(receipt_path),"all_original_repository_file_checksums_verified":True,
        "files":files,"individual_target_instrument_and_timing_review_complete":False,"training_approved":False,
        "model_fitting_started":False,"synthetic_rows_used":0}
    output = ROOT/"docs/fatigue-80-2026-10-25/new-rpe-workbook-inspection.json"
    output.write_text(json.dumps(report,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")
    for item in files:
        summary = {"source":item["source"],"filename":item["filename"]}
        if "sheets" in item:
            summary["sheets"] = [{k:sheet[k] for k in ("name","rows","columns","formula_cells","rpe_related_cells")} for sheet in item["sheets"]]
        else:
            summary["original_table_context"] = item["original_table_context"]
        print(json.dumps(summary,ensure_ascii=True),flush=True)
    return report


if __name__ == "__main__":
    inspect()
