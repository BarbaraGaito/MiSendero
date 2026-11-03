"""Verify the GP study; reuse only unchanged, already verified older studies."""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_gaussian_process as gp
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(selection):
    frame, train, test, manifest, _, pool, extra, inputs, _ = gp.parent.load_inputs()
    signature = gp.fingerprint(inputs)
    require(all(selection.get(k) == v for k, v in signature.items())
            and selection["status"] == "complete" and len(selection["results"]) == 18
            and selection["plan"] == gp.plan(manifest, inputs["specifications"])
            and selection["train_row_keys"] == train["row_key"].tolist(), "GP frozen plan, source, code or software changed")
    require(len(frame) == 666 and len(train) == selection["evaluation_denominator"] == 487
            and len(test) == selection["test_denominator"] == 179
            and not set(train["group_key"]) & set(test["group_key"])
            and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["alternative_input_views"] == selection["synthetic_borg_targets"] == 0
            and len(extra) == selection["extra_actual_report_pool"] == 56, "GP changed labels, cases, participant holdout or test gate")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    previous = json.loads((gp.parent.DIRECTORY / "selection.json").read_text())
    for row in selection["results"]:
        candidate = row["candidate"]
        prediction = np.asarray(row["oof_predictions"])
        require(prediction.shape == (487,) and set(prediction) <= {f"Borg {i}" for i in range(11)}, "GP decisions changed native target support")
        scores = [accuracy_score(train.iloc[val]["label"], prediction[val]) for _, val in folds]
        np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train["label"], prediction)-row["pooled_oof_accuracy"]) < 1e-12, "GP saved metrics disagree with exact original OOF decisions")
        for number, (fit, val) in enumerate(folds):
            saved = json.loads((gp.DIRECTORY / "folds" / f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == row["folds"][number] and saved["signature"] == signature
                    and saved["candidate"] == candidate and saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                    and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "GP cached fold membership changed")
            np.testing.assert_array_equal(saved["predicted"], prediction[val])
            if candidate["algorithm"] == "gaussian_process":
                fitting, target, summary = gp.fitting_reports(train.iloc[fit], extra, candidate["include_extra"])
                require(not set(fitting["group_key"]) & set(train.iloc[val]["group_key"])
                        and summary == saved["training_summary"] and fitting["row_key"].is_unique
                        and np.isfinite(saved["training_diagnostics"]["log_marginal_likelihood"]), "GP additional reports leaked validation people or inflated targets")
            else:
                path = gp.parent.DIRECTORY / "sources" / f"{candidate['initialization']}-fold-{number}.joblib"
                descriptor = json.loads(path.with_suffix(".json").read_text())
                require(digest(path) == descriptor["model_sha256"] == saved["training_diagnostics"]["source_model_sha256"]
                        and descriptor["signature"] == gp.parent.fingerprint(inputs), "Historical GP source control changed")
                source = joblib.load(path)
                require(source["fit_row_keys"] == train.iloc[fit]["row_key"].tolist(), "Historical control includes different fitting people")
                native = source["classifier"].predict(source["preprocessor"].transform(train.iloc[val][source["features"]])).astype(int)
                native = np.clip(native+train.iloc[val]["prior_borg"].to_numpy(int), 0, 10)
                np.testing.assert_array_equal(prediction[val], [f"Borg {i}" for i in native])
        if candidate["algorithm"] == "historical_point_control":
            reference = next(r["oof_predictions"] for r in previous["results"]
                if r["candidate"]["initialization"] == candidate["initialization"] and r["candidate"]["mode"] == "point_control")
            np.testing.assert_array_equal(prediction, reference)
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"], "GP selection does not follow grouped training CV")
    best_gp = max((r for r in selection["results"] if r["candidate"]["algorithm"] == "gaussian_process"), key=lambda r: r["accuracy_mean"])
    # Refit a genuinely new GP even when a historical control wins.
    for number, (fit, val) in enumerate(folds):
        with threadpool_limits(limits=1):
            model = gp.GaussianBorg(best_gp["candidate"]).fit(train.iloc[fit], extra)
            predicted = model.predict(train.iloc[val])
        np.testing.assert_array_equal(predicted, np.asarray(best_gp["oof_predictions"])[val])
        recorded = best_gp["folds"][number]["training_diagnostics"]
        require(model.training_diagnostics["fitted_kernel"] == recorded["fitted_kernel"], "Independently fitted GP kernel changed")
        np.testing.assert_allclose(model.training_diagnostics["log_marginal_likelihood"], recorded["log_marginal_likelihood"], rtol=0, atol=1e-9)
        require(set(vars(model)) == {"candidate", "features", "training_summary", "preprocessing", "model", "training_diagnostics"},
                "GP wrapper retains participant identifiers or a runtime response pool")
        changed = train.iloc[val].assign(label="current outcome unavailable", row_key="unused", group_key="unused")
        np.testing.assert_array_equal(model.predict(changed), predicted)
        np.testing.assert_array_equal(model.predict(train.iloc[val][model.features]), predicted)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"gp.joblib"
            joblib.dump(model, path)
            np.testing.assert_array_equal(joblib.load(path).predict(changed), predicted)
        if number == 0:
            poisoned = extra.copy()
            excluded = ~poisoned["group_key"].isin(set(train.iloc[fit]["group_key"]))
            poisoned.loc[excluded, model.features] = 1e9
            poisoned.loc[excluded, "label"] = "unavailable held-person outcome"
            clean = gp.GaussianBorg(best_gp["candidate"]).fit(train.iloc[fit], poisoned)
            np.testing.assert_array_equal(clean.predict(train.iloc[val]), predicted)
            np.testing.assert_array_equal(clean.preprocessing.transform(train.iloc[fit][model.features]), model.preprocessing.transform(train.iloc[fit][model.features]))
            require(clean.training_diagnostics == model.training_diagnostics, "Excluded extra participant information affected GP learning")
        print(f"Best new Gaussian process independently refitted fold {number+1}/5", flush=True)
    best_extra = max((r for r in selection["results"] if r["candidate"]["algorithm"] == "gaussian_process"
                      and r["candidate"]["include_extra"]), key=lambda r: r["accuracy_mean"])
    if best_extra["candidate"]["id"] != best_gp["candidate"]["id"]:
        fit, val = folds[0]
        with threadpool_limits(limits=1):
            model = gp.GaussianBorg(best_extra["candidate"]).fit(train.iloc[fit], extra)
            predicted = model.predict(train.iloc[val])
        np.testing.assert_array_equal(predicted, np.asarray(best_extra["oof_predictions"])[val])
        require(model.training_summary == best_extra["folds"][0]["training_summary"]
                and model.training_summary["additional_actual_reports"] > 0, "New extra-report GP did not independently reproduce actual additional supervision")
        np.testing.assert_allclose(model.training_diagnostics["log_marginal_likelihood"],
            best_extra["folds"][0]["training_diagnostics"]["log_marginal_likelihood"], rtol=0, atol=1e-9)
        print("Best additional-report GP independently refitted its first grouped fold", flush=True)
    if winner["accuracy_mean"] < .65:
        require(not (gp.DIRECTORY / "evaluation/metrics.json").exists(), "Weak GP selection bypassed the frozen test gate")
    return {"original_training_cases": 487, "original_test_cases": 179, "extra_actual_report_pool": 56,
        "all_18_oof_recipes_recomputed": True, "historical_point_controls_reproduced": 2,
        "all_extra_report_person_filters_verified": True, "best_new_gp_grouped_folds_refitted": 5,
        "best_new_gp_id": best_gp["candidate"]["id"], "best_new_gp_cv_accuracy": best_gp["accuracy_mean"],
        "best_additional_report_gp_id": best_extra["candidate"]["id"],
        "best_additional_report_gp_folds_refitted": 5 if best_extra["candidate"]["id"] == best_gp["candidate"]["id"] else 1,
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"],
        "minimum_cv_for_new_test_evaluation": .65, "new_test_gate_passed": winner["accuracy_mean"] >= .65,
        "gp_keeps_only_fitting_normalized_examples_and_encoded_classes": True,
        "verification_code_sha256": digest(Path(__file__))}


def checkpoint():
    previous_path = ROOT / "docs/fatigue-80-2026-10-25/checkpoint.json"
    previous = json.loads(previous_path.read_text())
    unchanged = {}
    for name, evidence in previous["experiments"].items():
        path = gp.parent.RESEARCH / name / "selection.json"
        require(evidence["status"] == "complete" and digest(path) == evidence["selection_snapshot_sha256"],
                "Previously verified study changed; run its full independent verification")
        unchanged[name] = evidence["selection_snapshot_sha256"]
    incumbent = validate_incumbent()
    require(incumbent["correct"] == previous["best_verified_test_correct"] == 108
            and incumbent["accuracy"] == previous["best_verified_test_accuracy"], "Previous test artifact/metric changed")
    path = gp.DIRECTORY / "selection.json"
    selection = json.loads(path.read_text())
    verification = validate(selection)
    require(not verification["new_test_gate_passed"],
            "A GP crossed its frozen CV gate: evaluate and independently verify its saved native test artifact before reporting the goal score")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(),
        "previous_checkpoint_sha256": digest(previous_path), "unchanged_previous_study_selections": unchanged,
        "additional_study": "gaussian-process-80-v1", "selection_sha256": digest(path),
        "completed_candidates": len(selection["results"]), "verification": verification,
        "best_verified_test_correct": incumbent["correct"], "best_verified_test_accuracy": incumbent["accuracy"],
        "target_accuracy": .8, "achieved": False,
        "scope": "New GP study independently verified. The earlier full verification is historical evidence; this run checks that its selection reports are unchanged, without refitting all previous models. Native labels, participant holdout and the retained best test model are independently revalidated by the incumbent release verifier. CV alone does not satisfy the 80-percent target."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = checkpoint()
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
