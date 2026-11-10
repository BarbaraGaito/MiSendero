"""One-time evaluation of the frozen CatBoost winner on all original cases."""
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
import fatigue_catboost as experiment
from public_sources import digest, verify_source_snapshot


def evaluate():
    verify_source_snapshot("fatigue")
    frame, train, test, manifest, protocol = experiment.load_inputs()
    selection_path = experiment.DIRECTORY / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (selection["status"] != "complete" or selection["test_used_for_selection"]
            or selection["code_sha256"] != digest(Path(experiment.__file__))
            or selection["dataset_sha256"] != manifest["dataset_sha256"]
            or selection["plan"] != experiment.plan(manifest)
            or selection["train_row_keys"] != train["row_key"].tolist()):
        raise ValueError("Frozen CatBoost fitting inputs changed or selection is incomplete")
    for package, version in selection["software_versions"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError("CatBoost runtime differs from the frozen search")
    for key, filename in (("phone_loader_code_sha256", "fatigue_phone_experiment.py"), ("dynamics_plan_code_sha256", "fatigue_dynamics_experiment.py")):
        if selection[key] != digest(Path(__file__).with_name(filename)):
            raise ValueError("CatBoost feature dependencies changed")
    winner = max(selection["results"], key=lambda row: row["accuracy_mean"])
    candidate = winner["candidate"]
    if candidate["id"] != selection["winner_id"]:
        raise ValueError("Winner differs from the frozen grouped CV selection")
    destination = experiment.DIRECTORY / "evaluation"
    if destination.exists():
        raise ValueError("Preserve the existing one-time CatBoost evaluation")
    model = experiment.CatBoostBorg(candidate).fit(train)
    predicted = model.predict(test)
    labels = [f"Borg {i}" for i in range(11)]
    validity = {"real_public_ground_truth": True, "native_labels": True, "synthetic_rows": 0,
                "deployment_approved": False, "status": "participant_holdout_with_causal_observed_feedback",
                "reason": "Uses actual earlier Borg aged 1-15 minutes and causal activity history. Reused published benchmark: descriptive research, not fresh external confirmation or field approval."}
    metrics = evaluate_training_run(clf=model, dataset_name="Fatiga Borg con CatBoost y respuestas previas",
        declared_source=manifest["source"]["source"], source_note=validity["reason"], feature_cols=candidate["features"], labels=labels,
        full_features=frame[candidate["features"]], full_labels=frame["label"], x_train=train[candidate["features"]],
        x_test=test[candidate["features"]], y_train=train["label"], y_test=test["label"])
    metrics.update(trained_at=datetime.now(timezone.utc).isoformat(), evaluation_validity=validity,
                   target_accuracy=.8, target_accuracy_achieved=metrics["accuracy"] >= .8,
                   input_contract={**manifest["input_contract"], "feature_order": candidate["features"],
                                   "categorical_features": ["current_terrain"],
                                   "history_policy": "Actual earlier same-session reports only; no current/future outcome. Missing older history remains missing and does not exclude a query."},
                   model_selection={"winner_id": candidate["id"], "candidate_count": len(selection["results"]), "test_used_for_selection": False},
                   hyperparameters=candidate)
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": winner["accuracy_mean"], "accuracy_std": float(np.std(winner["fold_accuracy"]))}
    metrics["evaluation_protocol"] = {**protocol, "selection_sha256": digest(selection_path),
                                      "previous_benchmark_results_are_published": True, "test_used_for_selection": False,
                                      "prior_observed_user_reports_are_inputs": True}
    metrics["evaluation_details"] = holdout_details(train["label"], test["label"], predicted, labels, train["group_key"], test["group_key"])
    metrics["previous_borg_baseline"] = {"strategy": "repeat_previous_observed_Borg", **_summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], labels)}
    destination.mkdir()
    model_path, descriptor_path = destination / "model.cbm", destination / "model.json"
    model.save(model_path, descriptor_path)
    restored = experiment.CatBoostBorg.load(model_path, descriptor_path)
    np.testing.assert_array_equal(restored.predict(frame), model.predict(frame))
    mutated = frame.copy()
    mutated["label"], mutated["group_key"] = "Borg 10", "unused_person_identifier"
    np.testing.assert_array_equal(restored.predict(mutated), model.predict(frame))
    metrics["model_artifact"] = {"path": model_path.name, "sha256": digest(model_path), "format": "catboost_native_cbm"}
    metrics["model_descriptor"] = {"path": descriptor_path.name, "sha256": digest(descriptor_path)}
    predictions_path = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted,
                  "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(predictions_path, index=False)
    metrics["test_predictions_sha256"] = digest(predictions_path)
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    correct = int(np.sum(predicted == test["label"].to_numpy()))
    print(f"Frozen CatBoost {candidate['id']}: exact test {correct}/179={correct/179:.6f}; >=80% achieved: {correct>=144}", flush=True)


if __name__ == "__main__":
    evaluate()
