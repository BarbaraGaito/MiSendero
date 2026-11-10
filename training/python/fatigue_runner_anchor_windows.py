"""Past sensor windows at the exact already-observed prior Borg timestamp."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_features import RESEARCH
from fatigue_phone_context import available_sources
from fatigue_phone_spectral import BIN_COLUMNS, cached_bins
from fatigue_runner_windows import BIN_NS, LENGTH, DIRECTORY as CURRENT_WINDOWS, dimensionless_window
from fatigue_spectral_experiment import load_inputs
from public_sources import digest

DIRECTORY = RESEARCH / "runner-prior-anchor-windows-80-v1"


def anchor_time(query, source, calibration):
    """Current outcome is deliberately absent from the accessed fields."""
    if source["row_key"] != calibration["row_key"] or calibration["row_key"] != query["row_key"]:
        raise ValueError("Prior-report lineage belongs to a different query")
    if "group_key" in calibration and (calibration["group_key"] != query["group_key"] or source["group_key"] != query["group_key"]):
        raise ValueError("Prior-report lineage belongs to a different person")
    now = pd.Timestamp(source["response_time"])
    if now != pd.Timestamp(calibration["prediction_time"]) or not calibration["previous_observed_reports"]:
        raise ValueError("Current time or actual observed prior report is missing")
    previous = calibration["previous_observed_reports"][-1]
    when = pd.Timestamp(previous["response_time"])
    age = (now-when).total_seconds()/60
    if (not 1 <= age <= 15 or abs(age-float(query["prior_age_minutes"])) > 1e-9
            or float(previous["observed_borg"]) != float(query["prior_borg"])
            or int(when >= pd.Timestamp(source["task_start"])) != int(query["prior_in_current_task"])):
        raise ValueError("Sensor anchor must match the exact eligible actual prior input")
    return when.value


def build():
    frame, _, _, manifest, _ = load_inputs()
    calibration = {r["row_key"]: r for r in manifest["calibration_lineage"]}
    if len(calibration) != len(frame):
        raise ValueError("Duplicate or missing prior-report lineage")
    sources, _ = available_sources(require_complete=True)
    grouped = {}
    for i, source in enumerate(manifest["lineage"]):
        person = "p"+re.search(r"/p(\d+)-", source["sensor_members"][0])[1]
        terrain = next(t for t in ("stairs", "ramp", "flat_trail") if frame.iloc[i]["terrain_"+t] == 1)
        grouped.setdefault((person, terrain), []).append((i, source))
    windows = np.zeros((len(frame), 6, LENGTH), dtype=np.float32)
    lineage = []
    for number, ((person, terrain), queries) in enumerate(grouped.items()):
        parts = [cached_bins(s) for s in sources if s["participant"] == person and s["terrain"] == terrain]
        bins = pd.concat(parts).sort_index() if parts else pd.DataFrame(columns=BIN_COLUMNS, index=pd.DatetimeIndex([], tz="UTC"))
        if bins.index.duplicated().any():
            raise ValueError("Native phone source traces overlap")
        times, values = bins.index.as_unit("ns").asi8, bins[BIN_COLUMNS].to_numpy(float)
        for i, source in queries:
            query = frame.iloc[i]
            when = anchor_time(query, source, calibration[query["row_key"]])
            task_start = pd.Timestamp(source["task_start"]).value
            windows[i] = dimensionless_window(times, values, when, task_start)
            end = when//BIN_NS*BIN_NS
            observed = times[(times >= max(task_start, end-LENGTH*BIN_NS)) & (times+BIN_NS <= end)]
            lineage.append({"row_key": query["row_key"], "prediction_time_ns": pd.Timestamp(source["response_time"]).value,
                "actual_prior_report_time_ns": when, "latest_anchor_bin_end_ns": int(observed[-1]+BIN_NS) if len(observed) else None})
        if (number+1) % 20 == 0 or number+1 == len(grouped):
            print(f"Actual prior-report signal anchors {number+1}/{len(grouped)} groups", flush=True)
    return windows, frame["row_key"].to_numpy(str), lineage, manifest


def prepare():
    DIRECTORY.mkdir(exist_ok=True)
    if any((DIRECTORY / n).exists() for n in ("prior.npz", "provenance.json")):
        raise ValueError("Preserve the frozen prior-anchor snapshot")
    current_manifest = json.loads((CURRENT_WINDOWS / "provenance.json").read_text())
    if digest(CURRENT_WINDOWS / "native.npz") != current_manifest["native_npz_sha256"]:
        raise ValueError("Previously prepared current windows changed")
    windows, keys, lineage, manifest = build()
    with np.load(CURRENT_WINDOWS / "native.npz", allow_pickle=False) as current:
        np.testing.assert_array_equal(current["row_keys"], keys)
        current_has_signal = current["windows"][:, 3:].sum(axis=(1, 2)) > 0
    np.savez_compressed(DIRECTORY / "prior.npz", windows=windows, row_keys=keys)
    prior_has_signal = windows[:, 3:].sum(axis=(1, 2)) > 0
    result = {"version": 1, "feature_code_sha256": digest(Path(__file__)),
        "dependency_code_sha256": {n: digest(Path(__file__).with_name(n)) for n in ("fatigue_runner_windows.py", "fatigue_phone_spectral.py", "fatigue_spectral_experiment.py")},
        "current_window_provenance_sha256": digest(CURRENT_WINDOWS / "provenance.json"),
        "current_npz_sha256": digest(CURRENT_WINDOWS / "native.npz"), "prior_npz_sha256": digest(DIRECTORY / "prior.npz"),
        "parent_dataset_sha256": manifest["dataset_sha256"],
        "actual_prior_lineage_sha256": hashlib.sha256(json.dumps(manifest["calibration_lineage"], sort_keys=True).encode()).hexdigest(),
        "native_queries_retained": len(keys), "prior_windows_with_any_signal": int(prior_has_signal.sum()),
        "current_windows_with_any_signal": int(current_has_signal.sum()),
        "both_windows_with_any_signal": int((current_has_signal & prior_has_signal).sum()),
        "lineage": lineage, "native_borg_targets_stored": 0, "new_borg_targets": 0,
        "policy": "Use the exact previously observed report time, matching the already authorized prior Borg value and age. The reference window ends at that earlier report, and centering/gravity/scaling never use later sensor values. Restrict reference signals to the current task; unavailable pre-task/reference inputs remain masked, with no query removal. No current label, inferred report time, target interpolation or UTC guess."}
    (DIRECTORY / "provenance.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Prepared all {len(keys)} prior sensor anchors; {result['both_windows_with_any_signal']} pairs contain observations", flush=True)
    return result


if __name__ == "__main__":
    prepare()
