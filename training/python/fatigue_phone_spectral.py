"""Causal 10 Hz phone spectra, adding predictors without changing targets.

Observed 100 ms bins only, no gap interpolation. Generalized Lomb-Scargle
uses actual bin times. Gravity direction is estimated within each available
window; future samples never normalize a current or earlier-report window.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import lombscargle

from common.privacy import assert_no_restricted_columns
from fatigue_features import RESEARCH
from fatigue_phone_context import available_sources
from fatigue_phone_experiment import load_inputs as parent_inputs
from fetch_geofatigue_context import DIRECTORY as RAW_DIRECTORY
from public_sources import digest

DIRECTORY = RESEARCH / "phone-spectral-80-v1"
CACHE = RAW_DIRECTORY / "spectral-10hz-cache"
BIN = pd.Timedelta(milliseconds=100)
BIN_COLUMNS = ["acc_mag", "gyro_mag", "ax", "ay", "az"]
CHANNELS = ("acc_mag", "gyro_mag", "vertical")
BANDS = {"low": (.15, .6), "mid": (.6, 1.5), "gait": (1.5, 3.), "high": (3., 4.50001)}


def observed_bins(raw):
    required = ["time", "ax", "ay", "az", "wx", "wy", "wz", "speed", "altitude"]
    data = raw[required].copy()
    data["time"] = pd.to_datetime(data["time"], utc=True)
    if data["time"].isna().any():
        raise ValueError("Phone samples need explicit original timestamps")
    for column in required[1:]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    quality = {"original_sample_rows": len(data), "excluded_ambiguous_sample_rows": 0, "ambiguous_timestamps": 0, "identical_duplicate_sample_rows": 0}
    if data["time"].duplicated().any():
        duplicates = data[data["time"].duplicated(keep=False)].groupby("time").nunique(dropna=False)
        ambiguous = duplicates.index[(duplicates > 1).any(axis=1)]
        rejected = data["time"].isin(ambiguous)
        quality.update(ambiguous_timestamps=len(ambiguous), excluded_ambiguous_sample_rows=int(rejected.sum()))
        data = data[~rejected]
        quality["identical_duplicate_sample_rows"] = int(data["time"].duplicated().sum())
        data = data.drop_duplicates("time")
    data = data.sort_values("time").set_index("time")
    acc = np.sqrt((data[["ax", "ay", "az"]]**2).sum(axis=1, min_count=3))
    gyro = np.sqrt((data[["wx", "wy", "wz"]]**2).sum(axis=1, min_count=3))
    good_acc = acc.between(0, 150)
    signals = data[["ax", "ay", "az"]].where(good_acc, axis=0)
    signals = signals.assign(acc_mag=acc.where(good_acc), gyro_mag=gyro.where(gyro.between(0, 50)))
    bins = signals.groupby(signals.index.floor("100ms")).mean()[BIN_COLUMNS]
    bins.attrs["quality"] = quality
    return bins


def cached_bins(source):
    if digest(source["path"]) != source["sha256"]:
        raise ValueError("Phone source changed before spectral preparation")
    code = digest(Path(__file__))
    CACHE.mkdir(exist_ok=True)
    stem = source["path"].name + "." + code[:12]
    data_path, meta_path = CACHE / (stem+".npz"), CACHE / (stem+".json")
    if data_path.exists() and meta_path.exists():
        metadata = json.loads(meta_path.read_text())
        if metadata["original_sha256"] != source["sha256"] or metadata["code_sha256"] != code or metadata["cache_sha256"] != digest(data_path):
            raise ValueError("Spectral cache differs from its source/code/content")
        with np.load(data_path, allow_pickle=False) as payload:
            if payload["columns"].tolist() != BIN_COLUMNS or payload["values"].shape != (len(payload["time_ns"]), len(BIN_COLUMNS)):
                raise ValueError("Unexpected data-only spectral cache schema")
            result = pd.DataFrame(payload["values"], columns=BIN_COLUMNS, index=pd.to_datetime(payload["time_ns"], unit="ns", utc=True))
        result.attrs["quality"] = metadata["quality"]
        return result
    raw = pd.read_csv(source["path"], usecols=["time", "ax", "ay", "az", "wx", "wy", "wz", "speed", "altitude"])
    result = observed_bins(raw)
    np.savez_compressed(data_path, time_ns=result.index.as_unit("ns").asi8, values=result.to_numpy(float), columns=np.asarray(BIN_COLUMNS))
    metadata = {"version": 1, "original_sha256": source["sha256"], "code_sha256": code, "cache_sha256": digest(data_path),
                "quality": result.attrs["quality"], "observed_bins": len(result), "timestamp_unit": "ns", "bin_duration_ms": 100}
    meta_path.write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
    return result


def spectrum(times, values):
    values = np.asarray(values, dtype=float)
    good = np.isfinite(values)
    t = (times.as_unit("ns").asi8[good] - times.as_unit("ns").asi8[good][0]) / 1e9 if good.any() else np.asarray([])
    y = values[good]
    result = {"valid_bins": len(y), "std": float(np.std(y)) if len(y) else np.nan, "peak_hz": np.nan,
              "peak_normalized_power": np.nan, "entropy": np.nan, "supported_max_hz": np.nan,
              **{f"band_{name}_share": np.nan for name in BANDS}}
    if len(y) < 50 or t[-1]-t[0] < 10 or np.std(y) < 1e-8:
        return result
    delta = np.diff(t)
    if (delta <= 0).any():
        raise ValueError("Spectral samples must have distinct chronological times")
    maximum = min(4.5, .49 / float(np.median(delta)))
    # Resolve narrow peaks in the longest (120 s) window instead of measuring
    # coarse-grid attenuation as a change in movement periodicity.
    frequencies = np.linspace(.15, 4.5, 1024)
    frequencies = frequencies[frequencies <= maximum]
    if len(frequencies) < 3:
        return result
    power = lombscargle(t, y, 2*np.pi*frequencies, normalize=True, floating_mean=True)
    finite = np.isfinite(power)
    power, frequencies = np.maximum(power[finite], 0), frequencies[finite]
    if len(power) < 3 or power.sum() <= 0:
        return result
    mass = power / power.sum()
    result.update(peak_hz=float(frequencies[power.argmax()]), peak_normalized_power=float(power.max()),
                  entropy=float(-(mass*np.log(mass.clip(1e-15))).sum()/np.log(len(mass))), supported_max_hz=float(frequencies[-1]))
    for name, (low, high) in BANDS.items():
        selected = (frequencies >= low) & (frequencies < high)
        result[f"band_{name}_share"] = float(mass[selected].sum()) if selected.any() else np.nan
    return result


def describe(window):
    channels = {name: window[name].to_numpy(float) for name in ("acc_mag", "gyro_mag")}
    axes = window[["ax", "ay", "az"]].to_numpy(float)
    valid = np.isfinite(axes).all(axis=1)
    vertical = np.full(len(window), np.nan)
    if valid.any():
        gravity = axes[valid].mean(axis=0)
        norm = np.linalg.norm(gravity)
        if norm > 1e-8:
            vertical[valid] = axes[valid] @ (gravity/norm)
    channels["vertical"] = vertical
    result = {"observed_bins": len(window)}
    for name, values in channels.items():
        result.update({name+"_"+key: value for key, value in spectrum(window.index, values).items()})
    return result


def causal_features(bins, now, task_start, prior_time):
    complete = bins[(bins.index >= task_start) & (bins.index + BIN <= now)]
    windows = {"spectral60": complete[complete.index >= now-pd.Timedelta(seconds=60)],
               "spectral120": complete[complete.index >= now-pd.Timedelta(seconds=120)]}
    described = {prefix: describe(window) for prefix, window in windows.items()}
    result = {prefix+"_"+key: value for prefix, row in described.items() for key, value in row.items()}
    initial = describe(complete[complete.index + BIN <= task_start+pd.Timedelta(seconds=60)])
    old = describe(complete[(complete.index + BIN <= prior_time) & (complete.index >= prior_time-pd.Timedelta(seconds=60))])
    result.update(spectral_initial_observed_bins=initial["observed_bins"], spectral_prior_observed_bins=old["observed_bins"])
    for channel in CHANNELS:
        for metric in ("peak_hz", "std", "entropy"):
            key = channel+"_"+metric
            result["spectral_"+key+"_change_from_initial"] = described["spectral60"][key]-initial[key]
            result["spectral_"+key+"_change_after_prior"] = described["spectral60"][key]-old[key]
    return result


def prepare(probe=False):
    sources, _ = available_sources(require_complete=True)
    frame, _, _, parent, _ = parent_inputs()
    grouped = {}
    for index, evidence in enumerate(parent["lineage"]):
        person = "p"+re.search(r"/p(\d+)-", evidence["sensor_members"][0])[1]
        if probe and person != "p0":
            continue
        terrain = next(name for name in ("stairs", "ramp", "flat_trail") if frame.iloc[index]["terrain_"+name] == 1)
        grouped.setdefault((person, terrain), []).append((index, evidence))
    rows, lineage, quality = {}, [], []
    for step, ((person, terrain), queries) in enumerate(grouped.items()):
        matched = [source for source in sources if source["participant"] == person and source["terrain"] == terrain]
        data = [cached_bins(source) for source in matched]
        quality.extend({"filename": source["path"].name, **item.attrs["quality"]} for source, item in zip(matched, data))
        bins = pd.concat(data).sort_index() if data else pd.DataFrame(columns=BIN_COLUMNS, index=pd.DatetimeIndex([], tz="UTC"))
        if bins.index.duplicated().any():
            raise ValueError("Original phone files overlap at 100 ms resolution")
        for index, evidence in queries:
            now, start = pd.Timestamp(evidence["response_time"]), pd.Timestamp(evidence["task_start"])
            old = now-pd.Timedelta(minutes=float(frame.iloc[index]["prior_age_minutes"]))
            rows[index] = causal_features(bins, now, start, old)
            available = bins[(bins.index >= start) & (bins.index + BIN <= now)]
            lineage.append({"row_key": evidence["row_key"], "prediction_time": now.isoformat(),
                            "latest_available_complete_bin_end": (available.index[-1]+BIN).isoformat() if len(available) else None,
                            "original_phone_files": [{"filename": s["path"].name, "sha256": s["sha256"]} for s in matched]})
        print(f"Phone spectra {step+1}/{len(grouped)}: {person} {terrain}, {len(queries)} unchanged query rows", flush=True)
    added = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    if probe:
        report = {"mode": "schema_probe_only", "original_rows": len(added), "features": len(added.columns), "lineage": lineage}
        (RESEARCH / "phone-spectral-probe-80-v1.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print(f"Spectral probe complete: {len(added)} original p0 responses / {len(added.columns)} predictors / no model fitted", flush=True)
        return
    if len(added) != 666 or added.index.tolist() != frame.index.tolist():
        raise ValueError("Spectral extraction changed the original cohort")
    assert_no_restricted_columns(added, "phone-spectral-80-v1")
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "dataset.csv"
    if path.exists():
        raise ValueError("Preserve the frozen spectral snapshot before preparing another version")
    added.insert(0, "row_key", frame["row_key"].to_numpy())
    added.to_csv(path, index=False)
    provenance = {"version": 1, "dataset_sha256": digest(path), "parent_dataset_sha256": parent["dataset_sha256"],
                  "parent_feature_code_sha256": parent["feature_code_sha256"], "feature_code_sha256": digest(Path(__file__)),
                  "features": [c for c in added if c != "row_key"], "original_rows": 666, "synthetic_rows": 0,
                  "phone_receipt_sha256": parent["phone_receipt_sha256"], "phone_lineage": lineage, "phone_sensor_quality": quality,
                  "no_gap_interpolation": True, "bin_duration_ms": 100, "timestamps_in_cache": "explicit nanoseconds",
                  "periodogram_grid": {"minimum_hz": .15, "maximum_hz": 4.5, "points": 1024, "floating_mean": True},
                  "policy": "Current, earlier-report and initial windows contain observed bins ending no later than the applicable report. Periodogram times are relative to each window; gravity direction uses that window only. No coordinates, absolute time/height, identities or current/future Borg predictors. Missing coverage retains every target case."}
    (DIRECTORY / "provenance.json").write_text(json.dumps(provenance, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Prepared spectra for all 666 unchanged original responses: {len(provenance['features'])} predictors", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    prepare(parser.parse_args().probe)
