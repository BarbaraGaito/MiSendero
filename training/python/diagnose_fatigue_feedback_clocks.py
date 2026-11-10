"""Training-only feedback clock inspection; no labels, fitting or gate changes."""
import json
import re
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd

import fatigue_survey_prior_teachers as study
from public_sources import RAW,OUTPUT,ROOT,digest


def summary(values):
    values = np.asarray(values,dtype=float)
    return {"count":len(values),"minimum_seconds":float(values.min()),"median_seconds":float(np.median(values)),
        "maximum_seconds":float(values.max()),"values_and_counts":{str(k):int(v) for k,v in pd.Series(values).value_counts().sort_index().to_dict().items()}}


def inspect():
    _,train,_,_,expanded,_,_,_ = study.load_inputs()
    keys = set(train.row_key)
    original_path = OUTPUT/"fatigue/provenance.json"
    original = json.loads(original_path.read_text())
    reports_path = RAW/"geofatigue/self_reported_fatigue_level.original.tab"
    reports = pd.read_csv(reports_path,usecols=["id","time"])
    reports["time"] = pd.to_datetime(reports.time,utc=True)
    sessions_path = RAW/"geofatigue/session_metadata.json"
    sessions = json.loads(sessions_path.read_text())
    ages = []
    for item in original["lineage"]:
        if item["row_key"] not in keys:
            continue
        person = "p"+re.search(r"/p(\d+)-",item["lineage"]["member"])[1]
        now = pd.Timestamp(item["lineage"]["label_time"])
        session = next(s for s in sessions[person] if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"]))
        past = reports[reports.id.eq(person) & (reports.time >= pd.Timestamp(session["start_time"])) & (reports.time < now)]
        if past.empty:
            raise ValueError("An original eligible query has no actual earlier public report")
        ages.append((now-past.time.max()).total_seconds())
    if len(ages) != 487 or any(a < 60 for a in ages):
        raise ValueError("Reinspect changed native original report clock distribution")
    _,manifests,_ = study.parent.source_inputs()
    sts = {r["row_key"]:r for r in manifests["sts"]["lineage"]}
    sts_ages = []
    for key in expanded.loc[expanded.source_domain.eq("sts"),"row_key"]:
        row = sts[key]
        age = row["response_time_seconds"]-row["prior_response_time_seconds"]
        if not 60 <= age <= 900:
            raise ValueError("STS original report clock is not a real eligible prior")
        sts_ages.append(age)
    worker = {r["row_key"]:r for r in manifests["worker"]["lineage"]}
    endpoint_gaps,unknown_previous_endpoint = [],0
    for row in expanded[expanded.source_domain.eq("worker")].itertuples():
        if row.prior_row_key not in worker:
            unknown_previous_endpoint += 1
            continue
        current,previous = worker[row.row_key],worker[row.prior_row_key]
        if current["questionnaire_worksheet_row"] != previous["questionnaire_worksheet_row"]:
            raise ValueError("Source clock endpoints belong to different sessions")
        gap = (current["repetition_end_elapsed_ms"]-previous["repetition_end_elapsed_ms"])/1000.
        if gap <= 0:
            raise ValueError("Source physical-recording endpoints are not chronological")
        endpoint_gaps.append(gap)
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"diagnostic_code_sha256":digest(Path(__file__)),
        "native_original_provenance_sha256":digest(original_path),"native_public_report_file_sha256":digest(reports_path),
        "native_session_metadata_sha256":digest(sessions_path),"native_fitting_queries_only":487,
        "native_nearest_actual_report_age":summary(ages),"native_actual_prior_reports_younger_than_60_seconds":0,
        "sts_actual_prior_report_age":summary(sts_ages),"worker_recorded_repetition_endpoint_gap":summary(endpoint_gaps),
        "worker_prior_survey_without_previous_published_sensor_endpoint":unknown_previous_endpoint,
        "worker_endpoint_gap_is_exact_borg_survey_age":False,"test_responses_inspected":False,
        "input_contract_changed":False,"new_fitting_performed":False,"synthetic_reports_added":0,
        "interpretation":"No more recent actual prior report exists for the original fitting queries, so no fabricated fresh input is available. STS supplies exact report gaps. Worker supplies physical repetition endpoints; its exact survey times remain unpublished and those endpoint gaps must not be relabeled as Borg ages. Future transfer should represent observed exposure/context separately rather than assuming equal feedback intervals or inventing source clocks. This is not an accuracy ceiling or a changed native evaluation task."}


if __name__ == "__main__":
    result = inspect()
    path = ROOT/"docs/fatigue-80-2026-10-25/feedback-clock-diagnostic.json"
    path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"native_training_nearest_report_age":result["native_nearest_actual_report_age"],
        "sts_actual_report_age":result["sts_actual_prior_report_age"],
        "worker_recording_endpoint_gap_median_seconds":result["worker_recorded_repetition_endpoint_gap"]["median_seconds"],
        "source_endpoint_gap_is_survey_age":False}))
