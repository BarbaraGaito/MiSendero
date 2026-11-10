"""Independent raw-lineage, report-weight and grouped-fit audit of prior views."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_prior_view_training as training
import fatigue_prior_views as views
from public_sources import RAW, digest


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(selection, frame, train, test, manifest):
    pool, evidence = views.load()
    require(evidence["raw_reports_sha256"] == digest(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
            and evidence["session_metadata_sha256"] == digest(RAW / "geofatigue/session_metadata.json")
            and evidence["canonical_dataset_sha256"] == manifest["dataset_sha256"], "Prior-view raw/canonical sources changed")
    rebuilt, rebuilt_evidence = views.build()
    for key, value in rebuilt_evidence.items():
        require(evidence.get(key) == value, "Prior-view raw lineage or preparation policy changed: "+key)
    require(pool.columns.tolist() == rebuilt.columns.tolist(), "Prior-view schema changed")
    for column in ("view_key", "target_row_key", "group_key", "prefix_only", "label"):
        np.testing.assert_array_equal(pool[column], rebuilt[column])
    np.testing.assert_allclose(pool[evidence["features"]], rebuilt[evidence["features"]], rtol=0, atol=1e-12, equal_nan=True)
    require(len(pool) == evidence["alternative_input_views"] == 6672 and pool["target_row_key"].nunique() == 456
            and int(pool["prefix_only"].sum()) == 1210 and evidence["max_eligible_history_reports"] == 6
            and not set(pool["group_key"]) & set(test["group_key"])
            and set(pool["group_key"]) <= set(train["group_key"]), "Input-view counts or fitting participant scope changed")
    require(evidence["new_observed_targets"] == evidence["synthetic_borg_targets"] == evidence["interpolated_targets"] == evidence["assumed_zero_targets"] == 0
            and not evidence["heldout_person_views_prepared"] and evidence["original_queries_reconstructed"] == 666,
            "Alternative inputs changed observed targets or evaluation cohort")
    for entry in evidence["lineage"]:
        now = pd.Timestamp(entry["prediction_time"])
        require(now-pd.Timedelta(minutes=15) <= pd.Timestamp(entry["oldest_input_time"])
                <= pd.Timestamp(entry["latest_input_time"]) <= now-pd.Timedelta(minutes=1)
                and pd.Timestamp(entry["oldest_input_time"]) >= pd.Timestamp(entry["session_start"]), "Alternative history used future/current/expired/cross-session reports")
    signature = training.fingerprint(manifest, evidence)
    require(all(selection.get(k) == v for k, v in signature.items()) and selection["plan"] == training.plan(manifest)
            and selection["status"] == "complete" and len(selection["results"]) == len(selection["plan"]) == 31
            and selection["train_row_keys"] == train["row_key"].tolist() and not selection["test_used_for_selection"]
            and selection["evaluation_uses_original_complete_history"] and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["evaluation_denominator"] == 487 and selection["test_denominator"] == 179,
            "Frozen input-view training plan, runtime, target queries or test gate changed")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for row in selection["results"]:
        predicted = np.asarray(row["oof_predictions"])
        require(len(predicted) == 487 and set(predicted) <= {f"Borg {i}" for i in range(11)}, "OOF target/denominator changed")
        scores = [accuracy_score(train.iloc[val]["label"], predicted[val]) for _, val in folds]
        np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(float(np.mean(scores))-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train["label"], predicted)-row["pooled_oof_accuracy"]) < 1e-12, "Prior-view exact accuracy differs from predictions")
        candidate = row["candidate"]
        for number, (fit, val) in enumerate(folds):
            saved = row["folds"][number]
            require(saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                    and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist()
                    and saved["unique_actual_targets"] == len(fit)
                    and abs(saved["total_report_weight"]-len(fit)) < 1e-9, "Input-view fitting/evaluation people or report weights changed")
            if candidate["algorithm"] != "control":
                data, weights, keys = training.fitting_views(train.iloc[fit], pool, candidate["view_policy"], candidate["view_mass"])
                require(len(keys) == saved["alternative_input_views"] and len(data) == len(fit)+len(keys)
                        and not set(data["group_key"]) & set(train.iloc[val]["group_key"]), "An alternative view leaked a validation person")
    original = json.loads((training.RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["id"] == "alternative-023")
    control = next(r for r in selection["results"] if r["candidate"]["algorithm"] == "control")
    np.testing.assert_array_equal(control["oof_predictions"], expected)
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"], "Input-view winner was not chosen on original grouped CV")
    for number, (fit, val) in enumerate(folds):
        with threadpool_limits(limits=1):
            refit = training.PriorViewBorg(winner["candidate"]).fit(train.iloc[fit], pool, selection["core_candidate"])
            predicted = refit.predict(train.iloc[val])
        np.testing.assert_array_equal(predicted, np.asarray(winner["oof_predictions"])[val])
        changed = train.iloc[val].copy()
        changed["label"], changed["row_key"], changed["group_key"] = "unavailable_current_target", "unused_query_id", "unused_person_id"
        np.testing.assert_array_equal(predicted, refit.predict(changed))
        if number == 0 and winner["candidate"]["algorithm"] != "control":
            poisoned = pool.copy()
            excluded = ~poisoned["target_row_key"].isin(train.iloc[fit]["row_key"])
            poisoned.loc[excluded, evidence["features"]] = 1e9
            poisoned.loc[excluded, "label"] = "unavailable_validation_target"
            with threadpool_limits(limits=1):
                clean_room = training.PriorViewBorg(winner["candidate"]).fit(train.iloc[fit], poisoned, selection["core_candidate"])
            np.testing.assert_array_equal(clean_room.predict(train.iloc[val]), predicted)
            for actual, same in zip(refit.model.coefs_, clean_room.model.coefs_):
                np.testing.assert_array_equal(actual, same)
        print(f"Observed-history winner independently refitted fold {number+1}/5", flush=True)
    if winner["accuracy_mean"] < .65:
        require(not (training.DIRECTORY / "evaluation/metrics.json").exists(), "Input-view study bypassed its predeclared test gate")
    return {"alternative_input_views": len(pool), "unique_training_targets_with_views": 456, "unique_training_targets_total": 487,
            "new_observed_borg_targets": 0, "heldout_people_used_for_augmentation": False,
            "all_666_original_feature_rows_reconstructed": True, "all_views_reconstructed_from_raw_reports": True,
            "all_report_weight_totals_verified": True, "winner_grouped_folds_refitted": 5,
            "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"],
            "minimum_cv_for_new_test_evaluation": .65, "new_test_gate_passed": winner["accuracy_mean"] >= .65,
            "verification_code_sha256": digest(Path(__file__))}
