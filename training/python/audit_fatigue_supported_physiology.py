"""Reproduce supported probability anchors and real-data grouped training."""
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

import fatigue_supported_physiology as study
from audit_fatigue_physiology_pair_learning import independent_offsets
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent


def require(value, reason):
    if not value:
        raise ValueError(reason)


def validate():
    inputs = study.load_inputs()
    _, train, test, extra, arrays, lookup, manifest = inputs
    signature = study.fingerprint(inputs)
    previous = json.loads(study.PREVIOUS_AUDIT.read_text())
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k, v in signature.items())
            and selection["plan"] == study.plan() and len(selection["results"]) == 11
            and selection["train_row_keys"] == train.row_key.tolist(), "Frozen supported native recipe or source changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train.group_key) & set(test.group_key) and set(extra.group_key) <= set(train.group_key)
            and not selection["test_used_for_selection"] and selection["synthetic_examples"] == 0
            and selection["minimum_cv_for_new_test_evaluation"] == .65, "Original native task, real observations or holdout changed")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    specification = study.parent.core_candidate(manifest)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    fresh_caches, core = [], np.empty(len(train), dtype=object)
    for number, (fit, val) in enumerate(folds):
        fitting, validation = train.iloc[fit], train.iloc[val]
        eligible = extra[extra.group_key.isin(set(fitting.group_key))]
        require(not set(validation.group_key) & set(eligible.group_key), "Extra outcomes leaked outer held people")
        cache_path = study.parent.DIRECTORY/"bases"/f"fold-{number}.joblib"
        metadata = json.loads(cache_path.with_suffix(".json").read_text())
        require(metadata["signature"] == signature["parent_signature"] and metadata["cache_sha256"] == digest(cache_path)
                and metadata["fit_row_keys"] == fitting.row_key.tolist() and metadata["validation_row_keys"] == validation.row_key.tolist()
                and metadata["extra_eligible_row_keys"] == eligible.row_key.tolist(), "Previously verified nested cache changed")
        saved = joblib.load(cache_path)
        fresh = independent_offsets(fitting, eligible, specification)
        require(fresh["inner_folds"] == saved["inner_folds"] == metadata["inner_folds"], "Inner original/extra membership changed")
        for key in ("fit_logits", "extra_logits"):
            torch.testing.assert_close(fresh[key], saved[key], rtol=0, atol=0)
            raw = fresh[key]
            probabilities = torch.softmax(raw, dim=1)
            for mass in (0., .05):
                anchor = study.supported_anchor(raw, mass)
                # Independent probability-space calculation, rather than logaddexp.
                torch.testing.assert_close(anchor.exp(), probabilities*(1-mass)+mass/21, rtol=1e-12, atol=1e-15)
                np.testing.assert_array_equal(anchor.argmax(dim=1), raw.argmax(dim=1))
                if mass:
                    require(bool((anchor.exp() >= mass/21-1e-15).all()), "Unseen native classes lost finite probability support")
        for key, value in fresh["base"].model.state_dict().items():
            torch.testing.assert_close(value, saved["base"].model.state_dict()[key], rtol=0, atol=0)
        core[val] = fresh["base"].global_predict(validation)
        fresh_caches.append(fresh)
        print(f"Independent native probability anchor and nested baseline {number+1}/5", flush=True)
    parent = json.loads((study.parent.DIRECTORY/"selection.json").read_text())
    for row in selection["results"]:
        candidate, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted) <= {f"Borg {v}" for v in range(11)}, "OOF native outputs or scope changed")
        scores = [float(accuracy_score(train.iloc[val].label, predicted[val])) for _, val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
                and float(accuracy_score(train.label, predicted)) == row["pooled_oof_accuracy"], "Native OOF score changed")
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in parent["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted, old["oof_predictions"])
            if candidate["id"] == "supported-phys-000":
                np.testing.assert_array_equal(predicted, core)
            continue
        for number, (fit, val) in enumerate(folds):
            eligible = extra[extra.group_key.isin(set(train.iloc[fit].group_key))]
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            cache_path = study.parent.DIRECTORY/"bases"/f"fold-{number}.joblib"
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist() and saved["validation_row_keys"] == train.iloc[val].row_key.tolist()
                    and saved["extra_eligible_row_keys"] == eligible.row_key.tolist() and saved["nested_offset_cache_sha256"] == digest(cache_path), "Saved supported native fitting data changed")
            np.testing.assert_array_equal(saved["predicted"], predicted[val])
            counts = saved["training_summary"]
            require(counts["original_native_targets"] == len(fit) and counts["additional_actual_targets"] == len(eligible)
                    and counts["total_actual_targets"] == len(fit)+len(eligible)
                    and counts["original_weight_sum"] == len(fit) and counts["extra_weight_sum"] == len(eligible)*candidate["extra_report_weight"]
                    and not counts["label_smoothing"] and counts["unchanged_integer_targets"]
                    and counts["synthetic_examples"] == counts["artificial_input_masks"] == counts["missing_native_cases_dropped"] == 0, "Targets, real report weights or training counts changed")
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"], "Winner differs from frozen participant-CV rule")
    new = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    best = max(new, key=lambda r: r["accuracy_mean"])
    supported = max((r for r in new if r["candidate"]["anchor_uniform_mass"] > 0), key=lambda r: r["accuracy_mean"])
    matched = next(r for r in new if r["candidate"]["anchor_uniform_mass"] == 0
        and r["candidate"]["correction_penalty"] == supported["candidate"]["correction_penalty"]
        and r["candidate"]["extra_report_weight"] == supported["candidate"]["extra_report_weight"])
    selected = {r["candidate"]["id"]: r for r in (best, supported, matched)}
    actual_visits, loss_calls = 0, 0
    for row in selected.values():
        candidate = row["candidate"]
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            eligible = extra[extra.group_key.isin(set(fitting.group_key))]
            expected = pd.concat([fitting, eligible], ignore_index=True)
            expected_target = torch.tensor(expected.label.str.removeprefix("Borg ").to_numpy(int)-expected.prior_borg.to_numpy(int)+10)
            native_windows = study.parent.select_windows(arrays, lookup, fitting.row_key)
            extra_windows = study.parent.select_windows(arrays, lookup, eligible.row_key)
            held_windows = study.parent.select_windows(arrays, lookup, validation.row_key)
            seen, seen_losses = [], []
            def observe(features, windows, current, prior, weights):
                pd.testing.assert_frame_equal(features, expected[specification["features"]])
                for name in windows:
                    np.testing.assert_array_equal(windows[name], np.concatenate([native_windows[name], extra_windows[name]]))
                np.testing.assert_array_equal(current, expected.label.str.removeprefix("Borg ").to_numpy(int))
                np.testing.assert_array_equal(prior, expected.prior_borg.to_numpy(int))
                np.testing.assert_array_equal(weights[:len(fitting)], np.ones(len(fitting)))
                np.testing.assert_array_equal(weights[len(fitting):], np.full(len(eligible), candidate["extra_report_weight"]))
                seen.append(len(current))
            real_loss = torch.nn.functional.cross_entropy
            def observe_loss(logits, target, **kwargs):
                torch.testing.assert_close(target, expected_target, rtol=0, atol=0)
                require(target.dtype == torch.long and not kwargs.get("label_smoothing", 0), "Actual native targets were altered or smoothed")
                seen_losses.append(1)
                return real_loss(logits, target, **kwargs)
            before = {k: v.clone() for k, v in fresh_caches[number]["base"].model.state_dict().items()}
            with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial histories prohibited")), patch("torch.rand", side_effect=AssertionError("Artificial input masks prohibited")), patch("torch.nn.functional.cross_entropy", side_effect=observe_loss):
                model = study.SupportedPhysiologyBorg(candidate).fit(fitting, eligible, native_windows, extra_windows,
                    specification, fresh_caches[number], observe)
            require(seen == [len(expected)] and len(seen_losses) == candidate["epochs"], "Raw input/target observer was bypassed")
            actual_visits += len(expected)
            loss_calls += len(seen_losses)
            predicted = model.predict(validation, held_windows)
            np.testing.assert_array_equal(predicted, np.asarray(row["oof_predictions"])[val])
            require(model.loss_endpoints == row["folds"][number]["loss_endpoints"], "Supported model losses failed exact reproduction")
            context, raw_offsets = study.parent.base_features(model.base, validation)
            offsets = study.supported_anchor(raw_offsets, candidate["anchor_uniform_mass"])
            with torch.no_grad():
                correction = study.bounded_correction(model.network(study.parent.normalize_windows(held_windows, candidate), context.float(), offsets), candidate["maximum_logit_correction"])
            require(float(correction.abs().max()) <= 3. and bool(torch.isfinite(correction).all()), "Physiological correction exceeded its bound")
            require(all(torch.equal(value, model.base.model.state_dict()[key]) for key, value in before.items())
                    and not set(vars(model)) & {"fit_logits", "extra_logits", "inner_folds", "windows", "row_keys", "extra", "pool", "histories"}, "Native baseline changed or inference stores current training data")
            runtime = validation[model.input_features]
            np.testing.assert_array_equal(model.predict(runtime, held_windows), predicted)
            with tempfile.TemporaryDirectory() as directory:
                artifact = Path(directory)/"actual-supported-physiology.joblib"
                joblib.dump(model, artifact)
                np.testing.assert_array_equal(joblib.load(artifact).predict(runtime, held_windows), predicted)
            print(f"Independent supported physiological refit {candidate['id']} fold {number+1}/5", flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A supported model crossed the test gate: freeze and evaluate its original-179 artifact next")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous["best_verified_test_accuracy"], "Retained original test model changed")
    return {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(), "verification_code_sha256": digest(Path(__file__)),
        "selection_sha256": digest(path), "previous_verification_sha256": digest(study.PREVIOUS_AUDIT), "diagnostic_sha256": digest(study.DIAGNOSTIC),
        "public_real_data_policy_sha256": digest(study.parent.source.POLICY),
        "independent_nested_native_baselines": 5, "inner_person_folds_per_baseline": 3,
        "all_11_oof_recipes_recomputed": True, "inherited_real_controls_reproduced": 3,
        "finite_support_probabilities_independently_checked": True, "initial_argmax_preserved": True,
        "best_new_candidate_id": best["candidate"]["id"], "best_new_cv_accuracy": best["accuracy_mean"],
        "best_positive_floor_candidate_id": supported["candidate"]["id"], "best_positive_floor_cv_accuracy": supported["accuracy_mean"],
        "matched_zero_floor_candidate_id": matched["candidate"]["id"], "matched_zero_floor_cv_accuracy": matched["accuracy_mean"],
        "native_recipes_independently_refitted": sorted(selected), "grouped_folds_per_refit": 5,
        "actual_report_visits_checked": actual_visits, "integer_target_loss_calls_observed": loss_calls,
        "label_smoothing_disabled": True, "real_waveforms_and_weights_observed_during_refits": True,
        "extra_targets_only_from_each_fold_fitting_people": True, "artificial_history_and_input_masking_disabled": True,
        "winner_id": selection["winner_id"], "best_cv_accuracy": winner["accuracy_mean"], "new_test_gate_passed": False,
        "original_training_cases": 487, "original_test_cases": 179, "best_verified_test_correct": incumbent["correct"],
        "best_verified_test_accuracy": incumbent["accuracy"], "target_accuracy": .8, "achieved": False,
        "scope": "Unchanged actual integer Borg targets and exact original cases. Only model probabilities are regularized. Original person-disjoint folds, finite bounded corrections and actual public native/extra observations; no synthetic inputs, altered labels, artificial masks or test tuning."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = validate()
    if arguments.output:
        arguments.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
