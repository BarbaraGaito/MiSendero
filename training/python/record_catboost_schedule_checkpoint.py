"""Record only verified fixed-rate/native-tree-budget evidence."""
import argparse
import json
from pathlib import Path

import fatigue_catboost_schedule as study
from public_sources import digest


def update(phase):
    path = study.DOCS/"current-research-status.json"
    status = json.loads(path.read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((48,1776),(49,1792))
    assert status["python_tests_passed"] in (260,264) and status["goal_status"] == "active"
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["plan"] == study.plan() and all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    tests = (study.DOCS/"catboost-schedule-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    status["python_tests_passed"] = 264
    status["catboost_schedule_proposal"] = {"document":study.PROPOSAL.name,"sha256":digest(study.PROPOSAL),
        "implementation_started":True,"model_fitting_started":True,"used_in_study":study.DIRECTORY.name,
        "planned_configurations_including_controls":16,"new_unique_schedules":10,"fresh_historical_controls":2,
        "learning_rates":list(study.RATES),"tree_prefixes":list(study.PREFIXES),"maximum_tree_trajectory_fits":15,
        "native_prefix_evaluations":60,"source_outcomes_fitted":0}
    if phase in ("start","pending"):
        assert status["completed_studies"] == 48
        status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":16,
            "inherited_controls":4,"new_unique_native_schedules":10,"fresh_historical_controls":2,
            "native_maximum_tree_trajectory_fits":15,"fixed_native_prefix_evaluations":60,
            "learning_rates":list(study.RATES),"tree_prefixes":list(study.PREFIXES),"depth":3,"l2_leaf_reg":30.,
            "source_outcomes_fitted":0,"training_log":"catboost-schedule-training.log","counted_as_complete":False,
            "phase":"training_selection" if phase == "start" else "independent_native_trajectory_verification",
            "training_selection_complete":selection["status"] == "complete"}
        status["next_evidence_based_direction"] = (
            "Study49addresses the previously fixed CatBoost learning rate:16predeclared recipes,3rates crossed with4tree budgets,original29history variables,depth3/L2=30and all other original parameters held constant. "
            "Fifteen maximum2700-tree trajectories yield60fixed-prefix evaluations across original5personfolds. Historical.03/300and.03/900prefixes must exactly reproduce old OOFcontrols in everyfold. "
            "Four actual-native tests passed,including all3rates,true estimator targets/params,no evalset,natural missing inputs,prefix-versus-short-fit equivalence and input-only reload. Cumulative264distinct tests are not a joint historical rerun. "
            "Finish selection and independent trajectory/short-control refits before counting49; preserve487/179native cases and.65CVtest gate. No synthetic rows,source-label pooling,adaptive outer-fold early stopping or test-directed tuning.80percent requires144of179from a frozen reloaded artifact.")
        if phase == "pending":
            assert selection["status"] == "complete" and len(selection["results"]) == 16
            status["running_study"].update(training_process_terminal=True,verification_log="catboost-schedule-verification.log")
    else:
        assert selection["status"] == "complete" and len(selection["results"]) == 16
        audit_path = study.DOCS/"catboost-schedule-verification.json"
        audit = json.loads(audit_path.read_text())
        assert audit["verification"] == "passed" and audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_catboost_schedule.py"))
        assert audit["selection_sha256"] == digest(selection_path) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
        assert audit["all_16_oof_recipes_recomputed"] and audit["stored_native_trajectories_independently_reloaded"] == 15
        assert audit["actual_native_trajectory_refits"] == len(audit["trajectory_refits"]) and audit["actual_native_trajectory_refits"] in (5,10)
        assert audit["actual_native_short_control_refits"] == len(audit["shortened_control_refits"]) == 2
        assert audit["actual_native_estimator_targets_and_parameters_observed"]
        assert audit["all_stored_native_cbm_and_joblib_prefix_predictions_checked"] and audit["both_historical_prefix_controls_verified_in_all_folds"] == 10
        assert audit["natural_missing_inputs_preserved"] and audit["fitting_only_original_cases"]
        assert selection["synthetic_training_rows"] == selection["source_targets_fitted"] == selection["new_native_borg_targets"] == 0
        status.update(completed_studies=49,evaluated_configurations_including_controls=1792)
        status.pop("running_study",None)
        status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
        status["catboost_schedule_proposal"]["model_study_completed"] = True
        genuinely_new = max((r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"
            and r["candidate"]["matched_historical_candidate_id"] is None),key=lambda r:r["accuracy_mean"])
        diagnostic_path = study.DOCS/"catboost-schedule-fit-cv-diagnostic.json"
        diagnostic = json.loads(diagnostic_path.read_text())
        assert diagnostic["diagnostic"] == "passed" and diagnostic["selection_sha256"] == digest(selection_path)
        assert diagnostic["diagnostic_code_sha256"] == digest(Path(__file__).with_name("diagnose_catboost_schedule_overfit.py"))
        assert diagnostic["fixed_prefix_fit_cv_comparisons"] == 60 and diagnostic["new_estimator_fits"] == 0
        assert diagnostic["native_test_predictions_computed"] == 0 and diagnostic["all_frozen_models_immutable"]
        status["catboost_schedule_fit_cv_diagnostic"] = {"document":diagnostic_path.name,"sha256":digest(diagnostic_path),
            "comparisons":60,"new_estimator_fits":0,"native_test_predictions_computed":0,
            "transitions_with_better_fit_and_worse_cv":diagnostic["transitions_with_better_fit_and_worse_cv"]}
        status["latest_complete_results"].update(catboost_schedule_best_native_cv=audit["best_schedule"]["accuracy_mean"],
            catboost_schedule_best_genuinely_new_cv=genuinely_new["accuracy_mean"],
            catboost_schedule_best_overall_cv=audit["best_cv_accuracy"])
        test = audit["new_test_evaluation"]
        if test and test["correct"] > status["best_verified_test_correct"]:
            status.update(best_verified_test_correct=test["correct"],best_verified_test_accuracy=test["test_accuracy"],
                best_verified_test_artifact=str(study.DIRECTORY/"evaluation/model.joblib"))
        status["goal_achieved"] = status["best_verified_test_correct"] >= 144
        status["next_evidence_based_direction"] = (
            "Study49completed the16recipe native CatBoost rate/tree-budget comparison with15actual maximum-tree trajectories and60fixed-prefix person-fold evaluations. "
            "All old.03/300and.03/900predictions reproduced exactly. Independent verification reloaded all45trajectory artifacts,observed native targets/parameters and independently refitted selected maximum trajectories plus genuine300/900controls. "
            "The60comparison fitting-only diagnostic confirms7transitions with better fit and worseCV;do not repeat this grid or extend MLPbudgets whose best original models already converged. "
            "Next verify/finish the new shoulder-source combination and a bounded separate-output transfer design:920additional actual fitting pairs/27people,187reserved/7people;retain all1416old source fitting targets. "
            "Use only original public measurements and fitting-person CV;keep native487/179cases and.65CVgate. Source outcomes remain separate,natural missing histories retained,no synthetic observations or test-directed tuning.80percent needs144of179from a frozen reloaded artifact.")
        summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
            "configurations":16,"inherited_controls":4,"new_unique_schedules":10,"fresh_historical_controls":2,
            "actual_maximum_tree_trajectory_fits":15,"fixed_native_prefix_evaluations":60,
            "independent_native_trajectory_refits":audit["actual_native_trajectory_refits"],"independent_native_short_control_refits":2,
            "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],"best_schedule":audit["best_schedule"],
            "best_genuinely_new_schedule":{k:genuinely_new[k] for k in ("candidate","accuracy_mean","fold_accuracy")},
            "fitting_cv_diagnostic_sha256":digest(diagnostic_path),
            "results":[{k:r[k] for k in ("candidate","accuracy_mean","fold_accuracy")} for r in selection["results"]],
            "original_training_cases":487,"original_test_cases":179,"test_used_for_selection":False,"new_test_evaluation":test,
            "retained_test_correct":status["best_verified_test_correct"],"retained_test_accuracy":status["best_verified_test_accuracy"],
            "public_real_data_policy_sha256":selection["public_real_data_policy_sha256"],"target_accuracy":.8,"achieved":status["goal_achieved"]}
        (study.DOCS/"catboost-schedule.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    for field in ("additional_scoped_verifications","additional_data_audits","additional_public_candidate_inspections"):
        assert all(digest(study.DOCS/name) == expected for name,expected in status[field].items())
    path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"phase":phase,"completed_studies":status["completed_studies"],"completed_configurations":status["evaluated_configurations_including_controls"],
        "cumulative_distinct_tests":status["python_tests_passed"],"selection_status":selection["status"],
        "best_verified_test_accuracy":status["best_verified_test_accuracy"],"goal_achieved":status["goal_achieved"]}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("start","pending","complete"),default="complete")
    update(parser.parse_args().phase)
