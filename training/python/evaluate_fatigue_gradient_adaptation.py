"""One-time original holdout evaluation of the frozen personal-MAML winner."""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
import fatigue_gradient_adaptation as experiment
from public_sources import digest


class RuntimeHistoryView:
    """Evaluation adapter only; the runtime history is never serialized."""
    def __init__(self, model, pool, contexts):
        self.model, self.pool, self.contexts = model, pool, contexts

    def predict(self, queries):
        return self.model.predict(queries, self.pool, self.contexts)


def evaluate():
    frame, train, test, manifest, protocol = experiment.load_inputs()
    histories = experiment.load_contexts(frame, manifest)
    selection_path = experiment.DIRECTORY / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    signature = experiment.fingerprint(manifest, histories)
    if (selection["status"] != "complete" or selection["test_used_for_selection"]
            or any(selection.get(k) != v for k, v in signature.items())
            or selection["plan"] != experiment.plan(manifest)
            or selection["train_row_keys"] != train["row_key"].tolist()):
        raise ValueError("Personal MAML selection incomplete or frozen inputs changed")
    frozen = json.loads((experiment.DIRECTORY / "frozen-plan.json").read_text())
    if any(frozen.get(k) != v for k, v in {**signature, "plan": selection["plan"], "train_row_keys": train["row_key"].tolist()}.items()):
        raise ValueError("MAML plan changed after its snapshot")
    if digest(experiment.DIRECTORY / "selection-source.py") != selection["code_sha256"]:
        raise ValueError("MAML source snapshot changed")
    best = max(selection["results"], key=lambda row: row["accuracy_mean"])
    candidate = best["candidate"]
    if candidate["id"] != selection["winner_id"]:
        raise ValueError("Personal MAML winner differs from frozen CV")
    destination = experiment.DIRECTORY / "evaluation"
    if destination.exists():
        raise ValueError("Preserve the existing one-time MAML evaluation")
    context = histories[candidate["scope"]]
    model = experiment.GradientAdaptiveBorg(candidate).fit(train, context)
    population = {name: value.detach().clone() for name, value in model.model.named_parameters()}
    view = RuntimeHistoryView(model, frame, context)
    predicted = view.predict(test)
    labels = [f"Borg {i}" for i in range(11)]
    validity = {"real_public_ground_truth": True, "native_labels": True, "synthetic_rows": 0, "deployment_approved": False,
                "status": "population_participant_holdout_with_causal_runtime_personal_SGD",
                "reason": "Population weights fit only the original 28 fitting people. At each query, functional SGD may use actual earlier same-person reports as authorized runtime calibration; current/future reports are excluded. Original 179 cases and native Borg remain unchanged. Reused published benchmark: descriptive research, not fresh independent or field confirmation."}
    metrics = evaluate_training_run(clf=view, dataset_name="Fatiga Borg con adaptación MAML causal",
        declared_source=manifest["source"]["source"], source_note=validity["reason"], feature_cols=candidate["features"], labels=labels,
        full_features=frame[candidate["features"]], full_labels=frame["label"], x_train=train, x_test=test,
        y_train=train["label"], y_test=test["label"])
    metrics.update(trained_at=datetime.now(timezone.utc).isoformat(), evaluation_validity=validity,
                   target_accuracy=.8, target_accuracy_achieved=metrics["accuracy"] >= .8,
                   input_contract={**manifest["input_contract"], "feature_order": candidate["features"],
                       "runtime_actual_earlier_report_features_required": candidate["features"],
                       "runtime_history_scope": candidate["scope"], "minimum_history_age_minutes": 1,
                       "exact_task_boundaries_required": candidate["scope"] == "task", "current_or_future_borg_required": False,
                       "metadata_for_history_lookup_only": ["row_key", "group_key", "session_start", "task_start", "response_time"]},
                   hyperparameters=candidate,
                   model_selection={"winner_id": candidate["id"], "candidate_count": len(selection["results"]), "test_used_for_selection": False},
                   software_versions=signature["software_versions"], runtime_history_serialized_in_model=False)
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": best["accuracy_mean"], "accuracy_std": float(np.std(best["fold_accuracy"]))}
    metrics["evaluation_protocol"] = {**protocol, "selection_sha256": digest(selection_path),
        "previous_benchmark_results_are_published": True, "test_used_for_selection": False,
        "population_weights_exclude_test_participants": True, "earlier_observed_test_person_reports_are_runtime_inputs": True}
    metrics["evaluation_details"] = holdout_details(train["label"], test["label"], predicted, labels, train["group_key"], test["group_key"])
    metrics["previous_borg_baseline"] = {"strategy": "repeat_previous_observed_Borg", **_summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], labels)}
    # Deliberately corrupt every unavailable label/feature for deterministic
    # test queries. Their selected earlier support remains the only pool read.
    for i in range(min(8, len(test))):
        query = test.iloc[[i]].drop(columns="label")
        allowed = {r["row_key"] for r in context[query.iloc[0]["row_key"]]}
        changed = frame.copy().astype({"prior_borg": float})
        unavailable = ~changed["row_key"].isin(allowed)
        changed.loc[unavailable, "label"] = "unavailable_current_or_future_outcome"
        changed.loc[unavailable, "prior_borg"] = np.inf
        np.testing.assert_array_equal(model.predict(query, frame, context), model.predict(query, changed, context))
    if any(not torch.equal(population[name], value) for name, value in model.model.named_parameters()):
        raise ValueError("Runtime calibration changed the population weights")
    destination.mkdir()
    model_path = destination / "model.joblib"
    joblib.dump(model, model_path)
    restored = joblib.load(model_path)
    np.testing.assert_array_equal(restored.predict(frame, frame, context), model.predict(frame, frame, context))
    changed_queries = frame.copy()
    changed_queries["label"] = "unavailable_query_target"
    np.testing.assert_array_equal(restored.predict(changed_queries, frame, context), model.predict(frame, frame, context))
    metrics["model_artifact"] = {"path": model_path.name, "sha256": digest(model_path), "format": "joblib_own_sha_pinned_global_model_no_runtime_history"}
    output = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted,
                  "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(output, index=False)
    metrics["test_predictions_sha256"] = digest(output)
    metrics["causality_checks"] = {"unavailable_current_future_pool_rows_corrupted_for_test_queries": 8,
                                    "population_weights_unchanged": True, "all_666_reloaded_predictions_match": True}
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    correct = int(np.sum(predicted == test["label"].to_numpy()))
    print(f"Frozen MAML {candidate['id']}: exact original test {correct}/179={correct/179:.6f}; >=80% achieved: {correct>=144}", flush=True)


if __name__ == "__main__":
    evaluate()
