"""Recompute compact physiology CV and independently refit new recipes."""
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

import fatigue_compact_physiology as compact
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate():
    folder = ROOT / "docs/fatigue-80-2026-10-25"
    parent_path = folder / "runner-anchor-verification.json"
    parent = json.loads(parent_path.read_text())
    require(parent["selection_sha256"] == digest(compact.paired.DIRECTORY / "selection.json")
            and parent["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_runner_anchor_transfer.py")), "Verified paired parent evidence changed")
    inputs = compact.load_inputs()
    _, train, test, members, _, current, reference, _, previous = inputs
    signature = compact.fingerprint(inputs)
    path = compact.DIRECTORY / "selection.json"
    selection = json.loads(path.read_text())
    require(all(selection.get(k) == v for k, v in signature.items()) and selection["status"] == "complete"
            and len(selection["results"]) == len(selection["plan"]) == 10 and selection["plan"] == compact.plan()
            and selection["train_row_keys"] == train["row_key"].tolist(), "Frozen compact study source, code, runtime or plan changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train["group_key"]) & set(test["group_key"])
            and selection["new_native_borg_targets"] == 0 and not selection["test_used_for_selection"]
            and selection["minimum_cv_for_new_test_evaluation"] == .65, "Compact study changed native task, cases or holdout")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    encoders = {}
    for key in ("runner-encoder-000", "runner-encoder-001", "runner-encoder-004"):
        model_path = compact.paired.parent.DIRECTORY / "encoders" / (key+".joblib")
        descriptor = json.loads(model_path.with_suffix(".json").read_text())
        require(descriptor["model_sha256"] == digest(model_path)
                and descriptor["signature"] == signature["paired_input_fingerprint"]["parent_fingerprint"], "Frozen source-score encoder changed")
        encoder = joblib.load(model_path)
        encoders[key] = encoder
        now_present = current[:, 3:].sum(axis=(1, 2)) > 0
        old_present = reference[:, 3:].sum(axis=(1, 2)) > 0
        frame = inputs[0]
        with torch.no_grad():
            now = encoder.network(torch.from_numpy(current.copy())).numpy()
            old = encoder.network(torch.from_numpy(reference.copy())).numpy()
        delta = np.where(now_present & old_present, now-old, np.nan)
        expected = np.column_stack((np.where(now_present, now, np.nan), delta,
            delta/frame["prior_age_minutes"].to_numpy(float), current[:, 3:].mean(axis=(1, 2)),
            reference[:, 3:].mean(axis=(1, 2)), (now_present & old_present).astype(float)))
        actual = compact.compact_scores(frame, current, reference, encoder)[compact.SCORES].to_numpy()
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-6, equal_nan=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for row in selection["results"]:
        c, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(predicted.shape == (487,) and set(predicted) <= {f"Borg {i}" for i in range(11)}, "Compact output changed native labels or denominator")
        scores = [accuracy_score(train.iloc[val]["label"], predicted[val]) for _, val in folds]
        np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
        require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train["label"], predicted)-row["pooled_oof_accuracy"]) < 1e-12, "Compact saved metrics disagree with original OOF decisions")
        if c["algorithm"] == "parent_control":
            inherited = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            np.testing.assert_array_equal(predicted, inherited["oof_predictions"])
            continue
        for number, (fit, val) in enumerate(folds):
            saved = json.loads((compact.DIRECTORY / "folds" / f"{c['id']}-fold-{number}.json").read_text())
            require(saved == row["folds"][number] and saved["signature"] == signature and saved["candidate"] == c
                    and saved["fold_number"] == number and saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                    and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "Concurrent compact fitting/validation membership changed")
            np.testing.assert_array_equal(saved["predicted"], predicted[val])
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"], "Compact winner did not follow original grouped CV")
    best = max((r for r in selection["results"] if r["candidate"]["algorithm"] != "parent_control"), key=lambda r: r["accuracy_mean"])
    gait = max((r for r in selection["results"] if r["candidate"]["algorithm"] != "parent_control" and r["candidate"]["mode"] != "hr_only"), key=lambda r: r["accuracy_mean"])
    recipes = {r["candidate"]["id"]: r for r in (best, gait)}
    for row in recipes.values():
        c = row["candidate"]
        encoder = encoders.get(c["encoder_id"])
        before = {} if encoder is None else {k: v.clone() for k, v in encoder.network.state_dict().items()}
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            model = compact.CompactPhysiologyBorg(c, encoder).fit(fitting, current[fitting.index], reference[fitting.index], members["member_specifications"])
            predicted = model.predict(validation, current[validation.index], reference[validation.index])
            np.testing.assert_array_equal(predicted, np.asarray(row["oof_predictions"])[val])
            changed = validation.assign(label="unavailable current response", row_key="unused", group_key="unused")
            np.testing.assert_array_equal(model.predict(changed, current[validation.index], reference[validation.index]), predicted)
            np.testing.assert_array_equal(model.predict(validation[model.input_features], current[validation.index], reference[validation.index]), predicted)
            require(set(vars(model)) == {"candidate", "encoder", "input_features", "model"}, "Compact model stores a query/target history lookup")
            if encoder is not None:
                require(all(torch.equal(value, encoder.network.state_dict()[key]) for key, value in before.items()), "Native fitting changed source weights")
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/"compact.joblib"
                joblib.dump(model, output)
                np.testing.assert_array_equal(joblib.load(output).predict(changed, current[validation.index], reference[validation.index]), predicted)
            print(f"Compact recipe {c['id']} independently refitted fold {number+1}/5", flush=True)
    require(winner["accuracy_mean"] < .65 and not (compact.DIRECTORY / "evaluation/metrics.json").exists(),
            "A compact model crossed its CV gate: verify its frozen original-179 test artifact before reporting a new goal score")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == parent["best_verified_test_accuracy"], "Retained native test model changed")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(),
        "parent_verification_sha256": digest(parent_path), "selection_sha256": digest(path), "verification_code_sha256": digest(Path(__file__)),
        "all_10_recipes_recomputed": True, "all_concurrent_fold_memberships_verified": True,
        "compact_source_scores_checked_directly_against_three_network_heads": True,
        "new_recipes_independently_refitted": sorted(recipes), "grouped_folds_per_new_recipe": 5,
        "best_new_recipe_id": best["candidate"]["id"], "best_new_cv_accuracy": best["accuracy_mean"],
        "best_gait_recipe_id": gait["candidate"]["id"], "best_gait_cv_accuracy": gait["accuracy_mean"],
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"], "new_test_gate_passed": False,
        "original_training_cases": 487, "original_test_cases": 179, "best_verified_test_correct": incumbent["correct"],
        "best_verified_test_accuracy": incumbent["accuracy"], "target_accuracy": .8, "achieved": False,
        "scope": "Exact native Borg, original participant holdout and all cases retained. Earlier source fitting is referenced through unchanged verification; the new compact transformations and two new native recipes are independently reproduced. Source protocol performance is not the native goal score."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
