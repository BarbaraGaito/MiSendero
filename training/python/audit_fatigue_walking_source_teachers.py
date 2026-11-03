"""Audit original combined cells and reproduce source/native transfer fitting."""
from __future__ import annotations

import argparse
import json
import tempfile
import warnings
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_walking_source_teachers as study
from audit_walking_spe_eligibility import original_table
from public_sources import ROOT, digest, group_key
from validate_fatigue_release import validate as validate_incumbent


def require(value, reason):
    if not value:
        raise ValueError(reason)


def validate():
    inputs = study.load_inputs()
    parents, combined, provenance, previous_controls = inputs
    _, train, test, members, original_borg, old_provenance, _, _ = parents
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k, v in signature.items())
            and selection["plan"] == study.plan() and len(selection["results"]) == 22
            and selection["train_row_keys"] == train.row_key.tolist(), "Frozen walking source model selection changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train.group_key) & set(test.group_key) and not selection["test_used_for_selection"]
            and selection["minimum_cv_for_new_test_evaluation"] == .65 and selection["synthetic_training_rows"] == 0
            and selection["new_native_borg_targets"] == 0 and not selection["walking_sensor_join_performed"]
            and not selection["walking_person_holdout_claimed"], "Original native task, real-source scope or test boundary changed")
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    previous_path = folder/"supported-physiology-verification.json"
    previous = json.loads(previous_path.read_text())
    require(previous["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_supported_physiology.py")), "Previous scoped audit changed")
    original_spe, spe_provenance = study.source.walking.load()
    expected = pd.concat([original_borg, original_spe], ignore_index=True, sort=False)
    pd.testing.assert_frame_equal(combined, expected, check_dtype=False, rtol=0, atol=1e-12)
    require(len(combined) == 458 and combined.row_key.is_unique
            and combined.groupby("source_domain").size().to_dict() == {"worker":253,"sts":49,"walking_spe":156}, "Original combined source rows changed")
    for name, split in old_provenance["external_splits"].items():
        part = combined[combined.source_domain.eq(name)]
        require(not set(part.row_key) & set(split["test_row_keys"]) and not set(part.group_key) & set(split["test_groups"]), "Reserved Worker/STS source people entered fitting")
    walking = combined[combined.source_domain.eq("walking_spe")]
    require(walking.group_key.nunique() == 1 and walking.sequence_key.nunique() == 52
            and walking[["hr_last", "hr_history_mean", "borg_native"]].isna().all().all(), "Walking rows acquired guessed HR, native labels or person identities")
    source_lineage = {r["row_key"]:r for r in spe_provenance["lineage"]}
    verified_cells = 0
    with zipfile.ZipFile(study.source.walking.source.DIRECTORY/"All_data.zip") as archive:
        for condition in study.source.walking.CONDITIONS:
            values, sha = original_table(archive, f"SPE_{condition}.txt")
            heart, _ = original_table(archive, f"HR_{condition}.txt")
            require(len(values) == 13 and len(heart) == 12, "Original unidentified source row counts changed")
            for _, row in walking[walking.source_condition.eq(condition)].iterrows():
                evidence = source_lineage[row.row_key]
                i, j = evidence["source_row_zero_based"], evidence["current_column_zero_based"]
                require(evidence["member_sha256"] == sha and row.spe_native == values[i][j] and row.prior_spe == values[i][j-1], "Source current/prior cell differs from original public bytes")
                require(row.prior_row_key == group_key(f"Walking-SPE-original-cell:SPE_{condition}.txt:{i}:{j-1}")
                        and row.nominal_elapsed_minutes == 5*(j+1) and row.nominal_prior_age_minutes == 5, "Original prior cell or nominal time changed")
                require((j >= 2 and row.prior2_spe == values[i][j-2]) or (j == 1 and pd.isna(row.prior2_spe)), "Second earlier source response was invented or changed")
                verified_cells += 1
    require(verified_cells == 156 and not provenance["native_target_merge"] and provenance["synthetic_rows"] == 0, "Source observations were converted into native labels or synthetic rows")
    stored_walking, stored_existing = study.read_teachers(signature)
    fresh_walking, fresh_existing = {}, {}
    source_target_calls = 0
    for algorithm in ("ridge", "svr", "random_forest"):
        observed, pending_targets, target_calls = [], [], []
        def observe(condition, features, current, prior):
            expected = walking[walking.source_condition.eq(condition)]
            pd.testing.assert_frame_equal(features, expected[study.FEATURES])
            np.testing.assert_array_equal(current, expected.spe_native.to_numpy())
            np.testing.assert_array_equal(prior, expected.prior_spe.to_numpy())
            pending_targets.append(current-prior)
            observed.append(condition)
        estimator_class = {"ridge":study.Ridge, "svr":study.SVR, "random_forest":study.RandomForestRegressor}[algorithm]
        actual_fit = estimator_class.fit
        def observe_fit(model, features, target, **kwargs):
            require(len(features) == 39, "Walking source estimator received additional rows")
            np.testing.assert_array_equal(target, pending_targets[len(target_calls)])
            target_calls.append(1)
            return actual_fit(model, features, target, **kwargs)
        with patch.object(estimator_class, "fit", new=observe_fit):
            fresh = study.fit_walking_teachers(combined, algorithm, observe)
        require(observed == list(study.source.walking.CONDITIONS) and len(target_calls) == 4, "Real walking source observer was bypassed")
        source_target_calls += len(target_calls)
        for condition, teacher in fresh.items():
            actual_features = walking[walking.source_condition.eq(condition)][study.FEATURES]
            require(teacher[0].feature_names_in_.tolist() == study.FEATURES and int(teacher[-2].n_samples_seen_) == 39, "Native data or target fields entered source normalization")
            np.testing.assert_allclose(teacher.predict(actual_features), stored_walking[algorithm][condition].predict(actual_features), rtol=0, atol=1e-12)
            query = study.query_source_features(train)
            np.testing.assert_allclose(teacher.predict(query), stored_walking[algorithm][condition].predict(query), rtol=0, atol=1e-12)
        fresh_walking[algorithm] = fresh
        fresh_existing[algorithm] = study.parent.parent.fit_teachers(original_borg, algorithm)
        for domain, teacher in fresh_existing[algorithm].items():
            rows = original_borg[original_borg.source_domain.eq(domain)]
            np.testing.assert_allclose(teacher.predict(rows[study.parent.parent.FEATURES]), stored_existing[algorithm][domain].predict(rows[study.parent.parent.FEATURES]), rtol=0, atol=1e-12)
        print(f"Independently refitted real source heads:{algorithm},4 SPE conditions and2 Borg sources", flush=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    for row in selection["results"]:
        candidate, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted) <= {f"Borg {v}" for v in range(11)}, "Original native OOF scope changed")
        scores = [float(accuracy_score(train.iloc[val].label, predicted[val])) for _, val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
                and float(accuracy_score(train.label, predicted)) == row["pooled_oof_accuracy"], "Exact native grouped accuracy changed")
        if candidate["algorithm"] == "previous_real_control":
            control = next(r for r in previous_controls["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted, control["oof_predictions"])
            continue
        require(len(row["folds"]) == 5, "A native participant fold is missing")
        for number, (fit, val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist()
                    and saved["actual_walking_source_targets"] == 156
                    and saved["actual_existing_source_targets"] == (302 if candidate["include_existing_borg_teachers"] else 0), "Native/source fitting membership changed")
            np.testing.assert_array_equal(saved["predicted"], predicted[val])
    winner = max(selection["results"], key=lambda r:r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"] and selection["best_cv_accuracy"] == winner["accuracy_mean"], "Winner differs from predeclared grouped CV")
    new = [row for row in selection["results"] if row["candidate"]["algorithm"] != "previous_real_control"]
    best = max(new, key=lambda r:r["accuracy_mean"])
    combined_best = max((r for r in new if r["candidate"]["include_existing_borg_teachers"]), key=lambda r:r["accuracy_mean"])
    combined_recipe = combined_best["candidate"]
    parent_recipe = next(c for c in study.parent.plan() if c.get("teacher_algorithm") == combined_recipe["teacher_algorithm"]
        and c.get("member") == combined_recipe["member"] and c["algorithm"] == "expanded_actual_source_pairs")
    matched_control = next(r for r in previous_controls["results"] if r["candidate"]["id"] == parent_recipe["id"])
    selected = {r["candidate"]["id"]:r for r in (best, combined_best)}
    refits = [(row, False) for row in selected.values()]+[(matched_control, True)]
    convergence = []
    native_fit_visits = 0
    for row, old in refits:
        candidate = row["candidate"]
        algorithm = candidate["teacher_algorithm"]
        member = candidate["member"]
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            observed_fit = []
            classifier = study.parent.parent.baseline.DynamicsClassifier if member == "core" else study.parent.parent.baseline.CatBoostBorg
            actual_fit = classifier.fit
            def observe_native(model, data):
                pd.testing.assert_frame_equal(data[fitting.columns], fitting)
                np.testing.assert_array_equal(data.row_key, fitting.row_key)
                np.testing.assert_array_equal(data.label, fitting.label)
                observed_fit.append(len(data))
                return actual_fit(model, data)
            with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial history examples prohibited")), patch.object(classifier, "fit", new=observe_native), warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always", ConvergenceWarning)
                if old:
                    model = study.parent.parent.TransitionBorg(candidate, fresh_existing[algorithm]).fit(fitting, members["member_specifications"])
                else:
                    model = study.WalkingSourceBorg(candidate, fresh_walking[algorithm], fresh_existing[algorithm]).fit(fitting, members["member_specifications"])
            require(observed_fit == [len(fitting)], "Actual native fitting rows/labels observer was bypassed")
            native_fit_visits += len(fitting)
            predicted = model.predict(validation)
            np.testing.assert_array_equal(predicted, np.asarray(row["oof_predictions"])[val])
            runtime = validation[model.input_features]
            np.testing.assert_array_equal(model.predict(runtime), predicted)
            require(not set(model.input_features) & {"label", "row_key", "group_key"}
                    and not set(vars(model)) & {"frame", "combined", "histories", "pool", "row_keys"}, "Current truth/IDs or a report pool entered inference")
            with tempfile.TemporaryDirectory() as directory:
                artifact = Path(directory)/"real-walking-source.joblib"
                joblib.dump(model, artifact)
                np.testing.assert_array_equal(joblib.load(artifact).predict(runtime), predicted)
            issues = [str(w.message) for w in captured if issubclass(w.category, ConvergenceWarning)]
            convergence.append({"candidate_id": candidate["id"], "fold":number, "convergence_warning_count":len(issues), "messages":issues})
            print(f"Independent walking-source native refit {candidate['id']} fold{number+1}/5", flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A walking-source model crossed its gate: freeze and evaluate the full original179 artifact next")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous["best_verified_test_accuracy"], "Retained original test model changed")
    return {"version":1, "verified_at":datetime.now(timezone.utc).isoformat(), "verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(path), "previous_verification_sha256":digest(previous_path),
        "public_real_data_policy_sha256":digest(study.parent.native.POLICY),
        "combined_actual_source_pairs_verified":458, "walking_current_prior_cells_independently_rebuilt":156,
        "walking_sensor_join_disabled":True, "walking_no_invented_person_holdout":True,
        "source_models_independently_refitted":18, "actual_source_estimator_target_calls_observed":source_target_calls,
        "walking_heads_per_algorithm":4, "source_algorithms":3, "all_22_oof_recipes_recomputed":True,
        "best_new_candidate_id":best["candidate"]["id"], "best_new_cv_accuracy":best["accuracy_mean"],
        "best_combined_source_candidate_id":combined_recipe["id"], "best_combined_source_cv_accuracy":combined_best["accuracy_mean"],
        "matching_previous_source_candidate_id":parent_recipe["id"], "matching_previous_source_cv_accuracy":matched_control["accuracy_mean"],
        "native_recipes_independently_refitted":sorted(selected)+[parent_recipe["id"]], "grouped_folds_per_refit":5,
        "actual_native_fitting_visits_observed":native_fit_visits, "convergence_warnings_by_refit":convergence,
        "native_labels_and_rows_verified_at_actual_fitter":True, "artificial_history_fitting_disabled":True,
        "winner_id":selection["winner_id"], "best_cv_accuracy":winner["accuracy_mean"], "new_test_gate_passed":False,
        "original_training_cases":487, "original_test_cases":179, "best_verified_test_correct":incumbent["correct"],
        "best_verified_test_accuracy":incumbent["accuracy"], "target_accuracy":.8, "achieved":False,
        "scope":"Exact original native Borg on all original cases. Real public source-specific Borg and SPE heads remain distinct; no guessed walking HR/identities, target conversion, synthetic examples, artificial history views, native holdout changes or test tuning. Source predictions are computed representations, not measured native targets."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
