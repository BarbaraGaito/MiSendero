"""Evaluate the frozen source-transfer winner once on all original test cases."""
import importlib.metadata
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
import fatigue_gait_transfer as experiment
from public_sources import digest


def evaluate():
    frame, train, test, manifest, protocol, source, source_manifest = experiment.load_inputs()
    path = experiment.DIRECTORY / "selection.json"
    selection = json.loads(path.read_text(encoding="utf-8"))
    signature = experiment.fingerprint(manifest, source_manifest)
    if (selection["status"] != "complete" or selection["test_used_for_selection"]
            or any(selection.get(k) != v for k, v in signature.items())
            or selection["plan"] != experiment.plan(manifest)
            or selection["train_row_keys"] != train["row_key"].tolist()):
        raise ValueError("Source-transfer search incomplete or frozen inputs changed")
    best = max(selection["results"], key=lambda row: row["accuracy_mean"])
    candidate = best["candidate"]
    if candidate["id"] != selection["winner_id"]:
        raise ValueError("Source-transfer winner changed after frozen CV")
    controls = [r["accuracy_mean"] for r in selection["results"] if r["candidate"]["teacher"] is None]
    if candidate["teacher"] is None or best["accuracy_mean"] <= max(controls):
        raise ValueError("No new source-transfer winner improved its original controls")
    destination = experiment.DIRECTORY / "evaluation"
    if destination.exists():
        raise ValueError("Preserve the existing one-time source-transfer evaluation")
    with threadpool_limits(limits=1):
        model = experiment.GaitTransferBorg(candidate, source).fit(train)
    # Keep the fitted source estimator, not its source rows/labels/identifiers.
    model.source = None
    raw_features = list(dict.fromkeys([c for c in candidate["features"] if c not in experiment.TEACHER_COLUMNS]
                                     + candidate["teacher"]["features"]))
    labels = [f"Borg {i}" for i in range(11)]
    predicted = model.predict(test)
    validity = {"real_public_ground_truth": True, "native_labels": True, "synthetic_rows": 0, "deployment_approved": False,
                "status": "participant_holdout_with_actual_prior_borg_and_source_only_transfer",
                "reason": "Exact original momentary Borg with real earlier user feedback. Six-minute-walk post-test CR10 trains only an external auxiliary estimator on 48 people; 12 external people stay reserved. The original published benchmark has been reused: descriptive research, not fresh external confirmation."}
    metrics = evaluate_training_run(clf=model, dataset_name="Fatiga Borg con transferencia auxiliar de caminatas",
        declared_source=manifest["source"]["source"], source_note=validity["reason"], feature_cols=raw_features, labels=labels,
        full_features=frame[raw_features], full_labels=frame["label"], x_train=train[raw_features], x_test=test[raw_features],
        y_train=train["label"], y_test=test["label"])
    metrics.update(trained_at=datetime.now(timezone.utc).isoformat(), evaluation_validity=validity,
                   target_accuracy=.8, target_accuracy_achieved=metrics["accuracy"] >= .8,
                   input_contract={**manifest["input_contract"], "feature_order": raw_features,
                                   "generated_auxiliary_features": experiment.TEACHER_COLUMNS,
                                   "student_feature_order": candidate["features"], "observed_current_borg_required": False},
                   model_selection={"winner_id": candidate["id"], "candidate_count": len(selection["results"]), "test_used_for_selection": False},
                   hyperparameters=candidate, external_source={"provenance_sha256": signature["source_provenance_sha256"],
                       "fitting_reports": 48, "reserved_reports": 12, "reserved_reports_used": False,
                       "original_momentary_targets_added": 0},
                   software_versions={p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn", "joblib")})
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": best["accuracy_mean"], "accuracy_std": float(np.std(best["fold_accuracy"]))}
    metrics["evaluation_protocol"] = {**protocol, "selection_sha256": digest(path), "previous_benchmark_results_are_published": True,
                                      "test_used_for_selection": False, "prior_observed_user_reports_are_inputs": True}
    metrics["evaluation_details"] = holdout_details(train["label"], test["label"], predicted, labels, train["group_key"], test["group_key"])
    metrics["previous_borg_baseline"] = {"strategy": "repeat_previous_observed_Borg", **_summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], labels)}
    destination.mkdir()
    model_path = destination / "model.joblib"
    joblib.dump(model, model_path)
    restored = joblib.load(model_path)
    np.testing.assert_array_equal(restored.predict(frame), model.predict(frame))
    np.testing.assert_array_equal(restored.predict(frame[raw_features]), model.predict(frame))
    changed = frame.copy()
    changed["label"], changed["group_key"] = "Borg 10", "unused_identifier"
    np.testing.assert_array_equal(restored.predict(changed), model.predict(frame))
    metrics["model_artifact"] = {"path": model_path.name, "sha256": digest(model_path), "format": "joblib_own_sha_pinned_model"}
    output = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted,
                  "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(output, index=False)
    metrics["test_predictions_sha256"] = digest(output)
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    correct = int(np.sum(predicted == test["label"].to_numpy()))
    print(f"Frozen gait transfer {candidate['id']}: exact test {correct}/179={correct/179:.6f}; >=80% achieved: {correct>=144}", flush=True)


if __name__ == "__main__":
    evaluate()
