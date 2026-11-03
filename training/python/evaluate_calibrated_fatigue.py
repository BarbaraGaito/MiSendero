"""Evaluate one frozen calibrated candidate once on the complete original test."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from threadpoolctl import threadpool_limits

from common.calibrated_forest import JsonCalibratedPredictor, export_calibrated_forest, predict_calibrated_json
from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
from common.export_classifier import predict_proba_json
from common.calibrated_forest import transformed_features
from fatigue_calibrated import candidate_plan
from fatigue_experiment import estimator_for
from fatigue_features import RESEARCH
from public_sources import OUTPUT, ROOT, digest, verify_source_snapshot


def main(version="calibrated-v1"):
    verify_source_snapshot("fatigue")
    source = RESEARCH / version
    expected_plan = candidate_plan
    selection_code = "fatigue_calibrated.py"
    if version == "calibrated-v2":
        from fatigue_calibrated_v2 import plan
        expected_plan = plan
        selection_code = "fatigue_calibrated_v2.py"
    manifest = json.loads((source / "provenance.json").read_text(encoding="utf-8"))
    selection = json.loads((source / "selection.json").read_text(encoding="utf-8"))
    if (selection["status"] != "complete" or selection["dataset_sha256"] != digest(source / "dataset.csv")
            or selection["plan"] != expected_plan(manifest)
            or selection["experiment_code_sha256"] != digest(Path(__file__).with_name(selection_code))):
        raise ValueError("Calibrated inputs/plan changed or training-only search is incomplete")
    selected = max(selection["results"], key=lambda row: row["cv"]["accuracy_mean"])
    if selected["candidate"]["id"] != selection["winner_id"]:
        raise ValueError("Frozen winner differs from train-only accuracy objective")
    candidate, cv = selected["candidate"], selected["cv"]
    frame = pd.read_csv(source / "dataset.csv", dtype={"label": str})
    frame["row_key"] = [r["row_key"] for r in manifest["lineage"]]
    frame["group_key"] = [r["group_key"] for r in manifest["lineage"]]
    original_protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    train = frame[frame["row_key"].isin(original_protocol["train_row_keys"])].copy()
    test = frame[frame["row_key"].isin(original_protocol["test_row_keys"])].copy()
    if (len(train) != len(original_protocol["train_row_keys"]) or len(test) != len(original_protocol["test_row_keys"])
            or set(train["group_key"]) & set(test["group_key"])):
        raise ValueError("Complete original participant holdout was changed")
    if selection["train_row_keys"] != train["row_key"].tolist():
        raise ValueError("Calibrated selection used different training rows")
    destination = source / "evaluation-v1"
    if destination.exists():
        raise ValueError("This frozen candidate has already been evaluated; preserve the original holdout evidence")
    classifier = estimator_for(candidate)
    target = train["label"].str.replace("Borg ", "", regex=False).astype(int)
    if candidate["target_mode"] == "change_from_prior":
        target = target - train["prior_borg"].astype(int)
    with threadpool_limits(limits=1):
        classifier.fit(train[candidate["features"]], target.astype(str))
    validity = {"real_public_ground_truth": True, "status": "observed_native_borg_with_prior_user_calibration",
                "deployment_approved": False, "native_labels": True, "synthetic_rows": 0,
                "reason": "Exact native Borg ratings on the original active-task cohort with a real user Borg report from 1-15 minutes earlier. Requires chronological calibration feedback; not sensor-only or clinical field validation."}
    payload = export_calibrated_forest(classifier, candidate, manifest["input_contract"], validity)
    transformed, _ = transformed_features(payload, frame[candidate["features"]])
    if not np.allclose(predict_proba_json(payload["forest"], transformed), classifier.predict_proba(frame[candidate["features"]]), atol=1e-10, rtol=1e-10):
        raise AssertionError("Portable model differs from fitted forest probabilities")
    actual = classifier.predict(frame[candidate["features"]]).astype(int)
    if candidate["target_mode"] == "change_from_prior":
        actual = np.clip(actual + frame["prior_borg"].to_numpy(dtype=int), 0, 10)
    expected = np.asarray([f"Borg {i}" for i in actual])
    if not np.array_equal(predict_calibrated_json(payload, frame[candidate["features"]]), expected):
        raise AssertionError("Portable calibrated predictions differ from fitted estimator")
    predictor = JsonCalibratedPredictor(payload)
    labels = [f"Borg {i}" for i in range(11)]
    metrics = evaluate_training_run(clf=predictor, dataset_name="Fatiga Borg con calibración previa",
        declared_source=manifest["source"]["source"], source_note=validity["reason"],
        feature_cols=candidate["features"], labels=labels, full_features=frame[candidate["features"]], full_labels=frame["label"],
        x_train=train[candidate["features"]], x_test=test[candidate["features"]], y_train=train["label"], y_test=test["label"])
    predicted = predictor.predict(test[candidate["features"]])
    metrics["trained_at"] = datetime.now(timezone.utc).isoformat()
    metrics["evaluation_validity"] = validity
    metrics["hyperparameters"] = {**candidate["params"], "algorithm": candidate["algorithm"], "target_mode": candidate["target_mode"],
                                   "selection_method": "cross_validated", "cv_folds": 5, "cv_f1_macro_mean": float(np.mean([f["f1_macro"] for f in cv["folds"]]))}
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": cv["accuracy_mean"], "accuracy_std": cv["accuracy_std"],
        "f1_macro_mean": metrics["hyperparameters"]["cv_f1_macro_mean"], "f1_macro_std": float(np.std([f["f1_macro"] for f in cv["folds"]]))}
    metrics["evaluation_protocol"] = {**original_protocol, "calibration_provenance_sha256": digest(source / "provenance.json"),
        "selection_sha256": digest(source / "selection.json"), "test_used_for_model_selection": False,
        "previous_calibrated_family_test_is_published": version != "calibrated-v1",
        "prior_reports_from_test_participants_are_observed_inputs": True,
        "interpretation": "Unseen participant fitting with causal, observed previous Borg feedback. Test participants are not used to fit, impute or tune the model. This conditional task has a different input contract from the sensor-only baseline."}
    metrics["evaluation_details"] = holdout_details(train["label"], test["label"], predicted, labels, train["group_key"], test["group_key"])
    previous = [f"Borg {i:g}" for i in test["prior_borg"]]
    metrics["previous_borg_baseline"] = {"strategy": "repeat_observed_previous_borg_1_to_15_minutes_old",
                                          **_summary_metrics(test["label"], previous, labels)}
    metrics["input_contract"] = manifest["input_contract"]
    metrics["model_selection"] = {"winner_id": candidate["id"], "candidate_count": len(selection["results"]),
                                   "objective": "exact_native_borg_accuracy", "test_used_for_selection": False}
    metrics["guardrails"]["warnings"].insert(0, "Requiere una Borg previa real de 1 a 15 minutos; el resultado no corresponde al modo de sensores solos.")
    destination.mkdir()
    path = destination / "model.calibrated.json"
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    metrics["model_artifact"] = {"path": path.name, "sha256": digest(path), "algorithm": candidate["algorithm"]}
    predictions_path = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted,
                  "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(predictions_path, index=False)
    metrics["test_predictions_sha256"] = digest(predictions_path)
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Frozen candidate {candidate['id']}: test accuracy={metrics['accuracy']:.6f} ({sum(predicted == test['label'])}/{len(test)}), previous-Borg baseline={metrics['previous_borg_baseline']['accuracy']:.6f}", flush=True)
    print(f"Target >=60% achieved on the original complete test: {metrics['accuracy'] >= .6}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=["calibrated-v1", "calibrated-v2"], default="calibrated-v1")
    args = parser.parse_args()
    main(args.version)
