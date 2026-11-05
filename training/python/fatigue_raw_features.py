"""Past-only waveform, pulse-interval and motion features from original AVRO.

One output row per existing observed Borg response. Raw 64-Hz samples never
become additional labeled examples. All feature windows end before response.
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
from scipy.signal import welch

from fatigue_features import RESEARCH
from public_sources import RAW, ROOT, digest, verify_source_snapshot


def signal_chunk(data, values):
    frequency, start = float(data["samplingFrequency"]), int(data["timestampStart"])
    if frequency <= 0 or not start or not len(values):
        return None
    if not 0.1 <= frequency <= 2000:
        raise ValueError("Unexpected physiological sampling frequency")
    values = np.asarray(values, dtype=float)
    timestamps = start + np.floor(np.arange(len(values), dtype=float) * 1e6 / frequency).astype(np.int64)
    return timestamps, values, frequency


def combine_chunks(chunks):
    if not chunks:
        return np.array([], dtype=np.int64), np.array([], dtype=float), np.nan
    times = np.concatenate([row[0] for row in chunks])
    values = np.concatenate([row[1] for row in chunks])
    order = np.argsort(times, kind="stable")
    times, values = times[order], values[order]
    unique = np.r_[True, np.diff(times) != 0]
    if np.any(~unique & ~np.r_[False, np.isclose(values[1:], values[:-1], equal_nan=True)]):
        raise ValueError("Conflicting waveform samples at the same timestamp")
    return times[unique], values[unique], float(np.median([row[2] for row in chunks]))


def past_window(times, values, endpoint_us, seconds):
    a, b = np.searchsorted(times, [endpoint_us - int(seconds * 1e6), endpoint_us], side="left")
    selected_times, selected = times[a:b], values[a:b]
    valid = np.isfinite(selected)
    return selected_times[valid], selected[valid]


def describe_window(signal, endpoint_us, seconds):
    times, values, frequency = signal
    t, x = past_window(times, values, endpoint_us, seconds)
    result = {key: np.nan for key in ("mean", "std", "q10", "q90", "range", "slope",
                                      "skew", "kurtosis", "rms", "dominant_hz", "power_05_4hz")}
    result["coverage"] = min(1., len(x) / (seconds * frequency)) if np.isfinite(frequency) else 0.
    if len(x) < 5:
        return result
    mean, std = float(np.mean(x)), float(np.std(x))
    result.update(mean=mean, std=std, q10=float(np.quantile(x, .1)), q90=float(np.quantile(x, .9)),
                  range=float(np.ptp(x)), rms=float(np.sqrt(np.mean(x * x))))
    if std > 1e-9:
        standardized = (x - mean) / std
        result["skew"] = float(np.mean(standardized ** 3))
        result["kurtosis"] = float(np.mean(standardized ** 4) - 3)
    elapsed = (t[-1] - t[0]) / 1e6
    if elapsed > 0:
        tenth = max(1, len(x) // 10)
        result["slope"] = float((np.mean(x[-tenth:]) - np.mean(x[:tenth])) / elapsed)
    # Do not interpolate gaps to manufacture uniformly sampled waveforms.
    if (np.isfinite(frequency) and frequency >= 2 and result["coverage"] >= .8
            and (len(t) < 2 or np.max(np.diff(t)) <= 2.5e6 / frequency)):
        frequencies, powers = welch(x, fs=frequency, nperseg=min(512, len(x)), detrend="constant")
        selected = (frequencies >= .5) & (frequencies <= min(4., frequency / 2))
        if np.any(selected):
            result["dominant_hz"] = float(frequencies[selected][np.argmax(powers[selected])])
            result["power_05_4hz"] = float(np.trapezoid(powers[selected], frequencies[selected]))
    return result


def pulse_features(peaks_us, endpoint_us, seconds=120):
    selected = peaks_us[(peaks_us >= endpoint_us - int(seconds * 1e6)) & (peaks_us < endpoint_us)]
    intervals = np.diff(selected) / 1000
    valid = intervals[(intervals >= 300) & (intervals <= 2000)]
    result = {"peak_count": len(selected), "valid_interval_count": len(valid),
              "mean_rr_ms": np.nan, "sdnn_ms": np.nan, "rmssd_ms": np.nan,
              "pnn50": np.nan, "median_hr_bpm": np.nan}
    if len(valid) >= 3:
        result.update(mean_rr_ms=float(np.mean(valid)), sdnn_ms=float(np.std(valid, ddof=1)),
                      median_hr_bpm=float(60000 / np.median(valid)))
        # Adjacent differences must not bridge an invalid intervening interval.
        adjacent = (intervals[:-1] >= 300) & (intervals[:-1] <= 2000) & (intervals[1:] >= 300) & (intervals[1:] <= 2000)
        differences = np.diff(intervals)[adjacent]
        if len(differences):
            result["rmssd_ms"] = float(np.sqrt(np.mean(differences ** 2)))
            result["pnn50"] = float(np.mean(np.abs(differences) > 50))
    return result


def prepare_raw():
    from fastavro import reader
    verify_source_snapshot("fatigue")
    source_dir = RESEARCH / "multisensor-v1"
    base = pd.read_csv(source_dir / "dataset.csv", dtype={"label": str})
    manifest = json.loads((source_dir / "provenance.json").read_text(encoding="utf-8"))
    if digest(source_dir / "dataset.csv") != manifest["dataset_sha256"]:
        raise ValueError("Multisensor source features changed after audit")
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for index, row in enumerate(manifest["lineage"]):
        prefix = row["sensor_members"][0].split("/digital_biomarkers/")[0]
        grouped[prefix].append((index, row))
    rows, lineage = {}, []
    with zipfile.ZipFile(RAW / "geofatigue/Physiological Data.zip") as archive:
        for group_index, (prefix, observations) in enumerate(sorted(grouped.items())):
            members = sorted(name for name in archive.namelist() if name.startswith(prefix + "/raw_data/") and name.endswith(".avro"))
            if not members:
                raise ValueError("Missing original raw waveforms for a benchmark participant/day")
            chunks = defaultdict(list)
            peaks = []
            participant = re.search(r"/p(\d+)-", prefix)[1]
            for member in members:
                for record in reader(io.BytesIO(archive.read(member))):
                    observed_id = re.search(r"p(\d+)$", record["enrollment"]["participantID"])
                    if not observed_id or observed_id[1] != participant:
                        raise ValueError("AVRO enrollment differs from benchmark participant")
                    raw = record["rawData"]
                    for name in ("bvp", "eda", "temperature"):
                        chunk = signal_chunk(raw[name], raw[name]["values"])
                        if chunk is not None:
                            chunks[name].append(chunk)
                    acceleration = raw["accelerometer"]
                    params = acceleration["imuParams"]
                    span = params["digitalMax"] - params["digitalMin"]
                    if span and acceleration["x"]:
                        axes = np.column_stack([acceleration[axis] for axis in ("x", "y", "z")]).astype(float)
                        physical = (axes - params["digitalMin"]) * (params["physicalMax"] - params["physicalMin"]) / span + params["physicalMin"]
                        for axis_index, name in enumerate(("acc_x", "acc_y", "acc_z")):
                            chunks[name].append(signal_chunk(acceleration, physical[:, axis_index]))
                        chunks["acc_magnitude"].append(signal_chunk(acceleration, np.linalg.norm(physical, axis=1)))
                    peaks.append(np.asarray(raw["systolicPeaks"]["peaksTimeNanos"], dtype=np.int64) // 1000)
            signals = {name: combine_chunks(values) for name, values in chunks.items()}
            peak_times = np.unique(np.concatenate(peaks)) if peaks else np.array([], dtype=np.int64)
            for index, row in observations:
                endpoint = pd.Timestamp(row["response_time"]).value // 1000
                task_start = pd.Timestamp(row["task_start"]).value // 1000
                features = {}
                for name, signal in signals.items():
                    baseline_stats = describe_window(signal, task_start, 120)
                    for seconds in (60, 120):
                        stats = describe_window(signal, endpoint, seconds)
                        features.update({f"raw_{name}_{seconds}s_{key}": value for key, value in stats.items()})
                        for key in ("mean", "std", "rms"):
                            features[f"raw_{name}_{seconds}s_{key}_delta_baseline"] = stats[key] - baseline_stats[key]
                features.update({f"raw_pulse_{key}": value for key, value in pulse_features(peak_times, endpoint).items()})
                matches = [s for s in sessions["p" + participant] if pd.Timestamp(s["start_time"]).value // 1000 <= task_start <= pd.Timestamp(s["end_time"]).value // 1000]
                features["screening_sleep_hours"] = float(matches[0]["baseline"]["total_sleep_hours"]) if len(matches) == 1 and matches[0]["baseline"].get("total_sleep_hours") is not None else np.nan
                rows[index] = features
                lineage.append({"row_key": row["row_key"], "group_key": row["group_key"], "raw_members": members,
                                "response_time": row["response_time"], "raw_window_end_exclusive_us": int(endpoint)})
            print(f"Raw waveform feature groups {group_index+1}/{len(grouped)}", flush=True)
    if set(rows) != set(range(len(base))):
        raise ValueError("Raw feature preparation changed the benchmark cohort")
    raw_features = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    frame = pd.concat([base.drop(columns=["label"]), raw_features, base[["label"]]], axis=1)
    if np.isinf(frame.drop(columns=["label"]).to_numpy(dtype=float)).any():
        raise ValueError("Infinite derived waveform feature")
    directory = RESEARCH / "raw-v1"
    directory.mkdir(exist_ok=True)
    frame.to_csv(directory / "dataset.csv", index=False)
    row_order = {row["row_key"]: i for i, row in enumerate(manifest["lineage"])}
    result = {**manifest, "dataset_sha256": digest(directory / "dataset.csv"),
              "feature_code_sha256": digest(Path(__file__)), "parent_dataset_sha256": manifest["dataset_sha256"],
              "raw_features": list(raw_features), "features": [name for name in frame if name != "label"],
              "missing_counts": frame.drop(columns=["label"]).isna().sum().astype(int).to_dict(),
              "raw_lineage": sorted(lineage, key=lambda row: row_order[row["row_key"]]),
              "raw_temporal_policy": "Raw samples and systolic peaks strictly before the questionnaire response; baseline strictly before task start. Derived windows are 60/120 seconds. No interpolation across gaps, ratings are unchanged."}
    (directory / "provenance.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(frame)} observed responses with {len(result['features'])} causal predictors", flush=True)


if __name__ == "__main__":
    prepare_raw()
