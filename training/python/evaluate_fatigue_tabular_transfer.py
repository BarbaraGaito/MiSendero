"""Evaluate the already frozen TabPFN winner once on the original 179 cases.

Built with PriorLabs-TabPFN. Published benchmark reuse is descriptive research.
This script neither selects another candidate from test errors nor changes an
application model. Saved evidence is never overwritten by another run.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
import fatigue_tabular_transfer as transfer
from public_sources import digest


def evaluate():
    transfer.configure_local_runtime()
    transfer.verify_weights()
    frame, train, test, manifest, protocol, sources = transfer.load_inputs()
    path = transfer.DIRECTORY / "selection.json"
    selection = json.loads(path.read_text(encoding="utf-8"))
    if (selection["status"] != "complete" or selection["test_used_for_selection"]
            or selection["code_sha256"] != digest(Path(transfer.__file__)) or selection["sources"] != sources
            or selection["weights_sha256"] != digest(transfer.WEIGHTS)
            or selection["plan"] != transfer.plan(manifest) or selection["train_row_keys"] != train["row_key"].tolist()):
        raise ValueError("TabPFN winner is not frozen with its original fitting inputs")
    best = max(selection["results"], key=lambda r: r["accuracy_mean"])
    if best["candidate"]["id"] != selection["winner_id"]:
        raise ValueError("Winner differs from the completed grouped CV selection")
    destination = transfer.DIRECTORY / "evaluation"
    if destination.exists():
        raise ValueError("Preserve the existing one-time evaluation evidence")
    model = transfer.TabPFNBorg(best["candidate"]).fit(train)
    candidate = best["candidate"]
    predicted = model.predict(test)
    labels = [f"Borg {i}" for i in range(11)]
    validity = {"real_public_ground_truth": True, "native_labels": True, "synthetic_rows": 0,
                "deployment_approved": False, "status": "participant_holdout_with_causal_observed_feedback",
                "reason": "Uses actual prior Borg aged 1-15 minutes. Reused published benchmark: descriptive research, not fresh external confirmation or field approval."}
    metrics = evaluate_training_run(clf=model, dataset_name="Fatiga Borg con TabPFN v2", declared_source=manifest["source"]["source"],
        source_note=validity["reason"], feature_cols=candidate["features"], labels=labels,
        full_features=frame[candidate["features"]], full_labels=frame["label"], x_train=train[candidate["features"]],
        x_test=test[candidate["features"]], y_train=train["label"], y_test=test["label"])
    metrics.update(trained_at=datetime.now(timezone.utc).isoformat(), evaluation_validity=validity,
                   input_contract=manifest["input_contract"], target_accuracy=.8, target_accuracy_achieved=metrics["accuracy"] >= .8,
                   attribution="Built with PriorLabs-TabPFN", license="Apache 2.0 with additional attribution clause 10; original license in docs/fatigue-80-2026-10-25/licenses/TabPFN-LICENSE.txt",
                   model_selection={"winner_id": selection["winner_id"], "candidate_count": len(selection["results"]), "test_used_for_selection": False},
                   hyperparameters=candidate)
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": best["accuracy_mean"], "accuracy_std": best["accuracy_std"]}
    metrics["evaluation_protocol"] = {**protocol, "selection_sha256": digest(path), "sources": sources,
                                      "previous_benchmark_results_are_published": True, "test_used_for_selection": False,
                                      "prior_observed_user_reports_are_inputs": True}
    metrics["evaluation_details"] = holdout_details(train["label"], test["label"], predicted, labels, train["group_key"], test["group_key"])
    metrics["previous_borg_baseline"] = {"strategy": "repeat_previous_observed_Borg", **_summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], labels)}
    destination.mkdir()
    model_path = destination / "TabPFN-v2-model.joblib"
    joblib.dump(model, model_path, compress=3)
    restored = joblib.load(model_path)  # This run's own local fitted model only.
    np.testing.assert_array_equal(restored.predict(frame), model.predict(frame))
    mutated = frame.copy()
    mutated["label"] = "Borg 10"
    np.testing.assert_array_equal(restored.predict(mutated), restored.predict(frame))
    metrics["model_artifact"] = {"path": model_path.name, "sha256": digest(model_path), "trusted_local_training_artifact": True}
    predictions_path = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted,
                  "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(predictions_path, index=False)
    metrics["test_predictions_sha256"] = digest(predictions_path)
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    correct = int(np.sum(predicted == test["label"].to_numpy()))
    print(f"Frozen TabPFN winner {candidate['id']}: exact native test={correct}/179={correct/179:.6f}; target achieved={correct>=144}", flush=True)


if __name__ == "__main__":
    evaluate()
