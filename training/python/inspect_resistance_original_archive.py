"""Inspect archive data/annotation structure without executing code or models."""
import csv
import io
import json
import re
import zipfile
from datetime import datetime,timezone
from pathlib import Path

import openpyxl

import fetch_more_public_rpe_metadata as source
from public_sources import ROOT,digest


def inspect():
    receipt_path = source.DIRECTORY/"resistance-archive-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["code_sha256"] == digest(Path(__file__).with_name("fetch_resistance_original_archive.py"))
    path = source.DIRECTORY/receipt["local_filename"]
    assert path.stat().st_size == receipt["bytes"] and digest(path) == receipt["sha256"] and digest(path,"md5") == receipt["repository_md5"]
    with zipfile.ZipFile(path) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        inventory = [{"filename":i.filename,"bytes":i.file_size} for i in infos]
        readmes,annotations,references = [],[],[]
        for info in infos:
            name = info.filename.lower()
            if "readme" in Path(name).name and info.file_size<100_000:
                readmes.append({"filename":info.filename,"text":archive.read(info).decode("utf-8-sig",errors="replace")[:16000]})
            if name.endswith(".py") and info.file_size<200_000:
                text = archive.read(info).decode("utf-8-sig",errors="replace")
                matches = [{"line":number,"text":line[:250]} for number,line in enumerate(text.splitlines(),1)
                    if re.search(r"\.xlsx|\.csv|SMOTE|jitter|ground.truth|rpe.*file",line,re.I)]
                if matches:
                    references.append({"filename":info.filename,"references":matches[:30]})
            if info.file_size <= 5_000_000 and (name.endswith(".xlsx") or (name.endswith(".csv") and re.search(r"rpe|rating|annotation|ground.?truth",name))):
                payload = archive.read(info)
                item = {"filename":info.filename,"bytes":info.file_size}
                if name.endswith(".xlsx"):
                    workbook = openpyxl.load_workbook(io.BytesIO(payload),read_only=False,data_only=False)
                    sheets = []
                    for sheet in workbook:
                        preview = [[[cell.coordinate,str(cell.value)[:200],cell.data_type] for cell in row if cell.value is not None][:25]
                            for row in sheet.iter_rows(min_row=1,max_row=min(sheet.max_row,6))]
                        sheets.append({"name":sheet.title,"rows":sheet.max_row,"columns":sheet.max_column,
                            "formula_cells":sum(c.data_type == "f" for row in sheet for c in row),"preview":preview})
                    item["sheets"] = sheets
                else:
                    text = payload.decode("utf-8-sig",errors="replace")
                    rows = list(csv.reader(io.StringIO(text)))
                    item.update(csv_rows=len(rows),preview=[r[:30] for r in rows[:5]])
                annotations.append(item)
    report = {"version":1,"inspected_at":datetime.now(timezone.utc).isoformat(),"inspection_code_sha256":digest(Path(__file__)),
        "archive_receipt_sha256":digest(receipt_path),"fixed_public_record":17259404,"original_archive_sha256":digest(path),
        "archive_files":inventory,"readme_text":readmes,"annotation_candidates":annotations,"source_code_references_read_as_text_only":references,
        "downloaded_code_executed":False,"pretrained_weights_loaded":False,"training_approved":False,"model_fitting_started":False,
        "scope":"Inventory and original annotation review only. Published SMOTE/jitter methods and learned EMG labels are excluded from any actual-target claim. Only manually reported original RPE cells may enter a future independently verified adapter; no model weights or study scripts are executed."}
    output = ROOT/"docs/fatigue-80-2026-10-25/resistance-original-archive-inspection.json"
    output.write_text(json.dumps(report,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")
    print(json.dumps({"archive_files":len(inventory),"annotation_candidate_files":annotations,
        "readme_files":[r["filename"] for r in readmes],"code_reference_files":len(references),"model_fitting_started":False},ensure_ascii=True),flush=True)
    return report


if __name__ == "__main__":
    inspect()
