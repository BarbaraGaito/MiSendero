"""Train-only refinement of calibrated Borg: causal HR changes and history.

The v1 held-out result is preserved. New candidates are ranked exclusively by
the same participant-disjoint training folds; no held-out errors are inspected.
"""
from __future__ import annotations

import json
import hashlib
import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import ParameterSampler

from fatigue_calibrated import evaluate, previous_reports
from fatigue_features import RESEARCH
from public_sources import OUTPUT, RAW, digest, verify_source_snapshot


def prepare():
    verify_source_snapshot("fatigue")
    raw_dir, calibrated_dir = RESEARCH / "raw-v1", RESEARCH / "calibrated-v1"
    raw_manifest = json.loads((raw_dir / "provenance.json").read_text(encoding="utf-8"))
    prior_manifest = json.loads((calibrated_dir / "provenance.json").read_text(encoding="utf-8"))
    for directory, manifest in ((raw_dir, raw_manifest), (calibrated_dir, prior_manifest)):
        if digest(directory / "dataset.csv") != manifest["dataset_sha256"]:
            raise ValueError("Audited source features changed")
    frame = pd.read_csv(raw_dir / "dataset.csv", dtype={"label": str})
    prior_frame = pd.read_csv(calibrated_dir / "dataset.csv", dtype={"label": str})
    if frame["label"].tolist() != prior_frame["label"].tolist():
        raise ValueError("Calibration and waveform observations do not match")
    frame = pd.concat([frame.drop(columns=["label"]), prior_frame[prior_manifest["calibration_features"]], frame[["label"]]], axis=1)
    canonical = json.loads((OUTPUT / "fatigue/provenance.json").read_text(encoding="utf-8"))
    responses = pd.read_csv(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
    responses["time"] = pd.to_datetime(responses["time"], utc=True)
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    cached = {}
    additions, history_evidence = [], []
    with zipfile.ZipFile(RAW / "geofatigue/Physiological Data.zip") as archive:
        for i, row in enumerate(canonical["lineage"]):
            member = row["lineage"]["member"]
            if member not in cached:
                data = pd.read_csv(io.BytesIO(archive.read(member)))
                data["time"] = pd.to_datetime(data["timestamp_unix"], unit="ms", utc=True)
                values = pd.to_numeric(data["pulse_rate_bpm"], errors="coerce")
                valid = (data["missing_value_reason"].isna() | data["missing_value_reason"].eq("")) & values.between(30, 240)
                cached[member] = pd.Series(values[valid].to_numpy(), index=data.loc[valid, "time"]).sort_index()
            participant = "p" + re.search(r"/p(\d+)-", member)[1]
            t = pd.Timestamp(row["lineage"]["label_time"])
            session = next(s for s in sessions[participant] if pd.Timestamp(s["start_time"]) <= t <= pd.Timestamp(s["end_time"]))
            old = previous_reports(responses[responses["id"].eq(participant)], t, pd.Timestamp(session["start_time"]))
            if old.empty:
                raise ValueError("No observed prior input; do not exclude rows to improve accuracy")
            last_time = old.iloc[-1]["time"]
            heart_rate = cached[member]
            prior_samples = heart_rate[(heart_rate.index + pd.Timedelta(minutes=1) <= last_time)
                                       & (heart_rate.index >= last_time - pd.Timedelta(minutes=2))]
            prior_hr = float(prior_samples.iloc[-1]) if len(prior_samples) else np.nan
            change = float(frame.iloc[i]["hr_last"]) - prior_hr
            ratings = old["borg_scale"].to_numpy(dtype=float)
            additions.append({"prior_hr_at_report": prior_hr, "hr_change_after_prior": change,
                              "hr_change_per_minute_after_prior": change / float(frame.iloc[i]["prior_age_minutes"]),
                              "prior_history_mean": float(np.mean(ratings)), "prior_history_std": float(np.std(ratings)),
                              "prior_history_min": float(np.min(ratings)), "prior_history_max": float(np.max(ratings)),
                              "prior_history_count": len(ratings)})
            history_evidence.append({"row_key": row["row_key"], "reports": [{"time": r["time"].isoformat(), "observed_borg": float(r["borg_scale"])} for _, r in old.iterrows()],
                                     "prior_hr_signal_start": prior_samples.index[-1].isoformat() if len(prior_samples) else None})
    extra = pd.DataFrame(additions)
    frame = pd.concat([frame.drop(columns=["label"]), extra, frame[["label"]]], axis=1)
    directory = RESEARCH / "calibrated-v2"
    directory.mkdir(exist_ok=True)
    frame.to_csv(directory / "dataset.csv", index=False)
    manifest = {**prior_manifest, "version": 2, "features": [c for c in frame if c != "label"],
                "dataset_sha256": digest(directory / "dataset.csv"), "feature_code_sha256": digest(Path(__file__)),
                "parent_calibrated_dataset_sha256": prior_manifest["dataset_sha256"],
                "parent_waveform_dataset_sha256": raw_manifest["dataset_sha256"],
                "raw_features": raw_manifest["raw_features"], "raw_lineage": raw_manifest["raw_lineage"],
                "history_features": list(extra), "history_lineage": history_evidence,
                "temporal_history_policy": "Only observed Borg 1-15 minutes before prediction; HR change uses the last complete observed minute ending before that prior report. No current/future target or physiology is used."}
    (directory / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(frame)} unchanged calibrated responses, with causal prior HR and Borg history", flush=True)
    return frame, manifest


def plan(manifest):
    prior = manifest["calibration_features"]
    history = manifest["history_features"]
    context = ["elapsed_minutes", "cumulative_active_minutes", "task_order", "terrain_stairs", "terrain_flat_trail", "terrain_ramp"]
    normalized = [c for c in manifest["features"] if not c.startswith("raw_") and c.endswith(("delta_baseline", "ratio_baseline", "recent_slope", "history_std"))]
    # The old train-CV winner remains an eligible control. Its test score has
    # no role in this ranking or in choosing any new hyperparameter.
    old = json.loads((RESEARCH / "calibrated-v1/selection.json").read_text(encoding="utf-8"))
    incumbent = next(r["candidate"] for r in old["results"] if r["candidate"]["id"] == old["winner_id"])
    candidates = [{**incumbent, "id": "calibrated-v2-000", "incumbent_control": True}]
    sets = {"compact_history": prior + history + ["hr_last", "elapsed_minutes"],
            "normalized_history": list(dict.fromkeys(prior + history + normalized + context)),
            "waveform_relative_history": list(dict.fromkeys(prior + history + context + [c for c in manifest["raw_features"] if c.endswith("delta_baseline") or c.startswith("raw_pulse_")]))}
    space = {"max_depth": [3, 5, 8, 12, None], "min_samples_leaf": [1, 2, 3, 5, 8], "max_features": [.5, .7, 1.]}
    sampled = list(ParameterSampler(space, n_iter=12, random_state=42))
    for name, features in sets.items():
        for algorithm in ("random_forest", "extra_trees"):
            for parameters in sampled:
                candidates.append({"id": f"calibrated-v2-{len(candidates):03d}", "algorithm": algorithm,
                                   "params": {"n_estimators": 200, **parameters}, "features": features,
                                   "feature_set": name, "target_mode": "change_from_prior"})
    return candidates


def main():
    directory = RESEARCH / "calibrated-v2"
    if not (directory / "provenance.json").exists():
        prepare()
    manifest = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if digest(directory / "dataset.csv") != manifest["dataset_sha256"] or digest(Path(__file__)) != manifest["feature_code_sha256"]:
        raise ValueError("Calibrated v2 inputs changed; preserve old evidence before rebuilding")
    frame = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
    frame["row_key"] = [r["row_key"] for r in manifest["lineage"]]
    frame["group_key"] = [r["group_key"] for r in manifest["lineage"]]
    protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    training = frame[frame["row_key"].isin(protocol["train_row_keys"])].copy()
    if len(training) != len(protocol["train_row_keys"]) or set(training["group_key"]) & set(protocol["test_groups"]):
        raise ValueError("Calibrated v2 changed the original held-out cohort")
    candidates = plan(manifest)
    report = {"version": 2, "objective": "exact_native_Borg_accuracy_with_authorized_previous_report", "target_accuracy": .6,
              "test_evaluated_for_this_selection": False, "prior_version_test_is_published": True,
              "selection_uses_heldout_errors": False, "dataset_sha256": manifest["dataset_sha256"],
              "experiment_code_sha256": digest(Path(__file__)), "plan": candidates,
              "plan_sha256": hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest(),
              "train_row_keys": training["row_key"].tolist(), "status": "running", "results": []}
    path = directory / "selection.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        for key in ("dataset_sha256", "experiment_code_sha256", "plan_sha256"):
            if old[key] != report[key]:
                raise ValueError("Calibrated v2 plan changed; preserve old results before a new version")
        report = old
    done = {r["candidate"]["id"] for r in report["results"]}
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        cv = evaluate(training, candidate)
        report["results"].append({"candidate": candidate, "cv": cv})
        winner = max(report["results"], key=lambda r: r["cv"]["accuracy_mean"])
        report["winner_id"] = winner["candidate"]["id"]
        report["best_cv_accuracy"] = winner["cv"]["accuracy_mean"]
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']}: exact CV accuracy={cv['accuracy_mean']:.4f}, best={report['best_cv_accuracy']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
