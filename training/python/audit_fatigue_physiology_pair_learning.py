"""Verify grouped physiology selection and reproduce its real-data training."""
from __future__ import annotations

import argparse
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

import fatigue_physiology_pair_learning as study
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(value, reason):
    if not value:
        raise ValueError(reason)


def independent_offsets(frame, extra, specification):
    """Refit original-only baselines; never consume extra targets in a base."""
    original = torch.empty((len(frame), 21), dtype=torch.float64)
    additional = torch.empty((len(extra), 21), dtype=torch.float64)
    inner = []
    with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial histories prohibited")):
        for fit, val in GroupKFold(n_splits=3).split(frame, groups=frame.group_key):
            fitting, validation = frame.iloc[fit], frame.iloc[val]
            indexes = np.flatnonzero(extra.group_key.isin(set(validation.group_key)))
            require(not set(fitting.group_key) & (set(validation.group_key) | set(extra.iloc[indexes].group_key)), "Independent baseline leaked native/extra held people")
            base = study.WarmPersonalBorg({"steps": 0}).fit(fitting, specification)
            original[val] = study.base_features(base, validation)[1]
            if len(indexes):
                additional[indexes] = study.base_features(base, extra.iloc[indexes])[1]
            inner.append({"fit_row_keys": fitting.row_key.tolist(), "validation_row_keys": validation.row_key.tolist(),
                          "extra_validation_row_keys": extra.iloc[indexes].row_key.tolist()})
        base = study.WarmPersonalBorg({"steps": 0}).fit(frame, specification)
    return {"base": base, "fit_logits": original, "extra_logits": additional, "inner_folds": inner,
            "fit_row_keys": frame.row_key.tolist(), "extra_row_keys": extra.row_key.tolist()}


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    previous_path = folder/"prior-joint-verification.json"
    previous = json.loads(previous_path.read_text())
    require(previous["selection_sha256"] == digest(study.PREVIOUS)
            and previous["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_prior_joint_transfer.py")), "Previous real-data verification changed")
    inputs = study.load_inputs()
    _, train, test, extra, arrays, lookup, manifest = inputs
    signature = study.fingerprint(inputs)
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k, v in signature.items())
            and selection["plan"] == study.plan() and len(selection["results"]) == 10
            and selection["train_row_keys"] == train.row_key.tolist(), "Frozen real-physiology study changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train.group_key) & set(test.group_key) and set(extra.group_key) <= set(train.group_key)
            and not selection["test_used_for_selection"] and selection["synthetic_examples"] == 0
            and selection["minimum_cv_for_new_test_evaluation"] == .65, "Original task, real-data restriction or test boundary changed")
    input_audit = json.loads(study.INPUT_AUDIT.read_text())
    require(input_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_physiology_pairs.py"))
            and input_audit["actual_raw_windows_independently_rebuilt"] == 2888
            and input_audit["missing_cases_dropped"] == input_audit["interpolated_bins"] == 0, "Independent actual waveform evidence changed")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    specification = study.core_candidate(manifest)
    caches, core = [], np.empty(len(train), dtype=object)
    for number, (fit, val) in enumerate(folds):
        fitting, validation = train.iloc[fit], train.iloc[val]
        eligible = extra[extra.group_key.isin(set(fitting.group_key))]
        require(not set(validation.group_key) & set(eligible.group_key), "Extra reports from outer validation people entered fitting")
        path = study.DIRECTORY/"bases"/f"fold-{number}.joblib"
        metadata = json.loads(path.with_suffix(".json").read_text())
        saved = joblib.load(path)
        require(metadata["signature"] == signature and metadata["cache_sha256"] == digest(path)
                and metadata["fit_row_keys"] == fitting.row_key.tolist()
                and metadata["validation_row_keys"] == validation.row_key.tolist()
                and metadata["extra_eligible_row_keys"] == eligible.row_key.tolist(), "Nested offset metadata changed")
        fresh = independent_offsets(fitting, eligible, specification)
        for key in ("fit_logits", "extra_logits"):
            torch.testing.assert_close(fresh[key], saved[key], rtol=0, atol=0)
        require(fresh["inner_folds"] == saved["inner_folds"] == metadata["inner_folds"], "Inner native/extra participant membership changed")
        for key, value in fresh["base"].model.state_dict().items():
            torch.testing.assert_close(value, saved["base"].model.state_dict()[key], rtol=0, atol=0)
        core[val] = fresh["base"].global_predict(validation)
        caches.append(fresh)
        print(f"Independent real native/extra baseline offsets {number+1}/5", flush=True)
    parent = json.loads(study.PREVIOUS.read_text())
    for row in selection["results"]:
        c, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(c in study.plan() and len(predicted) == 487 and set(predicted) <= {f"Borg {v}" for v in range(11)}, "OOF recipe or full denominator changed")
        scores = [float(accuracy_score(train.iloc[val].label, predicted[val])) for _, val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
                and float(accuracy_score(train.label, predicted)) == row["pooled_oof_accuracy"], "Original-person OOF accuracy changed")
        if c["algorithm"] == "previous_real_control":
            old = next(r for r in parent["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            np.testing.assert_array_equal(predicted, old["oof_predictions"])
            if c["id"] == "phys-pair-000":
                np.testing.assert_array_equal(core, predicted)
            continue
        require(len(row["folds"]) == 5, "A native grouped fold is missing")
        for number, (fit, val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json").read_text())
            eligible = extra[extra.group_key.isin(set(train.iloc[fit].group_key))]
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == c
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist()
                    and saved["extra_eligible_row_keys"] == eligible.row_key.tolist(), "Saved physiological fold changed")
            np.testing.assert_array_equal(saved["predicted"], predicted[val])
            counts = saved["training_summary"]
            expected_extra = len(eligible) if c["include_extra_actual_reports"] else 0
            require(counts["original_native_targets"] == len(fit) and counts["additional_actual_targets"] == expected_extra
                    and counts["total_actual_targets"] == len(fit)+expected_extra
                    and counts["synthetic_examples"] == counts["artificial_input_masks"] == counts["missing_native_cases_dropped"] == 0, "Real actual training counts changed")
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"] and selection["best_cv_accuracy"] == winner["accuracy_mean"], "Winner differs from declared grouped CV")
    new = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    best = max(new, key=lambda r: r["accuracy_mean"])
    augmented = max((r for r in new if r["candidate"]["include_extra_actual_reports"]), key=lambda r: r["accuracy_mean"])
    matched = next(r for r in new if not r["candidate"]["include_extra_actual_reports"]
        and r["candidate"]["waveform_view"] == augmented["candidate"]["waveform_view"]
        and r["candidate"]["epochs"] == augmented["candidate"]["epochs"])
    selected = {r["candidate"]["id"]: r for r in (best, augmented, matched)}
    actual_visits = 0
    for row in selected.values():
        c = row["candidate"]
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            eligible = extra[extra.group_key.isin(set(fitting.group_key))]
            native_windows = study.select_windows(arrays, lookup, fitting.row_key)
            extra_windows = study.select_windows(arrays, lookup, eligible.row_key)
            validation_windows = study.select_windows(arrays, lookup, validation.row_key)
            expected = pd.concat([fitting, eligible], ignore_index=True) if c["include_extra_actual_reports"] else fitting
            seen = []
            def observe(features, windows, current, prior):
                pd.testing.assert_frame_equal(features, expected[specification["features"]])
                for name in windows:
                    real = np.concatenate([native_windows[name], extra_windows[name]]) if c["include_extra_actual_reports"] else native_windows[name]
                    np.testing.assert_array_equal(windows[name], real)
                np.testing.assert_array_equal(current, expected.label.str.removeprefix("Borg ").to_numpy(int))
                np.testing.assert_array_equal(prior, expected.prior_borg.to_numpy(int))
                seen.append(len(current))
            before = {k: v.clone() for k, v in caches[number]["base"].model.state_dict().items()}
            with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial histories prohibited")), patch("torch.rand", side_effect=AssertionError("Artificial masking prohibited")):
                model = study.PhysiologyPairBorg(c).fit(fitting, eligible, native_windows, extra_windows, specification, caches[number], observe)
            require(seen == [len(expected)], "Actual raw feature/target observer was bypassed")
            actual_visits += len(expected)
            predicted = model.predict(validation, validation_windows)
            np.testing.assert_array_equal(predicted, np.asarray(row["oof_predictions"])[val])
            require(model.loss_endpoints == row["folds"][number]["loss_endpoints"], "Training loss endpoints failed exact reproduction")
            runtime = validation[model.input_features]
            np.testing.assert_array_equal(model.predict(runtime, validation_windows), predicted)
            require(all(torch.equal(value, model.base.model.state_dict()[key]) for key, value in before.items())
                    and not set(vars(model)) & {"fit_logits", "extra_logits", "inner_folds", "windows", "row_keys", "extra", "histories", "pool"}, "Baseline changed or query model stores current training records")
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"real-physiology.joblib"
                joblib.dump(model, path)
                np.testing.assert_array_equal(joblib.load(path).predict(runtime, validation_windows), predicted)
            print(f"Independent real physiological refit {c['id']} fold {number+1}/5", flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A physiological model crossed the test gate: freeze and evaluate its full original-179 artifact next")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous["best_verified_test_accuracy"], "Retained verified test model changed")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(), "verification_code_sha256": digest(Path(__file__)),
        "selection_sha256": digest(selection_path), "previous_verification_sha256": digest(previous_path),
        "input_verification_sha256": digest(study.INPUT_AUDIT), "public_real_data_policy_sha256": digest(study.source.POLICY),
        "independent_nested_native_baselines": 5, "inner_person_folds_per_baseline": 3,
        "all_10_oof_recipes_recomputed": True, "inherited_real_controls_reproduced": 2,
        "best_new_candidate_id": best["candidate"]["id"], "best_new_cv_accuracy": best["accuracy_mean"],
        "best_with_extra_actual_reports_id": augmented["candidate"]["id"], "best_with_extra_actual_reports_cv": augmented["accuracy_mean"],
        "matching_without_extra_reports_id": matched["candidate"]["id"], "matching_without_extra_reports_cv": matched["accuracy_mean"],
        "native_recipes_independently_refitted": sorted(selected), "grouped_folds_per_refit": 5,
        "actual_report_visits_checked_during_refits": actual_visits, "raw_inputs_and_targets_observed_during_refits": True,
        "extra_targets_only_from_each_fold_fitting_people": True, "artificial_history_and_input_masking_disabled": True,
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"], "new_test_gate_passed": False,
        "original_training_cases": 487, "original_test_cases": 179, "best_verified_test_correct": incumbent["correct"],
        "best_verified_test_accuracy": incumbent["accuracy"], "target_accuracy": .8, "achieved": False,
        "scope": "Exact native Borg on all original cases. Real current/prior physiological sequences, naturally missing inputs and optional 56 original fitting-person reports. No synthetic windows, current/future target inputs, artificial masks, label conversion, easier denominator or test selection."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
