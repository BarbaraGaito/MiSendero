"""Verify original report pairs and refit source-conditioned Borg teachers."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_source_transitions as study
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    policy_path = folder/"public-real-data-policy.json"
    policy = json.loads(policy_path.read_text())
    require(policy["applies_to_all_further_fitting_and_model_selection"]
            and policy["active_study"]["artificial_history_views_used_for_fitting"] is False, "Public real-data constraint changed")
    previous_path = folder/"initialization-ensemble-verification.json"
    previous = json.loads(previous_path.read_text())
    from fatigue_initialization_ensemble import DIRECTORY as initialization_directory
    require(previous["selection_sha256"] == digest(initialization_directory/"selection.json")
            and previous["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_initialization_ensemble.py")), "Previous verified evidence changed")
    inputs = study.load_inputs()
    frame, train, test, manifest, sources, provenance = inputs
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(all(selection.get(k) == v for k, v in study.fingerprint(inputs).items())
            and selection["status"] == "complete" and selection["plan"] == study.plan()
            and len(selection["results"]) == 10 and selection["train_row_keys"] == train.row_key.tolist(), "Frozen transition study changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train.group_key) & set(test.group_key) and selection["new_native_borg_targets"] == 0
            and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65, "Native target or holdout changed")
    originals, manifests, splits = study.source_inputs()
    require(len(sources) == provenance["actual_transition_targets"] == 249
            and sources.row_key.is_unique and sources.source_domain.value_counts().to_dict() == {"worker": 200, "sts": 49}
            and provenance["invented_worker_report_timestamps"] == provenance["synthetic_targets"] == provenance["interpolated_targets"] == 0
            and provenance["native_target_merge"] is False, "Source transition counts, timing policy or native-label isolation changed")
    require(set(sources.columns) == {"source_domain", "row_key", "prior_row_key", "group_key", "prior_borg", "borg_native", "hr_last", "hr_history_mean"}, "Source table contains assumed survey times or extra inputs")
    for name in ("worker", "sts"):
        original = originals[name].set_index("row_key", drop=False)
        lineage = {r["row_key"]: r for r in manifests[name]["lineage"]}
        accepted = set()
        # Independently enumerate expected pairs from the original lineage.
        for key, current in original.iterrows():
            record = lineage[key]
            if name == "worker":
                rep = int(re.search(r"\[REP ([1-5])\]", record["questionnaire_column"])[1])
                candidates = [old for old in lineage.values() if old["row_key"] in original.index
                    and old["questionnaire_worksheet_row"] == record["questionnaire_worksheet_row"]
                    and int(re.search(r"\[REP ([1-5])\]", old["questionnaire_column"])[1]) == rep-1]
            else:
                candidates = [old for old in lineage.values() if old["row_key"] in original.index
                    and old["member"] == record["member"]
                    and old["response_time_seconds"] == record["prior_response_time_seconds"]]
            require(len(candidates) <= 1, "Original prior survey is ambiguous")
            if not candidates:
                continue
            old = candidates[0]
            actual = sources[sources.row_key.eq(key)]
            require(len(actual) == 1, "An eligible actual original transition was lost")
            row = actual.iloc[0]
            require(row.prior_row_key == old["row_key"] and row.group_key == current.group_key == original.loc[old["row_key"]].group_key
                    and row.borg_native == current.borg_native and row.prior_borg == original.loc[old["row_key"]].borg_native, "Source pair changed person, order or actual native survey value")
            np.testing.assert_allclose(row[["hr_last", "hr_history_mean"]].to_numpy(float), current[["hr_last", "hr_history_mean"]].to_numpy(float), rtol=0, atol=1e-12, equal_nan=True)
            if name == "sts":
                require(60 <= record["response_time_seconds"]-old["response_time_seconds"] <= 900, "STS prior age not supported by original recording")
            accepted.add(key)
        require(accepted == set(sources.loc[sources.source_domain.eq(name), "row_key"])
                and not accepted & set(splits[name]["test_row_keys"]), "Extra/held-out source targets entered transition fitting")
    teachers = {}
    for algorithm in ("ridge", "svr", "random_forest"):
        model_path = study.DIRECTORY/"teachers"/(algorithm+".joblib")
        require(selection["teacher_artifact_sha256"][algorithm] == digest(model_path), "Frozen source teachers changed")
        saved = joblib.load(model_path)
        teachers[algorithm] = study.fit_teachers(sources, algorithm)
        for domain in ("worker", "sts"):
            require(list(saved[domain].feature_names_in_) == study.FEATURES, "Teacher includes labels or identities as predictors")
            np.testing.assert_allclose(teachers[algorithm][domain].predict(frame[study.FEATURES]), saved[domain].predict(frame[study.FEATURES]), rtol=0, atol=1e-12)
        print(f"Freshly fitted source-only transition heads: {algorithm}", flush=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    parent = json.loads((study.baseline.DIRECTORY/"selection.json").read_text())
    for row in selection["results"]:
        predicted = np.asarray(row["oof_predictions"])
        require(predicted.shape == (487,) and set(predicted) <= {f"Borg {i}" for i in range(11)}, "Native predictions or cases changed")
        scores = [accuracy_score(train.iloc[val].label, predicted[val]) for _, val in folds]
        np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train.label, predicted)-row["pooled_oof_accuracy"]) < 1e-12, "Saved transition accuracy disagrees with original targets")
        c = row["candidate"]
        if c["algorithm"] == "parent_control":
            old = next(r for r in parent["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            np.testing.assert_array_equal(predicted, old["oof_predictions"])
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"]
            and winner["accuracy_mean"] == selection["best_cv_accuracy"], "Winner differs from grouped CV rule")
    best = max((r for r in selection["results"] if r["candidate"]["algorithm"] in teachers), key=lambda r: r["accuracy_mean"])
    control = max((r for r in selection["results"] if r["candidate"]["algorithm"] == "sensor_control"), key=lambda r: r["accuracy_mean"])
    for row in (best, control):
        c = row["candidate"]
        fitted_teachers = teachers.get(c["algorithm"], {})
        before = joblib.hash(fitted_teachers)
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            require(not set(fitting.group_key) & set(validation.group_key), "Native fitting and validation people overlap")
            # A prohibited artificial-history fitter must never be reached.
            # Native estimators receive exactly the original fitting reports.
            native_class = study.baseline.DynamicsClassifier if c["member"] == "core" else study.baseline.CatBoostBorg
            original_fit = native_class.fit
            def real_reports_only(estimator, data):
                np.testing.assert_array_equal(data.row_key, fitting.row_key)
                np.testing.assert_array_equal(data.label, fitting.label)
                np.testing.assert_array_equal(data.group_key, fitting.group_key)
                pd.testing.assert_frame_equal(data[study.FEATURES], fitting[study.FEATURES])
                return original_fit(estimator, data)
            with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial history rows are prohibited")), patch.object(native_class, "fit", real_reports_only):
                model = study.TransitionBorg(c, fitted_teachers).fit(fitting, manifest["member_specifications"])
            predicted = model.predict(validation)
            np.testing.assert_array_equal(predicted, np.asarray(row["oof_predictions"])[val])
            changed = validation.assign(label="unavailable", row_key="unused", group_key="unused")
            np.testing.assert_array_equal(model.predict(changed), predicted)
            np.testing.assert_array_equal(model.predict(validation[model.input_features]), predicted)
            require(set(vars(model)) == {"candidate", "teachers", "input_features", "model"}
                    and joblib.hash(fitted_teachers) == before, "Native training changed source-only weights or stored a query lookup")
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/"transition.joblib"
                joblib.dump(model, output)
                np.testing.assert_array_equal(joblib.load(output).predict(changed), predicted)
            print(f"Independent native transition refit {c['id']}: fold {number+1}/5", flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A transition model crossed its gate: evaluate and verify its frozen full original-179 artifact first")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous["best_verified_test_accuracy"], "Incumbent native test artifact changed")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(),
        "parent_verification_sha256": digest(previous_path), "selection_sha256": digest(path), "verification_code_sha256": digest(Path(__file__)),
        "public_real_data_policy_sha256": digest(policy_path), "artificial_history_fitting_disabled_during_native_refits": True,
        "actual_native_fitter_receives_only_original_reports_and_labels": True,
        "source_transition_pairs_checked_against_original_lineage": 249, "source_transition_counts": {"worker": 200, "sts": 49},
        "source_heads_independently_refitted": 6, "all_10_oof_recipes_recomputed": True, "inherited_controls_reproduced": 2,
        "best_new_teacher_id": best["candidate"]["id"], "best_new_teacher_cv_accuracy": best["accuracy_mean"],
        "best_matched_sensor_control_id": control["candidate"]["id"], "best_matched_sensor_control_cv_accuracy": control["accuracy_mean"],
        "native_recipes_independently_refitted": [best["candidate"]["id"], control["candidate"]["id"]], "grouped_folds_per_refit": 5,
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"], "new_test_gate_passed": False,
        "original_training_cases": 487, "original_test_cases": 179, "best_verified_test_correct": incumbent["correct"],
        "best_verified_test_accuracy": incumbent["accuracy"], "target_accuracy": .8, "achieved": False,
        "scope": "Exact native Borg on original participant-held cases. Combined source survey transitions remain auxiliary, with separate study-specific heads and no invented survey clock. Saved native test model is independently revalidated; source targets do not change the goal denominator."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
