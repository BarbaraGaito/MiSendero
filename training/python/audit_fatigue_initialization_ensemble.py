"""Recompute every fixed ensemble and independently refit selected members."""
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

import fatigue_initialization_ensemble as study
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate():
    folder = ROOT / "docs/fatigue-80-2026-10-25"
    prior_path = folder / "compact-physiology-verification.json"
    previous = json.loads(prior_path.read_text())
    from fatigue_compact_physiology import DIRECTORY as compact_directory
    require(previous["selection_sha256"] == digest(compact_directory / "selection.json")
            and previous["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_compact_physiology.py")),
            "Verified preceding study changed")
    _, train, test, _, _, pool, extra, inputs, _ = study.parent.load_inputs()
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY / "selection.json"
    selection = json.loads(path.read_text())
    require(all(selection.get(k) == v for k, v in signature.items()) and selection["status"] == "complete"
            and len(selection["results"]) == len(selection["plan"]) == 14 and selection["plan"] == study.plan()
            and selection["train_row_keys"] == train["row_key"].tolist(), "Frozen ensemble code, inputs, plan or membership changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train["group_key"]) & set(test["group_key"])
            and selection["new_native_borg_targets"] == 0 and not selection["test_used_for_selection"]
            and selection["minimum_cv_for_new_test_evaluation"] == .65, "Native task or reserved cases changed")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    scores = {family: np.empty((33, 487, 11)) for family in ("core", "view")}
    points = {family: np.empty((33, 487), dtype=int) for family in ("core", "view")}
    for number, (fit, val) in enumerate(folds):
        data_path = study.DIRECTORY / "folds" / f"fold-{number}.npz"
        metadata = json.loads(data_path.with_suffix(".json").read_text())
        require(metadata["signature"] == signature and metadata["npz_sha256"] == digest(data_path)
                and metadata["fold_number"] == number
                and metadata["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                and metadata["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "Ensemble fold metadata changed")
        require(not set(train.iloc[fit].group_key) & set(train.iloc[val].group_key), "Fold people overlap")
        with np.load(data_path, allow_pickle=False) as saved:
            require(set(saved.files) == {f+s for f in ("core", "view") for s in ("_scores", "_points")}, "Unexpected targets in member score cache")
            for family in ("core", "view"):
                scores[family][:, val], points[family][:, val] = saved[family+"_scores"], saved[family+"_points"]
                model_path = study.parent.DIRECTORY / "sources" / f"{family}-fold-{number}.joblib"
                descriptor = json.loads(model_path.with_suffix(".json").read_text())
                detail = metadata["details"][family]
                require(descriptor["signature"] == signature["parent_fingerprint"]
                        and descriptor["model_sha256"] == detail["source_model_sha256"] == digest(model_path), "Cached source template changed")
                require([r["seed"] for r in detail["member_training"]] == study.SEEDS
                        and abs(detail["training_summary"]["total_supervision_weight"]-len(fit)) < 1e-9
                        and detail["training_summary"]["extra_actual_targets"] == 0, "Members or original-report fitting mass changed")
    original = json.loads((study.parent.DIRECTORY / "selection.json").read_text())
    for row in selection["results"]:
        c = row["candidate"]
        predicted = study.ensemble_predict(scores[c["family"]], points[c["family"]], train.prior_borg.to_numpy(int), c["method"], c["members"])
        np.testing.assert_array_equal(predicted, row["oof_predictions"])
        measured = [accuracy_score(train.iloc[val].label, predicted[val]) for _, val in folds]
        np.testing.assert_allclose(measured, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(np.mean(measured)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train.label, predicted)-row["pooled_oof_accuracy"]) < 1e-12, "Saved ensemble metrics disagree with native outcomes")
        if c["method"] == "point_control":
            inherited = next(r for r in original["results"] if r["candidate"]["initialization"] == c["family"] and r["candidate"]["mode"] == "point_control")
            np.testing.assert_array_equal(predicted, inherited["oof_predictions"])
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"]
            and abs(winner["accuracy_mean"]-selection["best_cv_accuracy"]) < 1e-12, "Winner changed from the declared grouped CV rule")
    best = max((r for r in selection["results"] if r["candidate"]["method"] != "point_control"), key=lambda r: r["accuracy_mean"])
    c = best["candidate"]
    for number, (fit, val) in enumerate(folds):
        fitting, validation = train.iloc[fit], train.iloc[val]
        # Rebuild preprocessing and seed 42 from fitting data as well as all
        # other selected seeds, instead of trusting the saved template.
        model = study.InitializationEnsemble(c).fit(fitting, pool, extra, inputs["specifications"])
        actual_scores, actual_points = model.member_scores(validation)
        np.testing.assert_allclose(actual_scores, scores[c["family"]][:c["members"], val], rtol=0, atol=1e-12)
        np.testing.assert_array_equal(actual_points, points[c["family"]][:c["members"], val])
        predicted = model.predict(validation)
        np.testing.assert_array_equal(predicted, np.asarray(best["oof_predictions"])[val])
        np.testing.assert_array_equal(model.predict(validation[model.features]), predicted)
        changed = validation.assign(label="unavailable current outcome", row_key="unused", group_key="unused")
        np.testing.assert_array_equal(model.predict(changed), predicted)
        require(set(vars(model)) == {"candidate", "features", "preprocessing", "training_summary", "models", "training_diagnostics"}, "Stored model includes a query or history lookup")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"ensemble.joblib"
            joblib.dump(model, output)
            np.testing.assert_array_equal(joblib.load(output).predict(changed), predicted)
        print(f"Independent initialization ensemble refit {c['id']}, fold {number+1}/5 ({c['members']} members)", flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY / "evaluation/metrics.json").exists(),
            "An ensemble passed its gate: evaluate and verify the frozen full original-179 artifact before reporting its test accuracy")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous["best_verified_test_accuracy"], "Retained native test artifact changed")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(),
        "parent_verification_sha256": digest(prior_path), "selection_sha256": digest(path), "verification_code_sha256": digest(Path(__file__)),
        "all_14_recipes_recomputed": True, "original_seed_controls_reproduced": 2,
        "all_concurrent_fold_memberships_verified": True, "predeclared_seeds": study.SEEDS,
        "best_ensemble_id": c["id"], "best_ensemble_cv_accuracy": best["accuracy_mean"],
        "best_ensemble_independent_refit_folds": 5, "members_per_independent_refit": c["members"],
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"], "new_test_gate_passed": False,
        "original_training_cases": 487, "original_test_cases": 179, "best_verified_test_correct": incumbent["correct"],
        "best_verified_test_accuracy": incumbent["accuracy"], "target_accuracy": .8, "achieved": False,
        "scope": "Exact native Borg and original participant holdout. Every aggregation is recomputed and the best ensemble is freshly fitted including preprocessing and the original source network. Equal fixed weights do not select favorable seeds; published benchmark reuse remains descriptive research."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
