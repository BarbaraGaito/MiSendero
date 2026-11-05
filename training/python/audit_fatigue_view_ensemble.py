"""Refit all ensemble members and reproduce all native grouped-CV mixtures."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_view_ensemble as ensemble
from public_sources import digest


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(selection):
    frame, train, test, _, _, pool, evidence, source_winners = ensemble.load_inputs()
    signature = ensemble.fingerprint(evidence)
    require(all(selection.get(k) == v for k, v in signature.items()) and selection["plan"] == ensemble.plan()
            and selection["train_row_keys"] == train["row_key"].tolist()
            and selection["status"] == "complete" and len(selection["results"]) == len(selection["plan"]) == 54,
            "Frozen ensemble data, members, code, runtime or recipes changed")
    require(not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["evaluation_denominator"] == len(train) == 487 and selection["test_denominator"] == len(test) == 179
            and selection["new_observed_targets"] == selection["synthetic_borg_targets"] == 0
            and selection["native_scale_values"] == list(range(11)), "Ensemble target, native scale, cases or test gate changed")
    historical_cat = json.loads((ensemble.catboost.DIRECTORY / "selection.json").read_text())
    for package, version in historical_cat["software_versions"].items():
        require(importlib.metadata.version(package) == version, "CatBoost member runtime differs from its original study")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    scores = {name: np.empty((487, 11)) for name in ensemble.MEMBERS}
    point = {name: np.empty(487, dtype=object) for name in ensemble.MEMBERS}
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"], "Ensemble winner differs from original training CV ranking")
    for number, (fit, val) in enumerate(folds):
        fitting, validation = train.iloc[fit], train.iloc[val]
        path = ensemble.DIRECTORY / "folds" / f"fold-{number}.json"
        saved = json.loads(path.read_text())
        require(saved == selection["folds"][number] and saved["signature"] == signature
                and saved["fit_row_keys"] == fitting["row_key"].tolist()
                and saved["validation_row_keys"] == validation["row_key"].tolist()
                and not set(fitting["group_key"]) & set(validation["group_key"]), "Ensemble fold leaked people or changed membership")
        cache_path = path.with_suffix(".npz")
        require(digest(cache_path) == saved["npz_sha256"], "Ensemble score cache changed")
        with np.load(cache_path, allow_pickle=False) as cached:
            require(set(cached.files) == {name+suffix for name in ensemble.MEMBERS for suffix in ("_scores", "_point")},
                    "Current targets or unexpected identity channels entered the ensemble score cache")
            for name in ensemble.MEMBERS:
                scores[name][val] = ensemble.probabilities(cached[name+"_scores"])
                point[name][val] = cached[name+"_point"]
        with threadpool_limits(limits=1):
            model = ensemble.ViewProbabilityEnsemble(winner["candidate"], selection["member_specifications"]).fit(fitting, pool)
            rebuilt_scores, rebuilt_point = model.member_scores(validation), model.point_predictions(validation)
        require(model.view.fit_summary == saved["view_fitting_summary"]
                and model.view.fit_summary["unique_actual_targets"] == len(fit)
                and abs(model.view.fit_summary["total_report_weight"]-len(fit)) < 1e-9,
                "Ensemble history views changed original-report weight or fitting targets")
        for name in ensemble.MEMBERS:
            np.testing.assert_allclose(rebuilt_scores[name], scores[name][val], rtol=0, atol=1e-12)
            np.testing.assert_array_equal(rebuilt_point[name], point[name][val])
        np.testing.assert_array_equal(model.predict(validation), np.asarray(winner["oof_predictions"])[val])
        changed = validation.copy()
        changed["label"], changed["group_key"], changed["row_key"] = "unavailable_current_target", "unused_person_id", "unused_query_id"
        np.testing.assert_array_equal(model.predict(changed), model.predict(validation))
        np.testing.assert_array_equal(model.predict(validation[evidence["runtime_features"]]), model.predict(validation))
        require(set(vars(model)) == {"candidate", "specifications", *ensemble.MEMBERS}, "Ensemble serialized fitting rows or a runtime lookup pool")
        print(f"Native ensemble members and probabilities independently refitted fold {number+1}/5", flush=True)
    original = json.loads((ensemble.RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    original = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["id"] == "alternative-023")
    np.testing.assert_array_equal(point["core"], original)
    for name in ("cat", "view"):
        np.testing.assert_array_equal(point[name], source_winners[name]["oof_predictions"])
    for row in selection["results"]:
        candidate = row["candidate"]
        expected = point[candidate["member"]] if candidate["kind"] == "point_control" else ensemble.native_labels(ensemble.fuse_scores(scores, candidate))
        np.testing.assert_array_equal(expected, row["oof_predictions"])
        require(len(expected) == 487 and set(expected) <= {f"Borg {i}" for i in range(11)}, "Ensemble OOF native scale or denominator changed")
        accuracy = [accuracy_score(train.iloc[val]["label"], expected[val]) for _, val in folds]
        np.testing.assert_allclose(accuracy, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(float(np.mean(accuracy))-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train["label"], expected)-row["pooled_oof_accuracy"]) < 1e-12, "Ensemble score differs from saved original native decisions")
    if winner["accuracy_mean"] < .65:
        require(not (ensemble.DIRECTORY / "evaluation/metrics.json").exists(), "Ensemble bypassed its predeclared new-test gate")
    return {"native_member_models_per_fold": 3, "member_fits_reconstructed": 15, "probability_recipes_reproduced": 54,
            "historical_point_controls_reproduced": 3, "original_training_queries": 487, "original_test_queries": 179,
            "original_case_and_native_label_contract_preserved": True, "new_measured_borg_targets": 0,
            "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"],
            "minimum_cv_for_new_test_evaluation": .65, "new_test_gate_passed": winner["accuracy_mean"] >= .65,
            "verification_code_sha256": digest(Path(__file__))}
