"""Observed, causal waveform pairs for existing public Borg questionnaires.

This is an input cache, not new supervision. Empty bins have value zero and
an explicit zero observation mask. No interpolation, waveform augmentation,
manufactured history, or missing-case exclusion is permitted.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import fatigue_extra_feedback as extra_feedback
from fatigue_calibrated import previous_reports
from fatigue_dynamics import load_inputs as native_inputs
from fatigue_features import RESEARCH
from fatigue_raw_features import combine_chunks, signal_chunk
from public_sources import RAW, ROOT, digest, verify_source_snapshot

DIRECTORY = RESEARCH / "physiology-paired-windows-80-v1"
POLICY = ROOT / "docs/fatigue-80-2026-10-25/public-real-data-policy.json"
ARCHIVE = RAW / "geofatigue/Physiological Data.zip"
REPORTS = RAW / "geofatigue/self_reported_fatigue_level.original.tab"
SESSIONS = RAW / "geofatigue/session_metadata.json"
RATES = {"fast": (32, ("bvp", "acc_magnitude")), "slow": (4, ("eda", "temperature"))}
SECONDS = 16


def microseconds(value):
    return int(pd.Timestamp(value).value // 1000)


def dependencies():
    paths = {"archive": ARCHIVE, "raw_reports": REPORTS, "session_metadata": SESSIONS,
             "public_real_data_policy": POLICY, "preparation_code": Path(__file__),
             "multisensor_provenance": RESEARCH / "multisensor-v1/provenance.json",
             "extra_provenance": extra_feedback.DIRECTORY / "provenance.json"}
    paths.update({name: Path(__file__).with_name(name) for name in
                  ("fatigue_raw_features.py", "fatigue_dynamics.py", "fatigue_extra_feedback.py", "fatigue_calibrated.py")})
    return {name: digest(path) for name, path in paths.items()}


def input_rows():
    frame, train, test, native_manifest, _ = native_inputs()
    extra, extra_manifest = extra_feedback.load()
    manifest = json.loads((RESEARCH / "multisensor-v1/provenance.json").read_text(encoding="utf-8"))
    raw_rows = manifest["lineage"]
    if frame.row_key.tolist() != [row["row_key"] for row in raw_rows]:
        raise ValueError("Canonical waveform identities changed")
    reports = pd.read_csv(REPORTS)
    reports["time"] = pd.to_datetime(reports.time, utc=True)
    if reports.duplicated(["id", "time"]).any():
        raise ValueError("Ambiguous original questionnaires")
    sessions = json.loads(SESSIONS.read_text(encoding="utf-8"))
    prefixes = defaultdict(set)
    identified = []
    for raw in raw_rows:
        prefix = raw["sensor_members"][0].split("/digital_biomarkers/")[0]
        person = "p" + re.search(r"/p(\d+)-", prefix)[1]
        now = pd.Timestamp(raw["response_time"])
        matches = [s for s in sessions[person] if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"])]
        if len(matches) != 1:
            raise ValueError("Canonical session mapping is ambiguous")
        session = matches[0]
        key = (person, microseconds(session["start_time"]))
        prefixes[key].add(prefix)
        identified.append((person, now, session, raw["task_start"], raw["row_key"], raw["group_key"], "canonical"))
    for row in extra_manifest["extra_lineage"]:
        actual = reports.loc[row["original_response_row"]]
        now, person = pd.Timestamp(row["response_time"]), actual["id"]
        if actual["time"] != now:
            raise ValueError("Extra current report changed")
        matches = [s for s in sessions[person] if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"])]
        if len(matches) != 1:
            raise ValueError("Extra session mapping is ambiguous")
        identified.append((person, now, matches[0], row["task_start"], row["row_key"], row["group_key"], "extra_fitting_only"))
    context = pd.concat([frame[["row_key", "group_key", "prior_borg", "prior_age_minutes"]],
                         extra[["row_key", "group_key", "prior_borg", "prior_age_minutes"]]], ignore_index=True).set_index("row_key")
    calibration = {row["row_key"]: row for row in native_manifest["calibration_lineage"]}
    rows = []
    for person, now, session, task_start, key, group, cohort in identified:
        old = previous_reports(reports[reports.id.eq(person)], now, pd.Timestamp(session["start_time"]))
        if old.empty:
            raise ValueError("Missing genuine earlier Borg input")
        previous = old.iloc[-1]
        age = (now - previous["time"]).total_seconds() / 60
        if previous.borg_scale != context.loc[key, "prior_borg"] or abs(age-context.loc[key, "prior_age_minutes"]) > 1e-10:
            raise ValueError("Previous Borg/time differs from existing authorized inputs")
        if cohort == "canonical":
            earlier = calibration[key]["previous_observed_reports"][-1]
            if microseconds(earlier["response_time"]) != microseconds(previous["time"]) or earlier["observed_borg"] != previous.borg_scale:
                raise ValueError("Canonical prior provenance changed")
        source_prefixes = prefixes.get((person, microseconds(session["start_time"])))
        if not source_prefixes:
            raise ValueError("No observed physiological source mapping for extra questionnaire")
        rows.append({"row_key": key, "group_key": group, "participant": person, "cohort": cohort,
                     "source_prefixes": sorted(source_prefixes), "current_time_us": microseconds(now),
                     "current_lower_bound_us": microseconds(task_start),
                     "prior_time_us": microseconds(previous["time"]),
                     "prior_lower_bound_us": microseconds(session["start_time"]),
                     "prior_observed_borg": float(previous.borg_scale), "prior_age_minutes": age})
    if len(rows) != 722 or len({r["row_key"] for r in rows}) != 722 or not set(extra.group_key) <= set(train.group_key):
        raise ValueError("Existing 666+56 actual report scope changed")
    return rows, {"canonical_cases": len(frame), "extra_fitting_only_cases": len(extra),
                  "original_training_cases": len(train), "original_test_cases": len(test),
                  "original_training_people": len(set(train.group_key)), "original_test_people": len(set(test.group_key)),
                  "native_dataset_sha256": native_manifest["dataset_sha256"],
                  "extra_dataset_sha256": extra_manifest["dataset_sha256"]}


def read_signals(archive, prefixes):
    from fastavro import reader
    members = sorted(name for name in archive.namelist() if any(name.startswith(prefix + "/raw_data/") for prefix in prefixes) and name.endswith(".avro"))
    if not members:
        raise ValueError("Missing original AVRO source for session")
    chunks = defaultdict(list)
    people = {re.search(r"/p(\d+)-", prefix)[1] for prefix in prefixes}
    if len(people) != 1:
        raise ValueError("A physiological session cannot combine different people")
    person = next(iter(people))
    for member in members:
        for record in reader(io.BytesIO(archive.read(member))):
            identity = re.search(r"p(\d+)$", record["enrollment"]["participantID"])
            if not identity or identity[1] != person:
                raise ValueError("Original AVRO enrollment mismatch")
            raw = record["rawData"]
            for channel in ("bvp", "eda", "temperature"):
                chunk = signal_chunk(raw[channel], raw[channel]["values"])
                if chunk is not None:
                    chunks[channel].append(chunk)
            a = raw["accelerometer"]
            p = a["imuParams"]
            span = p["digitalMax"] - p["digitalMin"]
            if span and len(a["x"]):
                axes = np.column_stack([a[axis] for axis in ("x", "y", "z")]).astype(float)
                physical = (axes-p["digitalMin"])*(p["physicalMax"]-p["physicalMin"])/span+p["physicalMin"]
                chunk = signal_chunk(a, np.linalg.norm(physical, axis=1))
                if chunk is not None:
                    chunks["acc_magnitude"].append(chunk)
    return {name: combine_chunks(chunks[name]) for name in ("bvp", "acc_magnitude", "eda", "temperature")}, members


def observed_window(signals, query_us, lower_us, rate, channels):
    step = 1_000_000 // rate
    endpoint = (query_us // step) * step
    beginning = endpoint - SECONDS * 1_000_000
    size = SECONDS * rate
    output = np.zeros((2*len(channels), size), dtype=np.float32)
    evidence = {}
    for position, name in enumerate(channels):
        times, values, _ = signals[name]
        a, b = np.searchsorted(times, [max(beginning, lower_us), endpoint], side="left")
        t, x = times[a:b], values[a:b]
        valid = np.isfinite(x)
        t, x = t[valid], x[valid]
        bins = (t-beginning)//step
        counts = np.bincount(bins, minlength=size)
        sums = np.bincount(bins, weights=x, minlength=size)
        present = counts > 0
        output[position, present] = (sums[present]/counts[present]).astype(np.float32)
        output[len(channels)+position] = present
        evidence[name] = {"actual_samples": len(x), "observed_bins": int(present.sum()),
                          "earliest_sample_us": int(t[0]) if len(t) else None,
                          "latest_sample_us": int(t[-1]) if len(t) else None}
    if not np.isfinite(output).all():
        raise ValueError("Nonfinite cached observed waveform")
    return output, {"end_exclusive_us": int(endpoint), "window_beginning_us": int(beginning),
                    "effective_lower_bound_us": int(max(beginning, lower_us)), "channels": evidence}


def prepare():
    if (DIRECTORY / "provenance.json").exists() or (DIRECTORY / "windows.npz").exists():
        raise ValueError("Preserve frozen input cache; use a new version for changed preparation")
    verify_source_snapshot("fatigue")
    rows, cohort = input_rows()
    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[tuple(row["source_prefixes"])].append((index, row))
    arrays = {f"{band}_{phase}": np.zeros((len(rows), 4, SECONDS*rate), dtype=np.float32)
              for band, (rate, _) in RATES.items() for phase in ("current", "prior")}
    lineage = [None]*len(rows)
    with zipfile.ZipFile(ARCHIVE) as archive:
        for number, (prefix, observations) in enumerate(sorted(grouped.items()), 1):
            signals, members = read_signals(archive, prefix)
            for index, row in observations:
                proof = {**row, "raw_members": members, "windows": {}}
                for band, (rate, channels) in RATES.items():
                    for phase in ("current", "prior"):
                        name = f"{band}_{phase}"
                        arrays[name][index], proof["windows"][name] = observed_window(
                            signals, row[f"{phase}_time_us"], row[f"{phase}_lower_bound_us"], rate, channels)
                lineage[index] = proof
            print(f"Observed physiological session {number}/{len(grouped)}", flush=True)
    DIRECTORY.mkdir(exist_ok=True)
    np.savez_compressed(DIRECTORY / "windows.npz", row_keys=np.asarray([row["row_key"] for row in rows]), **arrays)
    result = {"version": 1, "cohort": cohort, "dependencies_sha256": dependencies(),
              "windows_sha256": digest(DIRECTORY / "windows.npz"), "window_seconds": SECONDS,
              "array_shapes": {name: list(value.shape) for name, value in arrays.items()},
              "observed_bin_coverage": {name: {"cases_with_any_observed_signal": int((value[:, 2:].sum(axis=(1, 2)) > 0).sum()),
                    "mean_fraction": float(value[:, 2:].mean()), "cases_fully_missing": int((value[:, 2:].sum(axis=(1, 2)) == 0).sum())}
                  for name, value in arrays.items()},
              "synthetic_examples": 0, "new_targets": 0, "interpolated_bins": 0, "current_targets_in_tensor_cache": False,
              "policy": "One paired input per existing current report. Actual finite sample means in fixed bins strictly before the referenced actual report; current lower bound is task start, prior lower bound is session start. Empty bins remain explicitly unobserved, never interpolated. No labels, participant IDs or row IDs enter neural input tensors. Canonical 487/179 targets and all missing cases retained; extra 56 targets are eligible fitting-person supervision only.",
              "channels": {name: list(channels)+["observed_"+channel for channel in channels] for name, (_, channels) in RATES.items()},
              "lineage": lineage}
    (DIRECTORY / "provenance.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"directory": str(DIRECTORY), "cohort": cohort, "coverage": result["observed_bin_coverage"]}), flush=True)


def load():
    manifest = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if manifest["dependencies_sha256"] != dependencies() or manifest["windows_sha256"] != digest(DIRECTORY / "windows.npz"):
        raise ValueError("Frozen real waveform source, code, policy or cache changed")
    with np.load(DIRECTORY / "windows.npz", allow_pickle=False) as stored:
        arrays = {name: stored[name].copy() for name in stored.files}
    if arrays["row_keys"].tolist() != [row["row_key"] for row in manifest["lineage"]]:
        raise ValueError("Waveform case order changed")
    return arrays, manifest


if __name__ == "__main__":
    prepare()
