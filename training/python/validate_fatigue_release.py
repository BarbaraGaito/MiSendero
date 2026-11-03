"""Independently verify the frozen >=60% native-Borg research artifact.

Does not search or select a replacement model. Reconstructs its 13 causal
inputs from original questionnaires and task metadata, refits its frozen
configuration on the original training people, and checks every prediction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from common.calibrated_network import predict_calibrated_network, predict_head_proba
from common.evaluation import _summary_metrics
from fatigue_calibrated_alternatives import DIRECTORY, CalibratedClassifier, plan, selection_code_digest
from fatigue_calibrated_ensemble import load_inputs
from public_sources import OUTPUT, RAW, ROOT, digest, verify_source_snapshot


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def reconstructed_inputs(lineage, features):
    """Rebuild only released inputs, independently of derived feature CSVs."""
    reports = pd.read_csv(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
    reports["time"] = pd.to_datetime(reports["time"], utc=True)
    require(not reports.duplicated(["id", "time"]).any(), "Ambiguous original response")
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    rows, labels = [], []
    for evidence in lineage:
        participant = "p" + re.search(r"/p(\d+)-", evidence["lineage"]["member"])[1]
        now = pd.Timestamp(evidence["lineage"]["label_time"])
        matches = [(session, task) for session in sessions[participant] for task in session["tasks"]
                   if pd.Timestamp(task["start_time"]) <= now <= pd.Timestamp(task["end_time"])]
        require(len(matches) == 1, "Original response must belong to one task")
        session, task = matches[0]
        start = pd.Timestamp(task["start_time"])
        person = reports[reports["id"].eq(participant)]
        current = person[person["time"].eq(now)]
        require(len(current) == 1, "Current ground truth not found exactly once")
        observed = float(current.iloc[0]["borg_scale"])
        require(observed.is_integer() and 0 <= observed <= 10, "Non-native current Borg")
        labels.append(f"Borg {observed:g}")
        # History is an observed input: no current/future, other-person or
        # other-session self-report can enter the model's predictors.
        history = person[(person["time"] >= pd.Timestamp(session["start_time"]))
                         & (person["time"] >= now - pd.Timedelta(minutes=15))
                         & (person["time"] <= now - pd.Timedelta(minutes=1))].sort_values("time")
        require(len(history) > 0, "Missing mandatory previous Borg; no rows may be dropped")
        last = history.iloc[-1]
        row = {"prior_borg": float(last["borg_scale"]),
               "prior_age_minutes": (now - last["time"]).total_seconds() / 60,
               "prior2_borg": np.nan, "prior2_age_minutes": np.nan, "prior_borg_slope": np.nan,
               "prior_in_current_task": int(last["time"] >= start),
               "prior_count_current_task": int((history["time"] >= start).sum()),
               "elapsed_minutes": (now - start).total_seconds() / 60}
        if len(history) >= 2:
            second = history.iloc[-2]
            interval = (last["time"] - second["time"]).total_seconds() / 60
            row.update(prior2_borg=float(second["borg_scale"]),
                       prior2_age_minutes=(now - second["time"]).total_seconds() / 60,
                       prior_borg_slope=(float(last["borg_scale"]) - float(second["borg_scale"])) / interval)
        completed = [t for t in session["tasks"] if pd.Timestamp(t["end_time"]) <= start]
        row.update(task_order=len(completed) + 1,
                   cumulative_active_minutes=row["elapsed_minutes"] + sum(
                       (pd.Timestamp(t["end_time"]) - pd.Timestamp(t["start_time"])).total_seconds() / 60
                       for t in completed))
        row.update({f"terrain_{name}": int(task["label"] == name) for name in ("stairs", "ramp", "flat_trail")})
        require(set(row) == set(features), "Reconstruction differs from released input contract")
        rows.append(row)
    return pd.DataFrame(rows)[features], labels


def validate():
    verify_source_snapshot("fatigue")
    original = pd.read_csv(OUTPUT / "fatigue/dataset.csv", dtype={"label": str})
    lineage = json.loads((OUTPUT / "fatigue/provenance.json").read_text(encoding="utf-8"))["lineage"]
    frame, train, test, manifest, original_protocol = load_inputs()
    selection_path = DIRECTORY / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    evaluation = DIRECTORY / "evaluation"
    metrics_path = evaluation / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    require(len(frame) == len(original) == 666 and len(train) == 487 and len(test) == 179, "Original denominators changed")
    require(frame["row_key"].is_unique, "Repeated target responses")
    require(frame["row_key"].tolist() == [r["row_key"] for r in lineage], "Original observation identities/order changed")
    require(frame["group_key"].tolist() == [r["group_key"] for r in lineage], "Original participant identities changed")
    require(frame["label"].tolist() == original["label"].tolist(), "Original Borg labels changed or binned")
    require(train["group_key"].nunique() == 28 and test["group_key"].nunique() == 12
            and not set(train["group_key"]) & set(test["group_key"]), "Participant leakage or denominator changed")
    for key, value in original_protocol.items():
        require(metrics["evaluation_protocol"][key] == value, f"Original protocol changed: {key}")
    require(selection["status"] == "complete" and len(selection["results"]) == 60, "Incomplete frozen search")
    require(selection["train_row_keys"] == train["row_key"].tolist(), "Selection used other observations")
    require(selection["dataset_sha256"] == manifest["dataset_sha256"], "Selection data changed")
    require(selection["code_sha256"] == selection_code_digest(), "Training/prediction source differs from frozen snapshot")
    require(selection["plan"] == plan(manifest), "Candidate plan changed")
    require(selection["plan_sha256"] == hashlib.sha256(json.dumps(selection["plan"], sort_keys=True).encode()).hexdigest(), "Plan digest differs")
    require(not selection["test_used_for_selection"] and selection["previous_benchmark_results_are_published"], "Research evaluation scope changed")
    require(metrics["evaluation_protocol"]["selection_sha256"] == digest(selection_path), "Selection evidence changed")
    require(metrics["evaluation_protocol"]["calibration_provenance_sha256"] == digest(DIRECTORY.parent / "calibrated-v2/provenance.json"), "Calibration evidence changed")
    require(manifest["synthetic_rows"] == 0 and not manifest["rest_observations_added"], "Synthetic/easier observations added")

    # Recompute every candidate's stored OOF objective, then refit the winner's
    # five original folds. The final test is never a selection objective here.
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    require([r["candidate"] for r in selection["results"]] == selection["plan"], "Search results differ from frozen plan")
    for result in selection["results"]:
        values = np.asarray(result["oof_predictions"])
        require(len(values) == len(train), "OOF denominator changed")
        scores = [accuracy_score(train.iloc[val]["label"], values[val]) for _, val in folds]
        np.testing.assert_allclose(scores, result["fold_accuracy"], rtol=0, atol=1e-12)
        require(np.isclose(np.mean(scores), result["accuracy_mean"], rtol=0, atol=1e-12), "OOF mean differs")
        require(np.isclose(accuracy_score(train["label"], values), result["pooled_oof_accuracy"], rtol=0, atol=1e-12), "Pooled OOF differs")
    winner = max(selection["results"], key=lambda row: row["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] == "alternative-023", "Winner differs from original train CV")
    candidate = winner["candidate"]
    rebuilt, labels = reconstructed_inputs(lineage, candidate["features"])
    np.testing.assert_allclose(rebuilt, frame[candidate["features"]], rtol=0, atol=1e-12, equal_nan=True)
    require(labels == frame["label"].tolist(), "Current native labels differ from original questionnaires")
    for fit, val in folds:
        require(not set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]), "CV participant leakage")
        with threadpool_limits(limits=1):
            fold_model = CalibratedClassifier(candidate).fit(train.iloc[fit])
        require(np.array_equal(fold_model.predict(train.iloc[val]), np.asarray(winner["oof_predictions"])[val]), "Refitted winner OOF differs")

    artifact = evaluation / metrics["model_artifact"]["path"]
    require(digest(artifact) == metrics["model_artifact"]["sha256"], "Trusted local model artifact changed")
    model = joblib.load(artifact)  # Only the SHA-pinned model fitted by this task.
    require(type(model).__module__ == "fatigue_calibrated_alternatives" and model.candidate == candidate, "Artifact class/configuration differs")
    portable_path = evaluation / metrics["portable_model_artifact"]["path"]
    require(digest(portable_path) == metrics["portable_model_artifact"]["sha256"], "Portable model changed")
    payload = json.loads(portable_path.read_text(encoding="utf-8"))
    require(payload["feature_order"] == candidate["features"] and payload["target_mode"] == candidate["target_mode"], "Portable input/head contract differs")
    require(payload["input_contract"] == metrics["input_contract"] == manifest["input_contract"], "Calibration contract changed")
    with threadpool_limits(limits=1):
        refit = CalibratedClassifier(candidate).fit(train)
    expected = model.predict(frame)
    require(np.array_equal(refit.predict(frame), expected), "Independent train-only refit differs from artifact")
    np.testing.assert_allclose(refit.model.predict_proba(rebuilt), model.model.predict_proba(rebuilt), rtol=1e-10, atol=1e-10)
    native = predict_calibrated_network(payload, rebuilt)
    require(np.array_equal(native, expected), "Data-only portable model differs from fitted model")
    np.testing.assert_allclose(predict_head_proba(payload, rebuilt), model.model.predict_proba(rebuilt), rtol=1e-10, atol=1e-10)
    altered = frame.copy()
    altered["label"] = "Borg 10"
    require(np.array_equal(model.predict(altered), expected), "Current response is used as a predictor")
    for column, value in (("prior_borg", np.nan), ("prior_borg", 2.5), ("prior_borg", 11),
                          ("prior_age_minutes", 0), ("prior_age_minutes", -1), ("prior_age_minutes", 16)):
        bad = rebuilt.copy()
        bad.loc[0, column] = value
        try:
            predict_calibrated_network(payload, bad)
        except ValueError:
            continue
        raise ValueError(f"Portable model accepted invalid calibration: {column}={value}")

    prediction_path = evaluation / "test_predictions.csv"
    require(digest(prediction_path) == metrics["test_predictions_sha256"], "Saved test evidence changed")
    predictions = pd.read_csv(prediction_path)
    require(predictions["row_key"].tolist() == test["row_key"].tolist(), "Test observations dropped or reordered")
    require(predictions["observed"].tolist() == test["label"].tolist(), "Saved test ground truth changed")
    predicted = native[test.index]
    require(np.array_equal(predicted, predictions["predicted"]), "Saved predictions differ from released artifact")
    np.testing.assert_allclose(predictions["previous_borg"], test["prior_borg"], rtol=0, atol=1e-12)
    np.testing.assert_allclose(predictions["prior_age_minutes"], test["prior_age_minutes"], rtol=0, atol=1e-12)
    summary = _summary_metrics(test["label"], predicted, metrics["labels"])
    for key, value in summary.items():
        require(np.isclose(value, metrics["metrics"]["test"][key], rtol=0, atol=1e-12), f"Reported test metric differs: {key}")
    previous = _summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], metrics["labels"])
    for key, value in previous.items():
        require(np.isclose(value, metrics["previous_borg_baseline"][key], rtol=0, atol=1e-12), f"Previous Borg baseline differs: {key}")
    require(metrics["accuracy"] == summary["accuracy"], "Top-level accuracy differs")
    for validity in (metrics["evaluation_validity"], payload["evaluation_validity"], payload["classifier"]["evaluation_validity"]):
        require(validity["real_public_ground_truth"] and validity["native_labels"] and validity["synthetic_rows"] == 0
                and validity["deployment_approved"] is False, "Research validity/approval scope changed")
    correct = int(np.sum(predicted == test["label"].to_numpy()))
    require(correct == 108 and summary["accuracy"] >= .6, "Frozen artifact does not meet original >=60% objective")
    admin_path = ROOT / "ai/models/calibratedFatigueMetrics.json"
    require(admin_path.exists() and admin_path.read_bytes() == metrics_path.read_bytes(), "Admin metric snapshot differs from verified evaluation")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(), "achieved": True,
            "objective": "accuracy >= 0.60 on exact native Borg for all original 179 test responses",
            "accuracy": summary["accuracy"], "correct": correct, "test_rows": len(test),
            "train_rows": len(train), "train_participants": 28, "test_participants": 12,
            "cv_accuracy_mean": winner["accuracy_mean"], "test_f1_macro": summary["f1_macro"],
            "previous_borg_baseline": previous, "sensor_only_accuracy_unchanged": json.loads((OUTPUT / "fatigue/metrics.json").read_text())["accuracy"],
            "checks": {"original_source_hashes": True, "all_666_original_native_labels": True,
                       "all_13_inputs_reconstructed_from_original_past_reports_and_task_metadata": True,
                       "all_60_candidate_oof_scores_recomputed": True, "winner_cv_refitted": True,
                       "independent_train_only_refit_matches_all_666_predictions_and_probabilities": True,
                       "saved_model_loaded_in_fresh_process": True, "portable_json_matches_all_666_rows": True,
                       "current_label_mutation_does_not_affect_prediction": True, "invalid_calibration_rejected": True,
                       "saved_test_predictions_match_portable_artifact": True, "admin_snapshot_exact": True},
            "inputs": {"required": "Observed prior Borg aged 1-15 minutes in same session, older feedback if available, and elapsed/task/terrain context",
                       "sensor_only": False, "feature_order": candidate["features"]},
            "limitations": ["Reused published benchmark; descriptive research, not fresh external confirmation.",
                            "Requires real recent user feedback and study activity context; not autonomous sensor inference.",
                            "Macro F1 remains low and below copying the previous Borg; exact accuracy alone does not establish per-class performance.",
                            "No field deployment approval; independent prospective evaluation remains required."],
            "deployment_approved": False,
            "evidence_sha256": {"selection": digest(selection_path), "metrics": digest(metrics_path),
                                "fitted_model": digest(artifact), "portable_model": digest(portable_path),
                                "test_predictions": digest(prediction_path), "verifier": digest(Path(__file__))}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
