"""Read-only evidence integrity for completed public-runner HR transfer."""
import ast
import json
from pathlib import Path

import fatigue_furukawa_hr_transfer as study
from public_sources import digest


def validate():
    status = json.loads((study.DOCS/"current-research-status.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (48,1776,260)
    assert status["goal_status"] == "active" and "running_study" not in status
    assert (status["original_training_cases"],status["original_test_cases"],status["required_correct_for_80_percent"]) == (487,179,144)
    assert status["public_real_data_policy_sha256"] == digest(study.DOCS/"public-real-data-policy.json")
    hashes = 0
    for field in ("additional_scoped_verifications","additional_data_audits","additional_public_candidate_inspections"):
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
    assert len(counts) == 48 and sum(counts.values()) == 1776
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert selection["plan"] == study.plan() and len(selection["results"]) == 14
    assert digest(study.DIRECTORY/"selection-source.py") == selection["code_sha256"]
    audit_path = study.DOCS/"furukawa-hr-transfer-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["verification"] == "passed" and audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_furukawa_hr_transfer.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["all_14_oof_recipes_recomputed"] and audit["original_native_rows_and_targets_preserved"]
    assert audit["native_hr_cache_identities_and_available_values_independently_checked"] == 666
    assert audit["source_fitting_actual_state_targets"] == 252 and audit["source_fitting_actual_delta_targets"] == 168
    assert audit["source_fitting_people"] == 12 and audit["source_reserved_targets_not_fitted"] == 84 and audit["source_reserved_people"] == 4
    assert audit["actual_source_function_refits"] == len(audit["source_function_refits"]) == 4
    assert audit["actual_native_refits"] == len(audit["native_refits"]) == 30
    assert audit["actual_source_and_native_estimator_targets_and_weights_observed"] and audit["source_functions_frozen_during_native_fitting"]
    assert audit["source_and_native_preprocessing_fitting_only"] and audit["natural_missing_representations_preserved"]
    assert not audit["source_outcomes_pooled_or_converted_to_native"]
    assert audit["synthetic_rows"] == audit["artificial_history_views"] == audit["invented_source_times_or_rest_baselines"] == 0
    for name,expected in audit["source_teacher_artifact_hashes"].items():
        assert digest(study.DIRECTORY/"teachers"/name) == expected
    for row in audit["native_refits"]:
        assert row["reload_without_current_truth_or_ids"] and row["optimizer_summary"]["source_teacher_frozen"]
        assert row["optimizer_summary"]["source_reserved_targets_not_fitted"] == 84
        assert not row["optimizer_summary"]["source_outcomes_pooled"]
    summary = json.loads((study.DOCS/"furukawa-pre-report-hr-transfer.json").read_text())
    assert summary["verification_sha256"] == digest(audit_path) and summary["selection_sha256"] == digest(selection_path)
    assert summary["best_cv_accuracy"] == selection["best_cv_accuracy"] and summary["independent_native_refits"] == 30
    test = audit["new_test_evaluation"]
    if audit["new_test_gate_passed"]:
        assert test and test["cases"] == 179 and test["test_accuracy"] == test["correct"]/179
        assert status["best_verified_test_correct"] == max(108,test["correct"])
    else:
        assert test is None and not (study.DIRECTORY/"evaluation/metrics.json").exists()
        assert status["best_verified_test_correct"] == 108
    assert status["best_verified_test_accuracy"] == status["best_verified_test_correct"]/179
    assert status["goal_achieved"] == (status["best_verified_test_correct"] >= 144)
    assert summary["retained_test_correct"] == status["best_verified_test_correct"]
    tests = (study.DOCS/"furukawa-hr-transfer-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    assert status["furukawa_pre_report_hr_opportunity"]["model_study_completed"] and status["next_furukawa_hr_proposal"]["model_study_completed"]
    assert status["next_furukawa_hr_proposal"]["sha256"] == digest(study.PROPOSAL)
    print(json.dumps({"integrity":"passed","completed_studies_counted_from_saved_selections":len(counts),
        "configurations_counted_from_saved_results":sum(counts.values()),"cumulative_distinct_tests":260,
        "scoped_evidence_hashes_checked":hashes,"source_teacher_artifact_hashes_checked":len(audit["source_teacher_artifact_hashes"]),
        "independent_source_function_refits_in_saved_audit":4,"independent_native_refits_in_saved_audit":30,
        "actual_source_state_fitting_targets":252,"actual_source_delta_fitting_targets":168,"source_reserved_targets_not_fitted":84,
        "retained_test_correct":status["best_verified_test_correct"],"retained_test_accuracy":status["best_verified_test_accuracy"],
        "goal_achieved":status["goal_achieved"],"historical_model_refitting_performed":False}),flush=True)


if __name__ == "__main__":
    validate()
