"""One original post-test CR10 report per person; auxiliary use only.

Only acceleration windows inside recording seconds [240, 360) are used.
Recording begins before the six-minute walk, so these windows precede the
post-walk HR measurement and Borg question without inventing a report time.
The separate HR_post scalar was measured before the Borg question. Gyroscope
units are not inferred from values; that channel is excluded from transfer.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat
from sklearn.model_selection import GroupShuffleSplit

from fatigue_features import RESEARCH
from fatigue_phone_spectral import BIN, describe, observed_bins
from fetch_sixmwt import DIRECTORY as RAW_DIRECTORY, METADATA
from public_sources import digest, group_key

DIRECTORY = RESEARCH / "sixmwt-v1"
METRICS = ("std", "peak_hz", "peak_normalized_power", "entropy", "band_low_share", "band_mid_share", "band_gait_share", "band_high_share")
ACC_FEATURES = [f"spectral{seconds}_{channel}_{metric}" for seconds in (60, 120)
                for channel in ("acc_mag", "vertical") for metric in METRICS]


def extract(data):
    target = float(data["BorgScale"])
    if not np.isfinite(target) or not 0 <= target <= 10:
        raise ValueError("A real native CR10 response is required; no missing-target filling")
    raw = data["RawData"]
    times = np.asarray(raw["Time"], dtype=float)
    axes = np.asarray(raw["Acc"], dtype=float)
    if (float(raw["Frequency"]) != 100 or times.ndim != 1
            or len(times) < 36001 or times[0] != 0 or not np.isfinite(times).all()
            or np.any(np.diff(times) <= 0) or np.max(np.abs(np.diff(times)-.01)) > 1e-6):
        raise ValueError("Original walking sensor timing/schema differs from the inspected source")
    hr = float(data["HR_post"])
    result = {name: np.nan for name in ACC_FEATURES}
    result["hr_last"] = hr if np.isfinite(hr) and 30 <= hr <= 240 else np.nan
    # Five source MAT files contain a time vector longer than their Acc array.
    # The location of the missing interval is not established: do not truncate,
    # shift or synthesize a clock. Keep the real report and HR, with missing Acc.
    if axes.shape != (len(times), 3):
        return result, target
    selected = (times >= 240) & (times < 360)
    epoch = pd.Timestamp("2000-01-01", tz="UTC")  # Relative clock only, never a predictor.
    frame = pd.DataFrame(axes[selected], columns=["ax", "ay", "az"])
    frame["time"] = epoch+pd.to_timedelta(times[selected], unit="s")
    for column in ("wx", "wy", "wz", "speed", "altitude"):
        frame[column] = np.nan  # Not observed/used, not an invented zero signal.
    bins = observed_bins(frame)
    for seconds in (60, 120):
        window = bins[(bins.index >= epoch+pd.Timedelta(seconds=360-seconds)) & (bins.index+BIN <= epoch+pd.Timedelta(seconds=360))]
        stats = describe(window)
        for channel in ("acc_mag", "vertical"):
            for metric in METRICS:
                result[f"spectral{seconds}_{channel}_{metric}"] = stats[f"{channel}_{metric}"]
    return result, target


def prepare():
    archive_path, receipt_path = RAW_DIRECTORY / "6MWT_IMU_Dataset.zip", RAW_DIRECTORY / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if digest(archive_path) != receipt["sha256"] or digest(METADATA) != receipt["metadata_sha256"]:
        raise ValueError("Original walking source archive/metadata changed")
    DIRECTORY.mkdir(exist_ok=True)
    if (DIRECTORY / "dataset.csv").exists():
        raise ValueError("Preserve the frozen original walking source before preparing another version")
    rows, lineage = [], []
    with zipfile.ZipFile(archive_path) as archive:
        members = [n for n in archive.namelist() if re.fullmatch(r"6MWT_IMU_Dataset/DATA/Subject \d+/Data\.mat", n)]
        if len(members) != 60:
            raise ValueError("Original sixty-person walking cohort changed")
        for name in members:
            payload = archive.read(name)
            data = loadmat(io.BytesIO(payload), simplify_cells=True)["Data"]
            features, target = extract(data)
            person = re.search(r"Subject (\d+)/", name)[1]
            # Keys identify a real source row, not model inputs.
            key = hashlib.sha256(("SixMWT:"+name).encode()).hexdigest()[:24]
            rows.append({**features, "borg_native": target, "row_key": key, "group_key": group_key("SixMWT:"+person)})
            lineage.append({"row_key": key, "member": name, "member_sha256": hashlib.sha256(payload).hexdigest(),
                            "actual_borg": target, "sensor_window_seconds": [240, 360], "post_test_outcome": True,
                            "raw_time_samples": len(data["RawData"]["Time"]), "raw_acc_samples": len(data["RawData"]["Acc"]),
                            "sensor_clock_alignment_valid": np.shape(data["RawData"]["Acc"]) == (len(data["RawData"]["Time"]), 3)})
    frame = pd.DataFrame(rows)
    if frame["group_key"].nunique() != 60 or not frame["row_key"].is_unique:
        raise ValueError("Source contains duplicated walking participants/reports")
    fit, reserved = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(frame, groups=frame["group_key"]))
    path = DIRECTORY / "dataset.csv"
    frame.to_csv(path, index=False)
    provenance = {"version": 1, "dataset_sha256": digest(path), "feature_code_sha256": digest(Path(__file__)),
                  "spectral_feature_code_sha256": digest(Path(__file__).with_name("fatigue_phone_spectral.py")),
                  "source_sha256": receipt["sha256"], "receipt_sha256": digest(receipt_path), "metadata_sha256": digest(METADATA),
                  "source": "https://doi.org/10.6084/m9.figshare.c.7954157", "study": "https://doi.org/10.1038/s41597-025-06506-3",
                  "license": "CC BY 4.0", "actual_reports": 60, "participants": 60, "source_report_field": "Data.BorgScale",
                  "features": [*ACC_FEATURES, "hr_last"], "lineage": lineage,
                  "split": {"train_row_keys": frame.iloc[fit]["row_key"].tolist(), "test_row_keys": frame.iloc[reserved]["row_key"].tolist(),
                            "train_groups": sorted(set(frame.iloc[fit]["group_key"])), "test_groups": sorted(set(frame.iloc[reserved]["group_key"]))},
                  "native_target_histogram": {str(k): int(v) for k, v in frame["borg_native"].value_counts().sort_index().items()},
                  "sensor_clock_mismatch_reports_retained_with_missing_acceleration": sum(not r["sensor_clock_alignment_valid"] for r in lineage),
                  "synthetic_rows": 0, "interpolated_targets": 0, "assumed_zero_targets": 0, "momentary_target_merge": False,
                  "exact_report_timestamp_published": False, "downloaded_code_executed": False,
                  "units": {"acceleration": "m/s^2 (README intensity metrics and original 10.9 m/s^2 threshold)", "heart_rate": "bpm", "gyroscope_used": False},
                  "policy": "One true post-test report per person. Recording starts before a 360-second walk; selected raw recording seconds 240-360 precede its completion. HR_post was measured before the Borg question. No assumed exact report timestamp, no backfilling a post-test label onto sensor rows. External fitting 48 people, reserved 12 people; source-only auxiliary regression, no GeoFatigue targets merged."}
    (DIRECTORY / "provenance.json").write_text(json.dumps(provenance, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print("Prepared 60 original post-test CR10 reports: 48 external fitting people / 12 reserved; no new momentary targets", flush=True)


def load():
    evidence = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if (digest(DIRECTORY / "dataset.csv") != evidence["dataset_sha256"]
            or digest(Path(__file__)) != evidence["feature_code_sha256"]
            or digest(Path(__file__).with_name("fatigue_phone_spectral.py")) != evidence["spectral_feature_code_sha256"]
            or digest(RAW_DIRECTORY / "receipt.json") != evidence["receipt_sha256"]):
        raise ValueError("Frozen walking source data/extractor changed")
    frame = pd.read_csv(DIRECTORY / "dataset.csv")
    split = evidence["split"]
    fitting = frame[frame["row_key"].isin(split["train_row_keys"])].copy()
    held = frame[frame["row_key"].isin(split["test_row_keys"])].copy()
    if len(frame) != 60 or len(fitting) != 48 or len(held) != 12 or set(fitting["group_key"]) & set(held["group_key"]):
        raise ValueError("Walking external participant holdout changed")
    return fitting, held, evidence


if __name__ == "__main__":
    prepare()
