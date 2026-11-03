"""Verify actual-prior anchors and independently reproduce paired native CV."""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_runner_anchor_transfer as paired
import fatigue_runner_anchor_windows as anchors
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate():
    folder = ROOT / "docs/fatigue-80-2026-10-25"
    parent_path = folder / "runner-transfer-verification.json"
    parent_report = json.loads(parent_path.read_text())
    require(parent_report["selection_sha256"] == digest(paired.parent.DIRECTORY / "selection.json")
            and parent_report["verification"]["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_runner_transfer.py")),
            "Verified source-only parent evidence changed")
    frame, train, test, members, window_manifest, current, reference, manifest, previous = paired.load_inputs()
    selection_path = paired.DIRECTORY / "selection.json"
    selection = json.loads(selection_path.read_text())
    signature = paired.fingerprint(members, window_manifest)
    require(all(selection.get(k) == v for k, v in signature.items()) and selection["status"] == "complete"
            and selection["plan"] == paired.plan(previous) and len(selection["results"]) == 8
            and selection["train_row_keys"] == train["row_key"].tolist(), "Frozen paired-input source, code, plan or cases changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train["group_key"]) & set(test["group_key"])
            and not selection["test_used_for_selection"] and selection["new_native_borg_targets"] == 0
            and selection["minimum_cv_for_new_test_evaluation"] == .65, "Paired experiment changed the original target/holdout/gate")
    rebuilt, keys, lineage, native_manifest = anchors.build()
    np.testing.assert_array_equal(rebuilt, reference)
    np.testing.assert_array_equal(keys, frame["row_key"].to_numpy(str))
    require(lineage == manifest["lineage"] and native_manifest["dataset_sha256"] == manifest["parent_dataset_sha256"]
            and all(r["actual_prior_report_time_ns"] <= r["prediction_time_ns"]-60_000_000_000
                    and (r["latest_anchor_bin_end_ns"] is None or r["latest_anchor_bin_end_ns"] <= r["actual_prior_report_time_ns"]) for r in lineage),
            "Reference clock or sensor window is not an actual eligible past observation")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for row in selection["results"]:
        c, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(predicted.shape == (487,) and set(predicted) <= {f"Borg {i}" for i in range(11)}, "Paired predictions changed native cases or labels")
        scores = [accuracy_score(train.iloc[val]["label"], predicted[val]) for _, val in folds]
        np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train["label"], predicted)-row["pooled_oof_accuracy"]) < 1e-12, "Paired metrics disagree with exact native predictions")
        if c["algorithm"] == "parent_control":
            inherited = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            np.testing.assert_array_equal(predicted, inherited["oof_predictions"])
            continue
        for number, (fit, val) in enumerate(folds):
            saved = json.loads((paired.DIRECTORY / "folds" / f"{c['id']}-fold-{number}.json").read_text())
            require(saved == row["folds"][number] and saved["signature"] == signature and saved["candidate"] == c
                    and saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                    and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "Paired native fold membership changed")
            np.testing.assert_array_equal(saved["predicted"], predicted[val])
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"], "Paired winner was not selected on original training CV")
    best = max((r for r in selection["results"] if r["candidate"]["algorithm"] != "parent_control"), key=lambda r: r["accuracy_mean"])
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    c = best["candidate"]
    path = paired.parent.DIRECTORY / "encoders" / (c["encoder"]["id"]+".joblib")
    descriptor = json.loads(path.with_suffix(".json").read_text())
    require(descriptor["model_sha256"] == digest(path) and descriptor["candidate"] == c["encoder"]
            and descriptor["signature"] == signature["parent_fingerprint"], "Frozen source encoder changed")
    encoder = joblib.load(path)
    before = {k: v.clone() for k, v in encoder.network.state_dict().items()}
    for number, (fit, val) in enumerate(folds):
        fitting, validation = train.iloc[fit], train.iloc[val]
        model = paired.AnchoredRunnerBorg(c, encoder).fit(fitting, current[fitting.index], reference[fitting.index], members["member_specifications"])
        predicted = model.predict(validation, current[validation.index], reference[validation.index])
        np.testing.assert_array_equal(predicted, np.asarray(best["oof_predictions"])[val])
        require(set(vars(model)) == {"candidate", "encoder", "input_features", "model"}, "Paired model stores query/label lookup state")
        changed = validation.assign(label="unknown current response", row_key="unused", group_key="unused")
        np.testing.assert_array_equal(model.predict(changed, current[validation.index], reference[validation.index]), predicted)
        np.testing.assert_array_equal(model.predict(validation[model.input_features], current[validation.index], reference[validation.index]), predicted)
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)/"paired.joblib"
            joblib.dump(model, temporary)
            np.testing.assert_array_equal(joblib.load(temporary).predict(changed, current[validation.index], reference[validation.index]), predicted)
        require(all(torch.equal(value, encoder.network.state_dict()[key]) for key, value in before.items())
                and all(not p.requires_grad and p.grad is None for p in encoder.network.parameters()), "Native fitting changed source parameters")
        print(f"Best paired-input native model independently refitted fold {number+1}/5", flush=True)
    if winner["accuracy_mean"] < .65:
        require(not (paired.DIRECTORY / "evaluation/metrics.json").exists(), "Weak paired selection bypassed its frozen test gate")
    else:
        raise ValueError("Verify a frozen original-179 test artifact before reporting a new goal score")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == parent_report["best_verified_test_accuracy"], "Retained original test artifact changed")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(),
        "source_parent_verification_sha256": digest(parent_path), "selection_sha256": digest(selection_path),
        "verification_code_sha256": digest(Path(__file__)), "prior_sensor_windows_independently_reconstructed": 666,
        "both_windows_with_observations": manifest["both_windows_with_any_signal"], "original_training_cases": 487, "original_test_cases": 179,
        "all_8_oof_recipes_recomputed": True, "inherited_point_controls_reproduced": 2,
        "best_new_paired_recipe_id": c["id"], "best_new_paired_cv_accuracy": best["accuracy_mean"],
        "best_new_paired_grouped_folds_refitted": 5, "source_weights_remain_frozen": True,
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"], "new_test_gate_passed": False,
        "best_verified_test_correct": incumbent["correct"], "best_verified_test_accuracy": incumbent["accuracy"],
        "target_accuracy": .8, "achieved": False,
        "scope": "Exact native Borg on the same original cases. Earlier source fitting is referenced through its unchanged independent verification. All prior sensor windows and the best new paired learner are rebuilt. No source protocol accuracy or subset accuracy is the native goal score."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
