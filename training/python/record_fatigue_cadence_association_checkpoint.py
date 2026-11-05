"""Record audited association evidence and measured session-rest follow-up."""
import argparse
import json
from pathlib import Path

import fatigue_cadence_association as study
import fatigue_session_rest_inputs as rest
from public_sources import ROOT, digest


def common():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["status"] == "complete" and len(selection["plan"]) == len(selection["results"]) == 30
    assert selection["code_sha256"] == digest(Path(study.__file__))
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((41,1634),(42,1664))
    assert status["python_tests_passed"] == 236
    tests = (folder/"cadence-association-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    input_audit = json.loads(study.INPUT_AUDIT.read_text())
    assert input_audit["verification"] == "passed" and input_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_cadence_association_inputs.py"))
    assert input_audit["source_provenance_sha256"] == digest(study.prepared.SOURCE_DIRECTORY/"provenance.json")
    assert input_audit["native_provenance_sha256"] == digest(study.prepared.NATIVE_DIRECTORY/"provenance.json")
    status["additional_data_audits"][study.INPUT_AUDIT.name] = digest(study.INPUT_AUDIT)
    diagnostic_path = folder/"cadence-baseline-context-diagnostic.json"
    diagnostic = json.loads(diagnostic_path.read_text())
    assert diagnostic["code_sha256"] == digest(Path(__file__).with_name("diagnose_cadence_baseline_context.py"))
    assert diagnostic["native_fitting_comparable_cases_task_baseline_above_session_by_more_than10bpm"] == 128
    assert not diagnostic["native_current_borg_used_for_diagnostic"] and not diagnostic["model_fitting_started"]
    status["additional_data_audits"][diagnostic_path.name] = digest(diagnostic_path)
    rest_audit_path = folder/"session-rest-input-verification.json"
    rest_audit = json.loads(rest_audit_path.read_text())
    assert rest_audit["verification"] == "passed" and rest_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_session_rest_inputs.py"))
    assert rest_audit["raw_csv_reader_code_sha256"] == digest(Path(__file__).with_name("audit_cadence_association_inputs.py"))
    assert rest_audit["input_provenance_sha256"] == digest(rest.DIRECTORY/"provenance.json")
    assert rest_audit["original_native_cases_independently_verified"] == 666 and rest_audit["natural_missing_baselines_per_feature"] == 30
    assert rest_audit["all_used_minutes_completed_before_first_task_and_query"] and not rest_audit["new_model_fitting_started"]
    status["additional_data_audits"][rest_audit_path.name] = digest(rest_audit_path)
    status["native_session_rest_input_opportunity"] = {"context_diagnostic":diagnostic_path.name,"input_verification":rest_audit_path.name,
        "input_directory":rest.DIRECTORY.name,"input_provenance_sha256":rest_audit["input_provenance_sha256"],
        "actual_sessions":44,"sessions_with_measured_pre_first_task_baseline":42,"original_native_cases":666,
        "cases_with_measured_session_baseline":636,"natural_missing_cases_per_feature":30,"baseline_features":rest.FEATURES,
        "fitting_cases_with_observed_session_baseline":472,"reserved_cases_with_observed_session_baseline":164,
        "fitting_cases_current_task_baseline_exceeds_session_mean_by_more_than10bpm":128,
        "original_cases_dropped":0,"synthetic_values":0,"independent_input_audit_completed":True,
        "new_model_fitting_started":False,"native_rest_posture_assumed_seated":False}
    return folder,status_path,status,selection_path,selection


def save_status(status_path,status,folder):
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def pending():
    folder,path,status,_,selection = common()
    assert status["completed_studies"] == 41 and status["evaluated_configurations_including_controls"] == 1634
    assert selection["best_cv_accuracy"] < .65
    status["running_study"].update(phase="independent_source_and_native_refit_verification",training_selection_complete=True,
        training_process_terminal=True,verification_log="cadence-association-verification.log")
    status["next_evidence_based_direction"] = (
        "Source-association selection completed30 recipes; strongest new source representation is below the unchanged global CatBoost control, so no original179 test was opened. "
        "Independent verification is refitting6 source functions and25 selected native folds with actual-row/target observers, source weights frozen and no artificial histories. "
        "A concrete follow-up input discrepancy was screened:128 original fitting cases have current-task baseline more than10bpm above their pre-first-task session mean. "
        "Both actual session mean and lowest completed minute were cached and independently rebuilt for all666 original cases:636 observed/30 naturally missing,44 sessions/42 observed. These new inputs have not entered model fitting. "
        "Wait on the specific verification process before accepting the selection. Preserve native487/179 exact targets and source6-20 separation; all future queries must use completed past measurements and public real observations only.")
    save_status(path,status,folder)
    print(json.dumps({"completed_studies":41,"completed_configurations":1634,"selection":"complete","independent_verification":"in_progress",
        "session_rest_input_audit":"passed","new_session_rest_models_fitted":False,"goal_achieved":False}),flush=True)


def complete():
    folder,status_path,status,selection_path,selection = common()
    audit_path = folder/"cadence-association-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["selection_sha256"] == digest(selection_path) and audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_association.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["all_30_oof_recipes_recomputed"] and audit["native_rows_and_delta_targets_verified_at_actual_fitter"]
    assert audit["source_state_and_difference_independently_verified"] and audit["all_original_native_rows_and_labels_preserved"]
    assert audit["actual_source_target_calls_observed"] == 6 and audit["actual_native_target_calls_observed"] == len(audit["actual_native_refits"]) == 25
    assert audit["source_task_is_retrospective_association"] and not audit["source_pre_rpe_forecast_claim_approved"]
    assert not audit["new_test_gate_passed"] and not audit["achieved"] and audit["best_verified_test_correct"] == 108
    status.update(completed_studies=42,evaluated_configurations_including_controls=1664)
    status.pop("running_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["latest_complete_results"].update({"cadence_association_best_source_cv":audit["best_source_cv_accuracy"],
        "cadence_association_best_mlp_cv":audit["best_source_by_member"]["core"]["accuracy_mean"],
        "cadence_association_best_catboost_cv":audit["best_source_by_member"]["cat"]["accuracy_mean"],
        "cadence_association_measured_mlp_cv":audit["measured_physiology_controls"]["core"]["accuracy_mean"],
        "cadence_association_measured_catboost_cv":audit["measured_physiology_controls"]["cat"]["accuracy_mean"],
        "cadence_association_best_overall_cv":audit["best_cv_accuracy"]})
    status["cadence_retrospective_association_opportunity"]["model_study_completed"] = True
    status["next_evidence_based_direction"] = (
        "Source-association study completed and independently reproduced30 native CV recipes,6 source functions and25 selected native refits. "
        "Best source representation improved its matched measured-input control but remains below the unchanged global CatBoost control; no new native test gate passed. "
        "Next test the concrete baseline-context discrepancy rather than repeat the same representation grid: source rest precedes the entire treadmill protocol, whereas existing native baseline precedes each task. "
        "In128 original fitting cases the per-task baseline is more than10bpm above the actual session preexercise mean. A new cache of pre-first-task session mean/lowest actual minute is independently audited for all666 cases(636 observed/30 missing;44 sessions/42 observed). "
        "Predeclare a bounded native-CV comparison using these baselines and the now-audited976-target source functions, while preserving source6-20/current native0-10 separation, all487/179 original cases and natural missing inputs. "
        "Native posture is not assumed seated and improvement remains unproven. No synthetic data, invented source clocks, case filtering or native test tuning;80percent goal remains active.")
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "input_verification_sha256":digest(study.INPUT_AUDIT),"configurations":30,"inherited_controls":4,"new_measured_controls":2,
        "new_source_representation_configurations":24,"source_fitting_targets":976,"source_fitting_people":124,
        "source_reserved_targets":238,"source_reserved_people":32,"source_original_scale":"6-20","native_original_scale":"0-10",
        "source_task":"Retrospective concurrent physiology/RPE association, not pre-RPE forecasting","native_queries_past_only":True,
        "source_functions":audit["actual_source_functions_independently_refitted"],"public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],
        "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],"best_source_id":audit["best_source_candidate_id"],
        "best_source_cv_accuracy":audit["best_source_cv_accuracy"],"best_source_by_member":audit["best_source_by_member"],
        "paired_current_change_comparison":audit["paired_current_change_comparison"],"measured_physiology_controls":audit["measured_physiology_controls"],
        "convergence_warning_folds":audit["convergence_warning_folds_in_grid"],
        "results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"new_test_gate_passed":False,"test_used_for_selection":False,
        "retained_test_correct":108,"retained_test_accuracy":audit["best_verified_test_accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Only actual public source association observations and original native targets. Computed source states/differences, genuine completed pre-query physiological inputs and fixed native person CV. No synthetic data, transformed native labels, invented source clocks, changed denominators or native test selection."}
    (folder/"cadence-association-transfer.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    save_status(status_path,status,folder)
    print(json.dumps({"studies":42,"configurations":1664,"best_source_cv":audit["best_source_cv_accuracy"],
        "best_mlp_cv":audit["best_source_by_member"]["core"]["accuracy_mean"],"best_catboost_cv":audit["best_source_by_member"]["cat"]["accuracy_mean"],
        "best_overall_cv":audit["best_cv_accuracy"],"retained_test":audit["best_verified_test_accuracy"],"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending",action="store_true")
    args = parser.parse_args()
    pending() if args.pending else complete()
