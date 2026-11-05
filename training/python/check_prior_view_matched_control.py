"""Post-selection diagnostic: same winner hyperparameters, no input views.

This control was not in the original 31-recipe search. It cannot be silently
substituted into that frozen plan or counted as held-out confirmation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from fatigue_dynamics import load_inputs
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_prior_view_training import DIRECTORY
from public_sources import digest


def check():
    _, train, _, manifest, _ = load_inputs()
    selection_path = DIRECTORY / "selection.json"
    selection = json.loads(selection_path.read_text())
    if selection["status"] != "complete":
        raise ValueError("Freeze the original input-view selection first")
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    specification = winner["candidate"]
    if specification["algorithm"] == "control":
        raise ValueError("The original control already won; another matched fit is unnecessary")
    candidate = {"algorithm": "mlp", **{k: specification[k] for k in ("features", "params", "target_mode")}}
    signature = {"code_sha256": digest(Path(__file__)), "selection_sha256": digest(selection_path),
                 "dataset_sha256": manifest["dataset_sha256"], "classifier_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py")),
                 "candidate": candidate, "original_selected_candidate": specification, "train_row_keys": train["row_key"].tolist(),
                 "minimum_cv_for_new_test_evaluation": .65}
    path = DIRECTORY / "matched-control.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if any(saved.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the completed post-selection diagnostic before changing it")
        print(f"Verified frozen matched-control result CV={saved['accuracy_mean']:.6f}", flush=True)
        return
    predicted, evidence = np.empty(len(train), dtype=object), []
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for number, (fit, val) in enumerate(folds):
        if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
            raise ValueError("Matched diagnostic leaked participants")
        with threadpool_limits(limits=1):
            model = DynamicsClassifier(candidate).fit(train.iloc[fit])
            predicted[val] = model.predict(train.iloc[val])
        evidence.append({"fit_row_keys": train.iloc[fit]["row_key"].tolist(), "validation_row_keys": train.iloc[val]["row_key"].tolist()})
        print(f"Matched no-view control fold {number+1}/5", flush=True)
    scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
    view_prediction, truth = np.asarray(winner["oof_predictions"]), train["label"].to_numpy()
    result = {**signature, "version": 1, "post_selection_diagnostic": True, "part_of_original_31_recipe_selection": False,
              "test_used_for_selection": False, "original_query_denominator": 487, "test_denominator": 179,
              "new_observed_targets": 0, "alternative_input_views": 0, "folds": evidence,
              "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
              "pooled_oof_accuracy": float(accuracy_score(truth, predicted)), "oof_predictions": predicted.tolist(),
              "selected_view_cv_accuracy": winner["accuracy_mean"],
              "view_minus_matched_control_cv": winner["accuracy_mean"]-float(np.mean(scores)),
              "view_fixes_matched_control_errors": int(((view_prediction == truth) & (predicted != truth)).sum()),
              "view_spoils_matched_control_correct": int(((view_prediction != truth) & (predicted == truth)).sum()),
              "deployment_approved": False}
    path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Matched control CV={np.mean(scores):.6f}; selected view model CV={winner['accuracy_mean']:.6f}; held-out test untouched", flush=True)


if __name__ == "__main__":
    check()
