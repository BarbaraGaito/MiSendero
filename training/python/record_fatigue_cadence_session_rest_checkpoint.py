"""Record the independently audited session-rest study and original EMAP review."""
import argparse
import json
from pathlib import Path

import fatigue_cadence_session_rest as study
from public_sources import ROOT, digest


def complete():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    path = folder/"current-research-status.json"
    status = json.loads(path.read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((42,1664),(43,1698))
    assert status["python_tests_passed"] == 240
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert selection["status"] == "complete" and selection["plan"] == study.plan() and len(selection["results"]) == 34
    audit_path = folder/"cadence-session-rest-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_session_rest.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["source_refit_verifier_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_association.py"))
    assert audit["all_34_oof_recipes_recomputed"] and audit["all_native_rows_and_labels_preserved"]
    assert audit["source_verification_refits"] == len(audit["source_functions_refitted_for_independent_verification_only"]) == 6
    assert audit["actual_native_target_calls_observed"] == len(audit["actual_native_refits"]) == 25
    assert not audit["source_functions_refitted_during_selection"] and audit["source_artifacts_unchanged_after_verification"]
    assert audit["source_states_and_changes_independently_computed"] and audit["native_rows_and_delta_targets_observed_at_actual_fitter"]
    assert audit["native_preprocessing_fitting_people_only"] and audit["source_functions_frozen_during_native_fitting"]
    assert audit["natural_missing_session_baselines"] == 30 and audit["artificial_history_fitting_disabled"]
    assert not audit["new_test_gate_passed"] and not audit["achieved"] and audit["best_verified_test_correct"] == 108
    tests = (folder/"cadence-session-rest-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    emap_path = folder/"exercise-rpe-original-verification.json"
    emap = json.loads(emap_path.read_text())
    assert emap["verification"] == "passed" and emap["audit_code_sha256"] == digest(Path(__file__).with_name("audit_exercise_rpe_originals.py"))
    assert emap["actual_published_cohort_rpe_cells"] == 407 and emap["actual_adjacent_rpe_pairs"] == 305
    assert emap["auxiliary_ordered_rpe_history_review_eligible"] and not emap["native_target_merge_approved"]
    assert not emap["concurrent_native_sensor_join_approved"] and not emap["model_fitting_started"]
    assert emap["synthetic_rows"] == emap["imputed_or_mean_targets_used"] == 0
    status.update(completed_studies=43,evaluated_configurations_including_controls=1698)
    status.pop("running_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["additional_data_audits"][emap_path.name] = digest(emap_path)
    status["latest_complete_results"].update({
        "cadence_session_rest_best_source_cv":audit["best_source_cv_accuracy"],
        "cadence_session_rest_best_mlp_cv":audit["best_source_by_member"]["core"]["accuracy_mean"],
        "cadence_session_rest_best_catboost_cv":audit["best_source_by_member"]["cat"]["accuracy_mean"],
        "cadence_session_rest_matched_measured_mlp_cv":audit["matching_measured_controls"]["core"]["accuracy_mean"],
        "cadence_session_rest_matched_measured_catboost_cv":audit["matching_measured_controls"]["cat"]["accuracy_mean"],
        "cadence_session_rest_best_overall_cv":audit["best_cv_accuracy"]})
    status["native_session_rest_input_opportunity"].update(new_model_fitting_started=True,model_study_completed=True)
    status["emap_real_cr10_history_opportunity"] = {
        "original_verification":emap_path.name,"original_verification_sha256":digest(emap_path),
        "public_record":"https://zenodo.org/records/19387250","license":"CC-BY-4.0",
        "published_cohort_people":109,"people_with_actual_responses":102,"actual_rpe_cells":407,
        "actual_adjacent_pairs":305,"source_fitting_pairs":248,"source_reserved_pairs":57,
        "source_fitting_people_with_responses":83,"source_reserved_people_with_responses":19,
        "original_cr10_scale":"0-10","synthetic_rows":0,"imputed_or_mean_targets_used":0,
        "auxiliary_history_only":True,"exact_report_clocks_known":False,
        "concurrent_sensor_join_approved":False,"native_target_merge_approved":False,"model_fitting_started":False}
    status["next_evidence_based_direction"] = (
        "Session-rest selection completed34 recipes and independent verification reproduced6 frozen source functions plus25 native fold fits. "
        "No recipe crossed the predeclared.65 native CV gate; original179 test remains unopened and retained108/179 result unchanged. "
        "A genuinely new public source is now original-cell verified:EMAP109 published cohort people,407 actual individual CR10 responses/102 people and305 actual adjacent pairs,248 fitting/57 reserved by original whole-person split. "
        "Build a versioned ordered-history-only adapter preserving original missing cells and questionnaire order, then compare separate/fused auxiliary functions using only measured prior RPE values. "
        "The source has no exact report clocks or concurrent HR; do not invent times, phase equivalence, Borg labels, accelerometer joins or imputed/mean targets. "
        "Preserve original487/179 native exact targets and person CV; public real observations only.80percent remains unachieved.")
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "input_verification_sha256":digest(study.INPUT_AUDIT),"configurations":34,"inherited_controls":6,"new_measured_controls":4,
        "new_source_representation_configurations":24,"source_fitting_targets":976,"source_fitting_people":124,
        "source_reserved_targets":238,"source_reserved_people":32,"source_functions_refitted_during_selection":False,
        "source_original_scale":"6-20","native_original_scale":"0-10","session_baselines":study.BASELINES,
        "original_native_cases":666,"observed_session_baselines":636,"natural_missing_session_baselines":30,
        "source_verification_refits":6,"native_verification_refits":25,"public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],
        "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],"best_source_id":audit["best_source_candidate_id"],
        "best_source_cv_accuracy":audit["best_source_cv_accuracy"],"best_source_by_member":audit["best_source_by_member"],
        "paired_session_baseline_comparison":audit["paired_session_baseline_comparison"],"matching_measured_controls":audit["matching_measured_controls"],
        "convergence_warning_folds":audit["convergence_warning_folds_in_grid"],
        "results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"new_test_gate_passed":False,"test_used_for_selection":False,
        "retained_test_correct":108,"retained_test_accuracy":108/179,"target_accuracy":.8,"achieved":False,
        "scope":"Actual public source/native rows only. First-task session mean/lowest completed minute; native posture not assumed seated. Source6-20 association outputs remain computed features; no changed native labels, fabricated histories, synthetic examples, case removal or native test tuning."}
    (folder/"cadence-session-rest-transfer.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"studies":43,"configurations":1698,"cumulative_distinct_tests":240,
        "best_source_cv":audit["best_source_cv_accuracy"],"best_overall_cv":audit["best_cv_accuracy"],
        "retained_test_accuracy":108/179,"new_emap_actual_pairs":305,"goal_achieved":False}),flush=True)


def pending():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    path = folder/"current-research-status.json"
    status = json.loads(path.read_text())
    selection = json.loads((study.DIRECTORY/"selection.json").read_text())
    assert status["completed_studies"] == 42 and selection["status"] == "complete" and len(selection["results"]) == 34
    assert selection["best_cv_accuracy"] < .65 and status["python_tests_passed"] == 240
    status["running_study"].update(phase="independent_source_and_native_verification",training_selection_complete=True,
        training_process_terminal=True,verification_log="cadence-session-rest-verification.log")
    for name in ("exercise-rpe-original-verification.json","emap-history-input-verification.json"):
        audit = json.loads((folder/name).read_text())
        assert audit["verification"] == "passed"
        status["additional_data_audits"][name] = digest(folder/name)
    status["next_evidence_based_direction"] = (
        "Study43completed34recipe selection;best new session-rest representation.6214878353 remains below original.6379721574control. "
        "Independent verification is running6source-function verification refits plus25native refits; no new original179test gate passed. "
        "New original public EMAPsource cells were verified and305actual ordered pairs independently rebuilt from XML:248fitting/57reserved. "
        "A versioned adapter preserves all302earlier Worker/STS pairs and separate outcomes, giving550fitting targets without synthetic data. "
        "Once43verification finishes, test16predeclared ordered-history-only recipes with EMAPalone or3separate source heads; no invented clocks, source sensor joins, imputed targets or changed native487/179cases.")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"study43_selection":"complete","independent_verification":"running","best_new_cv":.6214878352678864,
        "new_actual_emap_pairs":305,"new_combined_fitting_pairs":550,"new_source_models_fitted":False}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending",action="store_true")
    args = parser.parse_args()
    pending() if args.pending else complete()
