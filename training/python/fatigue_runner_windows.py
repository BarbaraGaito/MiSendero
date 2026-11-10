"""Dimensionless causal IMU windows; runner F/NF supervision stays separate."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_features import RESEARCH
from fatigue_phone_context import available_sources
from fatigue_phone_spectral import BIN_COLUMNS, cached_bins
from fatigue_spectral_experiment import load_inputs
from fetch_runner_fatigue_metadata import DIRECTORY as RAW
from fetch_runner_fatigue_signals import FILES
from public_sources import digest

DIRECTORY = RESEARCH / "runner-dimensionless-windows-80-v1"
LENGTH, BIN_NS = 256, 100_000_000
AXES = ["Accel_WR_"+s for s in "XYZ"]
GYRO = ["Gyro_"+s for s in "XYZ"]
CLOCK = "System_Timestamp_Plot_Zeroed"


def dimensionless_window(times, values, now, task_start):
    times, values = np.asarray(times, dtype=np.int64), np.asarray(values, dtype=float)
    if values.shape != (len(times), 5) or (len(times) > 1 and np.any(np.diff(times) <= 0)):
        raise ValueError("Distinct chronological five-channel bins required")
    if np.any(times % BIN_NS):
        raise ValueError("Observed bins must lie on the explicit 100 ms grid")
    end = int(now)//BIN_NS*BIN_NS
    start = end-LENGTH*BIN_NS
    take = (times >= max(start, int(task_start))) & (times+BIN_NS <= end)
    position, data = (times[take]-start)//BIN_NS, values[take]
    channels = np.full((3, LENGTH), np.nan)
    channels[0, position], channels[1, position] = data[:, 0], data[:, 1]
    good = np.isfinite(data[:, 2:5]).all(axis=1)
    if good.any():
        gravity = data[good, 2:5].mean(axis=0)
        norm = np.linalg.norm(gravity)
        if norm > 0:
            channels[2, position[good]] = data[good, 2:5] @ (gravity/norm)
    output = np.zeros((6, LENGTH), dtype=np.float32)
    for i in range(3):
        valid = np.isfinite(channels[i])
        if not valid.any():
            continue
        observed = channels[i, valid]
        scale = float(observed.std())
        tolerance = 8*np.finfo(float).eps*max(float(np.abs(observed).max()), np.finfo(float).tiny)
        if scale > tolerance:
            output[i, valid] = np.clip((observed-observed.mean())/scale, -10., 10.)
        output[i+3, valid] = 1.
    return output


def runner_bins(frame):
    """Actual relative-clock observations, with no imposed 256 Hz rate."""
    data = frame[[CLOCK, *AXES, *GYRO]].apply(pd.to_numeric, errors="coerce")
    invalid_time = ~np.isfinite(data[CLOCK]) | data[CLOCK].lt(0)
    data = data.loc[~invalid_time].copy()
    segments = np.cumsum(np.r_[False, np.diff(data[CLOCK].to_numpy()) < 0]) if len(data) else np.array([], dtype=int)
    result, quality = [], {"original_rows": len(frame), "invalid_clock_rows": int(invalid_time.sum()),
        "clock_reversals": int((np.diff(data[CLOCK].to_numpy()) < 0).sum()),
        "ambiguous_timestamp_rows": 0, "identical_duplicate_rows": 0}
    for number in np.unique(segments):
        part = data.iloc[np.flatnonzero(segments == number)].copy()
        duplicates = part[part[CLOCK].duplicated(keep=False)]
        if len(duplicates):
            counts = duplicates.groupby(CLOCK).nunique(dropna=False)
            ambiguous = counts.index[(counts > 1).any(axis=1)]
            bad = part[CLOCK].isin(ambiguous)
            quality["ambiguous_timestamp_rows"] += int(bad.sum())
            part = part.loc[~bad]
            quality["identical_duplicate_rows"] += int(part[CLOCK].duplicated().sum())
            part = part.drop_duplicates(CLOCK)
        times = np.rint(part[CLOCK].to_numpy(float)*1_000_000).astype(np.int64)
        a, g = part[AXES].to_numpy(dtype=float, copy=True), part[GYRO].to_numpy(float)
        a[~np.isfinite(a).all(axis=1)] = np.nan
        magnitudes = np.column_stack((np.linalg.norm(a, axis=1), np.linalg.norm(g, axis=1), a))
        bins = pd.DataFrame(magnitudes, columns=BIN_COLUMNS).groupby(times//BIN_NS*BIN_NS).mean()
        delta = np.diff(times)
        positive = delta[delta > 0]
        if len(bins):
            result.append((bins.index.to_numpy(np.int64), bins.to_numpy(float), {
                "clock_segment": int(number), "observed_bins": len(bins),
                "positive_step_median_ns": float(np.median(positive)) if len(positive) else None,
                "source_rows": len(part)}))
    return result, quality


def source_windows(receipt):
    windows, states, people, lineage, files = [], [], [], [], []
    for number, record in enumerate(receipt["files"]):
        path = FILES / record["filename"]
        if digest(path) != record["sha256"] or digest(path, "md5") != record["published_checksum"].removeprefix("md5:"):
            raise ValueError("Original runner waveform changed")
        frame = pd.read_csv(path, usecols=[CLOCK, *AXES, *GYRO])
        segments, quality = runner_bins(frame)
        skipped = retained = 0
        for times, values, segment in segments:
            for end in range(int(times[0])+LENGTH*BIN_NS, int(times[-1])+BIN_NS+1, LENGTH//2*BIN_NS):
                tensor = dimensionless_window(times, values, end, int(times[0]))
                if tensor[3:].mean(axis=1).min() < .9:
                    skipped += 1
                    continue
                windows.append(tensor)
                states.append(int(record["protocol_segment"] == "F"))
                people.append(record["participant"])
                retained += 1
                lineage.append({"filename": record["filename"], "clock_segment": segment["clock_segment"],
                                "window_end_ns": end, "protocol_state": states[-1]})
        files.append({"filename": record["filename"], "quality": quality,
                      "segments": [s[2] for s in segments], "retained_windows": retained, "low_coverage_windows_skipped": skipped})
        print(f"Dimensionless source windows {number+1}/30 files", flush=True)
    represented = {(p, y) for p, y in zip(people, states)}
    if represented != {(p, y) for p in receipt["fitting_participants"] for y in (0, 1)}:
        raise ValueError("Every declared fitting person must retain both original F/NF conditions")
    return np.stack(windows), np.asarray(states, dtype=np.int64), np.asarray(people), lineage, files


def native_windows():
    frame, _, _, manifest, _ = load_inputs()
    sources, _ = available_sources(require_complete=True)
    grouped = {}
    for i, row in enumerate(manifest["lineage"]):
        person = "p"+re.search(r"/p(\d+)-", row["sensor_members"][0])[1]
        terrain = next(t for t in ("stairs", "ramp", "flat_trail") if frame.iloc[i]["terrain_"+t] == 1)
        grouped.setdefault((person, terrain), []).append((i, row))
    windows, lineage = np.zeros((666, 6, LENGTH), dtype=np.float32), []
    for number, ((person, terrain), queries) in enumerate(grouped.items()):
        parts = [cached_bins(s) for s in sources if s["participant"] == person and s["terrain"] == terrain]
        bins = pd.concat(parts).sort_index() if parts else pd.DataFrame(columns=BIN_COLUMNS, index=pd.DatetimeIndex([], tz="UTC"))
        if bins.index.duplicated().any():
            raise ValueError("Native phone source traces overlap")
        times, values = bins.index.as_unit("ns").asi8, bins[BIN_COLUMNS].to_numpy(float)
        for i, row in queries:
            now, start = pd.Timestamp(row["response_time"]).value, pd.Timestamp(row["task_start"]).value
            windows[i] = dimensionless_window(times, values, now, start)
            end = now//BIN_NS*BIN_NS
            selected = times[(times >= max(start, end-LENGTH*BIN_NS)) & (times+BIN_NS <= end)]
            lineage.append({"row_key": row["row_key"], "prediction_time_ns": now,
                "latest_used_bin_end_ns": int(selected[-1]+BIN_NS) if len(selected) else None})
        if (number+1) % 20 == 0 or number+1 == len(grouped):
            print(f"Dimensionless native windows {number+1}/{len(grouped)} groups", flush=True)
    return windows, frame["row_key"].to_numpy(str), lineage, manifest


def prepare():
    receipt_path = RAW / "signals-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if not receipt["all_complete_and_verified"] or len(receipt["files"]) != 30 or receipt["reserved_waveforms_downloaded"]:
        raise ValueError("Wait for all 30 publisher-verified fitting-only source files")
    DIRECTORY.mkdir(exist_ok=True)
    if any((DIRECTORY / n).exists() for n in ("source.npz", "native.npz", "provenance.json")):
        raise ValueError("Preserve the frozen dimensionless window snapshot")
    source, states, people, source_lineage, quality = source_windows(receipt)
    native, keys, native_lineage, manifest = native_windows()
    np.savez_compressed(DIRECTORY / "source.npz", windows=source, protocol_states=states, participants=people)
    np.savez_compressed(DIRECTORY / "native.npz", windows=native, row_keys=keys)
    evidence = {"version": 1, "feature_code_sha256": digest(Path(__file__)),
        "dependency_code_sha256": {n: digest(Path(__file__).with_name(n)) for n in ("fatigue_phone_spectral.py", "fatigue_phone_context.py", "fatigue_spectral_experiment.py")},
        "source_receipt_sha256": digest(receipt_path), "inventory_sha256": receipt["inventory_sha256"],
        "source_npz_sha256": digest(DIRECTORY / "source.npz"), "native_npz_sha256": digest(DIRECTORY / "native.npz"),
        "parent_dataset_sha256": manifest["dataset_sha256"], "fitting_source_people": receipt["fitting_participants"],
        "reserved_source_people": receipt["reserved_participants"], "source_windows": len(source),
        "source_protocol_state_counts": {str(i): int((states == i).sum()) for i in (0, 1)},
        "source_file_quality": quality, "source_window_lineage": source_lineage,
        "native_query_count": 666, "native_queries_with_any_signal": int((native[:, 3:].sum(axis=(1, 2)) > 0).sum()),
        "native_query_lineage": native_lineage, "native_borg_targets_stored": 0,
        "interpolated_signals": False, "interpolated_borg_targets": 0,
        "clock_units": "Source relative-clock channel interpreted as milliseconds according to its exact manufacturer API name; per-file cadence is measured, never forced to 256 Hz. No UTC correspondence is inferred.",
        "normalization": "Per-window observed-only centering and scaling, with relative floating-point tolerance and no physical-unit floor. Positive acceleration/gyro unit scaling cancels. Native physical quality filters remain the existing verified cache filters; no unproven physical threshold is applied to the runner CSV values.",
        "policy": "F/NF are source-only protocol conditions, not Borg labels. Preserve all 666 native causal inputs, including empty/partial windows. Source windows require predefined 90-percent signal coverage. Never read current Borg labels, infer Borg from filenames, interpolate targets, or use reserved runners."}
    (DIRECTORY / "provenance.json").write_text(json.dumps(evidence, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Prepared {len(source)} source protocol windows and all 666 native inputs; zero native Borg targets in tensors", flush=True)
    return evidence


if __name__ == "__main__":
    prepare()
