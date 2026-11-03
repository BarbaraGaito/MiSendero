"""Eligibility evidence for three source workbooks, without merging targets."""
import json
from pathlib import Path

import openpyxl

from fetch_borg_candidates_v2 import DIRECTORY
from public_sources import digest


def audit():
    receipt_path = DIRECTORY / "workbooks-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not receipt["all_complete_and_publisher_verified"]:
        raise ValueError("Complete source downloads required")
    for entry in receipt["files"]:
        path = DIRECTORY / entry["file"]
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("A publisher-verified workbook changed")
    result = {"version": 1, "code_sha256": digest(Path(__file__)), "receipt_sha256": digest(receipt_path),
              "training_merge_approved": False, "original_geofatigue_targets_added": 0, "sources": {}}
    book = openpyxl.load_workbook(DIRECTORY / "biceps-updated.xlsx", read_only=True, data_only=False)
    sheets, sample_hr = [], []
    for sheet in book:
        headers = [str(c.value).strip() if c.value is not None else "" for c in next(sheet.iter_rows(min_row=1, max_row=1))]
        sheets.append({"sheet": sheet.title, "header_names": headers,
                       "explicit_native_borg_header": any("borg" in h.lower() or h.lower() == "rpe" for h in headers)})
        if sheet.title != "Summary" and "bpm" in headers:
            index = headers.index("bpm")
            for row in sheet.iter_rows(min_row=2, max_row=6, values_only=True):
                if isinstance(row[index], (int, float)):
                    sample_hr.append(float(row[index]))
    book.close()
    result["sources"]["biceps"] = {"source": "https://zenodo.org/records/15377599", "version": 2,
        "sheets": sheets, "sample_bpm_column_range": [min(sample_hr), max(sample_hr)], "used_for_training": False,
        "reason": "Inspected sheets expose period categories but no explicit numeric Borg/RPE header. Sample values in the bpm column are below one; an original-unit conversion and native outcome definition were not established. Do not treat period categories as current Borg scores."}
    book = openpyxl.load_workbook(DIRECTORY / "pharmaceutical.xlsx", read_only=True, data_only=False)
    sheet = book.active
    rows = sheet.iter_rows()
    headers = [c.value for c in next(rows)]
    column = headers.index("Borg Test")
    values, formulas = [], 0
    for row in rows:
        if len(row) > column and row[column].value is not None:
            cell = row[column]
            formulas += cell.data_type == "f"
            if isinstance(cell.value, (int, float)):
                values.append(float(cell.value))
    book.close()
    result["sources"]["pharmaceutical"] = {"source": "https://zenodo.org/records/14891916", "populated_numeric_borg_cells": len(values),
        "native_value_range": [min(values), max(values)], "formula_outcome_cells": formulas, "used_for_training": False,
        "independent_report_count_established": False,
        "reason": "Borg cells include values above ten and repeat across sensor rows. No conversion to CR10 or counting of copied cells as independent reports is permitted; exact report timing was not established."}
    book = openpyxl.load_workbook(DIRECTORY / "exercise-ppt.xlsx", read_only=True, data_only=True)
    sheet = book.active
    rows = sheet.iter_rows(values_only=True)
    headers = next(rows)
    column = headers.index("RPE CV 1")
    groups = {}
    for row in rows:
        if not isinstance(row[0], (int, float)):
            continue
        group = row[1]
        group_data = groups.setdefault(group, {"participants": 0, "numeric_rpe_cv_cells": 0, "zero_rpe_cv_cells": 0})
        group_data["participants"] += 1
        values = [v for v in row[column:column+25] if isinstance(v, (int, float))]
        group_data["numeric_rpe_cv_cells"] += len(values)
        group_data["zero_rpe_cv_cells"] += sum(v == 0 for v in values)
    book.close()
    protocol = DIRECTORY / "exercise-protocol-CERT.docx"
    protocol_text = DIRECTORY / "exercise-protocol-CERT.txt"
    result["sources"]["exercise_ppt"] = {"source": "https://zenodo.org/records/21724451", "groups": groups,
        "exercise_group_numeric_rpe_cv_cells": sum(v["numeric_rpe_cv_cells"] for k, v in groups.items() if k != "Control"),
        "used_for_training": False, "independent_report_timing_and_instrument_established": False,
        "protocol_sha256": digest(protocol) if protocol.exists() else None,
        "protocol_text_sha256": digest(protocol_text) if protocol_text.exists() else None,
        "reason": "The CERT supplement specifies minute-wise heart-rate monitoring but does not define the RPE-CV instrument or its collection cadence. RPE-CV and OMNI are distinct columns. Some control rows contain zeros and others missing values. Preserve cells without assuming they are independent momentary Borg reports or filling missing ratings."}
    path = DIRECTORY / "eligibility-audit.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print("Audited three original workbooks; none merged as unverified momentary Borg targets", flush=True)
    print(json.dumps({name: {k: v for k, v in item.items() if k not in ("sheets", "reason")} for name, item in result["sources"].items()}, indent=2))
    return result


if __name__ == "__main__":
    audit()
