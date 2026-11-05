"""Causal multisensor features for the existing native Borg observations.

Every digital biomarker summarizes one completed minute. Values whose minute
ends after the response are excluded, including from baseline normalization.
No Borg response, participant identifier or time of day is a predictor.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from public_sources import OUTPUT, RAW, ROOT, digest, verify_source_snapshot

RESEARCH = ROOT / "training/data/fatigue-research"
SIGNALS = {
    "hr": ("pulse-rate.csv", "pulse_rate_bpm", 30, 240),
    "eda": ("eda.csv", "eda_scl_usiemens", 0, 100),
    "prv": ("prv.csv", "prv_rmssd_ms", 0, 1000),
    "respiration": ("respiratory-rate.csv", "respiratory_rate_brpm", 3, 80),
    "temperature": ("temperature.csv", "temperature_celsius", 5, 45),
    "acceleration": ("accelerometers-std.csv", "accelerometers_std_g", 0, 10),
    "steps": ("step-counts.csv", "step_counts", 0, 300),
    "met": ("met.csv", "met", 0, 30),
}
MINUTE = pd.Timedelta(minutes=1)


def causal_statistics(signal, response_time, task_start, baseline_start):
    """Compute only past-complete task windows and past pre-task windows."""
    signal = signal.sort_index()
    complete = signal[signal.index + MINUTE <= response_time].dropna()
    task = complete[complete.index >= task_start]
    recent = task[task.index >= response_time - 3 * MINUTE]
    latest = task[task.index >= response_time - 2 * MINUTE]
    baseline = complete[(complete.index >= baseline_start) & (complete.index + MINUTE <= task_start)]
    last = float(latest.iloc[-1]) if len(latest) else np.nan
    base = float(baseline.mean()) if len(baseline) else np.nan
    slope = np.nan
    if len(recent) >= 2:
        minutes = (recent.index[-1] - recent.index[0]).total_seconds() / 60
        slope = float((recent.iloc[-1] - recent.iloc[0]) / minutes) if minutes else np.nan
    return {
        "last": last, "recent_mean": float(recent.mean()) if len(recent) else np.nan,
        "recent_std": float(recent.std(ddof=0)) if len(recent) else np.nan,
        "recent_slope": slope, "history_mean": float(task.mean()) if len(task) else np.nan,
        "history_std": float(task.std(ddof=0)) if len(task) else np.nan,
        "history_count": len(task), "baseline_mean": base,
        "delta_baseline": last - base,
        "ratio_baseline": last / base if np.isfinite(base) and abs(base) > 1e-9 else np.nan,
    }


def load_signal(archive, member, column, lower, upper):
    data = pd.read_csv(io.BytesIO(archive.read(member)))
    required = {"timestamp_unix", "participant_full_id", column, "missing_value_reason"}
    if not required <= set(data):
        raise ValueError(f"Unexpected public signal schema: {member}")
    values = pd.to_numeric(data[column], errors="coerce")
    valid = (data["missing_value_reason"].isna() | data["missing_value_reason"].eq("")) & values.between(lower, upper)
    data["value"] = values.where(valid)
    data["time"] = pd.to_datetime(data["timestamp_unix"], unit="ms", utc=True)
    if data.duplicated(["participant_full_id", "time"]).any():
        raise ValueError("Duplicate biomarker minute; audit before aggregating")
    return data


def prepare_multisensor(output_dir: Path | None = None):
    """Extend predictors without adding or deleting benchmark responses."""
    verify_source_snapshot("fatigue")
    canonical = OUTPUT / "fatigue"
    original = pd.read_csv(canonical / "dataset.csv", dtype={"label": str})
    provenance = json.loads((canonical / "provenance.json").read_text(encoding="utf-8"))
    if digest(canonical / "dataset.csv") != provenance["dataset_sha256"]:
        raise ValueError("Canonical measurements changed after audit")
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    responses = pd.read_csv(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
    responses["time"] = pd.to_datetime(responses["time"], utc=True)
    lineage = pd.DataFrame(provenance["lineage"])
    lineage["member"] = lineage["lineage"].map(lambda item: item["member"])
    records = {}
    evidence = []
    with zipfile.ZipFile(RAW / "geofatigue/Physiological Data.zip") as archive:
        members = set(archive.namelist())
        for member, observations in lineage.groupby("member", sort=True):
            prefix = member[:-len("pulse-rate.csv")]
            signals = {}
            for name, (suffix, column, lower, upper) in SIGNALS.items():
                target = prefix + suffix
                if target not in members:
                    raise ValueError(f"Missing corresponding original sensor file: {suffix}")
                signals[name] = load_signal(archive, target, column, lower, upper)
            participant_ids = signals["hr"]["participant_full_id"].unique()
            if len(participant_ids) != 1:
                raise ValueError("Expected one participant per biomarker member")
            full_id = str(participant_ids[0])
            participant = full_id.rsplit("-", 1)[-1]
            series = {name: data.set_index("time")["value"] for name, data in signals.items()}
            for row_index, row in observations.iterrows():
                response_time = pd.Timestamp(row["lineage"]["label_time"])
                matches = [(session, task) for session in sessions[participant] for task in session["tasks"]
                           if pd.Timestamp(task["start_time"]) <= response_time <= pd.Timestamp(task["end_time"])]
                if len(matches) != 1:
                    raise ValueError("Response must belong to exactly one published task")
                session, task = matches[0]
                start = pd.Timestamp(task["start_time"])
                tasks = sorted(session["tasks"], key=lambda item: item["start_time"])
                prior_tasks = [t for t in tasks if pd.Timestamp(t["end_time"]) <= start]
                prior_end = max([pd.Timestamp(t["end_time"]) for t in prior_tasks], default=pd.Timestamp(session["start_time"]))
                baseline_start = max(start - 5 * MINUTE, prior_end, pd.Timestamp(session["start_time"]))
                observed = responses[responses["id"].eq(participant) & responses["time"].eq(response_time)]
                if len(observed) != 1 or f"Borg {float(observed.iloc[0]['borg_scale']):g}" != original.iloc[row_index]["label"]:
                    raise ValueError("Independent Borg response differs from canonical observation")
                features = {"elapsed_minutes": (response_time - start).total_seconds() / 60,
                            "cumulative_active_minutes": sum((pd.Timestamp(t["end_time"]) - pd.Timestamp(t["start_time"])).total_seconds() / 60 for t in prior_tasks) + (response_time - start).total_seconds() / 60,
                            "task_order": len(prior_tasks) + 1}
                features.update({f"terrain_{name}": int(task["label"] == name) for name in ("flat_trail", "stairs", "ramp")})
                for name, signal in series.items():
                    features.update({f"{name}_{key}": value for key, value in causal_statistics(signal, response_time, start, baseline_start).items()})
                if not np.isclose(features["hr_last"], original.iloc[row_index]["hr"], atol=1e-12, rtol=0):
                    raise ValueError("Latest causal heart-rate minute differs from original predictor")
                records[row_index] = features
                evidence.append({"row_key": row["row_key"], "group_key": row["group_key"],
                                 "response_time": response_time.isoformat(), "task_start": start.isoformat(),
                                 "baseline_start": baseline_start.isoformat(),
                                 "latest_permitted_signal_start": (response_time - MINUTE).isoformat(),
                                 "sensor_members": [prefix + suffix for suffix, *_ in SIGNALS.values()]})
    if set(records) != set(range(len(original))):
        raise ValueError("Extended features omit or duplicate benchmark observations")
    features = pd.DataFrame.from_dict(records, orient="index").sort_index()
    if np.isinf(features.to_numpy(dtype=float)).any():
        raise ValueError("Infinite sensor feature")
    frame = features.assign(label=original["label"], group_key=lineage["group_key"], row_key=lineage["row_key"])
    directory = output_dir or RESEARCH / "multisensor-v1"
    directory.mkdir(parents=True, exist_ok=True)
    frame[list(features) + ["label"]].to_csv(directory / "dataset.csv", index=False)
    manifest = {"version": 1, "task": "exact_native_modified_Borg_rating_during_active_tasks",
                "source": provenance["source"], "canonical_dataset_sha256": provenance["dataset_sha256"],
                "canonical_provenance_sha256": digest(canonical / "provenance.json"),
                "feature_code_sha256": digest(Path(__file__)), "dataset_sha256": digest(directory / "dataset.csv"),
                "rows": len(frame), "groups": int(frame["group_key"].nunique()), "features": list(features),
                "missing_counts": features.isna().sum().astype(int).to_dict(),
                "labels_unchanged": True, "rest_observations_added": False, "synthetic_rows": 0,
                "temporal_policy": "Use only one-minute windows ending at or before response; baseline windows end before task start and begin after prior task end. No rating/history-of-ratings predictors.",
                "lineage": sorted(evidence, key=lambda item: frame["row_key"].tolist().index(item["row_key"]))}
    (directory / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(frame)} observed ratings, {len(features.columns)} causal features, {manifest['groups']} participants", flush=True)
    return frame, manifest


if __name__ == "__main__":
    prepare_multisensor()
