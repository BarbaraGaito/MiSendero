"""Read-only integrity of the completed real-data joint-history checkpoint."""
import ast
import json
from pathlib import Path

import fatigue_two_history_joint as study
from public_sources import digest


def validate():
    status = json.loads((study.DOCS/"current-research-status.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (46,1740,252)
    assert status["goal_status"] == "active" and not status["goal_achieved"] and "running_study" not in status
    assert status["best_verified_test_correct"] == 108 and status["best_verified_test_accuracy"] == 108/179
    assert (status["original_training_cases"],status["original_test_cases"],status["required_correct_for_80_percent"]) == (487,179,144)
    assert status["public_real_data_policy_sha256"] == digest(study.DOCS/"public-real-data-policy.json")
    hashes = 0
    for field in ("additional_scoped_verifications","additional_data_audits"):
        for name,expected in status[field].items():
            assert digest(study.DOCS/name) == expected,(field,name)
            hashes += 1
    tree = ast.parse(Path(__file__).with_name("fatigue_80_checkpoint.py").read_text())
    families = next(ast.literal_eval(node.iter) for node in ast.walk(tree)
        if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id == "name"
        and isinstance(node.iter,ast.Tuple) and any(isinstance(v,ast.Constant) and v.value == study.DIRECTORY.name for v in node.iter.elts))
    counts = {}
    for name in families:
        selection = json.loads((study.DIRECTORY.parent/name/"selection.json").read_text())
        assert selection["status"] == "complete",name
        counts[name] = len(selection["results"])
    assert len(counts) == 46 and sum(counts.values()) == 1740
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert selection["plan"] == study.plan(inputs["previous_audit"]) and len(selection["results"]) == 16
    assert digest(study.DIRECTORY/"selection-source.py") == selection["code_sha256"]
    audit_path = study.DOCS/"two-history-joint-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_two_history_joint.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["all_16_oof_recipes_recomputed"] and audit["original_native_rows_and_targets_preserved"]
    assert audit["native_base_caches_checked"] == 10 and audit["cached_native_base_fit_models_checked"] == 40
    assert audit["independent_native_base_fits"] == len(audit["independent_native_base_refits"]) == 8
    assert audit["actual_native_joint_refits"] == len(audit["joint_refits"]) == 20
    assert audit["actual_source_and_native_loss_targets_observed"] and audit["actual_source_encoder_gradients_verified"]
    assert audit["zero_auxiliary_control_excludes_source_labels"] and audit["native_base_weights_frozen"]
    assert audit["shared_preprocessing_fitting_rows_only"] and audit["native_context_preprocessing_fitting_people_only"]
    assert not audit["source_outcomes_pooled"] and audit["synthetic_rows"] == audit["invented_source_times_or_sensor_joins"] == 0
    assert not audit["new_test_gate_passed"] and audit["new_test_evaluation"] is None and not audit["achieved"]
    for name,expected in audit["native_base_artifact_hashes"].items():
        assert digest(study.DIRECTORY/"bases"/name) == expected
    summary = json.loads((study.DOCS/"two-history-joint-transfer.json").read_text())
    assert summary["verification_sha256"] == digest(audit_path) and summary["selection_sha256"] == digest(selection_path)
    assert summary["retained_test_correct"] == 108 and summary["source_fitting_actual_second_priors"] == 367
    assert not (study.DIRECTORY/"evaluation/metrics.json").exists()
    tests = (study.DOCS/"two-history-joint-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    preflight = (study.DOCS/"two-history-joint-audit-preflight.log").read_text()
    assert preflight.count('"audit_preflight": "passed"') == 2
    print(json.dumps({"integrity":"passed","completed_studies_counted_from_saved_selections":len(counts),
        "configurations_counted_from_saved_results":sum(counts.values()),"cumulative_distinct_tests":252,
        "scoped_evidence_hashes_checked":hashes,"native_base_cache_artifact_hashes_checked":len(audit["native_base_artifact_hashes"]),
        "cached_original_native_base_models_checked":40,"independent_native_base_refits_in_saved_audit":8,
        "independent_actual_joint_network_refits_in_saved_audit":20,"source_fitting_targets_available":550,
        "source_actual_fitting_second_priors":367,"source_reserved_targets_not_fitted":57,
        "actual_source_and_native_loss_targets_verified":True,"source_gradients_and_zero_weight_control_verified":True,
        "retained_test_correct":108,"retained_test_accuracy":108/179,"goal_achieved":False,
        "historical_model_refitting_performed":False}),flush=True)


if __name__ == "__main__":
    validate()
