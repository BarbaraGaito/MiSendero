"""Audit the original sparse STS Borg reports; never use interpolated labels.

Uses only the 60 original recording text files. Each non-empty Borg10_Value
cell is a measured report; processed Data_STS.csv labels and notebooks are
not executed or used as supervision. Sensor samples never become new labels.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_features import RESEARCH
from fetch_borg_sts import DIRECTORY as RAW_DIRECTORY
from public_sources import digest, group_key

DIRECTORY = RESEARCH / "sts-v1"


def recording_observations(frame):
    # The recording footer contains start/end wall-clock strings, not samples.
    # They are never model features. Only the Time column in seconds is used.
    times = pd.to_numeric(frame["Time"], errors="coerce")
    borg = pd.to_numeric(frame["Borg10_Value"], errors="coerce")
    hr = pd.to_numeric(frame["Heart_Beat"], errors="coerce")
    if borg[times.isna()].notna().any():
        raise ValueError("Borg response without a numeric recording timestamp")
    samples = pd.DataFrame({"time_seconds": times, "hr": hr.where(hr.between(30, 240)), "borg": borg})[times.notna()].copy()
    if len(samples) == 0 or not samples["time_seconds"].is_monotonic_increasing or samples["time_seconds"].min() < 0:
        raise ValueError("Original recording time is empty, negative or not chronological")
    reports = samples[samples["borg"].notna()].copy()
    if reports.empty or not reports["borg"].between(0, 10).all() or reports["time_seconds"].duplicated().any():
        raise ValueError("Original STS Borg cells are absent, ambiguous or outside native scale")
    if len(reports) > 8:
        raise ValueError("Unexpected dense Borg labels: audit for interpolation before use")
    observations, evidence = [], []
    for source_row, report in reports.iterrows():
        now = float(report["time_seconds"])
        past = samples[(samples["time_seconds"] < now) & samples["hr"].notna()]
        recent = past[past["time_seconds"] >= now - 5]
        latest = past[past["time_seconds"] >= now - 3]
        baseline = past[past["time_seconds"] < min(15., now)]
        previous = reports[(reports["time_seconds"] <= now - 60.) & (reports["time_seconds"] >= now - 900.)]
        last = previous.iloc[-1] if len(previous) else None
        base = float(baseline["hr"].median()) if len(baseline) else np.nan
        hr_last = float(latest.iloc[-1]["hr"]) if len(latest) else np.nan
        observations.append({"hr_last": hr_last, "hr_recent_mean": float(recent["hr"].mean()) if len(recent) else np.nan,
                             "hr_recent_std": float(recent["hr"].std(ddof=0)) if len(recent) else np.nan,
                             "hr_history_mean": float(past["hr"].mean()) if len(past) else np.nan,
                             "hr_history_std": float(past["hr"].std(ddof=0)) if len(past) else np.nan,
                             "hr_baseline_mean": base, "hr_delta_baseline": hr_last - base,
                             "hr_ratio_baseline": hr_last / base if base > 0 else np.nan,
                             "elapsed_minutes": now / 60.,
                             "prior_borg": float(last["borg"]) if last is not None else np.nan,
                             "prior_age_minutes": (now - float(last["time_seconds"])) / 60. if last is not None else np.nan,
                             "label": f"Borg {float(report['borg']):g}"})
        evidence.append({"source_dataframe_row": int(source_row), "observed_borg": float(report["borg"]),
                         "response_time_seconds": now, "latest_hr_time_seconds": float(latest.iloc[-1]["time_seconds"]) if len(latest) else None,
                         "prior_response_time_seconds": float(last["time_seconds"]) if last is not None else None,
                         "baseline_latest_time_seconds": float(baseline.iloc[-1]["time_seconds"]) if len(baseline) else None})
    return pd.DataFrame(observations), evidence


def prepare():
    archive_path = RAW_DIRECTORY / "STS_data.zip"
    receipt_path = RAW_DIRECTORY / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if digest(archive_path) != receipt["sha256"] or digest(archive_path, "md5") != receipt["published_md5"]:
        raise ValueError("Original STS archive differs from pinned publisher checksum")
    frames, lineage = [], []
    with zipfile.ZipFile(archive_path) as archive:
        members = sorted(n for n in archive.namelist() if re.fullmatch(r"STS_data/(?:Men|Women)/P\d+/S_P\d+\.txt", n))
        if len(members) != 60:
            raise ValueError("Unexpected number of original participant recordings")
        for member in members:
            participant = member.rsplit("/", 1)[0]
            if "/" + member.rsplit("/", 1)[-1].removeprefix("S_").removesuffix(".txt") != "/" + participant.rsplit("/", 1)[-1]:
                raise ValueError("Recording filename differs from participant folder")
            with archive.open(member) as stream:
                # Original footer uses Windows Latin-1 Spanish text. Numeric
                # columns have an explicit schema; no code is read/executed.
                original = pd.read_csv(stream, sep=r"\s+", encoding="latin1", usecols=["Time", "Heart_Beat", "Borg10_Value"])
            rows, observed = recording_observations(original)
            key = group_key("STS-original:" + participant)
            for record, row in zip(observed, rows.to_dict("records")):
                record.update(group_key=key, row_key=group_key(f"STS-original:{member}:{record['source_dataframe_row']}"), member=member)
                lineage.append(record)
            frames.append(rows)
    combined = pd.concat(frames, ignore_index=True)
    if combined["label"].isna().any():
        raise ValueError("Unobserved/fabricated supervision target")
    DIRECTORY.mkdir(exist_ok=True)
    data_path = DIRECTORY / "dataset.csv"
    if data_path.exists():
        raise ValueError("STS snapshot already exists; preserve it before preparing a new version")
    combined.to_csv(data_path, index=False)
    provenance = {"version": 1, "source": "Original STS recordings, Aguirre et al., Sensors 2021",
                  "doi": receipt["doi"], "archive_sha256": receipt["sha256"], "download_receipt_sha256": digest(receipt_path),
                  "dataset_sha256": digest(data_path), "feature_code_sha256": digest(Path(__file__)),
                  "native_scale": "Borg CR10 0-10", "rows": len(combined), "groups": 60,
                  "interpolated_targets": 0, "synthetic_rows": 0, "assumed_zero_targets": 0,
                  "repeated_sensor_samples_as_labels": 0, "lineage": lineage,
                  "features": [c for c in combined if c != "label"],
                  "missing_hr_last": int(combined["hr_last"].isna().sum()),
                  "recent_borg_1_to_15_minutes_available": int(combined["prior_borg"].notna().sum()),
                  "measurement_notes": "Zephyr chest HR in bpm; not wrist HRV/EDA. Five-second recent sensor summaries differ from GeoFatigue one-minute summaries and must not be equated without explicit harmonization. Only actual non-empty Borg cells are targets.",
                  "training_merge_approved": False}
    (DIRECTORY / "provenance.json").write_text(json.dumps(provenance, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Audited {len(combined)} original sparse Borg responses from 60 participants; eligible recent prior in {combined['prior_borg'].notna().sum()} rows; no interpolated labels", flush=True)


if __name__ == "__main__":
    prepare()
