"""Audit original post-trial OxBioZ ratings for auxiliary transfer only.

The published HDF5 has one scalar RPE per long trial, not one per sensor row.
Heart rate is already aligned at the high-rate acquisition grid; interpolated
predictors are never counted as extra measurements or supervision responses.
No exact RPE timestamp is published. These trial outcomes must not become
momentary GeoFatigue labels, previous-report inputs, or benchmark test cases.
"""
from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from fatigue_features import RESEARCH
from fetch_oxbioz import DIRECTORY as RAW_DIRECTORY, FILES, REVISION
from public_sources import digest, group_key

DIRECTORY = RESEARCH / "oxbioz-v1"


def episode_features(timestamps, heart_rate):
    t, hr = np.asarray(timestamps, dtype=float), np.asarray(heart_rate, dtype=float).reshape(-1)
    if t.ndim != 1 or len(t) != len(hr) or len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("Aligned strictly increasing original timestamps required")
    minute = np.floor((t - t[0]) / 60).astype(int)
    completed_minutes = int(np.floor((t[-1] - t[0]) / 60))
    valid = np.isfinite(hr) & (hr >= 30) & (hr <= 240) & (minute < completed_minutes)
    averages = pd.Series(hr[valid]).groupby(minute[valid]).mean()
    if averages.empty:
        raise ValueError("No elapsed-complete observed pulse bin before the post-trial rating")
    return {"hr_last": float(averages.iloc[-1]), "hr_history_mean": float(averages.mean()),
            "observed_recording_minutes": float((t[-1] - t[0]) / 60), "elapsed_complete_bins": len(averages),
            "last_predictor_time_offset_seconds": float((averages.index[-1] + 1) * 60),
            "source_aligned_sample_rows": len(t), "predictor_sample_rows": int(valid.sum())}


def prepare():
    name, expected_bytes, expected_sha = FILES["gel"]
    path = RAW_DIRECTORY / name
    receipt = json.loads((RAW_DIRECTORY / "gel-receipt.json").read_text(encoding="utf-8"))
    if (path.stat().st_size != expected_bytes or digest(path) != expected_sha or receipt["revision"] != REVISION
            or not receipt["publisher_lfs_sha256_verified"]):
        raise ValueError("OxBioZ source is not the pinned complete official cohort")
    rows, lineage = [], []
    with h5py.File(path, "r") as archive:
        if set(archive) != {str(i) for i in range(1, 21)}:
            raise ValueError("Expected the published 20-person gel-electrode cohort")
        for person in sorted(archive, key=int):
            for trial in ("lt1", "lt2"):
                record = archive[person][trial]
                if record["RPE"].shape != ():
                    raise ValueError("Expected one original post-trial RPE scalar")
                borg = float(record["RPE"][()])
                if not np.isfinite(borg) or not 0 <= borg <= 10:
                    raise ValueError("No native observed post-trial Borg present")
                features = episode_features(record["timestamp"][:], record["hr"][:])
                key = group_key(f"OxBioZ:gel:{person}:{trial}")
                rows.append({"row_key": key, "group_key": group_key("OxBioZ:gel:" + person),
                             "hr_last": features["hr_last"], "hr_history_mean": features["hr_history_mean"],
                             "borg_native": borg, "source": "OxBioZ_post_trial"})
                lineage.append({"row_key": key, "original_scalar_path": f"{person}/{trial}/RPE",
                                "original_hr_path": f"{person}/{trial}/hr", "report_phase": "after_long_trial",
                                "exact_report_timestamp": None, **{k: v for k, v in features.items() if k not in ("hr_last", "hr_history_mean")}})
    frame = pd.DataFrame(rows)
    if len(frame) != 40 or frame["group_key"].nunique() != 20 or frame["row_key"].duplicated().any():
        raise ValueError("Original OxBioZ report/participant counts changed")
    DIRECTORY.mkdir(exist_ok=True)
    if (DIRECTORY / "provenance.json").exists() or (DIRECTORY / "dataset.csv").exists():
        raise ValueError("Preserve the frozen OxBioZ audit before preparing another version")
    frame.to_csv(DIRECTORY / "dataset.csv", index=False)
    report = {"version": 1, "source": "https://github.com/XinyuHou97/OxBioZ", "revision": REVISION,
              "paper": "https://doi.org/10.1145/3737903.3768566", "paper_protocol": "Section 4.2: a 0-10 Borg response after each long trial.",
              "source_sha256": expected_sha, "dataset_sha256": digest(DIRECTORY / "dataset.csv"),
              "feature_code_sha256": digest(Path(__file__)), "receipt_sha256": digest(RAW_DIRECTORY / "gel-receipt.json"),
              "h5py_version": h5py.__version__, "native_reports": 40, "participants": 20,
              "native_value_counts": {str(k): int(v) for k, v in frame["borg_native"].value_counts().sort_index().items()},
              "interpolated_supervision_rows": 0, "synthetic_rows": 0, "fabric_probe_rows_used": 0,
              "original_momentary_target_merge_approved": False, "auxiliary_post_trial_outcome_use_approved": True,
              "heart_rate_note": "Published HR is aligned at the acquisition grid, much faster than the 0.2 Hz device. These derived readings are predictors only; minute aggregation does not recover independent original measurement times or create new ratings.",
              "timing_note": "One post-trial outcome without an exact report timestamp. Recording durations vary and are not treated as known task elapsed time. Only earlier elapsed-complete recording bins are used. The full recording or outcome never becomes a current/future input of a GeoFatigue query.",
              "lineage": lineage}
    (DIRECTORY / "provenance.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Audited {len(frame)} original post-trial Borg scalars / 20 people; momentary-label merge remains disabled", flush=True)


def load():
    report = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if digest(DIRECTORY / "dataset.csv") != report["dataset_sha256"] or digest(Path(__file__)) != report["feature_code_sha256"]:
        raise ValueError("Frozen OxBioZ data/preparation changed")
    return pd.read_csv(DIRECTORY / "dataset.csv"), report


if __name__ == "__main__":
    prepare()
