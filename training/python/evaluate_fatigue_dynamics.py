"""Evaluate one frozen dynamics winner on all original 179 native Borg cases."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from common.calibrated_network import export_calibrated_network, predict_calibrated_network, predict_head_proba
from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
from fatigue_dynamics import DIRECTORY as CLASSIFICATION_DIRECTORY, load_inputs
from fatigue_dynamics_experiment import DynamicsClassifier, plan, selection_code_digest
from public_sources import digest, verify_source_snapshot


def evaluate(family="classification"):
    verify_source_snapshot("fatigue")
    input_loader = load_inputs
    provenance_directory = CLASSIFICATION_DIRECTORY
    if family == "classification":
        directory, estimator_type = CLASSIFICATION_DIRECTORY, DynamicsClassifier
        candidate_plan, code_digest = plan, selection_code_digest
        source_path = Path(__file__).with_name("fatigue_dynamics_experiment.py")
    elif family == "regression":
        import fatigue_dynamics_regression as continuous
        directory, estimator_type = continuous.DIRECTORY, continuous.ContinuousBorg
        candidate_plan, code_digest = continuous.plan, lambda: digest(Path(continuous.__file__))
        source_path = Path(continuous.__file__)
    elif family == "phone":
        import fatigue_phone_experiment as phone
        directory, estimator_type = phone.DIRECTORY, DynamicsClassifier
        candidate_plan, code_digest = phone.plan, lambda: digest(Path(phone.__file__))
        input_loader, provenance_directory = phone.load_inputs, directory
        source_path = Path(phone.__file__)
    else:
        raise ValueError("Unknown dynamics model family")
    frame, train, test, manifest, protocol = input_loader()
    path = directory / "selection.json"
    selection = json.loads(path.read_text(encoding="utf-8"))
    if (selection["status"] != "complete" or selection["code_sha256"] != code_digest()
            or selection["plan"] != candidate_plan(manifest) or selection["dataset_sha256"] != manifest["dataset_sha256"]
            or selection["train_row_keys"] != train["row_key"].tolist() or selection["test_used_for_selection"]):
        raise ValueError("Dynamics search incomplete or its frozen inputs changed")
    best = max(selection["results"], key=lambda r: r["accuracy_mean"])
    if family == "phone":
        expected_dependencies = {"grouped_search_code_sha256": digest(Path(__file__).parent / "common/grouped_fatigue_search.py"),
                                 "classifier_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py"))}
        if any(selection.get(k) != v for k, v in expected_dependencies.items()):
            raise ValueError("Phone training dependencies changed after model selection")
    if best["candidate"]["id"] != selection["winner_id"]:
        raise ValueError("Frozen winner differs from original training CV")
    destination = directory / "evaluation"
    if destination.exists():
        raise ValueError("Frozen dynamics already evaluated; retain the held-out evidence")
    candidate = best["candidate"]
    with threadpool_limits(limits=1):
        classifier = estimator_type(candidate).fit(train)
    predicted = classifier.predict(test)
    labels = [f"Borg {i}" for i in range(11)]
    validity = {"real_public_ground_truth": True, "native_labels": True, "synthetic_rows": 0,
                "deployment_approved": False, "status": "participant_holdout_with_causal_observed_feedback",
                "reason": "Requires real prior Borg aged 1-15 minutes, actual earlier same-session feedback and compatible activity/physiology context. Reused published benchmark; descriptive research, not fresh external confirmation or field approval."}
    metrics = evaluate_training_run(clf=classifier, dataset_name=f"Fatiga Borg con dinámica de respuestas previas ({family})",
        declared_source=manifest["source"]["source"], source_note=validity["reason"], feature_cols=candidate["features"], labels=labels,
        full_features=frame[candidate["features"]], full_labels=frame["label"], x_train=train[candidate["features"]],
        x_test=test[candidate["features"]], y_train=train["label"], y_test=test["label"])
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    f1 = [float(f1_score(train.iloc[val]["label"], np.asarray(best["oof_predictions"])[val], labels=labels, average="macro", zero_division=0)) for _, val in folds]
    metrics.update(trained_at=datetime.now(timezone.utc).isoformat(), evaluation_validity=validity,
                   input_contract=manifest["input_contract"], target_accuracy=.8, target_accuracy_achieved=metrics["accuracy"] >= .8,
                   model_selection={"winner_id": selection["winner_id"], "candidate_count": len(selection["results"]), "test_used_for_selection": False})
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": best["accuracy_mean"], "accuracy_std": best["accuracy_std"],
                                               "f1_macro_mean": float(np.mean(f1)), "f1_macro_std": float(np.std(f1))}
    metrics["hyperparameters"] = {**candidate["params"], "algorithm": candidate["algorithm"], "target_mode": candidate["target_mode"],
                                  "selection_method": "cross_validated", "cv_folds": 5, "cv_f1_macro_mean": float(np.mean(f1))}
    metrics["evaluation_protocol"] = {**protocol, "selection_sha256": digest(path), "dynamics_provenance_sha256": digest(provenance_directory / "provenance.json"),
                                       "previous_benchmark_results_are_published": True, "test_used_for_selection": False,
                                       "prior_observed_user_reports_are_inputs": True}
    metrics["evaluation_details"] = holdout_details(train["label"], test["label"], predicted, labels, train["group_key"], test["group_key"])
    metrics["previous_borg_baseline"] = {"strategy": "repeat_previous_observed_Borg", **_summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], labels)}
    metrics["guardrails"]["warnings"].insert(0, "Requiere historia Borg observada antes de predecir; benchmark reutilizado y sin aprobación de campo.")
    destination.mkdir()
    model_path = destination / "model.joblib"
    joblib.dump(classifier, model_path)
    restored = joblib.load(model_path)  # Only this task's own fitted artifact.
    if not np.array_equal(restored.predict(frame), classifier.predict(frame)):
        raise AssertionError("Saved dynamics model differs from fitted model")
    metrics["model_artifact"] = {"path": model_path.name, "sha256": digest(model_path), "trusted_local_training_artifact": True}
    if family in ("classification", "phone") and candidate["algorithm"] == "mlp":
        payload = export_calibrated_network(classifier, validity, manifest["input_contract"])
        features = frame[candidate["features"]]
        if not np.array_equal(predict_calibrated_network(payload, features), classifier.predict(frame)):
            raise AssertionError("Portable dynamics network decisions differ")
        np.testing.assert_allclose(predict_head_proba(payload, features), classifier.model.predict_proba(features), atol=1e-10, rtol=1e-10)
        model_json_path = destination / "model.calibrated.json"
        model_json_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        metrics["portable_model_artifact"] = {"path": model_json_path.name, "sha256": digest(model_json_path), "verified_rows": len(frame)}
    predictions_path = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted,
                  "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(predictions_path, index=False)
    metrics["test_predictions_sha256"] = digest(predictions_path)
    metrics["training_source"] = {"frozen_selection_code_sha256": code_digest(), "current_reporting_code_sha256": digest(source_path),
                                   "persistence_recovery": "Recovered candidate 59 from a verified temporary checkpoint after Windows denied file replacement. Only report persistence changed; candidate and classifier AST match the original snapshot." if family == "classification" else None}
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    correct = int(np.sum(predicted == test["label"].to_numpy()))
    print(f"Frozen dynamics {candidate['id']}: exact test accuracy={metrics['accuracy']:.6f} ({correct}/{len(test)}); >=80%: {metrics['target_accuracy_achieved']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=("classification", "regression", "phone"), default="classification")
    evaluate(parser.parse_args().family)
