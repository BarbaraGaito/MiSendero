"""Read-only integrity of the completed fixed native CatBoost schedule study."""
import ast
import importlib.metadata
import json
from pathlib import Path

import fatigue_catboost_schedule as study
from public_sources import digest


def validate():
    status = json.loads((study.DOCS/"current-research-status.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (49,1792,264)
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
    assert len(counts) == 49 and sum(counts.values()) == 1792
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert selection["plan"] == study.plan() and len(selection["results"]) == 16
    assert digest(study.DIRECTORY/"selection-source.py") == selection["code_sha256"]
    assert selection["actual_native_trajectory_fits"] == 15 and selection["matched_original_prefix_controls_verified"] == 10
    audit_path = study.DOCS/"catboost-schedule-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["verification"] == "passed" and audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_catboost_schedule.py"))
    assert audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["real_native_tests_code_sha256"] == digest(Path(__file__).with_name("test_fatigue_catboost_schedule.py"))
    assert audit["real_native_tests_log_sha256"] == digest(study.DOCS/"catboost-schedule-tests.log")
    assert audit["all_16_oof_recipes_recomputed"] and audit["original_native_rows_and_targets_preserved"]
    assert audit["stored_native_trajectories_independently_reloaded"] == 15
    assert audit["all_stored_native_cbm_and_joblib_prefix_predictions_checked"]
    assert audit["both_historical_prefix_controls_verified_in_all_folds"] == 10
    assert audit["actual_native_trajectory_refits"] == len(audit["trajectory_refits"]) == 5*len(audit["independently_refitted_learning_rates"])
    assert audit["actual_native_trajectory_refits"] in (5,10)
    assert audit["actual_native_short_control_refits"] == len(audit["shortened_control_refits"]) == 2
    for key in ("actual_native_estimator_targets_and_parameters_observed","genuine_shorter_fits_equal_stored_long_prefixes",
        "natural_missing_inputs_preserved","fitting_only_original_cases"):
        assert audit[key],key
    assert not audit["validation_or_test_eval_set_supplied"]
    assert audit["source_outcomes_fitted"] == audit["synthetic_rows"] == audit["artificial_history_views"] == 0
    assert len(audit["trajectory_artifact_hashes"]) == 45
    for name,expected in audit["trajectory_artifact_hashes"].items():
        assert digest(study.DIRECTORY/name) == expected
    original = json.loads((study.BASELINE_DIRECTORY/"selection.json").read_text())
    installed = {name:importlib.metadata.version(name) for name in original["software_versions"]}
    assert installed == original["software_versions"] == audit["software_versions_independently_verified"]
    summary = json.loads((study.DOCS/"catboost-schedule.json").read_text())
    assert summary["verification_sha256"] == digest(audit_path) and summary["selection_sha256"] == digest(selection_path)
    assert summary["best_cv_accuracy"] == selection["best_cv_accuracy"] and summary["actual_maximum_tree_trajectory_fits"] == 15
    test = audit["new_test_evaluation"]
    if audit["new_test_gate_passed"]:
        assert test and test["cases"] == 179 and test["test_accuracy"] == test["correct"]/179
        assert status["best_verified_test_correct"] == max(108,test["correct"])
    else:
        assert test is None and not (study.DIRECTORY/"evaluation/metrics.json").exists()
        assert status["best_verified_test_correct"] == 108
    assert status["best_verified_test_accuracy"] == status["best_verified_test_correct"]/179
    assert status["goal_achieved"] == (status["best_verified_test_correct"] >= 144)
    tests = (study.DOCS/"catboost-schedule-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    assert status["catboost_schedule_proposal"]["model_study_completed"]
    assert status["catboost_schedule_proposal"]["sha256"] == digest(study.PROPOSAL)
    print(json.dumps({"integrity":"passed","completed_studies_counted_from_saved_selections":len(counts),
        "configurations_counted_from_saved_results":sum(counts.values()),"cumulative_distinct_tests":264,
        "scoped_evidence_hashes_checked":hashes,"native_trajectory_artifact_hashes_checked":45,
        "independent_native_trajectory_refits_in_saved_audit":audit["actual_native_trajectory_refits"],
        "independent_native_short_control_refits_in_saved_audit":2,"original_historical_prefix_controls_reproduced":10,
        "retained_test_correct":status["best_verified_test_correct"],"retained_test_accuracy":status["best_verified_test_accuracy"],
        "goal_achieved":status["goal_achieved"],"historical_model_refitting_performed":False}),flush=True)


if __name__ == "__main__":
    validate()
