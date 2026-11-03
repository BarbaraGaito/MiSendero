"""Past-complete phone movement windows, preserving all original Borg targets.

Exact coordinates, absolute altitude, participant IDs and absolute timestamps
are never predictors. Missing phone recordings/windows remain missing; no
original target response is removed or manufactured to improve accuracy.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from common.privacy import assert_no_restricted_columns
from fatigue_dynamics import load_inputs as parent_inputs
from fatigue_features import RESEARCH
from fetch_geofatigue_context import DIRECTORY as RAW_DIRECTORY, METADATA_PATH
from public_sources import digest

DIRECTORY = RESEARCH / "phone-context-80-v1"
CACHE_DIRECTORY = RAW_DIRECTORY / "seconds-cache"
SECOND = pd.Timedelta(seconds=1)
CHANNELS = ["acc_rms", "acc_std", "gyro_mean", "speed_native"]


def completed_seconds(raw, *, conflict_policy="raise"):
    if conflict_policy not in ("raise", "exclude_ambiguous"):
        raise ValueError("Unknown phone timestamp conflict policy")
    required = ["time", "ax", "ay", "az", "wx", "wy", "wz", "speed", "altitude"]
    if not set(required) <= set(raw):
        raise ValueError("Phone CSV does not match the published sensor schema")
    data = raw[required].copy()
    data["time"] = pd.to_datetime(data["time"], utc=True)
    for column in required[1:]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data["time"].isna().any():
        raise ValueError("Phone sensor sample lacks a timestamp")
    quality = {"original_sample_rows": len(data), "ambiguous_timestamps": 0, "excluded_ambiguous_sample_rows": 0,
               "identical_duplicate_sample_rows": 0}
    if data["time"].duplicated().any():
        duplicates = data[data["time"].duplicated(keep=False)].groupby("time").nunique(dropna=False)
        ambiguous = duplicates.index[(duplicates > 1).any(axis=1)]
        if len(ambiguous) and conflict_policy == "raise":
            raise ValueError("Conflicting phone samples at an identical timestamp require source audit")
        # Source audit found two contradictory samples at one millisecond in
        # p22-ramp (2/133077 rows). Apply this rule to every file without using
        # any Borg label: retain neither ambiguous reading, then aggregate the
        # remaining actual samples. Target observations are never removed.
        rejected = data["time"].isin(ambiguous)
        quality.update(ambiguous_timestamps=len(ambiguous), excluded_ambiguous_sample_rows=int(rejected.sum()))
        data = data[~rejected]
        quality["identical_duplicate_sample_rows"] = int(data["time"].duplicated().sum())
        data = data.drop_duplicates("time")
    data = data.sort_values("time").set_index("time")
    acceleration = np.sqrt((data[["ax", "ay", "az"]] ** 2).sum(axis=1, min_count=3))
    gyro = np.sqrt((data[["wx", "wy", "wz"]] ** 2).sum(axis=1, min_count=3))
    signals = pd.DataFrame({"acc": acceleration.where(acceleration.between(0, 150)),
                            "gyro": gyro.where(gyro.between(0, 50)),
                            "speed_native": data["speed"].where(data["speed"].between(0, 20)),
                            "altitude": data["altitude"].where(data["altitude"].between(-500, 8000))})
    # Only bins that contain actual samples exist; gaps are never interpolated.
    grouped = signals.groupby(signals.index.floor("s"))
    result = pd.DataFrame({"acc_rms": grouped["acc"].agg(lambda x: np.sqrt(np.nanmean(x.to_numpy() ** 2)) if x.notna().any() else np.nan),
                         "acc_std": grouped["acc"].std(ddof=0), "gyro_mean": grouped["gyro"].mean(),
                         "speed_native": grouped["speed_native"].median(), "relative_height_source": grouped["altitude"].median()})
    result.attrs["quality_audit"] = quality
    return result


def describe_window(window):
    result = {"observed_seconds": len(window)}
    for channel in CHANNELS:
        x = window[channel].dropna().to_numpy(float)
        result.update({f"{channel}_mean": float(np.mean(x)) if len(x) else np.nan,
                       f"{channel}_std": float(np.std(x)) if len(x) else np.nan,
                       f"{channel}_p90": float(np.quantile(x, .9)) if len(x) else np.nan})
    speed = window["speed_native"].dropna()
    result["stopped_fraction"] = float((speed < .1).mean()) if len(speed) else np.nan
    height = window["relative_height_source"].dropna()
    # Do not bridge GPS gaps or convert jumps into a physical ascent estimate.
    difference = height.diff().where(height.index.to_series().diff() <= pd.Timedelta(seconds=1.5))
    difference = difference.where(difference.abs() <= 4.)
    result["height_p90_range"] = float(height.quantile(.9) - height.quantile(.1)) if len(height) >= 2 else np.nan
    result["height_change"] = float(height.iloc[-1] - height.iloc[0]) if len(height) >= 2 else np.nan
    result["positive_height_change"] = float(difference[difference >= .3].sum()) if difference.notna().any() else np.nan
    return result


def causal_phone_features(seconds, now, task_start, prior_time):
    complete = seconds[(seconds.index >= task_start) & (seconds.index + SECOND <= now)]
    result = {}
    for prefix, window in (("phone_recent30", complete[complete.index >= now - pd.Timedelta(seconds=30)]),
                           ("phone_recent120", complete[complete.index >= now - pd.Timedelta(seconds=120)]),
                           ("phone_task", complete)):
        result.update({f"{prefix}_{k}": v for k, v in describe_window(window).items()})
    initial = complete[complete.index + SECOND <= task_start + pd.Timedelta(minutes=1)]
    old = complete[(complete.index + SECOND <= prior_time) & (complete.index >= prior_time - pd.Timedelta(seconds=30))]
    for channel in CHANNELS:
        base = float(initial[channel].mean()) if initial[channel].notna().any() else np.nan
        previous = float(old[channel].mean()) if old[channel].notna().any() else np.nan
        current = result[f"phone_recent30_{channel}_mean"]
        result.update({f"phone_{channel}_initial_mean": base,
                       f"phone_{channel}_change_from_initial": current - base,
                       f"phone_{channel}_at_prior_report": previous,
                       f"phone_{channel}_change_after_prior": current - previous})
    return result


def cached_seconds(source):
    """Data-only cache bound to the original file, extraction code and content."""
    if digest(source["path"]) != source["sha256"]:
        raise ValueError("Original phone CSV changed before cache preparation")
    code_sha256 = digest(Path(__file__))
    CACHE_DIRECTORY.mkdir(exist_ok=True)
    stem = source["path"].name + "." + code_sha256[:12]
    path = CACHE_DIRECTORY / (stem + ".npz")
    metadata_path = CACHE_DIRECTORY / (stem + ".json")
    expected_columns = CHANNELS + ["relative_height_source"]
    if path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (metadata["original_sha256"] != source["sha256"] or metadata["extraction_code_sha256"] != code_sha256
                or metadata["cache_sha256"] != digest(path)):
            raise ValueError("Phone second-cache differs from its pinned source/code/content")
        with np.load(path, allow_pickle=False) as payload:
            if payload["columns"].tolist() != expected_columns or payload["values"].shape != (len(payload["time_ns"]), len(expected_columns)):
                raise ValueError("Phone second-cache schema differs from original extraction")
            result = pd.DataFrame(payload["values"], columns=expected_columns,
                                  index=pd.to_datetime(payload["time_ns"], unit="ns", utc=True))
            result.attrs["quality_audit"] = metadata["quality_audit"]
            return result
    raw = pd.read_csv(source["path"], usecols=["time", "ax", "ay", "az", "wx", "wy", "wz", "speed", "altitude"])
    seconds = completed_seconds(raw, conflict_policy="exclude_ambiguous")
    # Pandas 3 can infer microsecond resolution. Store an explicit ns unit,
    # rather than assuming that DatetimeIndex.asi8 is always nanoseconds.
    np.savez_compressed(path, time_ns=seconds.index.as_unit("ns").asi8,
                        values=seconds[expected_columns].to_numpy(float), columns=np.asarray(expected_columns))
    metadata = {"version": 1, "original_filename": source["path"].name, "original_sha256": source["sha256"],
                "extraction_code_sha256": code_sha256, "cache_sha256": digest(path), "observed_seconds": len(seconds),
                "quality_audit": seconds.attrs["quality_audit"]}
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return seconds


def cache_available():
    sources, _ = available_sources(require_complete=False)
    for index, source in enumerate(sources):
        seconds = cached_seconds(source)
        print(f"Phone schema/cache {index+1}/{len(sources)} {source['path'].name}: {len(seconds)} observed seconds", flush=True)


def available_sources(require_complete):
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    receipt = json.loads((RAW_DIRECTORY / "receipt.json").read_text(encoding="utf-8"))
    if receipt["metadata_sha256"] != digest(METADATA_PATH):
        raise ValueError("Phone download receipt refers to other metadata")
    if require_complete and not receipt["all_complete_and_verified"]:
        raise ValueError(f"Phone download still in progress: {len(receipt['files'])}/{receipt['expected_files']} file results; poll the live download before preparation")
    sources = []
    for row in metadata["data"]["latestVersion"]["files"]:
        entry = row["dataFile"]
        if row.get("directoryLabel") != "Contextual Data/Contextual Sensing Data":
            continue
        name = entry["originalFileName"]
        path = RAW_DIRECTORY / name
        recorded = next((r for r in receipt["files"] if r["filename"] == name and r["status"] == "verified"), None)
        if recorded is None:
            continue
        if digest(path) != recorded["sha256"] or digest(path, "md5") != entry["checksum"]["value"]:
            raise ValueError("Original phone CSV no longer matches publisher/local checksums")
        match = re.fullmatch(r"(p\d+)-(flat_ground|ground|ramp|stairs|staris)(?:-\d+)?\.csv", name)
        if not match:
            raise ValueError("Unexpected original phone recording filename")
        terrain = {"flat_ground": "flat_trail", "ground": "flat_trail", "staris": "stairs"}.get(match[2], match[2])
        sources.append({"participant": match[1], "terrain": terrain, "path": path, "sha256": recorded["sha256"]})
    return sources, receipt


def prepare(probe=False):
    sources, receipt = available_sources(require_complete=not probe)
    frame, _, _, manifest, _ = parent_inputs()
    rows, evidence, quality = {}, [], []
    by_group = {}
    for index, item in enumerate(manifest["lineage"]):
        participant = "p" + re.search(r"/p(\d+)-", item["sensor_members"][0])[1]
        if probe and participant != "p0":
            continue
        terrain = next(name for name in ("stairs", "ramp", "flat_trail") if frame.iloc[index][f"terrain_{name}"] == 1)
        by_group.setdefault((participant, terrain), []).append((index, item))
    for (participant, terrain), observations in by_group.items():
        matched = [s for s in sources if s["participant"] == participant and s["terrain"] == terrain]
        frames = [cached_seconds(s) for s in matched]
        quality.extend({"filename": s["path"].name, **f.attrs["quality_audit"]} for s, f in zip(matched, frames))
        seconds = pd.concat(frames).sort_index() if frames else pd.DataFrame(columns=CHANNELS + ["relative_height_source"], index=pd.DatetimeIndex([], tz="UTC"))
        if seconds.index.duplicated().any():
            raise ValueError("Published phone recordings overlap within a task; audit before aggregation")
        for index, item in observations:
            now, start = pd.Timestamp(item["response_time"]), pd.Timestamp(item["task_start"])
            prior_time = now - pd.Timedelta(minutes=float(frame.iloc[index]["prior_age_minutes"]))
            row = causal_phone_features(seconds, now, start, prior_time)
            rows[index] = row
            available = seconds[(seconds.index >= start) & (seconds.index + SECOND <= now)]
            evidence.append({"row_key": item["row_key"], "prediction_time": now.isoformat(),
                             "latest_used_second_end": (available.index[-1] + SECOND).isoformat() if len(available) else None,
                             "original_phone_files": [{"filename": s["path"].name, "sha256": s["sha256"]} for s in matched],
                             "observed_seconds": len(available)})
    added = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    if probe:
        report = {"mode": "probe_only_no_training_dataset_written", "rows_inspected": len(added),
                  "new_features": len(added.columns), "available_source_files": len(sources),
                  "rows_without_past_phone_seconds": int((added["phone_task_observed_seconds"] == 0).sum()),
                  "lineage": evidence}
        destination = RESEARCH / "phone-probe-80-v1.json"
        destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"Phone probe: {len(added)} original p0 observations, {len(added.columns)} causal features; {report['rows_without_past_phone_seconds']} rows lack prior phone samples (retained)", flush=True)
        return
    if len(added) != 666 or added.index.tolist() != frame.index.tolist():
        raise ValueError("Phone preparation changed the original response cohort")
    combined = pd.concat([frame.drop(columns=["label", "row_key", "group_key"]), added, frame[["label"]]], axis=1)
    assert_no_restricted_columns(combined, "phone-context-80-v1")
    if (DIRECTORY / "dataset.csv").exists():
        raise ValueError("Frozen phone snapshot exists; preserve its previous version")
    DIRECTORY.mkdir(exist_ok=True)
    combined.to_csv(DIRECTORY / "dataset.csv", index=False)
    result = {**manifest, "dataset_sha256": digest(DIRECTORY / "dataset.csv"), "parent_dataset_sha256": manifest["dataset_sha256"],
              "feature_code_sha256": digest(Path(__file__)), "phone_metadata_sha256": digest(METADATA_PATH),
              "phone_receipt_sha256": digest(RAW_DIRECTORY / "receipt.json"), "phone_features": list(added), "phone_lineage": evidence,
              "phone_sensor_quality": quality,
              "phone_second_cache": "Data-only NPZ; original, extraction-code and cache-content SHA256 checked; timestamps stored with explicit nanosecond unit.",
              "phone_units_note": "Acceleration m/s2 and gyroscope rad/s per author loader. Speed retained in native units without conversion because README and loader disagree (km/h vs m/s). No exact coordinates or absolute altitude enter predictors.",
              "phone_policy": "Observed one-second bins end at or before prediction; prior-report windows end before that earlier report. No gap interpolation, current/future Borg, participant identifier, absolute timestamp, location coordinate or target exclusion.",
              "features": [c for c in combined if c != "label"]}
    (DIRECTORY / "provenance.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Prepared {len(combined)} unchanged native responses with {len(added.columns)} causal phone predictors", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--cache-available", action="store_true")
    args = parser.parse_args()
    cache_available() if args.cache_available else prepare(args.probe)
