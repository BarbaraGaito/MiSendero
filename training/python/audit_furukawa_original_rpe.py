"""Audit original experiment2 RPE cells and strictly preceding measured HR points."""
from __future__ import annotations

import json
import math
import re
from datetime import time,datetime,timezone
from pathlib import Path

import numpy as np
import openpyxl
from sklearn.model_selection import GroupShuffleSplit

import fetch_more_public_rpe_metadata as repository
from public_sources import ROOT,digest,group_key

DOCS = ROOT/"docs/fatigue-80-2026-10-25"
REVIEW = DOCS/"furukawa-runners-protocol-review.md"
FILES = {"rpe":"RPE_Experiment2.xlsx","hr":"HR_Experiment2.xlsx","steps":"Step Frequency_Experiment2.xlsx"}
UNITS = {"rpe":"Rating of Perceived Exertion in Points","hr":"Heart Rate in bpm (beats per minute)","steps":"Step Frequency in spm (steps per minute)"}
CONDITIONS = {"-10bpmFS","-5bpmFS","-3bpmFS","NF","+3bpmFS","+5bpmFS","+10bpmFS"}
PEOPLE = [f"p{i}" for i in range(1,17)]


def seconds(value):
    if isinstance(value,str) and re.fullmatch(r"[0-2][0-9]:[0-5][0-9]:[0-5][0-9]",value):
        hour,minute,second = map(int,value.split(":"))
        if hour > 23:
            raise ValueError("Invalid explicit elapsed clock")
        return hour*3600+minute*60+second
    if not isinstance(value,time) or value.microsecond:
        raise ValueError("Only original explicit whole-second elapsed clocks are admitted")
    return value.hour*3600+value.minute*60+value.second


def read_original(kind):
    receipt = json.loads((repository.DIRECTORY/"original-files-receipt.json").read_text())
    item = next(v for v in receipt["files"] if v["source"] == "runners" and v["filename"] == FILES[kind])
    path = repository.DIRECTORY/"files/runners"/FILES[kind]
    if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"] or digest(path,"md5") != item["repository_md5"]:
        raise ValueError("An original public experiment2 workbook changed")
    workbook = openpyxl.load_workbook(path,data_only=False)
    if {s.title.strip() for s in workbook} != CONDITIONS:
        raise ValueError("Original experiment2 condition identifiers changed")
    tables = {}
    for sheet in workbook:
        condition = sheet.title.strip()
        if sheet["B1"].value != UNITS[kind] or sheet["A2"].value != "Time" or [sheet.cell(2,c).value for c in range(2,18)] != PEOPLE:
            raise ValueError("Original experiment2 units/person headers changed")
        values,coordinates = {},{}
        for row in sheet.iter_rows(min_row=3):
            if not any(c.value is not None for c in row):
                continue
            stamp = seconds(row[0].value)
            if stamp in values or any(c.value is not None for c in row[17:]):
                raise ValueError("Duplicate/extra original time or participant cells")
            values[stamp],coordinates[stamp] = {},{}
            for column,person in enumerate(PEOPLE,start=2):
                cell = sheet.cell(row[0].row,column)
                if cell.data_type == "f" or not isinstance(cell.value,(int,float)) or not math.isfinite(cell.value):
                    raise ValueError("Missing/formula/nonfinite source values cannot become reported targets/sensors")
                values[stamp][person],coordinates[stamp][person] = float(cell.value),cell.coordinate
        expected = [60,180,300] if kind == "rpe" else list(range(10,311,10))
        if sorted(values) != expected:
            raise ValueError("Original experiment2 report/sample clocks changed")
        tables[condition] = {"original_sheet":sheet.title,"values":values,"coordinates":coordinates}
    return tables,{"filename":FILES[kind],"sha256":digest(path),"repository_md5":item["repository_md5"],"bytes":item["bytes"],"license":item["license"]}


def audit():
    tables,files = {},{}
    for kind in FILES:
        tables[kind],files[kind] = read_original(kind)
    original_people = np.asarray(PEOPLE)
    fit,res = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(original_people,groups=original_people))
    fitting,reserved = set(original_people[fit]),set(original_people[res])
    records,pairs = [],[]
    def key(condition,person,stamp):
        return group_key(f"Furukawa2023-original-exp2:{condition}:{person}:RPE:{stamp}")
    for condition in sorted(CONDITIONS):
        for person in PEOPLE:
            for index,stamp in enumerate((60,180,300)):
                raw = tables["rpe"][condition]
                current = raw["values"][stamp][person]
                if not 6 <= current <= 20:
                    raise ValueError("Original Borg points changed; do not convert/censor the source")
                sensors = {}
                for kind in ("hr","steps"):
                    table = tables[kind][condition]
                    window = [t for t in table["values"] if stamp-60 <= t < stamp]
                    sensors[kind] = [{"original_sheet":table["original_sheet"],"original_cell":table["coordinates"][t][person],
                        "elapsed_seconds":t,"value":table["values"][t][person]} for t in sorted(window)]
                    if len(window) != (5 if stamp == 60 else 6) or any(t >= stamp for t in window):
                        raise ValueError("Original pre-report sensor coverage changed")
                record = {"row_key":key(condition,person,stamp),"group_key":group_key(f"Furukawa2023-original-exp2-person:{person}"),
                    "sequence_key":group_key(f"Furukawa2023-original-exp2-condition:{condition}:person:{person}"),
                    "original_person_header":person,"original_condition":condition,"original_rpe_sheet":raw["original_sheet"],
                    "original_rpe_cell":raw["coordinates"][stamp][person],"original_rpe_points":current,"elapsed_seconds":stamp,
                    "source_partition":"fitting" if person in fitting else "reserved","preceding_measured_sensor_points":sensors}
                records.append(record)
                if index:
                    previous = (60,180,300)[index-1]
                    second = (60,180,300)[index-2] if index > 1 else None
                    pairs.append({"row_key":record["row_key"],"group_key":record["group_key"],"source_partition":record["source_partition"],
                        "prior_row_key":key(condition,person,previous),"prior_elapsed_seconds":previous,"prior_rpe_points":raw["values"][previous][person],
                        "second_prior_row_key":None if second is None else key(condition,person,second),
                        "second_prior_elapsed_seconds":second,"second_prior_rpe_points":None if second is None else raw["values"][second][person]})
    if len(records) != 336 or len(pairs) != 224 or len({r["row_key"] for r in records}) != 336:
        raise ValueError("Original experiment2 observed responses/pairs changed")
    counts = {partition:{"people":len(fitting if partition == "fitting" else reserved),
        "actual_responses":sum(r["source_partition"] == partition for r in records),
        "actual_adjacent_pairs":sum(r["source_partition"] == partition for r in pairs),
        "pairs_with_second_genuine_prior":sum(r["source_partition"] == partition and r["second_prior_row_key"] is not None for r in pairs)}
        for partition in ("fitting","reserved")}
    return {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "audit_code_sha256":digest(Path(__file__)),"original_file_receipt_sha256":digest(repository.DIRECTORY/"original-files-receipt.json"),
        "protocol_review_sha256":digest(REVIEW),"primary_article":"https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0280147",
        "primary_dataset":"https://doi.org/10.6084/m9.figshare.21779501","original_files":files,
        "original_experiment":2,"original_people":16,"all_original16_people_retained":True,"original_conditions":7,
        "original_actual_responses":336,"original_actual_adjacent_pairs":224,"original_source_rpe_values_min_max":[min(r["original_rpe_points"] for r in records),max(r["original_rpe_points"] for r in records)],
        "whole_person_split":{"method":"GroupShuffleSplit20percent_seed42_before_pair_eligibility","fitting_original_people":sorted(fitting),"reserved_original_people":sorted(reserved)},
        "source_partition_counts":counts,"response_lineage":records,"pair_lineage":pairs,
        "exp1_not_joined_or_used":True,"unknown_cross_experiment_person_mapping_not_invented":True,
        "only_original_within_condition_histories":True,"all_sensor_timestamps_strictly_before_current_rpe":True,
        "source_outcomes_must_remain_separate":True,"native_target_merge_approved":False,"step_frequency_native_sensor_join_approved":False,
        "auxiliary_pre_report_hr_task_eligible":True,"synthetic_rows":0,"imputed_source_targets_or_sensors":0,
        "invented_ages_rest_baselines_or_native_phase_mapping":0,"model_fitting_started":False,
        "scope":"Original experiment2only:336reported Borg-point cells in7conditions/16raw people,without the paper's one-person SFexclusion.224actual adjacent within-condition pairs; no histories between randomized conditions or other experiment.12people/252responses/168pairs fitting;4people/84responses/56pairs reserved before eligibility. Original points remain separate,never converted to native0-10. Strictly preceding measured HR and step-frequency cells documented; no interpolation,synthetic examples,age/rest invention or native step-frequency mapping."}


if __name__ == "__main__":
    report = audit()
    output = DOCS/"furukawa-original-rpe-verification.json"
    output.write_text(json.dumps(report,indent=2,ensure_ascii=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("verification","original_actual_responses","original_actual_adjacent_pairs","source_partition_counts","auxiliary_pre_report_hr_task_eligible","model_fitting_started")}),flush=True)
