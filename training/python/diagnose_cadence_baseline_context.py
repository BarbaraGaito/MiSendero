"""Screen actual session-preexercise baselines without fitting a model."""
from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import cadence_association_inputs as association
from fatigue_dynamics import load_inputs
from public_sources import RAW, ROOT, digest


def summarize(values):
    data = np.asarray(values,float)
    data = data[np.isfinite(data)]
    if not len(data):
        return {"actual_values":0,"minimum":None,"median":None,"maximum":None}
    return {"actual_values":len(data),"minimum":float(np.min(data)),"median":float(np.median(data)),"maximum":float(np.max(data))}


def screen():
    source,held,cache,manifests = association.load()
    frame,train,test,_,_ = load_inputs()
    cache = cache.set_index("row_key")
    sessions = json.loads((RAW/"geofatigue/session_metadata.json").read_text())
    identities,_ = association.previous_native.identities.input_rows()
    identities = {r["row_key"]:r for r in identities if r["cohort"] == "canonical"}
    grouped = defaultdict(list)
    for proof in manifests["native"]["lineage"]:
        grouped[tuple(proof["source_prefixes"])].append(proof)
    minute = pd.Timedelta(minutes=1)
    fitting_keys = set(train.row_key)
    observations,session_proofs = [],[]
    with zipfile.ZipFile(association.previous_native.ARCHIVE) as archive:
        for prefixes,rows in sorted(grouped.items()):
            person = rows[0]["participant"]
            signal,members = association.previous_native.read_pulse(archive,prefixes,person)
            identity = identities[rows[0]["row_key"]]
            now = pd.Timestamp(identity["current_time_us"],unit="us",tz="UTC")
            matching = [s for s in sessions[person] if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"])]
            assert len(matching) == 1
            session = matching[0]
            start = pd.Timestamp(session["start_time"])
            first_task = min(pd.Timestamp(task["start_time"]) for task in session["tasks"])
            lower = max(start,first_task-5*minute)
            observed = signal[(signal.index >= lower)&(signal.index+minute <= first_task)]
            mean = float(observed.mean()) if len(observed) else np.nan
            lowest = float(observed.min()) if len(observed) else np.nan
            groups = {r["group_key"] for r in rows}
            assert len(groups) == 1
            session_proofs.append({"group_key":next(iter(groups)),"session_start":start.isoformat(),"first_task_start":first_task.isoformat(),
                "baseline_lower_bound":lower.isoformat(),"actual_complete_minutes":len(observed),"actual_minute_starts":[t.isoformat() for t in observed.index],
                "session_preexercise_mean_hr_bpm":mean if np.isfinite(mean) else None,
                "session_preexercise_lowest_minute_hr_bpm":lowest if np.isfinite(lowest) else None,
                "source_members":members,"partition":"fitting" if rows[0]["row_key"] in fitting_keys else "reserved"})
            for row in rows:
                identity = identities[row["row_key"]]
                query = pd.Timestamp(identity["current_time_us"],unit="us",tz="UTC")
                current_task_start = pd.Timestamp(identity["current_lower_bound_us"],unit="us",tz="UTC")
                assert first_task <= current_task_start < query
                if len(observed):
                    assert observed.index[-1]+minute <= first_task < query
                current_hr = float(cache.loc[row["row_key"],"current_hr_bpm"])
                task_baseline = float(cache.loc[row["row_key"],"baseline_hr_bpm"])
                def ratio(base):
                    return current_hr/base if np.isfinite(base) and base > 0 else np.nan
                observations.append({"row_key":row["row_key"],"group_key":row["group_key"],
                    "partition":"fitting" if row["row_key"] in fitting_keys else "reserved",
                    "session_preexercise_mean_hr_bpm":mean,"session_preexercise_lowest_minute_hr_bpm":lowest,
                    "current_task_preexercise_mean_hr_bpm":task_baseline,"current_to_task_baseline_ratio":ratio(task_baseline),
                    "current_to_session_mean_ratio":ratio(mean),"current_to_session_lowest_ratio":ratio(lowest)})
    assert len(observations) == 666 and len({r["row_key"] for r in observations}) == 666
    rows = pd.DataFrame(observations)
    quantities = ["session_preexercise_mean_hr_bpm","session_preexercise_lowest_minute_hr_bpm","current_task_preexercise_mean_hr_bpm",
                  "current_to_task_baseline_ratio","current_to_session_mean_ratio","current_to_session_lowest_ratio"]
    by_partition = {part:{"original_native_cases":int(rows.partition.eq(part).sum()),
        "quantities":{name:summarize(rows.loc[rows.partition.eq(part),name]) for name in quantities}}
        for part in ("fitting","reserved")}
    fit_rows = rows[rows.partition.eq("fitting")]
    comparable = fit_rows.current_task_preexercise_mean_hr_bpm.notna()&fit_rows.session_preexercise_mean_hr_bpm.notna()
    drift = fit_rows.loc[comparable,"current_task_preexercise_mean_hr_bpm"]-fit_rows.loc[comparable,"session_preexercise_mean_hr_bpm"]
    source_people = source.groupby("group_key").baseline_hr_bpm.agg(["min","max"])
    assert np.allclose(source_people["min"],source_people["max"],rtol=0,atol=1e-12)
    result = {"version":1,"screened_at":datetime.now(timezone.utc).isoformat(),"status":"actual_baseline_context_screen_completed",
        "code_sha256":digest(Path(__file__)),"association_source_provenance_sha256":digest(association.SOURCE_DIRECTORY/"provenance.json"),
        "association_native_provenance_sha256":digest(association.NATIVE_DIRECTORY/"provenance.json"),
        "native_reader_code_sha256":digest(Path(association.previous_native.__file__)),
        "session_metadata_sha256":digest(RAW/"geofatigue/session_metadata.json"),"raw_archive_sha256":digest(association.previous_native.ARCHIVE),
        "public_real_data_policy_sha256":digest(ROOT/"docs/fatigue-80-2026-10-25/public-real-data-policy.json"),
        "source_fitting_people_rest_hr_summary":summarize(source_people["min"]),
        "source_fitting_current_to_rest_hr_ratio_summary":summarize(source.hr_ratio_baseline),
        "source_reserved_targets_used_for_diagnostic_selection":0,"native_current_borg_used_for_diagnostic":False,
        "native_actual_sessions":len(session_proofs),"native_session_baseline_observed_minutes":sum(r["actual_complete_minutes"] for r in session_proofs),
        "native_session_baseline_available_sessions":sum(r["actual_complete_minutes"] > 0 for r in session_proofs),
        "native_original_cases_by_partition":by_partition,"native_fitting_task_minus_session_mean_hr_bpm":summarize(drift),
        "native_fitting_comparable_cases_task_baseline_above_session_by_more_than10bpm":int((drift>10).sum()),
        "native_fitting_comparable_cases":int(comparable.sum()),"all_candidate_native_baseline_minutes_precede_first_task":True,
        "original_native_cases_dropped":0,"original_native_inputs_overwritten":False,"synthetic_values":0,
        "model_fitting_started":False,"new_input_cache_and_independent_raw_window_audit_required":True,
        "interpretation":"Source resting HR precedes the full treadmill protocol; existing native mean precedes each task and may reflect completed exercise. These actual session-before-first-task mean/minimum candidates investigate that context difference without using native Borg labels. Native pre-task posture remains undocumented, so no claim of identical seated-rest assays or guaranteed model improvement is made. All missing session baselines must remain unavailable and all487/179 native cases retained.",
        "session_lineage":session_proofs}
    output = ROOT/"docs/fatigue-80-2026-10-25/cadence-baseline-context-diagnostic.json"
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({key:result[key] for key in ("status","source_fitting_people_rest_hr_summary","source_fitting_current_to_rest_hr_ratio_summary",
        "native_actual_sessions","native_session_baseline_available_sessions","native_original_cases_by_partition",
        "native_fitting_task_minus_session_mean_hr_bpm","native_fitting_comparable_cases_task_baseline_above_session_by_more_than10bpm")}),flush=True)
    return result


if __name__ == "__main__":
    screen()
