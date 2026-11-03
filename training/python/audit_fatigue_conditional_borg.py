"""Refit warm sources and verify conditional-native Borg supervision/folds."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_conditional_borg as conditional
from public_sources import digest


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(selection):
    frame, train, test, _, _, pool, extra, inputs, view_winner = conditional.load_inputs()
    signature = conditional.fingerprint(inputs)
    require(all(selection.get(k) == v for k, v in signature.items()) and selection["plan"] == conditional.plan(inputs["specifications"])
            and selection["status"] == "complete" and len(selection["results"]) == len(selection["plan"]) == 36
            and selection["train_row_keys"] == train["row_key"].tolist(), "Conditional study data/code/runtime/initializations/plan changed")
    require(not selection["test_used_for_selection"] and selection["evaluation_denominator"] == len(train) == 487
            and selection["test_denominator"] == len(test) == 179 and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["extra_actual_report_pool"] == len(extra) == 56
            and selection["new_observed_targets"] == selection["synthetic_borg_targets"] == 0,
            "Conditional native study changed outcomes, original queries or test gate")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    rebuilt_sources = {}
    for initialization in ("core", "view"):
        for number, (fit, val) in enumerate(folds):
            fitting = train.iloc[fit]
            path = conditional.DIRECTORY / "sources" / f"{initialization}-fold-{number}.joblib"
            saved = json.loads(path.with_suffix(".json").read_text())
            require(saved["signature"] == signature and saved["model_sha256"] == digest(path)
                    and saved["initialization"] == initialization and saved["fit_row_keys"] == fitting["row_key"].tolist()
                    and not set(fitting["group_key"]) & set(train.iloc[val]["group_key"]), "Conditional source cache changed fitting/validation people")
            cached = joblib.load(path)
            fresh = conditional.make_source(fitting, pool, initialization, inputs["specifications"])
            require(set(cached) == {"initialization", "fit_row_keys", "features", "preprocessor", "classifier", "regularization", "source_input_views"}
                    and cached["initialization"] == fresh["initialization"] and cached["fit_row_keys"] == fresh["fit_row_keys"]
                    and cached["features"] == fresh["features"] and cached["regularization"] == fresh["regularization"]
                    and cached["source_input_views"] == fresh["source_input_views"], "Conditional source retained query data or changed its specification")
            np.testing.assert_array_equal(cached["classifier"].classes_, fresh["classifier"].classes_)
            for field in ("coefs_", "intercepts_"):
                for before, after in zip(getattr(cached["classifier"], field), getattr(fresh["classifier"], field)):
                    np.testing.assert_array_equal(before, after)
            np.testing.assert_array_equal(cached["preprocessor"].transform(frame[fresh["features"]]), fresh["preprocessor"].transform(frame[fresh["features"]]))
            rebuilt_sources[initialization, number] = fresh
        print(f"Conditional source {initialization}: five model/preprocessing states independently refitted", flush=True)
    for row in selection["results"]:
        candidate, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(len(predicted) == 487 and set(predicted) <= {f"Borg {i}" for i in range(11)}, "Conditional OOF labels or denominator changed")
        scores = [accuracy_score(train.iloc[val]["label"], predicted[val]) for _, val in folds]
        np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(float(np.mean(scores))-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train["label"], predicted)-row["pooled_oof_accuracy"]) < 1e-12, "Conditional exact-native score disagrees with its saved predictions")
        for number, (fit, val) in enumerate(folds):
            path = conditional.DIRECTORY / "folds" / f"{candidate['id']}-fold-{number}.json"
            saved = json.loads(path.read_text())
            require(saved == row["folds"][number] and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                    and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "Conditional fold identity or source changed")
            np.testing.assert_array_equal(saved["predicted"], predicted[val])
            source = rebuilt_sources[candidate["initialization"], number]
            expected_summary = {"unique_original_targets": len(fit), "source_input_views": source["source_input_views"],
                                "optimization_input_views": 0, "extra_actual_targets": 0, "extra_report_weight": 0.,
                                "total_supervision_weight": float(len(fit))}
            if candidate["mode"] == "fine_tune":
                data, weights, _, summary = conditional.training_data(train.iloc[fit], pool, extra, candidate["initialization"], candidate["extra_weight"])
                expected_summary.update(summary)
                require(not set(data["group_key"]) & set(train.iloc[val]["group_key"]), "Extra outcomes or history views leaked validation people")
                require(len(saved["loss_endpoints"]) == 2 and np.isfinite(saved["loss_endpoints"]).all(), "Conditional optimizer did not finish a finite likelihood fit")
            require(saved["training_summary"] == expected_summary, "Conditional report counts/weights changed or views inflated measured targets")
    original = json.loads((conditional.RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    original = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["id"] == "alternative-023")
    controls = [r for r in selection["results"] if r["candidate"]["mode"] != "fine_tune"]
    for row in controls:
        if row["candidate"]["mode"] == "point_control":
            expected = original if row["candidate"]["initialization"] == "core" else view_winner["oof_predictions"]
            np.testing.assert_array_equal(row["oof_predictions"], expected)
        for number, (fit, val) in enumerate(folds):
            model = conditional.ConditionalBorg(row["candidate"]).fit(train.iloc[fit], pool, extra, inputs["specifications"], rebuilt_sources[row["candidate"]["initialization"], number])
            np.testing.assert_array_equal(model.predict(train.iloc[val]), np.asarray(row["oof_predictions"])[val])
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"], "Conditional winner was not selected by original grouped training CV")
    for number, (fit, val) in enumerate(folds):
        candidate = winner["candidate"]
        with threadpool_limits(limits=1):
            model = conditional.ConditionalBorg(candidate).fit(train.iloc[fit], pool, extra, inputs["specifications"], rebuilt_sources[candidate["initialization"], number])
            decision = model.predict(train.iloc[val])
        np.testing.assert_array_equal(decision, np.asarray(winner["oof_predictions"])[val])
        require(not any(p.requires_grad or p.grad is not None for p in model.model.parameters()), "Saved population parameters remain trainable at inference")
        require(set(vars(model)) == {"candidate", "features", "preprocessing", "model", "regularization", "loss_endpoints", "iterations", "initialized_new_deltas", "training_summary"},
                "Conditional model stores original targets, people or runtime history")
        changed = train.iloc[val].copy()
        changed["label"], changed["row_key"], changed["group_key"] = "unavailable_current_outcome", "unused", "unused"
        np.testing.assert_array_equal(model.predict(changed), decision)
        np.testing.assert_array_equal(model.predict(train.iloc[val][model.features]), decision)
        if number == 0:
            bad_pool, bad_extra = pool.copy(), extra.copy()
            excluded = ~bad_pool["target_row_key"].isin(train.iloc[fit]["row_key"])
            bad_pool.loc[excluded, model.features], bad_pool.loc[excluded, "label"] = 1e9, "unavailable_validation_outcome"
            excluded = ~bad_extra["group_key"].isin(set(train.iloc[fit]["group_key"]))
            bad_extra.loc[excluded, model.features], bad_extra.loc[excluded, "label"] = 1e9, "unavailable_validation_outcome"
            with threadpool_limits(limits=1):
                clean_room = conditional.ConditionalBorg(candidate).fit(train.iloc[fit], bad_pool, bad_extra, inputs["specifications"])
            np.testing.assert_array_equal(clean_room.predict(train.iloc[val]), decision)
            for key, tensor in model.model.state_dict().items():
                require(torch.equal(tensor, clean_room.model.state_dict()[key]), "Excluded-view or extra-person outcomes changed conditional model weights")
        print(f"Conditional native winner independently reproduced fold {number+1}/5", flush=True)
    if winner["accuracy_mean"] < .65:
        require(not (conditional.DIRECTORY / "evaluation/metrics.json").exists(), "Conditional study bypassed its predeclared held-out gate")
    return {"warm_sources_refitted": 10, "source_model_and_preprocessing_values_reproduced": True,
            "original_point_controls_reproduced": 2, "inference_condition_only_controls_reproduced": 2,
            "native_training_cases": 487, "native_test_cases": 179, "extra_actual_report_pool": 56,
            "all_fold_extra_person_filters_and_report_weights_verified": True, "winner_grouped_folds_refitted": 5,
            "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"],
            "minimum_cv_for_new_test_evaluation": .65, "new_test_gate_passed": winner["accuracy_mean"] >= .65,
            "verification_code_sha256": digest(Path(__file__))}
