"""Record the predeclared comparison of separate real source-order functions."""
import argparse
import json
from pathlib import Path

import fatigue_emap_ordered_functions as study
from public_sources import digest


def common():
    folder = study.parent.source.DOCS
    path = folder/"current-research-status.json"
    status = json.loads(path.read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((44,1714),(45,1724))
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["plan"] == study.plan(inputs["previous_audit"]) and all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    tests = (folder/"emap-ordered-functions-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    raw_history_audit_path = folder/"public-two-prior-history-v2-verification.json"
    raw_history = json.loads(raw_history_audit_path.read_text())
    assert raw_history["verification"] == "passed" and raw_history["audit_code_sha256"] == digest(Path(__file__).with_name("audit_public_two_prior_histories_v2.py"))
    assert raw_history["source_preparation_code_sha256"] == digest(Path(__file__).with_name("fatigue_public_two_prior_histories_v2.py"))
    source_directory = study.DIRECTORY.parent/"public-two-prior-histories-80-v2"
    assert raw_history["source_provenance_sha256"] == digest(source_directory/"provenance.json")
    assert raw_history["worker_second_priors_independently_verified_from_original_cells"] == 202
    assert raw_history["fitting_observed_second_priors"] == 367 and not raw_history["model_fitting_started"]
    chain_path = folder/"public-two-prior-history-chain-review.json"
    chain = json.loads(chain_path.read_text())
    assert chain["status"] == "superseded_by_direct_original_cells" and chain["additional_original_available_second_priors"] == 2
    assert chain["preferred_verification_sha256"] == digest(raw_history_audit_path)
    assert not chain["chain_only_snapshot_used_for_model_fitting"] and not chain["eligible_chain_snapshot_for_future_model_fitting"]
    status["additional_data_audits"][raw_history_audit_path.name] = digest(raw_history_audit_path)
    status["additional_data_audits"][chain_path.name] = digest(chain_path)
    status["public_two_prior_history_opportunity"] = {"source_directory":source_directory.name,
        "source_provenance_sha256":raw_history["source_provenance_sha256"],"input_verification":raw_history_audit_path.name,
        "original_current_pairs":607,"fitting_current_pairs":550,"reserved_emap_current_pairs":57,
        "actual_worker_second_priors":202,"actual_emap_second_priors":203,"actual_second_priors":405,
        "fitting_actual_second_priors":367,"reserved_actual_second_priors":38,"unavailable_second_priors_preserved":202,
        "original_current_targets_preserved":True,"new_independent_current_observations":0,"synthetic_rows":0,
        "source_outcomes_must_remain_separate":True,"model_fitting_started":False,
        "chain_only_v1_superseded":True,"chain_only_v1_coverage_review":chain_path.name}
    return folder,path,status,selection_path,selection,inputs


def save(folder,path,status):
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def start():
    folder,path,status,_,selection,_ = common()
    assert status["completed_studies"] == 44 and status["python_tests_passed"] in (244,248)
    status["python_tests_passed"] = 248
    status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":10,
        "new_native_recipes":6,"predeclared_native_folds":30,"distinct_actual_emap_fitting_targets":248,
        "source_order_fitting_counts":{"T2":83,"T3":83,"T4":82},"reserved_emap_targets_not_fitted":57,
        "source_phase_equivalence_to_native_assumed":False,"inherited_source_functions_refitted":False,
        "training_log":"emap-ordered-functions-training.log","counted_as_complete":False,
        "phase":"training_selection","training_selection_complete":selection["status"] == "complete"}
    if "next_predeclared_study" in status:
        assert status["next_predeclared_study"]["plan_sha256"] == digest(study.DECLARATION)
        status["next_predeclared_study"].update(model_fitting_started=True,tests_executed=True)
    status["next_evidence_based_direction"] = (
        "Study45is executing its predeclared10recipes,4inherited real controls plus6new ordered-source recipes in30native folds. "
        "The same248actual fitting EMAPtargets remain83/83/82distinct T2/T3/T4tasks,with57source targets reserved. T2uses its one genuinely available prior only;T3/T4use two. "
        "All3source functions are computed for every native query without assigning native phases. Per-member Worker/STSinclusion is fixed from preceding audited native CV and those functions remain frozen. "
        "Four new actual-public tests passed,bringing cumulative distinct tests to248without rerunning all historical suites. Wait on the specific selection,then reproduce best new/matched preceding native folds. Original487/179exact cases and.65CVgate remain fixed; no synthetic data, invented clocks/phases/sensors or imputed targets.")
    save(folder,path,status)
    print(json.dumps({"completed_studies":44,"completed_configurations":1714,"running_study":study.DIRECTORY.name,
        "planned_configurations":10,"new_native_folds":30,"cumulative_distinct_tests":248,"goal_achieved":False}),flush=True)


def pending():
    folder,path,status,_,selection,_ = common()
    assert status["completed_studies"] == 44 and status["python_tests_passed"] == 248
    assert selection["status"] == "complete" and len(selection["results"]) == 10 and selection["best_cv_accuracy"] < .65
    status["running_study"].update(phase="independent_source_and_matched_native_verification",training_selection_complete=True,
        training_process_terminal=True,verification_log="emap-ordered-functions-verification.log")
    status["next_evidence_based_direction"] = (
        "All10ordered-source recipes completed native5fold CV; none crossed.65gate and no original179test was opened. "
        "Independent verification is refitting9ordered source functions and20native folds(best new plus exact matching preceding pooled-order controls). "
        "Original248distinct source-fitting targets remain83/83/82ordered tasks with only measured available priors,57source targets reserved, original487/179native cases unchanged and source weights frozen during native fitting. Wait for the specific audit before accepting the study.")
    save(folder,path,status)
    print(json.dumps({"selection":"complete","independent_verification":"running","best_overall_cv":selection["best_cv_accuracy"],"goal_achieved":False}),flush=True)


def complete():
    folder,path,status,selection_path,selection,_ = common()
    assert status["python_tests_passed"] == 248 and selection["status"] == "complete" and len(selection["results"]) == 10
    audit_path = folder/"emap-ordered-functions-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_emap_ordered_functions.py"))
    assert audit["selection_sha256"] == digest(selection_path) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["predeclared_plan_sha256"] == digest(study.DECLARATION) and audit["fitting_context_diagnostic_sha256"] == digest(study.DIAGNOSTIC)
    assert audit["all_10_oof_recipes_recomputed"] and audit["original_native_rows_and_targets_preserved"]
    assert audit["source_verification_refits"] == len(audit["actual_source_functions_independently_refitted"]) == 9
    assert audit["actual_native_target_calls_observed"] == len(audit["actual_native_refits"]) == 20
    assert audit["original248targets_unique_across_each_algorithm_source_tasks"] and audit["original_source_delta_targets_observed_at_actual_fitter"]
    assert audit["t2_unobserved_second_prior_excluded"] and audit["source_artifacts_unchanged_after_verification"] and not audit["inherited_source_functions_refitted"]
    assert audit["native_source_changes_independently_computed"] and audit["native_delta_targets_observed_at_actual_fitter"]
    assert audit["source_weights_frozen_during_native_fitting"] and audit["native_preprocessing_fitting_people_only"]
    assert not audit["native_phase_assignment_performed"] and audit["synthetic_rows"] == audit["invented_source_clocks_or_sensor_joins"] == 0
    assert not audit["new_test_gate_passed"] and not audit["achieved"] and audit["best_verified_test_correct"] == 108
    status.update(completed_studies=45,evaluated_configurations_including_controls=1724)
    status.pop("running_study",None)
    status.pop("next_predeclared_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["latest_complete_results"].update(emap_ordered_functions_best_new_cv=audit["best_new_cv_accuracy"],
        emap_ordered_functions_best_mlp_cv=audit["best_new_by_member"]["core"]["accuracy_mean"],
        emap_ordered_functions_best_catboost_cv=audit["best_new_by_member"]["cat"]["accuracy_mean"],
        emap_ordered_functions_matching_pooled_mlp_cv=audit["matched_pooled_order_controls"]["core"]["accuracy_mean"],
        emap_ordered_functions_matching_pooled_catboost_cv=audit["matched_pooled_order_controls"]["cat"]["accuracy_mean"],
        emap_ordered_functions_best_overall_cv=audit["best_cv_accuracy"])
    status["emap_real_cr10_history_opportunity"].update(ordered_function_study_completed=True)
    proposal = folder/"shared-two-prior-joint-proposal.md"
    status["next_joint_history_proposal"] = {"document":proposal.name,"sha256":digest(proposal),
        "implementation_started":False,"model_fitting_started":False,"planned_configurations_including_controls":16,
        "planned_new_native_folds":60,"actual_source_fitting_targets":550,"source_fitting_cases_with_two_actual_priors":367,
        "source_outcomes_kept_separate":True,"public_real_data_only":True}
    status["next_evidence_based_direction"] = (
        "Study45completed10recipes and independently reproduced9ordered source functions plus20native paired-fold refits. "
        "The same248actual EMAPsource-fitting targets were split83/83/82by recorded order with no target duplication, guessed native phases or nonexistent T2second prior. Worker/STSfunctions stayed frozen. "
        "No new.65nativeCVgate passed and retained108/179test result is unchanged. Repeated source-forward features have not established80percent. "
        "A distinct compatible-data improvement is already prepared and independently verified in public-two-prior-histories-80-v2:202Worker second priors from original cells plus203EMAPsecond priors,405total/367fitting/38reserved,with all607current pairs and550fitting targets unchanged. The conservative chain-only v1 missed2actual cells and is superseded; it was not fitted. STS49second priors stay unavailable. "
        "The concrete pending design is in shared-two-prior-joint-proposal.md:16recipes,4inherited controls and12new joint residual variants over nativeMLP/Cat bases,auxiliary weights0/.1/1 and80/200epochs. Separate source heads preserve actual outcomes; native fitting offsets use3inner person folds. The new two-prior cache has not entered model fitting and this joint proposal is not implemented yet. "
        "Compare any new transfer/regularization trial with a zero-auxiliary matched control under fixed participant CV. Do not repeat the same frozen-function grid, merge unlike labels, alter targets/denominators or generate examples.80percent goal remains active.")
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "predeclared_plan_sha256":digest(study.DECLARATION),"configurations":10,"inherited_controls":4,"new_native_recipes":6,
        "actual_distinct_emap_fitting_targets":248,"source_order_target_counts":{"T2":83,"T3":83,"T4":82},
        "source_reserved_targets":57,"source_verification_refits":9,"native_verification_refits":20,"native_phase_assignment_performed":False,
        "inherited_source_functions_refitted":False,"public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],
        "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],"best_new_cv_accuracy":audit["best_new_cv_accuracy"],
        "best_new_by_member":audit["best_new_by_member"],"matched_pooled_order_controls":audit["matched_pooled_order_controls"],
        "convergence_warning_folds":audit["convergence_warning_folds_in_grid"],
        "results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"test_used_for_selection":False,"new_test_gate_passed":False,
        "retained_test_correct":108,"retained_test_accuracy":108/179,"target_accuracy":.8,"achieved":False,
        "scope":"Original actual public CR10pairs and unchanged native exact labels. Separate recorded-order source tasks preserve83/83/82distinct targets and available measured priors,with no assumed native phase assignment. Existing functions frozen; native original person CV retained. No synthetic histories, inferred clocks/sensors, imputed targets or changed native487/179cases."}
    (folder/"emap-ordered-functions-transfer.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    save(folder,path,status)
    print(json.dumps({"completed_studies":45,"configurations":1724,"cumulative_distinct_tests":248,
        "best_new_cv":audit["best_new_cv_accuracy"],"best_overall_cv":audit["best_cv_accuracy"],"retained_test_accuracy":108/179,"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("start","pending","complete"),default="complete")
    args = parser.parse_args()
    {"start":start,"pending":pending,"complete":complete}[args.phase]()
