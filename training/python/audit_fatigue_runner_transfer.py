"""Rebuild runner/native inputs and independently refit frozen source transfer."""
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

import fatigue_runner_transfer as runner
import fatigue_runner_windows as window
from fetch_runner_fatigue_metadata import DIRECTORY as RAW
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(selection):
    frame, train, test, _, _, members, winners, source, states, people, native, evidence = runner.load_inputs()
    signature = runner.fingerprint(members, evidence)
    require(all(selection.get(k) == v for k, v in signature.items())
            and selection["status"] == "complete" and len(selection["results"]) == len(selection["plan"]) == 17
            and selection["plan"] == runner.plan() and selection["encoder_plan"] == runner.encoder_plan()
            and selection["train_row_keys"] == train["row_key"].tolist(), "Frozen runner transfer code, source, plan or cohort changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train["group_key"]) & set(test["group_key"])
            and selection["test_used_for_selection"] is False and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["new_native_borg_targets"] == 0 and not selection["source_protocol_states_are_native_borg_labels"],
            "Source protocol supervision changed the native Borg task or holdout")
    inventory = json.loads((RAW / "inventory.json").read_text())
    receipt = json.loads((RAW / "signals-receipt.json").read_text())
    require(digest(RAW / "signals-receipt.json") == evidence["source_receipt_sha256"]
            and receipt["all_complete_and_verified"] and receipt["expected_files"] == len(receipt["files"]) == 30
            and sum(r["bytes"] for r in receipt["files"]) == receipt["expected_bytes"] == 238626573
            and digest(RAW / "inventory.json") == receipt["inventory_sha256"] == evidence["inventory_sha256"]
            and digest(RAW / "record-11114096.json") == inventory["record_sha256"]
            and set(receipt["fitting_participants"]) == runner.ALLOWED_PEOPLE
            and not set(people) & set(receipt["reserved_participants"]), "Original fitting-only runner inventory or checksums changed")
    require(receipt["download_code_sha256"] == digest(Path(__file__).with_name("fetch_runner_fatigue_signals.py")), "Receiver code changed after publisher verification")
    with np.load(window.DIRECTORY / "source.npz", allow_pickle=False) as data:
        require(set(data.files) == {"windows", "protocol_states", "participants"}, "Unexpected target or identity channel in source tensors")
    with np.load(window.DIRECTORY / "native.npz", allow_pickle=False) as data:
        require(set(data.files) == {"windows", "row_keys"}, "Current native outcomes entered feature tensors")
    rebuilt, rebuilt_states, rebuilt_people, lineage, quality = window.source_windows(receipt)
    np.testing.assert_array_equal(rebuilt, source)
    np.testing.assert_array_equal(rebuilt_states, states)
    np.testing.assert_array_equal(rebuilt_people, people)
    require(lineage == evidence["source_window_lineage"] and quality == evidence["source_file_quality"], "Source clocks, missingness, state routing or window lineage changed")
    rebuilt, keys, lineage, parent_manifest = window.native_windows()
    np.testing.assert_array_equal(rebuilt, native)
    np.testing.assert_array_equal(keys, frame["row_key"].to_numpy(str))
    require(lineage == evidence["native_query_lineage"] and parent_manifest["dataset_sha256"] == evidence["parent_dataset_sha256"]
            and all(r["latest_used_bin_end_ns"] is None or r["latest_used_bin_end_ns"] <= r["prediction_time_ns"] for r in lineage),
            "Native queries use changed inputs or future observations")
    encoders = {}
    for specification in runner.encoder_plan():
        path = runner.DIRECTORY / "encoders" / (specification["id"]+".joblib")
        descriptor = json.loads(path.with_suffix(".json").read_text())
        require(descriptor["signature"] == signature and descriptor["candidate"] == specification
                and digest(path) == descriptor["model_sha256"], "Saved source-only encoder changed")
        saved = joblib.load(path)
        fresh = runner.FrozenRunnerEncoder(specification).fit(source, states, people)
        require(type(saved).__module__ == "fatigue_runner_transfer" and saved.source_summary == fresh.source_summary
                and saved.source_summary["native_borg_targets_used"] == 0, "Source encoder stores another target or cannot reload under its module")
        np.testing.assert_array_equal(saved.loss_endpoints, fresh.loss_endpoints)
        for key, value in fresh.network.state_dict().items():
            require(torch.equal(value, saved.network.state_dict()[key]), "Source protocol network weights failed independent reproduction")
        require(all(not p.requires_grad and p.grad is None for p in saved.network.parameters()), "Source parameters remain trainable")
        np.testing.assert_array_equal(saved.extract(native), fresh.extract(native))
        encoders[specification["id"]] = saved
        print(f"Runner source encoder {specification['id']} independently refitted", flush=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for row in selection["results"]:
        candidate, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(predicted.shape == (487,) and set(predicted) <= {f"Borg {i}" for i in range(11)}, "Native labels or OOF cases changed")
        scores = [accuracy_score(train.iloc[val]["label"], predicted[val]) for _, val in folds]
        np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train["label"], predicted)-row["pooled_oof_accuracy"]) < 1e-12, "Runner transfer score disagrees with original exact-native decisions")
        for number, (fit, val) in enumerate(folds):
            saved = json.loads((runner.DIRECTORY / "folds" / f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == row["folds"][number] and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                    and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "Native runner-transfer fold membership changed")
            np.testing.assert_array_equal(saved["predicted"], predicted[val])
            if "parallel_cache_producer_code_sha256" in saved:
                require(saved["parallel_cache_producer_code_sha256"] == digest(Path(__file__).with_name("precompute_runner_transfer_last_candidate.py")),
                        "Final-recipe parallel cache producer changed")
        if candidate["algorithm"] == "control":
            if candidate["member"] == "cat":
                expected = winners["cat"]["oof_predictions"]
            else:
                original = json.loads((runner.RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
                expected = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["id"] == "alternative-023")
            np.testing.assert_array_equal(predicted, expected)
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"], "Runner winner was not selected by original grouped training CV")
    trained = max((r for r in selection["results"] if r["candidate"]["algorithm"] != "control" and r["candidate"]["encoder"]["epochs"] > 0), key=lambda r: r["accuracy_mean"])
    # Old point controls already reproduce their independently verified OOF
    # decisions. Refit the genuinely new trained representation; include the
    # winner separately only when it is also a new representation recipe.
    recipes = {trained["candidate"]["id"]: trained}
    if winner["candidate"]["algorithm"] != "control":
        recipes[winner["candidate"]["id"]] = winner
    for row in recipes.values():
        candidate = row["candidate"]
        encoder = None if candidate["algorithm"] == "control" else encoders[candidate["encoder"]["id"]]
        before = {} if encoder is None else {k: v.clone() for k, v in encoder.network.state_dict().items()}
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            model = runner.RunnerTransferBorg(candidate, encoder).fit(fitting, native[fitting.index], members["member_specifications"])
            predicted = model.predict(validation, native[validation.index])
            np.testing.assert_array_equal(predicted, np.asarray(row["oof_predictions"])[val])
            require(set(vars(model)) == {"candidate", "encoder", "input_features", "model"}, "Native model stores a query/target history lookup")
            changed = validation.assign(label="unavailable current response", row_key="unused", group_key="unused")
            np.testing.assert_array_equal(model.predict(changed, native[validation.index]), predicted)
            np.testing.assert_array_equal(model.predict(validation[model.input_features], native[validation.index]), predicted)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/"native.joblib"
                joblib.dump(model, path)
                np.testing.assert_array_equal(joblib.load(path).predict(changed, native[validation.index]), predicted)
            if encoder is not None:
                require(all(torch.equal(value, encoder.network.state_dict()[key]) for key, value in before.items()), "Native learning altered source encoder weights")
            print(f"Native runner recipe {candidate['id']} independently refitted fold {number+1}/5", flush=True)
    matched = next(r for r in selection["results"] if r["candidate"]["algorithm"] != "control"
        and r["candidate"]["encoder"]["epochs"] == 0 and r["candidate"]["member"] == trained["candidate"]["member"]
        and r["candidate"]["alpha"] == trained["candidate"]["alpha"])
    if winner["accuracy_mean"] < .65:
        require(not (runner.DIRECTORY / "evaluation/metrics.json").exists(), "Weak source transfer bypassed the frozen test gate")
    return {"publisher_verified_fitting_files": 30, "publisher_verified_bytes": 238626573,
        "source_people": len(set(people)), "source_protocol_windows": len(source), "source_native_borg_targets_used": 0,
        "native_original_queries": 666, "native_training_queries": 487, "native_test_queries": 179,
        "native_queries_with_any_signal": evidence["native_queries_with_any_signal"],
        "all_source_and_native_tensors_reconstructed_from_actual_observations": True,
        "source_encoders_independently_refitted": 5, "all_17_oof_recipes_recomputed": True,
        "historical_point_control_decisions_reproduced": 2,
        "native_recipes_independently_refitted": sorted(recipes),
        "best_source_trained_recipe": trained["candidate"]["id"], "best_source_trained_cv_accuracy": trained["accuracy_mean"],
        "matched_untrained_encoder_control": matched["candidate"]["id"], "matched_untrained_encoder_cv_accuracy": matched["accuracy_mean"],
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"],
        "minimum_cv_for_new_test_evaluation": .65, "new_test_gate_passed": winner["accuracy_mean"] >= .65,
        "verification_code_sha256": digest(Path(__file__))}


def checkpoint():
    folder = ROOT / "docs/fatigue-80-2026-10-25"
    previous = json.loads((folder / "checkpoint.json").read_text())
    gp = json.loads((folder / "gaussian-process-verification.json").read_text())
    require(gp["previous_checkpoint_sha256"] == digest(folder / "checkpoint.json")
            and gp["selection_sha256"] == digest(runner.RESEARCH / "gaussian-process-80-v1/selection.json"), "Previous scoped GP evidence changed")
    for name, row in previous["experiments"].items():
        require(digest(runner.RESEARCH / name / "selection.json") == row["selection_snapshot_sha256"], "Previous frozen selection changed")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous["best_verified_test_accuracy"], "Retained best native test artifact changed")
    path = runner.DIRECTORY / "selection.json"
    verification = validate(json.loads(path.read_text()))
    require(not verification["new_test_gate_passed"], "A source-transfer model passed its CV gate: evaluate and independently verify its saved original-179 test artifact before reporting a new goal score")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(),
        "previous_full_checkpoint_sha256": digest(folder / "checkpoint.json"),
        "previous_gp_verification_sha256": digest(folder / "gaussian-process-verification.json"),
        "selection_sha256": digest(path), "verification": verification,
        "best_verified_test_correct": incumbent["correct"], "best_verified_test_accuracy": incumbent["accuracy"],
        "target_accuracy": .8, "achieved": False,
        "scope": "New runner-source transfer independently verified; earlier verification reports remain historical references and their selection hashes are checked without refitting all old families. The original labels, holdout and retained best test model are revalidated. Source F/NF accuracy is never the native Borg goal score."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = checkpoint()
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
