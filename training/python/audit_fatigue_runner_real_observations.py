"""Rebuild public inputs and refit unaugmented source/native transfer."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_runner_real_observations as study
import fatigue_runner_windows as window
from fetch_runner_fatigue_metadata import DIRECTORY as RAW
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    previous_path = folder/"source-transition-verification.json"
    previous = json.loads(previous_path.read_text())
    require(previous["selection_sha256"] == digest(study.PARENT)
            and previous["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_source_transitions.py")), "Previous real-public evidence changed")
    inputs = study.load_inputs()
    frame, train, test, members, source, states, people, native, evidence = inputs
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(all(selection.get(k) == v for k, v in signature.items()) and selection["status"] == "complete"
            and selection["plan"] == study.plan() and selection["encoder_plan"] == study.encoder_plan()
            and len(selection["results"]) == 17 and selection["train_row_keys"] == train.row_key.tolist(), "Frozen real-public study changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train.group_key) & set(test.group_key) and not selection["test_used_for_selection"]
            and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == 0
            and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["artificial_input_masking"] is False and selection["artificial_history_views"] is False
            and selection["source_protocol_states_are_native_borg_labels"] is False, "Task, real-data policy or original cases changed")
    receipt = json.loads((RAW/"signals-receipt.json").read_text())
    require(digest(RAW/"signals-receipt.json") == evidence["source_receipt_sha256"]
            and receipt["all_complete_and_verified"] and receipt["expected_files"] == len(receipt["files"]) == 30
            and set(receipt["fitting_participants"]) == study.helpers.ALLOWED_PEOPLE
            and not set(people) & set(receipt["reserved_participants"]), "Public raw fitting-only runner receipt changed")
    # Reconstruct observed bins from the public files, without running any
    # archived masked-input model fitter or history-view preparation.
    rebuilt, rebuilt_states, rebuilt_people, lineage, quality = window.source_windows(receipt)
    np.testing.assert_array_equal(rebuilt, source)
    np.testing.assert_array_equal(rebuilt_states, states)
    np.testing.assert_array_equal(rebuilt_people, people)
    require(lineage == evidence["source_window_lineage"] and quality == evidence["source_file_quality"], "Real source window clocks, masks or public lineage changed")
    rebuilt, keys, lineage, native_manifest = window.native_windows()
    np.testing.assert_array_equal(rebuilt, native)
    np.testing.assert_array_equal(keys, frame.row_key.to_numpy(str))
    require(lineage == evidence["native_query_lineage"] and native_manifest["dataset_sha256"] == evidence["parent_dataset_sha256"]
            and all(r["latest_used_bin_end_ns"] is None or r["latest_used_bin_end_ns"] <= r["prediction_time_ns"] for r in lineage), "Causal native real windows or original cases changed")
    encoders, batch_counts = {}, {}
    source_before = hashlib.sha256(source.tobytes()).hexdigest()
    for c in study.encoder_plan():
        model_path = study.DIRECTORY/"encoders"/(c["id"]+".joblib")
        descriptor = json.loads(model_path.with_suffix(".json").read_text())
        require(descriptor["signature"] == signature and descriptor["candidate"] == c
                and descriptor["model_sha256"] == digest(model_path), "Saved real-source encoder changed")
        saved = joblib.load(model_path)
        visits, batches = {}, []
        def observe(epoch, indexes, batch, labels):
            np.testing.assert_array_equal(batch, source[indexes])
            np.testing.assert_array_equal(labels, states[indexes])
            visits.setdefault(epoch, []).extend(indexes.tolist())
            batches.append(len(indexes))
        with patch("torch.rand", side_effect=AssertionError("Artificial input masking is prohibited")), patch.object(study.helpers.FrozenRunnerEncoder, "fit", side_effect=AssertionError("Archived masked-input fitting prohibited")):
            fresh = study.RealRunnerEncoder(c).fit(source, states, people, observe)
        require(len(visits) == c["epochs"] and all(sorted(rows) == list(range(330)) for rows in visits.values()), "Source fitting lost or fabricated observations")
        require(type(saved).__module__ == "fatigue_runner_real_observations" and type(saved) is study.RealRunnerEncoder
                and saved.source_summary == fresh.source_summary == descriptor["source_summary"]
                and saved.source_summary["native_borg_targets_used"] == 0
                and saved.source_summary["artificial_sensor_rows"] == 0 and not saved.source_summary["source_input_masking"], "Source-only real fitting cannot be reproduced")
        np.testing.assert_array_equal(saved.loss_endpoints, fresh.loss_endpoints)
        for key, value in fresh.network.state_dict().items():
            require(torch.equal(value, saved.network.state_dict()[key]), "Fresh no-augmentation weights differ")
        np.testing.assert_array_equal(saved.extract(native), fresh.extract(native))
        require(hashlib.sha256(source.tobytes()).hexdigest() == source_before, "Source fitting mutated the measured public input cache")
        batch_counts[c["id"]] = {"verified_unmodified_batches": len(batches), "verified_actual_window_visits": sum(batches)}
        encoders[c["id"]] = saved
        print(f"Fresh real-only source encoder {c['id']}: {len(batches)} unchanged public batches", flush=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    previous_selection = json.loads(study.PARENT.read_text())
    for row in selection["results"]:
        c, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(predicted.shape == (487,) and set(predicted) <= {f"Borg {i}" for i in range(11)}, "Native predictions or denominator changed")
        scores = [accuracy_score(train.iloc[val].label, predicted[val]) for _, val in folds]
        np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train.label, predicted)-row["pooled_oof_accuracy"]) < 1e-12, "Metrics disagree with original real native targets")
        if c["algorithm"] == "parent_control":
            old = next(r for r in previous_selection["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            np.testing.assert_array_equal(predicted, old["oof_predictions"])
            continue
        for number, (fit, val) in enumerate(folds):
            saved = json.loads((study.DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json").read_text())
            require(saved == row["folds"][number] and saved["signature"] == signature and saved["candidate"] == c
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(), "Concurrent real-only native fold membership changed")
            np.testing.assert_array_equal(saved["predicted"], predicted[val])
    winner = max(selection["results"], key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"], "Winner differs from declared participant CV rule")
    learned = {c["id"] for c in study.encoder_plan() if c["epochs"] > 0}
    best = max((r for r in selection["results"] if r["candidate"].get("encoder_id") in learned), key=lambda r:r["accuracy_mean"])
    match = next(r for r in selection["results"] if r["candidate"].get("encoder_id") == study.encoder_plan()[0]["id"]
        and r["candidate"].get("member") == best["candidate"]["member"] and r["candidate"].get("alpha") == best["candidate"]["alpha"])
    for row in (best, match):
        c = row["candidate"]
        encoder = encoders[c["encoder_id"]]
        before = {key:value.clone() for key,value in encoder.network.state_dict().items()}
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            require(not set(fitting.group_key) & set(validation.group_key), "Native fitting people leak into validation")
            native_class = study.helpers.DynamicsClassifier if c["member"] == "core" else study.helpers.CatBoostBorg
            original_fit = native_class.fit
            def real_reports_only(estimator, data):
                np.testing.assert_array_equal(data.row_key, fitting.row_key)
                np.testing.assert_array_equal(data.group_key, fitting.group_key)
                np.testing.assert_array_equal(data.label, fitting.label)
                pd.testing.assert_frame_equal(data[model_features], fitting[model_features])
                return original_fit(estimator, data)
            model_features = members["member_specifications"][c["member"]]["features"]
            with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial history examples prohibited")), patch.object(native_class, "fit", real_reports_only):
                model = study.RealRunnerBorg(c, encoder).fit(fitting, native[fitting.index], members["member_specifications"])
            predicted = model.predict(validation, native[validation.index])
            np.testing.assert_array_equal(predicted, np.asarray(row["oof_predictions"])[val])
            np.testing.assert_array_equal(model.predict(validation[model.input_features], native[validation.index]), predicted)
            without_truth = validation.drop(columns=["label", "row_key", "group_key"])
            np.testing.assert_array_equal(model.predict(without_truth, native[validation.index]), predicted)
            require(set(vars(model)) == {"candidate", "encoder", "input_features", "model"}
                    and all(torch.equal(value, encoder.network.state_dict()[key]) for key,value in before.items()), "Native fitting changed source weights or stored a query lookup")
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/"real-only.joblib"
                joblib.dump(model, output)
                np.testing.assert_array_equal(joblib.load(output).predict(without_truth, native[validation.index]), predicted)
            print(f"Independent real-only native refit {c['id']}: fold {number+1}/5", flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A real-only source model crossed its gate: freeze, evaluate and independently verify its complete original-179 artifact")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous["best_verified_test_accuracy"], "Retained original real-report native test model changed")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(),
        "parent_verification_sha256": digest(previous_path), "selection_sha256": digest(path), "verification_code_sha256": digest(Path(__file__)),
        "public_real_data_policy_sha256": digest(study.POLICY),
        "real_public_source_windows_reconstructed": 330, "real_native_causal_windows_reconstructed": 666,
        "source_encoders_independently_refitted": 5, "source_batch_verification": batch_counts,
        "artificial_input_masking_disabled_during_source_refits": True, "original_native_fitting_reports_and_labels_checked": True,
        "all_17_oof_recipes_recomputed": True, "inherited_controls_reproduced": 2,
        "best_new_source_trained_id": best["candidate"]["id"], "best_new_source_trained_cv_accuracy": best["accuracy_mean"],
        "matched_untrained_encoder_id": match["candidate"]["id"], "matched_untrained_encoder_cv_accuracy": match["accuracy_mean"],
        "native_recipes_independently_refitted": [best["candidate"]["id"], match["candidate"]["id"]], "grouped_folds_per_native_refit": 5,
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"], "new_test_gate_passed": False,
        "original_training_cases": 487, "original_test_cases": 179, "best_verified_test_correct": incumbent["correct"],
        "best_verified_test_accuracy": incumbent["accuracy"], "target_accuracy": .8, "achieved": False,
        "scope": "Only actual public observations and original participant-held native Borg. Every source training batch is checked against its original unmodified input rows; source F/NF is auxiliary protocol supervision, never new observed Borg. No archived augmented-input fitter is executed."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
