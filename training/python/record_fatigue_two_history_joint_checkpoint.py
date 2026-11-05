"""Record the public two-history backpropagation experiment and scoped evidence."""
import argparse
import json
from pathlib import Path

import fatigue_two_history_joint as study
from public_sources import digest


def common():
    path = study.DOCS/"current-research-status.json"
    status = json.loads(path.read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((45,1724),(46,1740))
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["plan"] == study.plan(inputs["previous_audit"]) and all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    tests = (study.DOCS/"two-history-joint-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    assert selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == 0
    assert selection["actual_source_fitting_targets_available"] == 550 and selection["actual_source_fitting_second_priors"] == 367
    assert selection["reserved_source_targets_not_fitted"] == 57 and not selection["test_used_for_selection"]
    return path,status,inputs,selection_path,selection


def save(path,status):
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(study.DOCS/name) == expected for name,expected in status[field].items())
    path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def start():
    path,status,_,_,selection = common()
    assert status["completed_studies"] == 45 and status["python_tests_passed"] in (248,252)
    status["python_tests_passed"] = 252
    status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":16,
        "new_native_recipes":12,"predeclared_native_joint_folds":60,"native_base_fits_including_inner_models":40,
        "native_inner_person_folds":3,"actual_source_fitting_targets_available":550,"actual_source_fitting_second_priors":367,
        "source_targets_by_separate_head":study.SOURCE_COUNTS,"source_reserved_targets_not_fitted":57,
        "auxiliary_loss_weights":[0,.1,1],"fixed_epoch_budgets":[80,200],"native_base_weights_frozen":True,
        "training_log":"two-history-joint-training.log","phase":"training_selection","counted_as_complete":False,
        "training_selection_complete":selection["status"] == "complete"}
    status["public_two_prior_history_opportunity"].update(model_fitting_started=True,used_in_study=study.DIRECTORY.name)
    status["next_joint_history_proposal"].update(implementation_started=True,model_fitting_started=True,used_in_study=study.DIRECTORY.name)
    status["next_evidence_based_direction"] = (
        "Study46is running the frozen16recipe actual two-history joint comparison:4inherited controls and12new residual networks over MLP/Cat bases,auxiliary weights0/.1/1 and80/200epochs. "
        "Shared histories retain550source fitting targets,367actual second priors and57reserved source targets. Three separate continuous-delta source heads preserve EMAP/Worker/STSoutcomes; zero auxiliary weight excludes source current labels from the objective with matched architecture/preprocessing. "
        "Native offsets are generated in3inner participant folds,with the native base frozen during full-batch AdamW. All487/179original native exact cases retained.4newactual-public tests passed in149.508s:8native base fits observed,actual source/native losses and source-to-encoder gradients,zero-source-label control and reload. Cumulative252distinct tests are not a rerun of all historical suites. "
        "Wait on the specific60joint-fold selection and40native base fits. If a new winner reaches the predeclared.65CVgate,freeze/evaluate its sole original179artifact before verification; otherwise do not open a new test. No synthetic data, fabricated history masks, source clocks/phases/sensors or label pooling.")
    save(path,status)
    print(json.dumps({"completed_studies":45,"completed_configurations":1724,"running_study":study.DIRECTORY.name,
        "planned_configurations":16,"new_native_joint_folds":60,"native_base_fits_including_inner":40,"cumulative_distinct_tests":252,"goal_achieved":False}),flush=True)


def pending():
    path,status,_,_,selection = common()
    assert status["completed_studies"] == 45 and status["python_tests_passed"] == 252
    assert selection["status"] == "complete" and len(selection["results"]) == 16
    qualified = selection["best_cv_accuracy"] >= .65
    if qualified:
        assert (study.DIRECTORY/"evaluation/metrics.json").exists()
    status["running_study"].update(phase="independent_base_and_joint_training_verification",training_selection_complete=True,
        training_process_terminal=True,verification_log="two-history-joint-verification.log",new_native_test_gate_passed=qualified)
    status["next_evidence_based_direction"] = (
        "All16actual two-history joint recipes completed original5person CV. Independent verification must inspect40cached native base fits and source/native fitting-only statistics,refit actual bases in one outer fold per member,and reproduce best positive/zero-auxiliary paired networks with actual-loss/gradient observers. "
        "A new frozen original179test is permitted only for the sole CVwinner if.65gate passed; its artifact must be reloaded and original labels/cases verified. Retain whichever independently verified test artifact has the highest exact accuracy;80percent requires144of179. No synthetic histories, pooled source outcomes, inferred source clocks or changed native487/179cases.")
    save(path,status)
    print(json.dumps({"selection":"complete","independent_verification":"running","best_cv_accuracy":selection["best_cv_accuracy"],
        "new_native_test_gate_passed":qualified,"goal_achieved":False}),flush=True)


def complete():
    path,status,_,selection_path,selection = common()
    assert status["python_tests_passed"] == 252 and selection["status"] == "complete" and len(selection["results"]) == 16
    audit_path = study.DOCS/"two-history-joint-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_two_history_joint.py"))
    assert audit["selection_sha256"] == digest(selection_path) and audit["input_verification_sha256"] == digest(study.INPUT_AUDIT)
    assert audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["all_16_oof_recipes_recomputed"] and audit["original_native_rows_and_targets_preserved"]
    assert audit["native_base_caches_checked"] == 10 and audit["cached_native_base_fit_models_checked"] == 40
    assert audit["independent_native_base_fits"] == 8 and audit["actual_native_joint_refits"] == len(audit["joint_refits"])
    assert len(audit["joint_refits"]) == len(audit["native_recipes_independently_refitted"])*5
    assert audit["actual_source_and_native_loss_targets_observed"] and audit["actual_source_encoder_gradients_verified"]
    assert audit["zero_auxiliary_control_excludes_source_labels"] and audit["native_base_weights_frozen"]
    assert audit["shared_preprocessing_fitting_rows_only"] and audit["native_context_preprocessing_fitting_people_only"]
    assert not audit["source_outcomes_pooled"] and audit["synthetic_rows"] == 0
    status.update(completed_studies=46,evaluated_configurations_including_controls=1740)
    status.pop("running_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["latest_complete_results"].update(two_history_joint_best_positive_cv=audit["best_positive_cv_accuracy"],
        two_history_joint_best_positive_mlp_cv=audit["best_positive_by_member"]["core"]["accuracy_mean"],
        two_history_joint_best_positive_catboost_cv=audit["best_positive_by_member"]["cat"]["accuracy_mean"],
        two_history_joint_matched_zero_mlp_cv=audit["matched_zero_auxiliary_controls"]["core"]["accuracy_mean"],
        two_history_joint_matched_zero_catboost_cv=audit["matched_zero_auxiliary_controls"]["cat"]["accuracy_mean"],
        two_history_joint_best_overall_cv=audit["best_cv_accuracy"])
    status["public_two_prior_history_opportunity"].update(joint_model_study_completed=True)
    status["next_joint_history_proposal"].update(model_study_completed=True)
    test = audit.get("new_test_evaluation")
    if test and test["correct"] > status["best_verified_test_correct"]:
        status.update(best_verified_test_correct=test["correct"],best_verified_test_accuracy=test["test_accuracy"],
            best_verified_test_artifact=str(study.DIRECTORY/"evaluation/model.joblib"))
    status["goal_achieved"] = status["best_verified_test_correct"] >= 144
    status["next_evidence_based_direction"] = (
        "Study46completed16joint actual-history recipes and independent verification of40cached native bases,8independent native base refits,and selected paired joint networks across5original person folds. "
        "Shared backpropagation used actual550source fitting targets with367measured second priors and separate EMAP/Worker/STSheads; zero-auxiliary controls excluded source current labels. "
        "Inspect the audited positive-versus-zero source comparisons and training endpoints before selecting another mechanism or hyperparameter axis. Do not repeat an unchanged source-weight/epoch grid. "
        "Preserve original487/179native exact cases and person validation,57source target reservation,all original unscaled responses and natural missing priors.80percent remains unproven unless a reloaded frozen artifact reaches144of179; no generated examples, source label pooling or benchmark exclusions.")
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "input_verification_sha256":digest(study.INPUT_AUDIT),"configurations":16,"inherited_controls":4,"new_native_recipes":12,
        "source_fitting_targets_available":550,"source_fitting_actual_second_priors":367,"reserved_source_targets_not_fitted":57,
        "native_base_fits_in_original_grid":40,"independent_native_base_fits":8,"independent_native_joint_refits":audit["actual_native_joint_refits"],
        "source_targets_pooled_across_instruments":False,"winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],
        "best_positive_by_member":audit["best_positive_by_member"],"matched_zero_auxiliary_controls":audit["matched_zero_auxiliary_controls"],
        "best_positive_cv_accuracy":audit["best_positive_cv_accuracy"],"results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"test_used_for_selection":False,"new_test_evaluation":test,
        "retained_test_correct":status["best_verified_test_correct"],"retained_test_accuracy":status["best_verified_test_accuracy"],
        "public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],"target_accuracy":.8,"achieved":status["goal_achieved"],
        "scope":"Actual public source/native rows and genuine prior histories only. Three separate continuous source-delta heads jointly trained with native exact-delta residual correction; native bases frozen and inner-person cross-fitting. Same original487/179cases and550/57source reservation. No artificial histories, synthesized rows, guessed clocks/phases/sensors, pooled labels or changed denominators."}
    (study.DOCS/"two-history-joint-transfer.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    save(path,status)
    print(json.dumps({"completed_studies":46,"configurations":1740,"cumulative_distinct_tests":252,
        "best_positive_cv":audit["best_positive_cv_accuracy"],"best_overall_cv":audit["best_cv_accuracy"],
        "best_verified_test_accuracy":status["best_verified_test_accuracy"],"goal_achieved":status["goal_achieved"]}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("start","pending","complete"),default="complete")
    args = parser.parse_args()
    {"start":start,"pending":pending,"complete":complete}[args.phase]()
