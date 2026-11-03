"""Alternative causal input views of existing real Borg reports.

Only history availability changes. Targets, people and original validation
queries do not change. The views are not new questionnaire measurements.
"""
from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_calibrated import previous_reports
from fatigue_dynamics import CONTEXT, load_inputs as canonical_inputs
from fatigue_features import RESEARCH
from fatigue_warm_sgd import core_candidate
from public_sources import OUTPUT, RAW, digest, group_key, verify_source_snapshot

DIRECTORY = RESEARCH / "observed-prior-views-80-v1"


def history_row(responses, session, task, now):
    start = pd.Timestamp(task["start_time"])
    past = previous_reports(responses, now, pd.Timestamp(session["start_time"]))
    if past.empty:
        raise ValueError("At least one actual earlier eligible report is required")
    last = past.iloc[-1]
    values = past["borg_scale"].to_numpy(float)
    if not np.isfinite(values).all() or not np.isin(values, np.arange(11)).all() or past["time"].duplicated().any():
        raise ValueError("Unique chronological native Borg observations required")
    result = {"prior_borg": float(last["borg_scale"]), "prior_age_minutes": (now-last["time"]).total_seconds()/60,
              "prior2_borg": np.nan, "prior2_age_minutes": np.nan, "prior_borg_slope": np.nan,
              "prior_in_current_task": int(last["time"] >= start),
              "prior_count_current_task": int(past["time"].ge(start).sum()), "elapsed_minutes": (now-start).total_seconds()/60}
    if len(past) >= 2:
        second = past.iloc[-2]
        interval = (last["time"]-second["time"]).total_seconds()/60
        result.update(prior2_borg=float(second["borg_scale"]), prior2_age_minutes=(now-second["time"]).total_seconds()/60,
                      prior_borg_slope=(float(last["borg_scale"])-float(second["borg_scale"]))/interval)
    completed = [t for t in session["tasks"] if pd.Timestamp(t["end_time"]) <= start]
    result.update(task_order=len(completed)+1, cumulative_active_minutes=result["elapsed_minutes"]+sum(
        (pd.Timestamp(t["end_time"])-pd.Timestamp(t["start_time"])).total_seconds()/60 for t in completed))
    result.update({"terrain_"+name: int(task["label"] == name) for name in ("stairs", "ramp", "flat_trail")})
    return result, past


def alternative_histories(past):
    if len(past) > 10:
        raise ValueError("Inspect unusually dense real report history before enumerating input views")
    for size in range(1, len(past)):
        for positions in itertools.combinations(range(len(past)), size):
            yield past.iloc[list(positions)], positions == tuple(range(size))


def build():
    frame, train, test, manifest, _ = canonical_inputs()
    features = core_candidate(manifest)["features"]
    raw_path, session_path = RAW / "geofatigue/self_reported_fatigue_level.original.tab", RAW / "geofatigue/session_metadata.json"
    reports = pd.read_csv(raw_path)
    reports["time"] = pd.to_datetime(reports["time"], utc=True)
    if reports.duplicated(["id", "time"]).any():
        raise ValueError("Original report identities are ambiguous")
    sessions = json.loads(session_path.read_text())
    canonical = json.loads((OUTPUT / "fatigue/provenance.json").read_text())["lineage"]
    fitting_keys = set(train["row_key"])
    rows, lineage, reconstructed, history_counts = [], [], [], []
    for i, source in enumerate(canonical):
        person = "p"+re.search(r"/p(\d+)-", source["lineage"]["member"])[1]
        now = pd.Timestamp(source["lineage"]["label_time"])
        personal = reports[reports["id"].eq(person)]
        target = personal[personal["time"].eq(now)]
        matches = [(s, t) for s in sessions[person] for t in s["tasks"] if pd.Timestamp(t["start_time"]) <= now <= pd.Timestamp(t["end_time"])]
        if len(target) != 1 or len(matches) != 1:
            raise ValueError("A canonical target or task differs from the original actual response")
        native = float(target.iloc[0]["borg_scale"])
        if not np.isfinite(native) or native != round(native) or not 0 <= native <= 10 or f"Borg {int(native)}" != frame.iloc[i]["label"]:
            raise ValueError("A canonical target differs from the exact original native integer")
        session, task = matches[0]
        original, past = history_row(personal, session, task, now)
        reconstructed.append(original)
        if source["row_key"] not in fitting_keys:
            continue
        history_counts.append(len(past))
        for retained, prefix in alternative_histories(past):
            values, used = history_row(retained, session, task, now)
            indexes = [int(j) for j in used.index]
            view_key = group_key("GeoFatigue-prior-view:"+source["row_key"]+":"+",".join(map(str, indexes)))
            rows.append({**values, "view_key": view_key, "target_row_key": source["row_key"], "group_key": frame.iloc[i]["group_key"],
                         "prefix_only": prefix, "label": frame.iloc[i]["label"]})
            lineage.append({"view_key": view_key, "target_row_key": source["row_key"], "actual_target_source_row": int(target.index[0]),
                            "prediction_time": now.isoformat(), "session_start": session["start_time"], "task_start": task["start_time"],
                            "retained_original_report_rows": indexes, "prefix_only": prefix,
                            "latest_input_time": used.iloc[-1]["time"].isoformat(),
                            "oldest_input_time": used.iloc[0]["time"].isoformat()})
    np.testing.assert_allclose(pd.DataFrame(reconstructed)[features], frame[features], rtol=0, atol=1e-12, equal_nan=True)
    views = pd.DataFrame(rows)
    if views["view_key"].duplicated().any() or not set(views["group_key"]) <= set(train["group_key"]) or set(views["group_key"]) & set(test["group_key"]):
        raise ValueError("Alternative input views duplicated or leaked held-out people")
    evidence = {"version": 1, "feature_code_sha256": digest(Path(__file__)), "canonical_dataset_sha256": manifest["dataset_sha256"],
                "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in ("fatigue_calibrated.py", "fatigue_dynamics.py", "fatigue_warm_sgd.py")},
                "raw_reports_sha256": digest(raw_path), "session_metadata_sha256": digest(session_path), "features": features,
                "original_queries_reconstructed": 666, "training_unique_actual_targets": 487, "test_unique_actual_targets": 179,
                "alternative_input_views": len(views), "targets_with_alternatives": int(views["target_row_key"].nunique()),
                "prefix_only_views": int(views["prefix_only"].sum()), "max_eligible_history_reports": max(history_counts),
                "new_observed_targets": 0, "synthetic_borg_targets": 0, "interpolated_targets": 0, "assumed_zero_targets": 0,
                "heldout_person_views_prepared": False, "lineage": lineage,
                "policy": "Proper nonempty subsets of actual same-session reports 1-15 minutes before each existing training query. Recompute both priors, slope and available task-report count from retained observations only. Targets are repeated as alternative input views, not claimed as additional measured reports. Validation/test retain their original complete histories and original denominators."}
    return views, evidence


def prepare():
    verify_source_snapshot("fatigue")
    DIRECTORY.mkdir(exist_ok=True)
    if any((DIRECTORY / name).exists() for name in ("dataset.csv", "provenance.json")):
        raise ValueError("Preserve the frozen prior-view snapshot before changing preparation")
    views, evidence = build()
    path = DIRECTORY / "dataset.csv"
    views.to_csv(path, index=False)
    evidence["dataset_sha256"] = digest(path)
    (DIRECTORY / "provenance.json").write_text(json.dumps(evidence, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Prepared {len(views)} alternative input views of {evidence['targets_with_alternatives']} real fitting reports; zero new Borg measurements", flush=True)


def load():
    evidence = json.loads((DIRECTORY / "provenance.json").read_text())
    if evidence["feature_code_sha256"] != digest(Path(__file__)) or evidence["dataset_sha256"] != digest(DIRECTORY / "dataset.csv"):
        raise ValueError("Frozen causal prior-view snapshot changed")
    for name, sha in evidence["dependency_code_sha256"].items():
        if digest(Path(__file__).with_name(name)) != sha:
            raise ValueError("Prior-view feature dependency changed")
    return pd.read_csv(DIRECTORY / "dataset.csv", dtype={"label": str}), evidence


if __name__ == "__main__":
    prepare()
