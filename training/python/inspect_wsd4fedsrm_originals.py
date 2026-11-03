"""Read original ZIP inventory and small Borg cells; no sensor/model execution."""
from __future__ import annotations

import csv
import io
import json
import math
import re
import zipfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path,PurePosixPath

import retrieve_wsd4fedsrm_public as retrieval
from public_sources import ROOT,digest

DOCS = ROOT/"docs/fatigue-80-2026-10-25"
DIRECTORY = retrieval.DIRECTORY
SMALL_LIMIT = 8*1024*1024


def number(value):
    value = value.strip()
    if not value:
        return None
    try:
        result = Decimal(value)
    except InvalidOperation:
        return None
    return float(result) if result.is_finite() else None


def normalized(value):
    return value.strip().casefold().replace(" ","_")


def inspect_borg(name,payload):
    try:
        decoded = payload.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        decoded,encoding = payload.decode("cp1252"),"cp1252"
    dialect = csv.Sniffer().sniff(decoded[:8192],delimiters=",;\t")
    raw = list(csv.reader(io.StringIO(decoded),dialect))
    nonempty = [(index+1,row) for index,row in enumerate(raw) if any(v.strip() for v in row)]
    if not nonempty:
        raise ValueError("The original Borg annotation file is empty")
    header_line,headers = nonempty[0]
    names = [normalized(h) for h in headers]
    if len(set(names)) != len(names):
        raise ValueError("Original Borg headers are ambiguous")
    subject_candidates = [i for i,h in enumerate(names) if "subject" in h or "participant" in h or h in ("id","id_subject")]
    task_candidates = [i for i,h in enumerate(names) if h == "task_order"]
    before_candidates = [i for i,h in enumerate(names) if h == "before_task"]
    end_candidates = [i for i,h in enumerate(names) if h == "end_of_trial"]
    duration_candidates = [i for i,h in enumerate(names) if "length_of_trial" in h]
    timed = {i:float(re.fullmatch(r"(\d+)_?sec(?:ond)?s?",h)[1]) for i,h in enumerate(names) if re.fullmatch(r"(\d+)_?sec(?:ond)?s?",h)}
    schema = {"encoding":encoding,"delimiter":dialect.delimiter,"header_csv_line":header_line,"headers":headers,
        "original_data_rows":len(nonempty)-1,"subject_header_candidates":[headers[i] for i in subject_candidates],
        "task_header_candidates":[headers[i] for i in task_candidates],"timed_headers_seconds":{headers[i]:stamp for i,stamp in timed.items()},
        "first_three_raw_data_rows":[r for _,r in nonempty[1:4]]}
    if not (len(subject_candidates) == len(task_candidates) == len(before_candidates) == len(end_candidates) == len(duration_candidates) == 1 and timed):
        return {"member":name,"member_sha256":__import__("hashlib").sha256(payload).hexdigest(),"schema":schema,
            "annotation_schema_resolved":False,"counts_not_claimed":True,"reason":"Exact original identity/time fields require direct schema review before interpreting labels"}
    subject_index,task_index = subject_candidates[0],task_candidates[0]
    before_index,end_index,duration_index = before_candidates[0],end_candidates[0],duration_candidates[0]
    # Original hierarchical CSV: one explicit subject header opens six rows.
    # Preserve the empty identity cells; validate the full block before using
    # its explicit subject identifier, without inventing any outcome or clock.
    expected_tasks = {"task1_35i","task2_45i","task3_55i","task4_35e","task5_45e","task6_55e"}
    blocks,block = [],None
    for line,row in nonempty[1:]:
        if len(row) != len(headers):
            raise ValueError("An original Borg data row has a different number of fields")
        explicit = row[subject_index].strip()
        if explicit:
            if block is not None:
                blocks.append(block)
            block = {"explicit_subject":explicit,"header_csv_line":line,"rows":[]}
        if block is None:
            raise ValueError("An original task row precedes every explicit subject header")
        block["rows"].append((line,row))
    if block is not None:
        blocks.append(block)
    if len({b["explicit_subject"] for b in blocks}) != len(blocks):
        raise ValueError("An explicit original subject begins more than one ambiguous block")
    for block in blocks:
        tasks = [row[task_index].strip() for _,row in block["rows"]]
        if len(tasks) != 6 or set(tasks) != expected_tasks:
            raise ValueError("An explicit original subject block does not contain exactly the six documented task identities")
    rows_with_identity = [(line,row,block["explicit_subject"],block["header_csv_line"])
        for block in blocks for line,row in block["rows"]]
    counts = Counter()
    per_person,per_condition = defaultdict(Counter),defaultdict(Counter)
    rows,cells,identities = [],[],set()
    known_reports = {}
    for line,row,person,subject_header_line in rows_with_identity:
        if len(row) != len(headers):
            raise ValueError("An original Borg data row has a different number of fields")
        task = row[task_index].strip()
        if not person or not task or (person,task) in identities:
            raise ValueError("Original within-exercise person/task identity is ambiguous")
        identities.add((person,task))
        duration = number(row[duration_index])
        row_count = Counter()
        actual_timed = []
        for index in [before_index,*sorted(timed,key=timed.get),end_index]:
            value = number(row[index])
            empty = not row[index].strip()
            in_range = value is not None and 6 <= value <= 20
            stamp = timed.get(index)
            category = "before_task" if index == before_index else "terminal" if index == end_index else "timed"
            status = "empty" if empty else "non_numeric_or_missing_marker" if value is None else "outside_documented_instrument" if not in_range else "in_documented_instrument"
            if category == "timed" and in_range:
                if duration is None:
                    status = "timed_range_valid_but_end_unknown"
                elif stamp > duration:
                    status = "timed_range_valid_after_recorded_end"
                else:
                    status = "timed_range_valid_within_recorded_end"
                    key = (person,task,stamp)
                    if key in known_reports:
                        raise ValueError("An original timed response clock was duplicated")
                    known_reports[key] = value
                    actual_timed.append((stamp,value))
            row_count[category+"_"+status] += 1
            row_count["original_nonempty_borg_cells"] += int(not empty)
            cells.append({"original_member":name,"original_csv_line":line,"original_csv_column":index+1,
                "original_person_from_verified_explicit_block":person,"raw_subject_cell":row[subject_index],
                "explicit_subject_block_header_csv_line":subject_header_line,
                "original_task_identifier":task,"original_header":headers[index],"raw_value":row[index],
                "numeric_value":value,"category":category,"timed_header_seconds":stamp,"recorded_trial_length_seconds":duration,"status":status})
        end_value = number(row[end_index])
        same_clock = [(stamp,value) for stamp,value in actual_timed if duration is not None and stamp == duration]
        if end_value is not None and 6 <= end_value <= 20:
            if same_clock:
                row_count["terminal_same_clock_candidate"] += 1
                row_count["terminal_same_clock_same_value_candidate"] += int(same_clock[0][1] == end_value)
                row_count["terminal_same_clock_conflicting_value_candidate"] += int(same_clock[0][1] != end_value)
            else:
                row_count["terminal_without_matching_timed_clock_not_counted_as_new_report"] += 1
        row_count["timed_ordered_pairs"] = max(len(actual_timed)-1,0)
        row_count["timed_targets_with_two_actual_timed_priors"] = max(len(actual_timed)-2,0)
        row_count["original_task_rows"] = 1
        row_count["original_blank_subject_cells_in_verified_explicit_block"] = int(not row[subject_index].strip())
        counts.update(row_count)
        per_person[person].update(row_count)
        per_condition[task].update(row_count)
        rows.append({"original_csv_line":line,"original_person_from_verified_explicit_block":person,"raw_subject_cell":row[subject_index],
            "explicit_subject_block_header_csv_line":subject_header_line,"original_task_identifier":task,
            "recorded_trial_length_seconds":duration,"counts":dict(row_count),"actual_timed_response_seconds":[v[0] for v in actual_timed],
            "terminal_not_assumed_new_response_or_clock":True,"before_task_exact_elapsed_clock_unknown":True})
    return {"member":name,"member_sha256":__import__("hashlib").sha256(payload).hexdigest(),"schema":schema,
        "annotation_schema_resolved":True,"original_people":len(per_person),"original_task_identifiers":len(per_condition),
        "explicit_subject_blocks":len(blocks),"all_blocks_have_exactly_six_unique_documented_task_identifiers":True,
        "blank_subject_cells_preserved_and_identity_linked_only_to_verified_explicit_block":True,
        "counts":dict(counts),"per_person":{k:dict(v) for k,v in sorted(per_person.items())},
        "per_condition":{k:dict(v) for k,v in sorted(per_condition.items())},"known_distinct_timed_report_clocks":len(known_reports),
        "original_cell_lineage":cells,"original_task_row_lineage":rows,
        "before_task_cells_separate_from_timed_clocks":True,"terminal_cells_not_added_to_unique_timed_reports":True,
        "across_task_chronology_inferred":False,"participant_partition_created":False}


def inspect():
    receipt_path = DIRECTORY/"receipt.json"
    receipt = json.loads(receipt_path.read_text())
    archive_path = DIRECTORY/receipt["local_filename"]
    if (not receipt["original_archive_complete_and_verified"] or archive_path.stat().st_size != retrieval.SIZE
        or receipt["official_md5"] != retrieval.MD5 or digest(archive_path,"md5") != retrieval.MD5
        or receipt["sha256"] != digest(archive_path) or receipt["retrieval_code_sha256"] != digest(Path(retrieval.__file__))
        or receipt["record_metadata_sha256"] != digest(DIRECTORY/"metadata.json")):
        raise ValueError("Original public ZIPmetadata/size/MD5/SHA256receipt is not verified")
    inventory,annotations,documents = [],[],[]
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            inventory.append({"member":info.filename,"uncompressed_bytes":info.file_size,"compressed_bytes":info.compress_size,"crc32":f"{info.CRC:08x}"})
            path = PurePosixPath(info.filename.replace("\\","/"))
            if path.name.casefold() == "borg_data.csv":
                if info.file_size>SMALL_LIMIT:
                    raise ValueError("Original Borg annotation unexpectedly exceeds the8MBsmall-file limit")
                annotations.append(inspect_borg(info.filename,archive.read(info)))
            if path.name.casefold().startswith("readme") and path.suffix.casefold() in (".txt",".md","") and info.file_size<=SMALL_LIMIT:
                payload = archive.read(info)
                documents.append({"member":info.filename,"bytes":len(payload),"text":payload.decode("utf-8-sig",errors="replace")[:100000]})
    if not annotations:
        raise ValueError("The original published Borg annotation member was not found; do not invent another table")
    report = {"version":1,"inspection":"complete","inspected_at":datetime.now(timezone.utc).isoformat(),
        "inspection_code_sha256":digest(Path(__file__)),"original_receipt_sha256":digest(receipt_path),"original_archive_sha256":receipt["sha256"],
        "official_original_size_and_md5_verified":True,"archive_file_count":len(inventory),"archive_inventory":inventory,
        "annotation_files":annotations,"readme_documents":documents,
        "included_code_or_weight_members_not_executed":[v["member"] for v in inventory if PurePosixPath(v["member"].replace("\\","/")).suffix.casefold() in (".py",".m",".r",".ipynb",".pkl",".pickle",".joblib",".pt",".pth")],
        "included_code_executed":False,"supplied_models_or_weights_loaded":False,"sensor_csvs_read":0,
        "sensor_annotation_temporal_join_verified":False,"native_target_merge":False,"participant_partition_created":False,
        "model_fitting_started":False,"scope":"Original complete public ZIPverified before reading any member. Only inventory,small original BorgCSVand READMEtext read; no bulk extraction,code execution,sensor alignment,scaleconversion,imputation or fitting. Original before_task,timed,and terminal Borgcells kept separate. Terminal responses are not assumed extra distincttimedlabels; clock/valuecoincidences,post-end populatedcells,instrument violations and naturalmissingness reported explicitly. Task identifiers never interpreted as actual between-task chronology."}
    output = DOCS/"wsd4fedsrm-original-inspection.json"
    output.write_text(json.dumps(report,indent=2,ensure_ascii=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"inspection":"complete","archive_files":len(inventory),"annotation_files":[{k:v for k,v in a.items() if k in ("member","annotation_schema_resolved","original_people","original_task_identifiers","counts","known_distinct_timed_report_clocks","schema")} for a in annotations],
        "sensor_csvs_read":0,"model_fitting_started":False},ensure_ascii=True),flush=True)
    return report


if __name__ == "__main__":
    inspect()
