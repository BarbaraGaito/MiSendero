"""Verify current 80% research evidence without changing targets or models."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from common.calibrated_network import predict_calibrated_network
from fatigue_dynamics import load_inputs
from fatigue_features import RESEARCH
from public_sources import OUTPUT, ROOT, digest, verify_source_snapshot
from validate_fatigue_release import validate as validate_incumbent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def snapshot(path):
    data = path.read_bytes()
    try:
        return json.loads(data), hashlib.sha256(data).hexdigest()
    except json.JSONDecodeError:
        # A live trainer keeps a complete temporary checkpoint before writing
        # the main report. Read that snapshot if the main write is in flight.
        recovery = path.with_suffix(".tmp")
        if recovery.exists():
            data = recovery.read_bytes()
            return json.loads(data), hashlib.sha256(data).hexdigest()
        # Other trainers write the main report directly. A transient read
        # during that write does not mean that the live trainer stopped.
        for attempt in range(5):
            time.sleep(.05)
            data = path.read_bytes()
            try:
                return json.loads(data), hashlib.sha256(data).hexdigest()
            except json.JSONDecodeError:
                if attempt == 4:
                    raise


def validate():
    verify_source_snapshot("fatigue")
    incumbent = validate_incumbent()
    frame, train, test, manifest, original_protocol = load_inputs()
    original = pd.read_csv(OUTPUT / "fatigue/dataset.csv", dtype={"label": str})
    require(frame["label"].tolist() == original["label"].tolist(), "Native labels changed")
    require(len(frame) == 666 and len(train) == 487 and len(test) == 179, "Original denominators changed")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    result = {"version": 1, "verified_at": datetime.now(timezone.utc).isoformat(), "target_accuracy": .8,
              "required_correct_of_179": 144, "best_verified_test_accuracy": incumbent["accuracy"],
              "best_verified_test_correct": incumbent["correct"], "achieved": False,
              "native_labels_and_original_participant_holdout_unchanged": True, "experiments": {}, "test_evaluations": {}}
    policy_path = ROOT / "docs/fatigue-80-2026-10-25/public-real-data-policy.json"
    policy = json.loads(policy_path.read_text()) if policy_path.exists() else {}
    archive_only = set(policy.get("archive_only_studies_with_artificial_input_training", []))
    result["real_public_data_policy"] = {"sha256": digest(policy_path) if policy else None,
        "archive_only_studies_not_refitted": sorted(archive_only)}
    sequence_observations = None
    for name in ("expanded-public-history-gate-80-v1", "cadence-ordered-residual-80-v1", "cadence-delta-regularization-80-v1", "cadence-full-delta-residual-80-v1", "cadence-recent-native-gate-80-v1", "cadence-binary-physiology-gate-80-v1", "change-gate-regularization-80-v1", "public-change-gate-transfer-80-v1", "observed-change-factorization-80-v1", "causal-transition-memory-80-v1", "domain-aligned-history-transfer-80-v1", "shoulder-history-joint-transfer-80-v1", "catboost-schedule-80-v1", "furukawa-pre-report-hr-transfer-80-v1", "resistance-history-joint-transfer-80-v1", "two-history-joint-transfer-80-v1", "emap-ordered-functions-80-v1", "emap-ordered-history-transfer-80-v1", "cadence-session-rest-transfer-80-v1", "cadence-association-transfer-80-v1", "cadence-compact-representation-80-v1", "cadence-physiology-transfer-80-v1", "real-mlp-hyperparameters-80-v1", "walking-source-teachers-80-v1", "supported-physiology-80-v1", "physiology-pair-learning-80-v1", "prior-conditioned-joint-transfer-80-v1", "survey-prior-teachers-80-v1", "runner-real-observations-80-v1", "source-transition-teachers-80-v1", "initialization-ensemble-80-v1", "compact-physiology-80-v1", "runner-supervised-transfer-80-v1", "runner-anchor-transfer-80-v1", "gaussian-process-80-v1", "conditional-native-borg-80-v1", "view-probability-ensemble-80-v1", "prior-view-augmentation-80-v1", "dynamics-80-v1", "dynamics-regression-80-v1", "online-calibration-80-v1", "body-context-80-v1", "auxiliary-transfer-80-v1", "phone-context-80-v1", "tabular-transfer-80-v1", "trajectory-bank-80-v1", "recurrent-feedback-80-v1", "source-specific-transfer-80-v1", "latent-curve-80-v1", "catboost-80-v1", "meta-adaptation-80-v1", "participant-weighting-80-v1", "augmented-observed-feedback-80-v1", "spectral-classification-80-v1", "gait-source-transfer-80-v1", "spectral-residual-80-v1", "gradient-adaptation-80-v1", "warm-sgd-80-v1", "joint-neural-transfer-80-v1", "frozen-source-transfer-80-v1", "temporal-transfer-80-v1"):
        directory = RESEARCH / name
        path = directory / "selection.json"
        if not path.exists():
            continue
        print(f"Verifying frozen study {name}", flush=True)
        evaluation_frame, evaluation_train, evaluation_test = frame, train, test
        if name == "phone-context-80-v1":
            import fatigue_phone_experiment as phone
            from fatigue_dynamics_experiment import DynamicsClassifier
            from fetch_geofatigue_context import DIRECTORY as phone_raw, METADATA_PATH
            evaluation_frame, evaluation_train, evaluation_test, phone_manifest, _ = phone.load_inputs()
            require(evaluation_train["row_key"].tolist() == train["row_key"].tolist()
                    and evaluation_test["row_key"].tolist() == test["row_key"].tolist(), "Phone original case identities changed")
            receipt = json.loads((phone_raw / "receipt.json").read_text(encoding="utf-8"))
            require(receipt["all_complete_and_verified"] and len(receipt["files"]) == receipt["expected_files"] == 125,
                    "Phone source download incomplete or unverified")
            require(phone_manifest["phone_receipt_sha256"] == digest(phone_raw / "receipt.json")
                    and phone_manifest["phone_metadata_sha256"] == digest(METADATA_PATH), "Phone source evidence changed")
            require(len(phone_manifest["phone_lineage"]) == 666, "Phone lineage denominator changed")
            for evidence in phone_manifest["phone_lineage"]:
                if evidence["latest_used_second_end"] is not None:
                    require(pd.Timestamp(evidence["latest_used_second_end"]) <= pd.Timestamp(evidence["prediction_time"]), "Phone window extends into future")
        selection, sha256 = snapshot(path)
        if name in archive_only:
            require(selection["test_used_for_selection"] is False
                    and selection["train_row_keys"] == train["row_key"].tolist(), "Archived experiment changed native membership")
            for row in selection["results"]:
                predicted = np.asarray(row["oof_predictions"])
                scores = [accuracy_score(train.iloc[val]["label"], predicted[val]) for _, val in folds]
                np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
                require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12, "Archived OOF metric changed")
            result["experiments"][name] = {"status": "archived_under_real_public_data_policy",
                "completed_candidates": len(selection["results"]), "selection_snapshot_sha256": sha256,
                "fresh_fitting_performed": False, "eligible_for_model_adoption": False}
            continue
        if name == "initialization-ensemble-80-v1":
            from audit_fatigue_initialization_ensemble import validate as validate_initializations
            result["initialization_ensemble"] = validate_initializations()
        if name == "source-transition-teachers-80-v1":
            from audit_fatigue_source_transitions import validate as validate_source_transitions
            result["source_transition_teachers"] = validate_source_transitions()
        if name == "runner-real-observations-80-v1":
            from audit_fatigue_runner_real_observations import validate as validate_real_runner
            result["runner_real_observations"] = validate_real_runner()
        if name == "survey-prior-teachers-80-v1":
            from audit_fatigue_survey_prior_teachers import validate as validate_survey_priors
            result["survey_prior_teachers"] = validate_survey_priors()
        if name == "prior-conditioned-joint-transfer-80-v1":
            from audit_fatigue_prior_joint_transfer import validate as validate_prior_joint
            result["prior_conditioned_joint_transfer"] = validate_prior_joint()
        if name == "physiology-pair-learning-80-v1":
            from audit_fatigue_physiology_pair_learning import validate as validate_physiology
            result["physiology_pair_learning"] = validate_physiology()
        if name == "supported-physiology-80-v1":
            from audit_fatigue_supported_physiology import validate as validate_supported_physiology
            result["supported_physiology"] = validate_supported_physiology()
        if name == "walking-source-teachers-80-v1":
            from audit_fatigue_walking_source_teachers import validate as validate_walking_teachers
            result["walking_source_teachers"] = validate_walking_teachers()
        if name == "real-mlp-hyperparameters-80-v1":
            from audit_fatigue_real_mlp_hyperparameters import validate as validate_real_hyperparameters
            result["real_mlp_hyperparameters"] = validate_real_hyperparameters()
        if name == "cadence-physiology-transfer-80-v1":
            from audit_fatigue_cadence_transfer import validate as validate_cadence
            result["cadence_physiology_transfer"] = validate_cadence()
        if name == "cadence-compact-representation-80-v1":
            from audit_fatigue_cadence_compact import validate as validate_compact_cadence
            result["cadence_compact_representation"] = validate_compact_cadence()
        if name == "expanded-public-history-gate-80-v1":
            from audit_fatigue_expanded_public_gate import validate as validate_expanded_gate
            gate_audit = validate_expanded_gate()
            result["expanded_public_gate"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "cadence-ordered-residual-80-v1":
            from audit_fatigue_cadence_ordered_residual import validate as validate_delta_regularization
            gate_audit = validate_delta_regularization()
            result["cadence_ordered_residual"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "cadence-delta-regularization-80-v1":
            from audit_fatigue_cadence_delta_regularization import validate as validate_delta_regularization
            gate_audit = validate_delta_regularization()
            result["cadence_delta_regularization"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "cadence-full-delta-residual-80-v1":
            from audit_fatigue_cadence_full_delta import validate as validate_full_delta
            gate_audit = validate_full_delta()
            result["cadence_full_delta_residual"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "cadence-recent-native-gate-80-v1":
            from audit_fatigue_cadence_recent_gate import validate as validate_recent_gate
            gate_audit = validate_recent_gate()
            result["cadence_recent_native_gate"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "cadence-binary-physiology-gate-80-v1":
            from audit_fatigue_cadence_binary_gate import validate as validate_cadence_binary_gate
            gate_audit = validate_cadence_binary_gate()
            result["cadence_binary_physiology_gate"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "change-gate-regularization-80-v1":
            from audit_fatigue_change_gate_regularization import validate as validate_change_gate_regularization
            gate_audit = validate_change_gate_regularization()
            result["change_gate_regularization_transfer"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "public-change-gate-transfer-80-v1":
            from audit_fatigue_public_change_gate import validate as validate_public_change_gate
            gate_audit = validate_public_change_gate()
            result["public_change_gate_transfer"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "observed-change-factorization-80-v1":
            from audit_fatigue_observed_change_factorization import validate as validate_observed_change_factorization
            change_audit = validate_observed_change_factorization()
            result["observed_change_factorization"] = change_audit
            if change_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": change_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    change_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "causal-transition-memory-80-v1":
            from audit_fatigue_causal_transition_memory import validate as validate_causal_transition_memory
            memory_audit = validate_causal_transition_memory()
            result["causal_transition_memory"] = memory_audit
            if memory_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": memory_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    memory_audit["new_test_evaluation"]["test_accuracy"])
                continue
        if name == "domain-aligned-history-transfer-80-v1":
            from audit_fatigue_domain_aligned_history import validate as validate_domain_aligned_history
            result["domain_aligned_history_transfer"] = validate_domain_aligned_history()
        if name == "shoulder-history-joint-transfer-80-v1":
            from audit_fatigue_shoulder_history_joint import validate as validate_shoulder_history
            result["shoulder_history_joint_transfer"] = validate_shoulder_history()
        if name == "catboost-schedule-80-v1":
            from audit_fatigue_catboost_schedule import validate as validate_catboost_schedule
            result["catboost_schedule"] = validate_catboost_schedule()
        if name == "furukawa-pre-report-hr-transfer-80-v1":
            from audit_fatigue_furukawa_hr_transfer import validate as validate_furukawa_hr
            result["furukawa_pre_report_hr_transfer"] = validate_furukawa_hr()
        if name == "resistance-history-joint-transfer-80-v1":
            from audit_fatigue_resistance_history_joint import validate as validate_resistance_history
            result["resistance_history_joint_transfer"] = validate_resistance_history()
        if name == "two-history-joint-transfer-80-v1":
            from audit_fatigue_two_history_joint import validate as validate_two_history_joint
            result["two_history_joint_backpropagation"] = validate_two_history_joint()
        if name == "emap-ordered-functions-80-v1":
            from audit_fatigue_emap_ordered_functions import validate as validate_emap_ordered
            result["emap_recorded_order_functions"] = validate_emap_ordered()
        if name == "emap-ordered-history-transfer-80-v1":
            from audit_fatigue_emap_history_transfer import validate as validate_emap_history
            result["emap_ordered_history"] = validate_emap_history()
        if name == "cadence-session-rest-transfer-80-v1":
            from audit_fatigue_cadence_session_rest import validate as validate_session_rest
            result["cadence_session_rest"] = validate_session_rest()
        if name == "cadence-association-transfer-80-v1":
            from audit_fatigue_cadence_association import validate as validate_association
            result["cadence_retrospective_association"] = validate_association()
        if name == "compact-physiology-80-v1":
            from audit_fatigue_compact_physiology import validate as validate_compact
            result["compact_physiology"] = validate_compact()
        if name == "runner-supervised-transfer-80-v1":
            from audit_fatigue_runner_transfer import validate as validate_runner
            result["runner_supervised_transfer"] = validate_runner(selection)
        if name == "runner-anchor-transfer-80-v1":
            from audit_fatigue_runner_anchor_transfer import validate as validate_runner_anchor
            result["runner_prior_anchor_transfer"] = validate_runner_anchor()
        if name == "gaussian-process-80-v1":
            from audit_fatigue_gaussian_process import validate as validate_gp
            result["gaussian_process"] = validate_gp(selection)
        if name == "conditional-native-borg-80-v1":
            from audit_fatigue_conditional_borg import validate as validate_conditional
            result["conditional_native_borg"] = validate_conditional(selection)
        if name == "view-probability-ensemble-80-v1":
            from audit_fatigue_view_ensemble import validate as validate_view_ensemble
            result["view_probability_ensemble"] = validate_view_ensemble(selection)
        if name == "prior-view-augmentation-80-v1":
            from audit_fatigue_prior_views import validate as validate_prior_views
            result["observed_prior_view_augmentation"] = validate_prior_views(selection, frame, train, test, manifest)
        if name == "temporal-transfer-80-v1":
            from audit_fatigue_temporal_transfer import validate as validate_temporal
            from fatigue_spectral_experiment import load_inputs as temporal_inputs
            temporal_frame, temporal_train, temporal_test, temporal_manifest, _ = temporal_inputs()
            require(temporal_train["row_key"].tolist() == train["row_key"].tolist()
                    and temporal_test["row_key"].tolist() == test["row_key"].tolist(), "Temporal study changed the native participant holdout")
            result["temporal_signal_transfer"] = validate_temporal(selection, temporal_frame, temporal_train, temporal_manifest)
        if name == "frozen-source-transfer-80-v1":
            import fatigue_frozen_source_transfer as frozen
            evaluation_frame, evaluation_train, evaluation_test, frozen_manifest, _ = frozen.spectral_inputs()
            external, source_manifest = frozen.source_inputs()
            signature = frozen.fingerprint(frozen_manifest, source_manifest)
            require(all(selection.get(k) == v for k, v in signature.items())
                    and selection["plan"] == frozen.plan(frozen_manifest, source_manifest["domains"])
                    and selection["source_plan"] == frozen.source_plan(), "Frozen source-transfer data/plan/code/runtime changed")
            require(selection["source_fitting_reports"] == len(external) == 520 and selection["external_test_used"] is False
                    and selection["native_momentary_target_merge"] is False and selection["synthetic_rows"] == 0
                    and selection["evaluation_denominator"] == 487 and selection["test_denominator"] == 179
                    and selection["minimum_cv_for_new_test_evaluation"] == .65
                    and evaluation_train["row_key"].tolist() == train["row_key"].tolist()
                    and evaluation_test["row_key"].tolist() == test["row_key"].tolist(), "Frozen source transfer changed supervision/holdout/gate")
            encoders = {}
            for specification in frozen.source_plan():
                path = directory / "encoders" / specification["id"]
                descriptor = json.loads((path / "descriptor.json").read_text())
                require(descriptor["signature"] == signature and descriptor["candidate"] == specification
                        and descriptor["model_sha256"] == digest(path / "model.joblib")
                        and descriptor["native_fractional_reports"] == 3 and descriptor["all_network_parameters_frozen"], "Saved frozen source encoder changed")
                encoder = joblib.load(path / "model.joblib")
                migration = descriptor.get("module_reference_migration")
                if migration is not None:
                    archive = path / "legacy-main-module"
                    legacy = json.loads((archive / "descriptor.json").read_text())
                    require(digest(archive / "model.joblib") == migration["legacy_model_sha256"] == legacy["model_sha256"]
                            and digest(archive / "descriptor.json") == migration["legacy_descriptor_sha256"]
                            and digest(Path(__file__).with_name("migrate_frozen_source_encoders.py")) == migration["migration_code_sha256"]
                            and type(encoder).__module__ == migration["new_module"] == "fatigue_frozen_source_transfer"
                            and {k: v for k, v in descriptor.items() if k not in ("model_sha256", "module_reference_migration")}
                            == {k: v for k, v in legacy.items() if k != "model_sha256"}, "Frozen source encoder module-reference migration changed its original evidence")
                refit = frozen.FrozenSourceEncoder(specification).fit(external)
                require(encoder.report_counts == refit.report_counts == descriptor["actual_source_report_counts"]
                        and sum(encoder.report_counts.values()) == 520
                        and not any(p.requires_grad for p in encoder.model.parameters()), "Source encoder used another fitting pool or remained trainable")
                for key, value in encoder.model.state_dict().items():
                    require(frozen.torch.equal(value, refit.model.state_dict()[key]), "Independent source pretraining differs from saved parameters")
                np.testing.assert_allclose(encoder.loss_endpoints, descriptor["loss_endpoints"], rtol=0, atol=1e-8)
                np.testing.assert_allclose(encoder.imputer.statistics_, refit.imputer.statistics_, rtol=0, atol=0, equal_nan=True)
                np.testing.assert_allclose(encoder.scaler.mean_, refit.scaler.mean_, rtol=0, atol=0)
                encoders[specification["id"]] = encoder
            winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
            for number, (fit, val) in enumerate(folds):
                fitting, validation = evaluation_train.iloc[fit], evaluation_train.iloc[val]
                evidence = selection["folds"][number]
                require(evidence["fit_row_keys"] == fitting["row_key"].tolist()
                        and evidence["validation_row_keys"] == validation["row_key"].tolist(), "Frozen source-transfer outer fold changed")
                with threadpool_limits(limits=1):
                    context, inner = frozen.inner_context(fitting, selection["core_candidate"])
                require(inner == evidence["inner_folds"], "Frozen source residual labels leaked their own participants")
                np.testing.assert_allclose(context, evidence["fit_context"], rtol=0, atol=1e-12)
                candidate = winner["candidate"]
                encoder = None if candidate["algorithm"] == "control" else encoders[candidate["source_encoder"]["id"]]
                population = {} if encoder is None else {key: value.detach().clone() for key, value in encoder.model.named_parameters()}
                refit = frozen.FrozenTransferBorg(candidate, encoder).fit(fitting, selection["core_candidate"])
                predicted = refit.predict(validation)
                np.testing.assert_array_equal(predicted, np.asarray(winner["oof_predictions"])[val])
                if encoder is not None:
                    require(all(frozen.torch.equal(population[key], value) for key, value in encoder.model.named_parameters()), "GeoFatigue correction fine-tuned the external frozen encoder")
            original_selection = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
            expected = next(r["oof_predictions"] for r in original_selection["results"] if r["candidate"]["id"] == "alternative-023")
            control = next(r["oof_predictions"] for r in selection["results"] if r["candidate"]["algorithm"] == "control")
            np.testing.assert_array_equal(control, expected)
            if winner["accuracy_mean"] < .65:
                require(not (directory / "evaluation/metrics.json").exists(), "Weak frozen-source selection bypassed its predeclared test gate")
            result["frozen_source_transfer"] = {"external_fitting_reports": 520, "source_only_encoders_verified": len(encoders),
                "source_and_normalization_weights_refitted_independently": True, "minimum_cv_for_new_test_evaluation": .65,
                "new_test_gate_passed": winner["accuracy_mean"] >= .65, "native_momentary_target_merge": False}
        if name in ("gradient-adaptation-80-v1", "warm-sgd-80-v1"):
            import fatigue_gradient_adaptation as gradient
            import fatigue_warm_sgd as warm
            from fatigue_online_calibration import temporal_metadata
            module = gradient if name == "gradient-adaptation-80-v1" else warm
            evaluation_frame, evaluation_train, evaluation_test, adaptation_manifest, _ = module.load_inputs()
            adaptation_contexts = module.load_contexts(evaluation_frame, adaptation_manifest)
            require(all(selection.get(k) == v for k, v in module.fingerprint(adaptation_manifest, adaptation_contexts).items()), "Personal gradient study inputs/source/context/software changed")
            expected_plan = gradient.plan(adaptation_manifest) if module is gradient else warm.plan()
            require(selection["plan"] == expected_plan and selection["synthetic_rows"] == 0
                    and selection["evaluation_denominator"] == 487 and selection["test_denominator"] == 179
                    and evaluation_train["row_key"].tolist() == train["row_key"].tolist()
                    and evaluation_test["row_key"].tolist() == test["row_key"].tolist(), "Personal gradient study changed targets or participant split")
            metadata = temporal_metadata(evaluation_frame, adaptation_manifest)
            positions = {key: i for i, key in enumerate(evaluation_frame["row_key"])}
            for scope, contexts in adaptation_contexts.items():
                for key, history in contexts.items():
                    now = metadata.iloc[positions[key]]
                    for earlier in history:
                        old = metadata.iloc[positions[earlier["row_key"]]]
                        age = (now["response_time"]-old["response_time"]).total_seconds()/60
                        require(now["group_key"] == old["group_key"] and now["session_start"] == old["session_start"]
                                and age == earlier["age_minutes"] and age >= 1, "Personal SGD consumed another person/current/future response")
                        if scope == "task":
                            require(now["task_start"] == old["task_start"], "Personal SGD mixed repeated terrains from distinct tasks")
            winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
            if module is gradient:
                require(digest(directory / "selection-source.py") == selection["code_sha256"], "Frozen MAML source copy changed")
                plan_snapshot = json.loads((directory / "frozen-plan.json").read_text())
                require(all(plan_snapshot.get(k) == selection.get(k) for k in plan_snapshot), "MAML frozen plan differs from the completed search")
                for row in selection["results"]:
                    for number, (fit, val) in enumerate(folds):
                        saved = json.loads((directory / "folds" / f"{row['candidate']['id']}-fold-{number}.json").read_text())
                        require(saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                                and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist()
                                and saved["candidate"] == row["candidate"] and saved["code_sha256"] == selection["code_sha256"]
                                and saved["dataset_sha256"] == selection["dataset_sha256"]
                                and saved["context_index_sha256"] == selection["context_index_sha256"], "MAML fold membership/inputs changed")
                        np.testing.assert_array_equal(saved["predicted"], np.asarray(row["oof_predictions"])[val])
            for number, (fit, val) in enumerate(folds):
                candidate = winner["candidate"]
                if module is gradient:
                    refit = gradient.GradientAdaptiveBorg(candidate).fit(evaluation_train.iloc[fit], adaptation_contexts[candidate["scope"]])
                    np.testing.assert_allclose(refit.training_loss_endpoints, winner["fold_training_loss_endpoints"][number], rtol=0, atol=1e-8)
                else:
                    require(selection["support_optimizer"] == "proximal_SGD", "Warm-start optimizer changed")
                    refit = warm.WarmPersonalBorg(candidate).fit(evaluation_train.iloc[fit], selection["core_candidate"])
                    evidence = selection["folds"][number]
                    require(evidence["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                            and evidence["validation_row_keys"] == train.iloc[val]["row_key"].tolist()
                            and evidence["base_fitting_iterations"] == refit.core.model[-1].n_iter_, "Warm-start fitting rows or base model changed")
                population = {key: value.detach().clone() for key, value in refit.model.named_parameters()}
                predicted = refit.predict(evaluation_train.iloc[val], evaluation_frame, adaptation_contexts[candidate["scope"]])
                np.testing.assert_array_equal(predicted, np.asarray(winner["oof_predictions"])[val])
                require(all(gradient.torch.equal(population[key], value) for key, value in refit.model.named_parameters()), "Personal inference mutated population weights")
            if module is warm:
                original_selection = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
                expected = next(r["oof_predictions"] for r in original_selection["results"] if r["candidate"]["id"] == "alternative-023")
                control = next(r["oof_predictions"] for r in selection["results"] if r["candidate"]["id"] == "warm-sgd-000")
                np.testing.assert_array_equal(control, expected)
        if name == "joint-neural-transfer-80-v1":
            import fatigue_joint_transfer as joint
            evaluation_frame, evaluation_train, evaluation_test, joint_manifest, _, external, joint_source_manifest = joint.load_inputs()
            require(all(selection.get(k) == v for k, v in joint.fingerprint(joint_manifest, joint_source_manifest).items())
                    and selection["plan"] == joint.plan(), "Frozen joint-source data/plan/source/runtime changed")
            require(selection["external_fitting_reports"] == len(external) == 520 and selection["external_test_used"] is False
                    and selection["native_momentary_target_merge"] is False and selection["synthetic_rows"] == 0
                    and selection["evaluation_denominator"] == 487 and selection["test_denominator"] == 179
                    and evaluation_train["row_key"].tolist() == train["row_key"].tolist()
                    and evaluation_test["row_key"].tolist() == test["row_key"].tolist(), "Combined source data changed original supervision/denominators")
            for number, (fit, val) in enumerate(folds):
                evidence = selection["folds"][number]
                require(evidence["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                        and evidence["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "Joint-source outer fold changed")
                require(len(evidence["inner_folds"]) == 3, "Joint-source inner baseline fold omitted")
                fitting = train.iloc[fit]
                for inner_evidence, (inner_fit, inner_val) in zip(evidence["inner_folds"], GroupKFold(n_splits=3).split(fitting, groups=fitting["group_key"])):
                    require(inner_evidence["fit_row_keys"] == fitting.iloc[inner_fit]["row_key"].tolist()
                            and inner_evidence["validation_row_keys"] == fitting.iloc[inner_val]["row_key"].tolist(), "Joint-source baseline offsets leaked their own person")
                winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
                refit = joint.JointBorg(winner["candidate"]).fit(evaluation_train.iloc[fit], external, selection["core_candidate"])
                np.testing.assert_array_equal(refit.predict(evaluation_train.iloc[val]), np.asarray(winner["oof_predictions"])[val])
            original_selection = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
            expected = next(r["oof_predictions"] for r in original_selection["results"] if r["candidate"]["id"] == "alternative-023")
            control = next(r["oof_predictions"] for r in selection["results"] if r["candidate"]["algorithm"] == "incumbent_control")
            np.testing.assert_array_equal(control, expected)
            supervised = [r for r in selection["results"] if r["candidate"].get("auxiliary_weight", 0) > 0]
            result["joint_source_comparison"] = {"external_fitting_reports": 520, "source_specific_auxiliary_heads": 4,
                "winner_auxiliary_weight": winner["candidate"].get("auxiliary_weight"),
                "best_cv_with_auxiliary_supervision": max(r["accuracy_mean"] for r in supervised),
                "direct_momentary_label_merge": False, "external_reserved_people_used": False}
        if name == "spectral-residual-80-v1":
            import fatigue_spectral_correction as correction
            evaluation_frame, evaluation_train, evaluation_test, correction_manifest, _ = correction.load_inputs()
            require(selection["code_sha256"] == digest(Path(correction.__file__))
                    and selection["parent_fingerprint"] == correction.spectral_fingerprint(correction_manifest)
                    and selection["plan"] == correction.plan(correction_manifest)
                    and selection["core_candidate"] == correction.core_candidate(correction_manifest), "Nested residual fitting inputs changed")
            require(selection["synthetic_rows"] == 0 and selection["nested_participant_cross_fitting"]
                    and selection["evaluation_denominator"] == 487 and selection["test_denominator"] == 179
                    and evaluation_train["row_key"].tolist() == train["row_key"].tolist()
                    and evaluation_test["row_key"].tolist() == test["row_key"].tolist(), "Nested correction changed supervision or cohort")
            winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
            base_predictions = np.empty(len(train), dtype=object)
            winner_predictions = np.empty(len(train), dtype=object)
            for number, (fit, val) in enumerate(folds):
                fitting, validation = evaluation_train.iloc[fit], evaluation_train.iloc[val]
                evidence = selection["folds"][number]
                require(evidence["fit_row_keys"] == fitting["row_key"].tolist()
                        and evidence["validation_row_keys"] == validation["row_key"].tolist(), "Nested residual outer fold changed")
                with threadpool_limits(limits=1):
                    fit_context, inner = correction.inner_context(fitting, selection["core_candidate"])
                    core = correction.DynamicsClassifier(selection["core_candidate"]).fit(fitting)
                    val_context = correction.base_context(core, validation)
                require(inner == evidence["inner_folds"], "Residual correction used another person's current label in its own base prediction")
                np.testing.assert_allclose(fit_context, evidence["fit_context"], rtol=0, atol=1e-12)
                np.testing.assert_allclose(val_context, evidence["validation_context"], rtol=0, atol=1e-12)
                baseline = np.asarray([f"Borg {i}" for i in val_context[:, 0].astype(int)])
                base_predictions[val] = baseline
                if winner["candidate"]["algorithm"] == "control":
                    winner_predictions[val] = baseline
                else:
                    data = correction.with_context(fitting, fit_context)
                    target = fitting["label"].str.removeprefix("Borg ").to_numpy(int)-fit_context[:, 0].astype(int)
                    inputs = correction.with_context(validation, val_context)
                    with threadpool_limits(limits=1):
                        corrector = correction.fit_corrector(data, target, winner["candidate"])
                    probability = corrector.predict_proba(inputs[winner["candidate"]["features"]])
                    winner_predictions[val] = correction.corrected_predictions(val_context[:, 0], probability, corrector.classes_, winner["candidate"]["zero_margin"])
            np.testing.assert_array_equal(winner_predictions, winner["oof_predictions"])
            original_selection = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
            expected = next(r["oof_predictions"] for r in original_selection["results"] if r["candidate"]["id"] == "alternative-023")
            np.testing.assert_array_equal(base_predictions, expected)
            for row in selection["results"]:
                predicted = np.asarray(row["oof_predictions"])
                truth = train["label"].to_numpy()
                require(row["changed_decisions"] == int((predicted != base_predictions).sum())
                        and row["corrected_errors"] == int(((predicted == truth) & (base_predictions != truth)).sum())
                        and row["spoiled_correct_decisions"] == int(((predicted != truth) & (base_predictions == truth)).sum()), "Residual correction diagnostics changed")
        if name == "gait-source-transfer-80-v1":
            import fatigue_gait_transfer as gait
            evaluation_frame, evaluation_train, evaluation_test, gait_manifest, _, source, source_manifest = gait.load_inputs()
            require(evaluation_train["row_key"].tolist() == train["row_key"].tolist()
                    and evaluation_test["row_key"].tolist() == test["row_key"].tolist()
                    and evaluation_frame["label"].tolist() == frame["label"].tolist(), "Gait transfer changed the original evaluation cases")
            signature = gait.fingerprint(gait_manifest, source_manifest)
            require(all(selection.get(k) == v for k, v in signature.items())
                    and selection["plan"] == gait.plan(gait_manifest), "Frozen gait transfer source/plan/participants changed")
            require(selection["external_test_used"] is False and selection["teachers_use_geofatigue_labels"] is False
                    and selection["original_momentary_target_merge"] is False and len(source) == 48, "Gait source labels became momentary supervision or leaked holdout")
            winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
            for fit, val in folds:
                with threadpool_limits(limits=1):
                    model = gait.GaitTransferBorg(winner["candidate"], source).fit(evaluation_train.iloc[fit])
                np.testing.assert_array_equal(model.predict(evaluation_train.iloc[val]), np.asarray(winner["oof_predictions"])[val])
            control = next((r for r in selection["results"] if r["candidate"]["id"] == "gait-transfer-000"), None)
            if control is not None:
                original_selection = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
                expected = next(r for r in original_selection["results"] if r["candidate"]["id"] == "alternative-023")
                np.testing.assert_array_equal(control["oof_predictions"], expected["oof_predictions"])
        if name == "spectral-classification-80-v1":
            import fatigue_spectral_experiment as spectral
            from fetch_geofatigue_context import DIRECTORY as phone_raw
            evaluation_frame, evaluation_train, evaluation_test, spectral_manifest, _ = spectral.load_inputs()
            require(evaluation_train["row_key"].tolist() == train["row_key"].tolist()
                    and evaluation_test["row_key"].tolist() == test["row_key"].tolist()
                    and evaluation_frame["label"].tolist() == frame["label"].tolist(), "Spectra changed original native target cases")
            signature = {**spectral.fingerprint(spectral_manifest), "plan": spectral.plan(spectral_manifest),
                         "train_row_keys": train["row_key"].tolist()}
            require(all(selection.get(k) == v for k, v in signature.items()), "Frozen spectral data/plan/source/runtime changed")
            require(selection["synthetic_rows"] == 0 and selection["evaluation_denominator"] == 487
                    and selection["test_denominator"] == 179, "Spectral evaluation denominator or native targets changed")
            evidence = json.loads((spectral.SPECTRAL_DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
            require(evidence["bin_duration_ms"] == 100 and evidence["no_gap_interpolation"]
                    and evidence["timestamps_in_cache"] == "explicit nanoseconds"
                    and evidence["periodogram_grid"] == {"minimum_hz": .15, "maximum_hz": 4.5, "points": 1024, "floating_mean": True}, "Spectral time/frequency policy changed")
            receipt = json.loads((phone_raw / "receipt.json").read_text(encoding="utf-8"))
            require(digest(phone_raw / "receipt.json") == evidence["phone_receipt_sha256"]
                    and receipt["all_complete_and_verified"], "Spectral original sources incomplete or changed")
            source_hashes = {r["filename"]: r["sha256"] for r in receipt["files"]}
            require(len(evidence["phone_lineage"]) == 666
                    and set(r["row_key"] for r in evidence["phone_lineage"]) == set(frame["row_key"]), "Spectral lineage changed target cases")
            for row in evidence["phone_lineage"]:
                latest = row["latest_available_complete_bin_end"]
                require(latest is None or pd.Timestamp(latest) <= pd.Timestamp(row["prediction_time"]), "Spectral window contains future samples")
                for source in row["original_phone_files"]:
                    require(source_hashes[source["filename"]] == source["sha256"], "Spectral lineage references another source")
            for row in selection["results"]:
                for fold, (fit, val) in enumerate(folds):
                    saved = json.loads((directory / "folds" / f"{row['candidate']['id']}-fold-{fold}.json").read_text(encoding="utf-8"))
                    require(saved["signature"] == signature and saved["candidate"] == row["candidate"]
                            and saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                            and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "Spectral fold membership or fitting inputs changed")
                    np.testing.assert_array_equal(saved["predicted"], np.asarray(row["oof_predictions"])[val])
            winner = max(selection["results"], key=lambda row: row["accuracy_mean"])
            for fit, val in folds:
                with threadpool_limits(limits=1):
                    refit = spectral.SpectralBorg(winner["candidate"]).fit(evaluation_train.iloc[fit])
                np.testing.assert_array_equal(refit.predict(evaluation_train.iloc[val]), np.asarray(winner["oof_predictions"])[val])
            for number, source, source_id in ((0, "calibrated-alternatives-v1", "alternative-023"), (1, "catboost-80-v1", None)):
                control = next((r for r in selection["results"] if r["candidate"]["id"] == f"spectra-{number:03d}"), None)
                if control is not None:
                    original_selection = json.loads((RESEARCH / source / "selection.json").read_text())
                    expected = (next(r for r in original_selection["results"] if r["candidate"]["id"] == source_id) if source_id
                                else max(original_selection["results"], key=lambda r: r["accuracy_mean"]))
                    np.testing.assert_array_equal(control["oof_predictions"], expected["oof_predictions"])
            result["spectral_inputs"] = {"original_responses": 666, "new_features": len(evidence["features"]),
                                         "bins_ms": 100, "interpolated_rows": 0, "future_samples_used": False,
                                         "current60_coverage": int(evaluation_frame["spectral60_observed_bins"].gt(0).sum())}
        if name == "meta-adaptation-80-v1":
            import fatigue_meta_adaptation as meta
            from public_sources import RAW
            metadata = meta.temporal_metadata(frame, manifest)
            histories = {scope: meta.context_keys(frame, metadata, scope) for scope in ("task", "session")}
            context_hash = hashlib.sha256(json.dumps(histories, sort_keys=True, allow_nan=False).encode()).hexdigest()
            require(selection["code_sha256"] == digest(Path(meta.__file__)) and selection["plan"] == meta.plan(manifest)
                    and selection["dataset_sha256"] == manifest["dataset_sha256"], "Meta-adaptation fitting inputs changed")
            require(selection["context_index_sha256"] == context_hash
                    and selection["session_metadata_sha256"] == digest(RAW / "geofatigue/session_metadata.json")
                    and selection["dynamics_provenance_sha256"] == digest(RESEARCH / "dynamics-80-v1/provenance.json"), "Meta-adaptation chronological support changed")
            require(selection["history_metadata_code_sha256"] == digest(Path(__file__).with_name("fatigue_online_calibration.py"))
                    and selection["dynamics_plan_code_sha256"] == digest(Path(__file__).with_name("fatigue_dynamics_experiment.py"))
                    and selection["torch_version"] == str(meta.torch.__version__), "Meta-adaptation dependencies/runtime changed")
            require(selection["synthetic_rows"] == 0 and selection["validation_person_outcomes_are_inputs_only_when_actually_recorded_earlier"], "Meta-adaptation feedback scope changed")
            positions = {key: i for i, key in enumerate(frame["row_key"])}
            for scope, history in histories.items():
                for key, earlier in history.items():
                    current = metadata.iloc[positions[key]]
                    for evidence in earlier:
                        old = metadata.iloc[positions[evidence["row_key"]]]
                        require(old["group_key"] == current["group_key"] and old["session_start"] == current["session_start"]
                                and old["response_time"] <= current["response_time"] - pd.Timedelta(minutes=1), "Meta-adaptation used current/future/other-person outcomes")
                        if scope == "task":
                            require(old["task_start"] == current["task_start"], "Meta-adaptation mixed distinct tasks with the same terrain")
            for row in selection["results"]:
                for fold, (fit, val) in enumerate(folds):
                    saved = json.loads((directory / "folds" / f"{row['candidate']['id']}-fold-{fold}.json").read_text())
                    require(saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                            and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist()
                            and saved["candidate"] == row["candidate"] and saved["code_sha256"] == selection["code_sha256"]
                            and saved["dataset_sha256"] == selection["dataset_sha256"], "Meta-adaptation fold evidence changed")
                    np.testing.assert_array_equal(saved["predicted"], np.asarray(row["oof_predictions"])[val])
            winner = max(selection["results"], key=lambda row: row["accuracy_mean"])
            for fit, val in folds:
                context = histories[winner["candidate"]["scope"]]
                refit = meta.MetaAdaptiveBorg(winner["candidate"]).fit(train.iloc[fit], context)
                np.testing.assert_array_equal(refit.predict(train.iloc[val], frame, context), np.asarray(winner["oof_predictions"])[val])
        if name == "participant-weighting-80-v1":
            import fatigue_participant_weighting as weighted
            require(selection["code_sha256"] == digest(Path(weighted.__file__)) and selection["plan"] == weighted.plan(manifest)
                    and selection["dataset_sha256"] == manifest["dataset_sha256"], "Participant-weighted fitting inputs changed")
            require(selection["dynamics_plan_code_sha256"] == digest(Path(__file__).with_name("fatigue_dynamics_experiment.py"))
                    and selection["synthetic_rows"] == selection["resampled_rows"] == 0
                    and selection["evaluation_weighting"] == "unit_weight_per_original_response", "Participant weighting changed evaluation cases/weights")
            for row in selection["results"]:
                for i, (fit, val) in enumerate(folds):
                    evidence = row["folds"][i]
                    counts = {str(k): int(v) for k, v in train.iloc[fit].groupby("group_key").size().items()}
                    require(evidence["fit_group_counts"] == counts and evidence["fit_weight_sum"] == len(fit)
                            and evidence["validation_groups"] == sorted(set(train.iloc[val]["group_key"])), "Participant loss balancing used held-out people")
                    weights = weighted.fitting_weights(train.iloc[fit]["group_key"], row["candidate"]["participant_weight_power"])
                    require(np.isclose(weights.sum(), len(fit)) and np.all(weights > 0), "Participant fitting weights dropped or multiplied evaluation rows")
            winner = max(selection["results"], key=lambda row: row["accuracy_mean"])
            for fit, val in folds:
                with threadpool_limits(limits=1):
                    refit = weighted.ParticipantWeightedBorg(winner["candidate"]).fit(train.iloc[fit])
                np.testing.assert_array_equal(refit.predict(train.iloc[val]), np.asarray(winner["oof_predictions"])[val])
        if name == "augmented-observed-feedback-80-v1":
            import fatigue_augmented_feedback as augmented
            evaluation_frame, evaluation_train, evaluation_test, aug_manifest, _, extra, extra_manifest = augmented.inputs()
            require(selection["code_sha256"] == digest(Path(augmented.__file__)) and selection["plan"] == augmented.plan(aug_manifest)
                    and selection["dataset_sha256"] == aug_manifest["dataset_sha256"]
                    and selection["extra_dataset_sha256"] == extra_manifest["dataset_sha256"], "Actual-feedback augmentation inputs changed")
            require(selection["extra_provenance_sha256"] == digest(augmented.EXTRA_DIRECTORY / "provenance.json")
                    and selection["extra_preparation_code_sha256"] == digest(Path(__file__).with_name("fatigue_extra_feedback.py"))
                    and selection["catboost_selection_sha256"] == digest(RESEARCH / "catboost-80-v1/selection.json"), "Extra-feedback source dependencies changed")
            require(selection["extra_actual_report_pool"] == len(extra) == 56 and selection["synthetic_rows"] == 0
                    and selection["evaluation_denominator"] == 487 and selection["test_denominator"] == 179
                    and selection["evaluation_weighting"] == "unit_weight_per_original_response", "Extra fitting reports changed the evaluation target/denominator")
            for row in selection["results"]:
                for i, (fit, val) in enumerate(folds):
                    data, _, keys = augmented.fitting_rows(train.iloc[fit], extra, row["candidate"]["extra_weight"])
                    evidence = row["folds"][i]
                    require(evidence["fit_groups"] == sorted(set(train.iloc[fit]["group_key"]))
                            and evidence["validation_groups"] == sorted(set(train.iloc[val]["group_key"]))
                            and evidence["extra_fitting_row_keys"] == keys and evidence["actual_fitting_rows"] == len(data)
                            and evidence["original_fitting_rows"] == len(fit), "Extra labels entered an unseen participant's base fitting set")
                    require(not set(data["group_key"]) & set(train.iloc[val]["group_key"]), "Extra fitting labels leaked validation participants")
        if name == "catboost-80-v1":
            import importlib.metadata
            import fatigue_catboost as catboost
            evaluation_frame, evaluation_train, evaluation_test, cat_manifest, _ = catboost.load_inputs()
            require(selection["code_sha256"] == digest(Path(catboost.__file__)) and selection["plan"] == catboost.plan(cat_manifest)
                    and selection["dataset_sha256"] == cat_manifest["dataset_sha256"], "Frozen CatBoost data/source/plan changed")
            require(selection["phone_loader_code_sha256"] == digest(Path(__file__).with_name("fatigue_phone_experiment.py"))
                    and selection["dynamics_plan_code_sha256"] == digest(Path(__file__).with_name("fatigue_dynamics_experiment.py")), "CatBoost feature dependencies changed")
            require(selection["synthetic_rows"] == 0 and selection["early_stopping_with_validation_or_test"] is False, "CatBoost used synthetic reports or evaluation stopping")
            for package, version in selection["software_versions"].items():
                require(importlib.metadata.version(package) == version, "CatBoost runtime differs from frozen study")
            for row in selection["results"]:
                for fold, (fit, val) in enumerate(folds):
                    saved = json.loads((directory / "folds" / f"{row['candidate']['id']}-fold-{fold}.json").read_text(encoding="utf-8"))
                    require(saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                            and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist()
                            and saved["candidate"] == row["candidate"] and saved["dataset_sha256"] == selection["dataset_sha256"]
                            and saved["code_sha256"] == selection["code_sha256"], "CatBoost fold membership or fitting inputs changed")
                    np.testing.assert_array_equal(saved["predicted"], np.asarray(row["oof_predictions"])[val])
            if not selection["results"]:
                require(selection["status"] == "running", "Completed CatBoost study has no results")
                result["experiments"][name] = {"status": "running", "completed_candidates": 0, "planned_candidates": len(selection["plan"]), "selection_snapshot_sha256": sha256}
                continue
        if name == "latent-curve-80-v1":
            import fatigue_latent_curve as latent
            if sequence_observations is None:
                import fatigue_trajectory_bank as trajectory
                reports, sessions = trajectory.observed_source()
                sequence_observations = reports, sessions, trajectory.build_queries(frame, reports, sessions)
            reports, sessions, queries = sequence_observations
            require(selection["code_sha256"] == digest(Path(latent.__file__)) and selection["plan"] == latent.plan()
                    and selection["dataset_sha256"] == manifest["dataset_sha256"], "Frozen latent-curve inputs changed")
            require(selection["query_source_code_sha256"] == digest(Path(__file__).with_name("fatigue_trajectory_bank.py"))
                    and selection["original_reports_sha256"] == digest(latent.RAW / "geofatigue/self_reported_fatigue_level.original.tab"), "Latent-curve questionnaire/query source changed")
            require(selection["interpolated_supervision_rows"] == 0 and selection["integration_grid_points"] == len(latent.GRID), "Latent numerical grid became supervision")
            winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
            for i, (fit, val) in enumerate(folds):
                prior = latent.fit_prior(reports, sessions, set(train.iloc[fit]["group_key"]), winner["candidate"]["power"])
                evidence = selection["folds"][i]
                require(evidence["fit_groups"] == prior["fit_groups"] and evidence["validation_groups"] == sorted(set(train.iloc[val]["group_key"]))
                        and evidence["actual_fitting_active_reports"] == len(prior["actual_active_report_rows"]), "Latent prior uses different people or reports")
                with threadpool_limits(limits=1):
                    refit_predictions = [latent.predict_query(prior, queries[train.index[position]], winner["candidate"]) for position in val]
                np.testing.assert_array_equal(refit_predictions, np.asarray(winner["oof_predictions"])[val])
        if name == "tabular-transfer-80-v1":
            import importlib.metadata
            import fatigue_tabular_transfer as transfer
            from fetch_tabular_transfer import DIRECTORY as model_raw
            _, transfer_train, transfer_test, transfer_manifest, _, sources = transfer.load_inputs()
            evaluation_frame, evaluation_train, evaluation_test, _, _, _ = transfer.load_inputs()
            transfer.configure_local_runtime()
            require(transfer_train["row_key"].tolist() == train["row_key"].tolist()
                    and transfer_test["row_key"].tolist() == test["row_key"].tolist(), "Transfer original cases changed")
            require(selection["code_sha256"] == digest(Path(transfer.__file__)) and selection["plan"] == transfer.plan(transfer_manifest), "Frozen TabPFN plan/source changed")
            require(selection["sources"] == sources, "Frozen TabPFN observations changed")
            require(selection["weights_sha256"] == digest(transfer.WEIGHTS) == transfer.WEIGHTS_SHA256
                    and selection["weights_metadata_sha256"] == digest(model_raw / "model.json"), "TabPFN public checkpoint changed")
            for package, version in selection["software_versions"].items():
                require(importlib.metadata.version(package) == version, "TabPFN runtime differs from frozen experiment")
            for row in selection["results"]:
                for fold, (fit, val) in enumerate(folds):
                    saved = json.loads((directory / "folds" / f"{row['candidate']['id']}-fold-{fold}.json").read_text(encoding="utf-8"))
                    require(saved["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                            and saved["validation_row_keys"] == train.iloc[val]["row_key"].tolist(), "TabPFN fold membership changed")
                    require(saved["candidate"] == row["candidate"] and saved["sources"] == sources
                            and saved["code_sha256"] == selection["code_sha256"]
                            and saved["weights_sha256"] == selection["weights_sha256"], "TabPFN fold fit inputs changed")
                    np.testing.assert_array_equal(np.asarray(row["oof_predictions"])[val], saved["predicted"])
        if name in ("trajectory-bank-80-v1", "recurrent-feedback-80-v1"):
            import fatigue_trajectory_bank as trajectory
            if sequence_observations is None:
                reports, sessions = trajectory.observed_source()
                sequence_observations = reports, sessions, trajectory.build_queries(frame, reports, sessions)
            reports, sessions, queries = sequence_observations
            require(selection["dataset_sha256"] == manifest["dataset_sha256"], "Sequence source observations changed")
            if name == "trajectory-bank-80-v1":
                require(selection["code_sha256"] == digest(Path(trajectory.__file__))
                        and selection["plan"] == trajectory.plan(), "Trajectory source/plan changed")
                require(selection["original_reports_sha256"] == digest(trajectory.RAW / "geofatigue/self_reported_fatigue_level.original.tab")
                        and selection["interpolated_supervision_rows"] == 0, "Trajectory actual supervision changed")
                for i, (fit, val) in enumerate(folds):
                    bank = trajectory.fit_bank(reports, sessions, set(train.iloc[fit]["group_key"]))
                    evidence = selection["folds"][i]
                    require(evidence["fit_groups"] == bank["fit_groups"] and evidence["validation_groups"] == sorted(set(train.iloc[val]["group_key"])), "Trajectory fit/validation people changed")
                    require(evidence["actual_fitting_active_reports"] == len(bank["actual_active_response_rows"])
                            and evidence["templates"] == len(bank["templates"]), "Trajectory source report counts changed")
                    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
                    refit_predictions = [trajectory.predict_query(bank, queries[train.index[position]], winner["candidate"]) for position in val]
                    np.testing.assert_array_equal(refit_predictions, np.asarray(winner["oof_predictions"])[val])
            else:
                import fatigue_recurrent as recurrent
                require(selection["code_sha256"] == digest(Path(recurrent.__file__))
                        and selection["plan"] == recurrent.plan(manifest), "Recurrent source/plan changed")
                require(selection["query_source_code_sha256"] == digest(Path(trajectory.__file__))
                        and selection["token_features"] == recurrent.TOKEN_FEATURES, "Recurrent history preparation changed")
                require(selection["torch_version"] == str(recurrent.torch.__version__)
                        and selection["synthetic_rows"] == selection["interpolated_supervision_rows"] == 0, "Recurrent runtime/supervision changed")
                for query in queries:
                    recurrent.history_tokens(query)
                winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
                for fit, val in folds:
                    refit = recurrent.RecurrentBorg(winner["candidate"]).fit(train.iloc[fit], [queries[train.index[position]] for position in fit])
                    np.testing.assert_array_equal(refit.predict(train.iloc[val], [queries[train.index[position]] for position in val]), np.asarray(winner["oof_predictions"])[val])
        if name == "source-specific-transfer-80-v1":
            import fatigue_source_teachers as source_teachers
            sources, splits = source_teachers.external_inputs()
            require(selection["code_sha256"] == digest(Path(source_teachers.__file__))
                    and selection["plan"] == source_teachers.plan(manifest)
                    and selection["dataset_sha256"] == manifest["dataset_sha256"], "Source-specific transfer code/plan/observations changed")
            require(selection["external_splits"] == splits and selection["external_test_used"] is False
                    and selection["teachers_use_geofatigue_labels"] is False and selection["original_momentary_target_merge"] is False,
                    "Source-specific teachers mixed target definitions or consumed reserved responses")
            require(selection["classifier_code_sha256"] == digest(Path(__file__).with_name("fatigue_dynamics_experiment.py"))
                    and selection["external_loader_code_sha256"] == digest(Path(__file__).with_name("fatigue_auxiliary_transfer.py"))
                    and selection["oxbioz_provenance_sha256"] == digest(source_teachers.OX_DIRECTORY / "provenance.json"), "Source-specific dependencies changed")
            require(selection["fitting_reports_per_source"] == {k: len(v) for k, v in sources.items()}, "External fitting report counts changed")
            winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
            algorithm = winner["candidate"]["teacher_algorithm"]
            transformed = train
            if algorithm != "control":
                teachers = {key: source_teachers.fit_teacher(data, algorithm) for key, data in sources.items()}
                transformed = source_teachers.add_teacher_features(train, teachers)
            for fit, val in folds:
                with threadpool_limits(limits=1):
                    refit = source_teachers.DynamicsClassifier(winner["candidate"]).fit(transformed.iloc[fit])
                np.testing.assert_array_equal(refit.predict(transformed.iloc[val]), np.asarray(winner["oof_predictions"])[val])
        if name == "phone-context-80-v1":
            require(selection["plan"] == phone.plan(phone_manifest) and selection["code_sha256"] == digest(Path(phone.__file__)), "Frozen phone plan/source changed")
            require(selection["dataset_sha256"] == phone_manifest["dataset_sha256"], "Phone features differ from frozen search")
            require(selection["grouped_search_code_sha256"] == digest(Path(__file__).parent / "common/grouped_fatigue_search.py")
                    and selection["classifier_code_sha256"] == digest(Path(__file__).with_name("fatigue_dynamics_experiment.py")), "Phone training dependency changed")
        require(selection["target_accuracy"] == .8 and selection["test_used_for_selection"] is False, "Experiment changed objective or used test for tuning")
        require(selection["train_row_keys"] == train["row_key"].tolist(), "Search used other target responses")
        for row in selection["results"]:
            predicted = np.asarray(row["oof_predictions"])
            require(len(predicted) == len(train), "OOF denominator differs from 487 original responses")
            require(set(predicted) <= {f"Borg {i}" for i in range(11)}, "OOF predictions changed the native scale")
            scores = [accuracy_score(train.iloc[val]["label"], predicted[val]) for _, val in folds]
            np.testing.assert_allclose(scores, row["fold_accuracy"], rtol=0, atol=1e-12)
            require(np.isclose(np.mean(scores), row["accuracy_mean"], rtol=0, atol=1e-12), "OOF mean not exact native accuracy")
            require(np.isclose(accuracy_score(train["label"], predicted), row["pooled_oof_accuracy"], rtol=0, atol=1e-12), "Pooled OOF accuracy differs")
        best = max(selection["results"], key=lambda r: r["accuracy_mean"])
        require(best["candidate"]["id"] == selection["winner_id"], "Winner not chosen by original training CV")
        result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                                       "best_cv_accuracy": best["accuracy_mean"], "winner_id": selection["winner_id"], "selection_snapshot_sha256": sha256}
        evaluation = directory / "evaluation"
        if not (evaluation / "metrics.json").exists():
            continue
        metrics = json.loads((evaluation / "metrics.json").read_text(encoding="utf-8"))
        for key, value in original_protocol.items():
            require(metrics["evaluation_protocol"][key] == value, "Original held-out protocol changed")
        require(metrics["evaluation_protocol"]["selection_sha256"] == sha256, "Evaluation uses a different frozen selection")
        require(metrics["evaluation_validity"]["deployment_approved"] is False, "Research deployment approval changed")
        require(metrics["evaluation_validity"]["native_labels"] and metrics["evaluation_validity"]["synthetic_rows"] == 0, "Non-native or synthetic evaluation")
        artifact = evaluation / metrics["model_artifact"]["path"]
        require(digest(artifact) == metrics["model_artifact"]["sha256"], "Fitted model changed after evaluation")
        if name == "catboost-80-v1":
            model = catboost.CatBoostBorg.load(artifact, evaluation / metrics["model_descriptor"]["path"])
            require(digest(evaluation / metrics["model_descriptor"]["path"]) == metrics["model_descriptor"]["sha256"], "CatBoost native-model descriptor changed")
            refit = catboost.CatBoostBorg(best["candidate"]).fit(evaluation_train)
            np.testing.assert_array_equal(refit.predict(evaluation_frame), model.predict(evaluation_frame))
        else:
            model = joblib.load(artifact)  # Only this task's SHA-pinned own model.
        require(model.candidate == best["candidate"], "Saved model differs from frozen CV winner")
        if name == "gait-source-transfer-80-v1":
            require(model.source is None, "Saved source-transfer model retained source rows/labels")
            require(metrics["external_source"]["fitting_reports"] == 48
                    and metrics["external_source"]["reserved_reports"] == 12
                    and metrics["external_source"]["reserved_reports_used"] is False
                    and metrics["external_source"]["original_momentary_targets_added"] == 0, "Saved gait model consumed reserved source outcomes")
            with threadpool_limits(limits=1):
                refit = gait.GaitTransferBorg(best["candidate"], source).fit(evaluation_train)
            np.testing.assert_array_equal(refit.predict(evaluation_frame), model.predict(evaluation_frame))
            raw_features = metrics["input_contract"]["feature_order"]
            np.testing.assert_array_equal(model.predict(evaluation_frame[raw_features]), model.predict(evaluation_frame))
            changed = evaluation_frame.copy()
            changed["label"], changed["group_key"] = "Borg 10", "unused_identifier"
            np.testing.assert_array_equal(model.predict(changed), model.predict(evaluation_frame))
            import importlib.metadata
            for package, version in metrics["software_versions"].items():
                require(importlib.metadata.version(package) == version, "Saved gait model runtime changed")
        if name == "gradient-adaptation-80-v1":
            context = adaptation_contexts[best["candidate"]["scope"]]
            require(metrics["runtime_history_serialized_in_model"] is False
                    and metrics["evaluation_protocol"]["population_weights_exclude_test_participants"]
                    and metrics["evaluation_protocol"]["earlier_observed_test_person_reports_are_runtime_inputs"], "MAML evaluation changed its runtime calibration contract")
            refit = gradient.GradientAdaptiveBorg(best["candidate"]).fit(evaluation_train, context)
            np.testing.assert_array_equal(refit.predict(evaluation_frame, evaluation_frame, context), model.predict(evaluation_frame, evaluation_frame, context))
            predicted = model.predict(evaluation_test, evaluation_frame, context)
            changed = evaluation_test.copy()
            changed["label"] = "unavailable_current_target"
            np.testing.assert_array_equal(predicted, model.predict(changed, evaluation_frame, context))
        else:
            predicted = model.predict(evaluation_test)
        if name == "phone-context-80-v1":
            with threadpool_limits(limits=1):
                refit = DynamicsClassifier(best["candidate"]).fit(evaluation_train)
            np.testing.assert_array_equal(refit.predict(evaluation_frame), model.predict(evaluation_frame))
            mutated = evaluation_frame.copy()
            mutated["label"] = "Borg 10"
            np.testing.assert_array_equal(model.predict(mutated), model.predict(evaluation_frame))
            features = evaluation_frame[best["candidate"]["features"]]
            if hasattr(model.model, "predict_proba"):
                np.testing.assert_allclose(refit.model.predict_proba(features), model.model.predict_proba(features), atol=1e-10, rtol=1e-10)
        predictions_path = evaluation / "test_predictions.csv"
        require(digest(predictions_path) == metrics["test_predictions_sha256"], "Saved prediction evidence changed")
        saved = pd.read_csv(predictions_path)
        require(saved["row_key"].tolist() == test["row_key"].tolist() and saved["observed"].tolist() == test["label"].tolist(), "Test cases/targets changed")
        np.testing.assert_array_equal(predicted, saved["predicted"])
        correct = int(np.sum(predicted == test["label"].to_numpy()))
        accuracy = correct / 179
        require(accuracy == metrics["accuracy"] == metrics["metrics"]["test"]["accuracy"], "Test accuracy differs from stored model")
        if "portable_model_artifact" in metrics:
            portable = evaluation / metrics["portable_model_artifact"]["path"]
            require(digest(portable) == metrics["portable_model_artifact"]["sha256"], "Portable network changed")
            payload = json.loads(portable.read_text(encoding="utf-8"))
            np.testing.assert_array_equal(predict_calibrated_network(payload, evaluation_frame[payload["feature_order"]]), model.predict(evaluation_frame))
        result["test_evaluations"][name] = {"correct": correct, "rows": 179, "accuracy": accuracy, "saved_artifact_and_csv_verified": True}
        if accuracy > result["best_verified_test_accuracy"]:
            result.update(best_verified_test_accuracy=accuracy, best_verified_test_correct=correct)
    sts_directory = RESEARCH / "sts-v1"
    sts = json.loads((sts_directory / "provenance.json").read_text(encoding="utf-8"))
    require(digest(sts_directory / "dataset.csv") == sts["dataset_sha256"], "Audited additional STS responses changed")
    require(sts["interpolated_targets"] == sts["synthetic_rows"] == sts["assumed_zero_targets"] == 0, "Unobserved supervision added")
    result["additional_sts_data"] = {"real_sparse_reports": sts["rows"], "participants": sts["groups"], "interpolated_targets": 0,
                                     "native_half_point_ratings_preserved": True, "supervision_is_original_nonempty_Borg_cells": True}
    from oxbioz_fatigue import DIRECTORY as ox_directory, load as load_ox
    from fetch_oxbioz import DIRECTORY as ox_raw, FILES as ox_files
    ox_frame, ox = load_ox()
    require(digest(ox_raw / ox_files["gel"][0]) == ox["source_sha256"], "Original OxBioZ source changed")
    require(len(ox_frame) == ox["native_reports"] == 40 and ox_frame["group_key"].nunique() == ox["participants"] == 20,
            "OxBioZ actual report/participant counts changed")
    require(ox["interpolated_supervision_rows"] == ox["synthetic_rows"] == ox["fabric_probe_rows_used"] == 0
            and ox["original_momentary_target_merge_approved"] is False, "OxBioZ trial outcome became a momentary label")
    result["additional_oxbioz_data"] = {"original_post_trial_reports": 40, "participants": 20, "exact_report_timestamp_published": False,
                                       "source_specific_auxiliary_use_only": True, "new_momentary_geofatigue_targets": 0}
    from fatigue_extra_feedback import DIRECTORY as extra_directory, load as load_extra, feedback_row
    from public_sources import RAW, group_key
    extra, extra_manifest = load_extra()
    require(extra_manifest["extra_actual_active_reports"] == len(extra) == 56
            and extra_manifest["rest_targets_added"] == extra_manifest["assumed_onset_zeros"] == extra_manifest["interpolated_supervision_rows"] == extra_manifest["synthetic_rows"] == 0,
            "Extra-feedback labels were invented, interpolated or taken from rest")
    raw_reports_path = RAW / "geofatigue/self_reported_fatigue_level.original.tab"
    require(extra_manifest["raw_reports_sha256"] == digest(raw_reports_path)
            and extra_manifest["session_metadata_sha256"] == digest(RAW / "geofatigue/session_metadata.json"), "Extra feedback original source changed")
    raw_reports = pd.read_csv(raw_reports_path)
    raw_reports["time"] = pd.to_datetime(raw_reports["time"], utc=True)
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text())
    original_lineage = json.loads((OUTPUT / "fatigue/provenance.json").read_text())["lineage"]
    canonical_pairs = {("p" + re.search(r"/p(\d+)-", r["lineage"]["member"])[1], pd.Timestamp(r["lineage"]["label_time"])) for r in original_lineage}
    seen = set()
    for i, evidence in enumerate(extra_manifest["extra_lineage"]):
        source = raw_reports.loc[evidence["original_response_row"]]
        pair = source["id"], source["time"]
        require(source["task"] == 1 and pair not in canonical_pairs and pair not in seen, "Additional outcomes duplicated canonical targets or rest")
        seen.add(pair)
        require(group_key("GeoFatigue:" + source["id"]) == extra.iloc[i]["group_key"]
                and extra.iloc[i]["group_key"] in set(train["group_key"]), "An extra fitting outcome belongs to a reserved person")
        require(extra.iloc[i]["label"] == f"Borg {int(source['borg_scale'])}"
                and evidence["actual_observed_borg"] == source["borg_scale"], "Extra native outcome differs from the original explicit cell")
        matches = [(s, t) for s in sessions[source["id"]] for t in s["tasks"] if pd.Timestamp(t["start_time"]) <= source["time"] <= pd.Timestamp(t["end_time"])]
        require(len(matches) == 1, "Extra source task is ambiguous")
        rebuilt = feedback_row(raw_reports[raw_reports["id"].eq(source["id"])], *matches[0], source["time"])
        require(rebuilt is not None and 1 <= rebuilt["prior_age_minutes"] <= 15, "Extra outcome lacks a real eligible prior")
        np.testing.assert_allclose([rebuilt[c] for c in extra_manifest["feature_order"]], extra.iloc[i][extra_manifest["feature_order"]].to_numpy(float), rtol=0, atol=1e-12, equal_nan=True)
    result["additional_original_active_feedback"] = {"actual_extra_fitting_reports": len(extra), "reserved_people_included": False,
                                                     "new_validation_or_test_cases": 0, "assumed_onset_zeros": 0}
    from fetch_pmdata import DIRECTORY as pm_raw
    pm_path = pm_raw / "eligibility-audit.json"
    if pm_path.exists():
        pm = json.loads(pm_path.read_text(encoding="utf-8"))
        require(pm["code_sha256"] == digest(Path(__file__).with_name("audit_pmdata.py")), "PMData eligibility code changed")
        receipt_path = pm_raw / "annotations-receipt.json"
        require(pm["annotation_receipt_sha256"] == digest(receipt_path) and pm["inventory_sha256"] == digest(pm_raw / "inventory.json"), "PMData public inventory/receipt changed")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        rows, ratings, people = 0, 0, 0
        for entry in receipt["files"]:
            source = pm_raw / entry["local_path"]
            require(digest(source) == entry["sha256"] and source.stat().st_size == entry["bytes"], "PMData original public annotation changed")
            if source.name == "srpe.csv":
                native = pd.read_csv(source)["perceived_exertion"]
                rows += len(native)
                ratings += int(native.notna().sum())
                people += int(native.notna().any())
        require(rows == pm["annotation_rows"] == 783 and ratings == pm["actual_nonempty_effort_cells"] == 772
                and people == pm["participants_with_actual_ratings"] == 15 and rows-ratings == pm["missing_effort_cells"] == 11, "PMData missing rows became observed labels")
        require(pm["training_merge_approved"] is False and pm["used_for_training"] is False
                and pm["timezone_offset_imputed"] is False and pm["synthetic_or_imputed_effort_labels"] == 0, "Unverified PMData alignment entered training")
        result["pmdata_eligibility"] = {"actual_session_ratings": ratings, "missing_ratings": rows-ratings,
                                       "participants_with_ratings": people, "used_for_training": False,
                                       "reason": pm["reason"], "audit_sha256": digest(pm_path)}
    from sixmwt_fatigue import DIRECTORY as gait_directory, load as load_gait, extract as extract_gait
    from fetch_sixmwt import DIRECTORY as gait_raw, METADATA as gait_metadata
    if (gait_directory / "provenance.json").exists():
        import io
        import zipfile
        from scipy.io import loadmat
        gait_fit, gait_held, gait_evidence = load_gait()
        gait_all = pd.read_csv(gait_directory / "dataset.csv")
        receipt = json.loads((gait_raw / "receipt.json").read_text())
        archive_path = gait_raw / "6MWT_IMU_Dataset.zip"
        require(digest(archive_path) == gait_evidence["source_sha256"] == receipt["sha256"]
                and digest(archive_path, "md5") == receipt["published_md5"] == "a23fb3753fc33648624725c33ec9d57e"
                and digest(gait_metadata) == gait_evidence["metadata_sha256"] == receipt["metadata_sha256"], "Original six-minute walking archive/metadata changed")
        require(len(gait_all) == gait_evidence["actual_reports"] == gait_evidence["participants"] == 60
                and len(gait_fit) == 48 and len(gait_held) == 12 and gait_evidence["momentary_target_merge"] is False
                and gait_evidence["synthetic_rows"] == gait_evidence["interpolated_targets"] == gait_evidence["assumed_zero_targets"] == 0, "Gait post-test reports were duplicated or changed into momentary labels")
        require(set(gait_fit["row_key"]) | set(gait_held["row_key"]) == set(gait_all["row_key"])
                and not set(gait_fit["group_key"]) & set(gait_held["group_key"]), "Six-minute walking external holdout changed")
        mismatch = 0
        with zipfile.ZipFile(archive_path) as archive:
            for evidence in gait_evidence["lineage"]:
                payload = archive.read(evidence["member"])
                require(hashlib.sha256(payload).hexdigest() == evidence["member_sha256"], "Original walking MAT member changed")
                data = loadmat(io.BytesIO(payload), simplify_cells=True)["Data"]
                reconstructed, target = extract_gait(data)
                stored = gait_all[gait_all["row_key"].eq(evidence["row_key"])]
                require(len(stored) == 1 and stored.iloc[0]["borg_native"] == target == evidence["actual_borg"], "Walking target differs from original explicit cell")
                np.testing.assert_allclose([reconstructed[c] for c in gait_evidence["features"]], stored.iloc[0][gait_evidence["features"]].to_numpy(float), rtol=0, atol=1e-12, equal_nan=True)
                valid_clock = np.shape(data["RawData"]["Acc"]) == (len(data["RawData"]["Time"]), 3)
                require(valid_clock == evidence["sensor_clock_alignment_valid"], "Walking sensor clock policy changed")
                mismatch += not valid_clock
        require(mismatch == gait_evidence["sensor_clock_mismatch_reports_retained_with_missing_acceleration"] == 5, "Unresolved walking sensor clocks were filled or reports removed")
        result["additional_sixmwt_data"] = {"actual_post_test_reports": 60, "external_fitting_people": 48, "external_reserved_people": 12,
                                           "unaligned_sensor_reports_retained": mismatch, "new_momentary_target_cases": 0,
                                           "source_only_auxiliary_use": True, "original_raw_cells_and_features_reconstructed": True}
    from fatigue_joint_sources import DIRECTORY as joint_directory, combine as combine_joint, load as load_joint
    if (joint_directory / "provenance.json").exists():
        from fatigue_source_teachers import external_inputs as original_joint_sources
        sources, splits = original_joint_sources()
        source, _, source_evidence = load_gait()
        sources["sixmwt_post_test"], splits["sixmwt_post_test"] = source, source_evidence["split"]
        rebuilt, counts = combine_joint(sources, splits)
        combined, combined_evidence = load_joint()
        require(counts == combined_evidence["domains"] and splits == combined_evidence["external_splits"]
                and len(combined) == combined_evidence["actual_reports"] == 520
                and combined["group_key"].nunique() == combined_evidence["participants"] == 143, "Combined source report counts or reserved splits changed")
        require(combined["row_key"].tolist() == rebuilt["row_key"].tolist()
                and combined["group_key"].tolist() == rebuilt["group_key"].tolist()
                and combined["source_domain"].tolist() == rebuilt["source_domain"].tolist(), "Combined source lineage changed")
        np.testing.assert_array_equal(combined["borg_native"], rebuilt["borg_native"])
        np.testing.assert_allclose(combined[combined_evidence["sensor_features"]], rebuilt[combined_evidence["sensor_features"]], rtol=0, atol=1e-10, equal_nan=True)
        require(combined_evidence["synthetic_rows"] == combined_evidence["interpolated_targets"] == combined_evidence["assumed_zero_targets"] == 0
                and combined_evidence["native_momentary_target_merge"] is False
                and combined_evidence["new_geofatigue_validation_or_test_cases"] == 0
                and combined_evidence["missing_sensor_values_filled_in_snapshot"] is False, "Combined source rows invented supervision or filled absent sensors")
        require(int((combined["borg_native"] % 1 != 0).sum()) == 3
                and not set(combined["group_key"]) & set(frame["group_key"]), "Native source fractions or participant namespaces changed")
        result["combined_external_sources"] = {"actual_fitting_reports": 520, "source_participants": 143,
            "source_report_counts": {name: c["reports"] for name, c in counts.items()}, "native_fractional_reports": 3,
            "reserved_external_reports_used": False, "new_original_test_cases": 0,
            "all_combined_targets_and_sensor_values_reconstructed_from_audited_parents": True}
    from fetch_borg_candidates_v2 import DIRECTORY as workbook_raw
    workbook_audit_path = workbook_raw / "eligibility-audit.json"
    if workbook_audit_path.exists():
        workbook = json.loads(workbook_audit_path.read_text(encoding="utf-8"))
        workbook_receipt = workbook_raw / "workbooks-receipt.json"
        require(workbook["code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_workbooks_v2.py"))
                and workbook["receipt_sha256"] == digest(workbook_receipt), "Workbook eligibility/source receipt changed")
        receipt = json.loads(workbook_receipt.read_text(encoding="utf-8"))
        require(receipt["all_complete_and_publisher_verified"] and len(receipt["files"]) == 3, "Workbook source downloads incomplete")
        for entry in receipt["files"]:
            source = workbook_raw / entry["file"]
            require(digest(source) == entry["sha256"] and source.stat().st_size == entry["bytes"], "Audited source workbook changed")
        require(workbook["training_merge_approved"] is False and workbook["original_geofatigue_targets_added"] == 0
                and all(s["used_for_training"] is False for s in workbook["sources"].values()), "Unverified workbook outcomes entered the native target cohort")
        protocol = workbook["sources"]["exercise_ppt"]
        require(protocol["protocol_sha256"] == digest(workbook_raw / "exercise-protocol-CERT.docx")
                and protocol["protocol_text_sha256"] == digest(workbook_raw / "exercise-protocol-CERT.txt"), "Exercise source protocol changed")
        result["additional_workbooks_eligibility"] = {"audited_sources": 3, "used_for_training": False,
                                                      "new_native_momentary_targets": 0, "audit_sha256": digest(workbook_audit_path)}
    result["achieved"] = result["best_verified_test_accuracy"] >= .8
    result["deployment_approved"] = False
    result["scope"] = "Exact native Borg on all original 179 cases. Reused published benchmark, descriptive research; CV alone cannot satisfy the goal."
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
