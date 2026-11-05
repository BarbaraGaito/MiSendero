"""Audit actual PMData exertion annotations before any fatigue training merge.

The public source has session outcomes and separate, zone-naive Fitbit clocks.
Do not turn missing ratings into zeros or assume that session-RPE and native
momentary GeoFatigue Borg are interchangeable labels.
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fetch_pmdata import DIRECTORY
from public_sources import digest


def audit():
    inventory_path = DIRECTORY / "inventory.json"
    receipt_path = DIRECTORY / "annotations-receipt.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not receipt["complete_and_publisher_verified"] or receipt["inventory_sha256"] != digest(inventory_path):
        raise ValueError("Complete official annotation download is required")
    for entry in receipt["files"]:
        path = DIRECTORY / entry["local_path"]
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("An original public PMData file changed after download")
    people, values, durations = [], [], []
    exercise_total, exercise_naive, exercise_with_zone = 0, 0, 0
    for person in sorted((DIRECTORY / "files/pmdata").iterdir()):
        frame = pd.read_csv(person / "pmsys/srpe.csv")
        native = pd.to_numeric(frame["perceived_exertion"], errors="coerce")
        nonempty = frame["perceived_exertion"].notna()
        if native.isna().sum() != (~nonempty).sum():
            raise ValueError("An actual nonempty effort cell could not be parsed")
        observed = frame[native.notna()]
        effort = native[native.notna()]
        if not effort.between(0, 10).all() or not effort.eq(effort.round()).all():
            raise ValueError("Original effort values differ from inspected native integers")
        for value in observed["end_date_time"].astype(str):
            if not value.strip().endswith("Z"):
                raise ValueError("An actual effort response lacks the observed explicit UTC clock")
        timestamps = pd.to_datetime(observed["end_date_time"], utc=True, format="mixed", errors="coerce")
        if timestamps.isna().any():
            raise ValueError("An observed session response has an invalid UTC timestamp")
        duration = pd.to_numeric(observed["duration_min"], errors="coerce")
        if duration.isna().any() or not np.isfinite(duration).all() or not duration.gt(0).all():
            raise ValueError("A real effort response has missing or invalid declared duration")
        people.append({"source_participant": person.name, "annotation_rows": len(frame), "nonempty_effort_cells": len(effort),
                       "missing_effort_cells": int(native.isna().sum()), "explicit_utc_effort_timestamps": len(timestamps)})
        values.extend(effort.tolist())
        durations.extend(duration.tolist())
        exercises = json.loads((person / "fitbit/exercise.json").read_text(encoding="utf-8"))
        for row in exercises:
            stamp = str(row["startTime"])
            exercise_total += 1
            if re.search(r"(?:Z|[+-]\d\d:\d\d)$", stamp):
                exercise_with_zone += 1
            else:
                exercise_naive += 1
    native = pd.Series(values)
    paper_text = DIRECTORY / "source-paper.txt"
    report = {"version": 1, "source": inventory["source"], "osf": inventory["osf"],
              "paper": "https://doi.org/10.1145/3339825.3394926", "inventory_sha256": digest(inventory_path),
              "annotation_receipt_sha256": digest(receipt_path), "code_sha256": digest(Path(__file__)),
              "participant_folders": len(people), "participants_with_actual_ratings": sum(p["nonempty_effort_cells"] > 0 for p in people),
              "annotation_rows": sum(p["annotation_rows"] for p in people), "actual_nonempty_effort_cells": len(values),
              "missing_effort_cells": sum(p["missing_effort_cells"] for p in people),
              "native_effort_value_counts": {str(int(k)): int(v) for k, v in native.value_counts().sort_index().items()},
              "declared_session_duration_range_minutes": [float(min(durations)), float(max(durations))],
              "fitbit_exercise_entries": exercise_total, "exercise_start_times_without_zone": exercise_naive,
              "exercise_start_times_with_explicit_zone": exercise_with_zone,
              "rating_definition": "Native PMSys session perceived exertion, not inferred or converted momentary Borg.",
              "source_license_text_sha256": digest(DIRECTORY / "files/license.txt"),
              "source_paper_text_sha256": digest(paper_text) if paper_text.exists() else None,
              "training_merge_approved": False, "used_for_training": False, "synthetic_or_imputed_effort_labels": 0,
              "timezone_offset_imputed": False,
              "reason": "Session outcomes differ from the current momentary Borg target. Fitbit timestamps lack an explicit timezone; no exact offset or report-to-exercise link was established from the inspected paper/metadata. Do not guess a timezone or count unlabelled rows as real ratings.",
              "participants": people}
    (DIRECTORY / "eligibility-audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "participants"}, indent=2, allow_nan=False))
    return report


if __name__ == "__main__":
    audit()
