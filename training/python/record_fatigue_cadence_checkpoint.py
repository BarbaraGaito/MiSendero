"""Record independently audited CADENCE transfer, preserving retained metrics."""
import json
from pathlib import Path

import fatigue_cadence_transfer as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    audit_path = folder/"cadence-transfer-verification.json"
    audit = json.loads(audit_path.read_text())
    assert selection["status"] == "complete" and len(selection["plan"]) == len(selection["results"]) == 16
    assert selection["code_sha256"] == digest(Path(study.__file__)) and audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_transfer.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT)
    assert audit["actual_native_rows_and_delta_targets_verified"] and audit["source_targets_original6to20_unchanged"]
    assert audit["actual_source_target_calls_observed"] == 6 and not audit["achieved"] and not audit["new_test_gate_passed"]
    assert audit["best_verified_test_correct"] == 108
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((39,1586),(40,1602))
    tests = (folder/"cadence-transfer-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    status.update(completed_studies=40,evaluated_configurations_including_controls=1602,python_tests_passed=228)
    status.pop("running_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["latest_complete_results"].update({"cadence_lagged_physiology_best_source_cv":audit["best_source_cv_accuracy"],
        "cadence_lagged_physiology_best_measured_control_cv":audit["best_measured_control_cv"],
        "cadence_lagged_physiology_matching_measured_control_cv":audit["matching_measured_control_cv"],
        "cadence_lagged_physiology_best_overall_cv":audit["best_cv_accuracy"]})
    status["cadence_lagged_source_adapter"]["model_study_completed"] = True
    candidate_audit_path = folder/"light-exercise-eligibility.json"
    candidate_audit = json.loads(candidate_audit_path.read_text())
    assert candidate_audit["verification"] == "passed" and candidate_audit["actual_coded_participant_rows"] == 24
    assert candidate_audit["numeric_B_cells"] == 1121 and candidate_audit["original_spreadsheet_error_B_cells"] == 31
    assert not candidate_audit["training_approved"] and not candidate_audit["used_for_training"]
    assert candidate_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_light_exercise_eligibility.py"))
    status["additional_data_audits"][candidate_audit_path.name] = digest(candidate_audit_path)
    status["light_exercise_public_candidate"] = {"source":candidate_audit["source"],"verification":candidate_audit_path.name,
        "actual_coded_participants":24,"numeric_B_cells":1121,"spreadsheet_error_B_cells":31,"observed_B_range":[2,7],
        "formatted_empty_rows_not_participants":15,"instrument_and_pulse_column_codebook_missing":True,
        "exact_session_dates_and_response_clock_missing":True,"training_approved":False,"used_for_training":False}
    status["next_evidence_based_direction"] = (
        "CADENCE lagged-physiology study completed16 recipes, with851 real source targets/123 people for fitting and206 targets/32 people reserved. "
        "Independent refits reproduce all6 source regressors and the selected source/physiology-control native recipes. "
        "Read audited scores before extending this family: source6-20 remains separate, measured source/native baseline contexts differ and exact source response clocks remain unknown. "
        "The new source did not qualify a native model for another test evaluation. Raw new physiological inputs reduced both matched controls; next isolate the source representation from redundant raw absolute/relative fields and compare a small predeclared regularization/capacity grid on original participant CV. "
        "A newly screened public longitudinal light-exercise workbook contains24 actual coded people and1121 numeric B cells, but scale/codebook and response timing remain undocumented; it is excluded from fitting pending source evidence. Do not repeat the frozen original-feature grid or tune on the original179 test. "
        "All original487/179 exact Borg person-held cases and public-real-only constraints remain fixed; the80percent goal is still active.")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "input_verification_sha256":digest(study.INPUT_AUDIT),"configurations":16,
        "source_fitting_targets":851,"source_fitting_people":123,"source_reserved_targets":206,"source_reserved_people":32,
        "source_original_scale":"6-20","native_original_scale":"0-10","source_label_conversion":False,
        "actual_source_regressors":audit["actual_source_regressors_independently_refitted"],
        "public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],"winner_id":selection["winner_id"],
        "best_cv_accuracy":selection["best_cv_accuracy"],"best_source_id":audit["best_source_candidate_id"],
        "best_source_cv_accuracy":audit["best_source_cv_accuracy"],"best_measured_control_id":audit["best_measured_control_id"],
        "best_measured_control_cv":audit["best_measured_control_cv"],"matching_measured_control_id":audit["matching_measured_control_id"],
        "matching_measured_control_cv":audit["matching_measured_control_cv"],"convergence_warning_folds":audit["convergence_warning_folds_in_grid"],
        "results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"new_test_gate_passed":False,"test_used_for_selection":False,
        "retained_test_correct":108,"retained_test_accuracy":audit["best_verified_test_accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Source-only original6-20 supervision and computed physiology representations, with matched measured-only controls. No synthetic examples, invented clocks, native label conversion, altered denominators or test tuning."}
    (folder/"cadence-physiology-transfer.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"studies":40,"configurations":1602,"best_source_cv":audit["best_source_cv_accuracy"],
        "best_measured_control_cv":audit["best_measured_control_cv"],"best_overall_cv":audit["best_cv_accuracy"],
        "retained_test":audit["best_verified_test_accuracy"],"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
