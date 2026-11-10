"""Additional original active-task reports for feedback-only model fitting.

Canonical 487/179 outcomes never change. Only noncanonical actual reports of
the original 28 fitting participants can be extra fitting supervision, and
only when a real prior report aged 1-15 minutes is available. Rest reports are
past inputs only, not extra targets; no onset Borg is invented or assumed zero.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_calibrated import previous_reports
from fatigue_dynamics import CONTEXT, feedback_dynamics, load_inputs as canonical_inputs
from fatigue_dynamics_experiment import plan as dynamics_plan
from fatigue_features import RESEARCH
from public_sources import OUTPUT, RAW, digest, group_key, verify_source_snapshot

DIRECTORY = RESEARCH / "extra-observed-feedback-80-v1"


def feedback_row(person, session, task, now):
    start = pd.Timestamp(task["start_time"])
    old = previous_reports(person, now, pd.Timestamp(session["start_time"]))
    if old.empty:
        return None
    last = old.iloc[-1]
    row = {"prior_borg": float(last["borg_scale"]), "prior_age_minutes": (now-last["time"]).total_seconds()/60,
           "prior2_borg": np.nan, "prior2_age_minutes": np.nan, "prior_borg_slope": np.nan,
           "prior_in_current_task": int(last["time"] >= start), "prior_count_current_task": int((old["time"] >= start).sum()),
           "elapsed_minutes": (now-start).total_seconds()/60}
    if len(old) >= 2:
        second = old.iloc[-2]
        interval = (last["time"]-second["time"]).total_seconds()/60
        row.update(prior2_borg=float(second["borg_scale"]), prior2_age_minutes=(now-second["time"]).total_seconds()/60,
                   prior_borg_slope=(float(last["borg_scale"])-float(second["borg_scale"]))/interval)
    completed = [t for t in session["tasks"] if pd.Timestamp(t["end_time"]) <= start]
    row.update(task_order=len(completed)+1, cumulative_active_minutes=row["elapsed_minutes"] + sum(
        (pd.Timestamp(t["end_time"])-pd.Timestamp(t["start_time"])).total_seconds()/60 for t in completed))
    row.update({"terrain_"+name: int(task["label"] == name) for name in ("stairs", "ramp", "flat_trail")})
    dynamics, _ = feedback_dynamics(person, session["tasks"], pd.Timestamp(session["start_time"]), now, task)
    row.update(dynamics)
    return row


def prepare():
    verify_source_snapshot("fatigue")
    frame, train, _, manifest, _ = canonical_inputs()
    raw_path = RAW / "geofatigue/self_reported_fatigue_level.original.tab"
    metadata_path = RAW / "geofatigue/session_metadata.json"
    reports = pd.read_csv(raw_path)
    reports["time"] = pd.to_datetime(reports["time"], utc=True)
    if reports.duplicated(["id", "time"]).any():
        raise ValueError("Original self-report events must be unique")
    sessions = json.loads(metadata_path.read_text(encoding="utf-8"))
    lineage = json.loads((OUTPUT / "fatigue/provenance.json").read_text(encoding="utf-8"))["lineage"]
    columns = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    canonical, rebuilt = {}, []
    for evidence in lineage:
        person = "p"+re.search(r"/p(\d+)-", evidence["lineage"]["member"])[1]
        now = pd.Timestamp(evidence["lineage"]["label_time"])
        matches = [(s, t) for s in sessions[person] for t in s["tasks"] if pd.Timestamp(t["start_time"]) <= now <= pd.Timestamp(t["end_time"])]
        if len(matches) != 1 or (person, now) in canonical:
            raise ValueError("Canonical questionnaire/task identities are ambiguous")
        canonical[person, now] = evidence["row_key"]
        row = feedback_row(reports[reports["id"].eq(person)], *matches[0], now)
        if row is None:
            raise ValueError("Canonical response lost its required earlier input")
        rebuilt.append(row)
    np.testing.assert_allclose(pd.DataFrame(rebuilt)[columns], frame[columns], rtol=0, atol=1e-12, equal_nan=True)
    allowed = set(train["group_key"])
    rows, extra_lineage, exclusions = [], [], []
    noncanonical_active = 0
    for index, response in reports[reports["task"].eq(1)].iterrows():
        person, now = response["id"], response["time"]
        if (person, now) in canonical:
            continue
        noncanonical_active += 1
        group = group_key("GeoFatigue:"+person)
        if group not in allowed:
            exclusions.append({"original_response_row": int(index), "reason": "reserved_or_nonfitting_participant"})
            continue
        matches = [(s, t) for s in sessions[person] for t in s["tasks"] if pd.Timestamp(t["start_time"]) <= now <= pd.Timestamp(t["end_time"])]
        if len(matches) != 1:
            exclusions.append({"original_response_row": int(index), "reason": "ambiguous_active_task"})
            continue
        row = feedback_row(reports[reports["id"].eq(person)], *matches[0], now)
        if row is None:
            exclusions.append({"original_response_row": int(index), "reason": "no_actual_prior_aged_1_to_15_minutes"})
            continue
        value = float(response["borg_scale"])
        if not np.isfinite(value) or value != round(value) or not 0 <= value <= 10:
            raise ValueError("Extra supervision must remain an actual native integer Borg")
        key = group_key("GeoFatigue-extra-feedback:"+person+":"+now.isoformat())
        rows.append({**{c: row[c] for c in columns}, "row_key": key, "group_key": group, "label": f"Borg {int(value)}"})
        extra_lineage.append({"row_key": key, "group_key": group, "original_response_row": int(index),
                              "response_time": now.isoformat(), "task_start": matches[0][1]["start_time"],
                              "actual_observed_borg": value, "prior_age_minutes": row["prior_age_minutes"],
                              "current_or_future_response_used_as_input": False})
    extra = pd.DataFrame(rows)
    if len(extra) != 56 or noncanonical_active != 138 or not set(extra["group_key"]) <= allowed:
        raise ValueError("Inspected extra-observation eligibility/counts changed")
    if extra["row_key"].duplicated().any() or set(extra["row_key"]) & set(frame["row_key"]):
        raise ValueError("Duplicate extra/canonical supervision")
    DIRECTORY.mkdir(exist_ok=True)
    if (DIRECTORY / "provenance.json").exists() or (DIRECTORY / "dataset.csv").exists():
        raise ValueError("Preserve the frozen extra-feedback snapshot before preparing another version")
    extra.to_csv(DIRECTORY / "dataset.csv", index=False)
    result = {"version": 1, "dataset_sha256": digest(DIRECTORY / "dataset.csv"), "feature_code_sha256": digest(Path(__file__)),
              "canonical_dataset_sha256": manifest["dataset_sha256"], "raw_reports_sha256": digest(raw_path),
              "session_metadata_sha256": digest(metadata_path), "feature_order": columns,
              "calibration_code_sha256": digest(Path(__file__).with_name("fatigue_calibrated.py")),
              "dynamics_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics.py")),
              "extra_actual_active_reports": len(extra), "noncanonical_active_reports_in_raw": noncanonical_active,
              "original_validation_rows": 487, "original_test_rows": 179, "unchanged_canonical_features_reconstructed": 666,
              "rest_targets_added": 0, "assumed_onset_zeros": 0, "interpolated_supervision_rows": 0, "synthetic_rows": 0,
              "excluded_extra_reports": exclusions, "extra_lineage": extra_lineage,
              "policy": "Extra original active reports are fitting supervision only, and only for the fitting participants of each fold. Original 487/179 target cohorts and labels never change. No report without a real 1-15 minute prior is invented or included."}
    (DIRECTORY / "provenance.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Verified all 666 canonical feature rows; prepared {len(extra)} extra actual fitting-person responses; 487/179 evaluation denominators unchanged", flush=True)


def load():
    if not (DIRECTORY / "provenance.json").exists():
        prepare()
    manifest = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    for key, path in (("feature_code_sha256", Path(__file__)), ("dataset_sha256", DIRECTORY / "dataset.csv"),
                      ("calibration_code_sha256", Path(__file__).with_name("fatigue_calibrated.py")),
                      ("dynamics_code_sha256", Path(__file__).with_name("fatigue_dynamics.py"))):
        if manifest[key] != digest(path):
            raise ValueError("Frozen additional reports or their preparation changed")
    return pd.read_csv(DIRECTORY / "dataset.csv", dtype={"label": str}), manifest


if __name__ == "__main__":
    prepare()
