"""Record the bounded, original-public-runner HR transfer comparison."""
import argparse
import json
from pathlib import Path

import fatigue_furukawa_hr_transfer as study
from public_sources import digest


def update(phase):
    path = study.DOCS/"current-research-status.json"
    status = json.loads(path.read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((47,1762),(48,1776))
    assert status["python_tests_passed"] in (256,260) and status["goal_status"] == "active"
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["plan"] == study.plan() and all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    tests = (study.DOCS/"furukawa-hr-transfer-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    status["python_tests_passed"] = 260
    for field in ("furukawa_pre_report_hr_opportunity","next_furukawa_hr_proposal"):
        status[field].update(model_fitting_started=True,used_in_study=study.DIRECTORY.name)
    status["other_new_public_candidates"]["runners"]["model_fitting_started"] = True
    if phase in ("start","pending"):
        assert status["completed_studies"] == 47
        status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":14,
            "inherited_controls":4,"new_native_recipes":10,"new_native_person_fold_fits":50,
            "source_function_fits":4,"source_state_fitting_targets":252,"source_delta_fitting_targets":168,
            "source_fitting_people":12,"source_reserved_targets_not_fitted":84,"source_reserved_people":4,
            "source_algorithms":["ridge","svr"],"source_tasks":["state","delta"],"native_members":["core","cat"],
            "training_log":"furukawa-hr-transfer-training.log","counted_as_complete":False,
            "phase":"training_selection" if phase == "start" else "independent_source_and_native_fit_verification",
            "training_selection_complete":selection["status"] == "complete"}
        status["next_evidence_based_direction"] = (
            "Study48compares14fixed recipes:4inherited controls,2measured nativeHRcontrols and8Ridge/SVR source-state/delta functions with nativeMLP/Cat. "
            "Four real-public tests passed in46.448s,observing actual source targets/person weights,native estimator targets,fold-only scalers,natural missing HR and input-only reload. Cumulative260distinct tests are not a historical joint rerun. "
            "Source252original Borgpoint responses/12people and168actual adjacentpairs remain separate from original native487targets;84source responses/4otherpeople stay reserved. "
            "Complete50new person-fold fits and independent four-source/thirty-native refits before counting48. Preserve original487/179cases and.65CVgate;80percent requires144of179from a frozen reloaded artifact. No synthetic rows,guessed clocks,rest baselines,source-native point conversion or test-directed tuning.")
        if phase == "pending":
            assert selection["status"] == "complete" and len(selection["results"]) == 14
            status["running_study"].update(training_process_terminal=True,verification_log="furukawa-hr-transfer-verification.log")
    else:
        assert selection["status"] == "complete" and len(selection["results"]) == 14
        audit_path = study.DOCS/"furukawa-hr-transfer-verification.json"
        audit = json.loads(audit_path.read_text())
        assert audit["verification"] == "passed" and audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_furukawa_hr_transfer.py"))
        assert audit["selection_sha256"] == digest(selection_path) and audit["input_verification_sha256"] == digest(study.INPUT_AUDIT)
        assert audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT) and audit["all_14_oof_recipes_recomputed"]
        assert audit["actual_source_function_refits"] == len(audit["source_function_refits"]) == 4
        assert audit["actual_native_refits"] == len(audit["native_refits"]) == 5*len(audit["native_recipes_independently_refitted"]) == 30
        assert audit["actual_source_and_native_estimator_targets_and_weights_observed"] and audit["source_functions_frozen_during_native_fitting"]
        assert audit["source_and_native_preprocessing_fitting_only"] and audit["natural_missing_representations_preserved"]
        assert audit["native_hr_cache_identities_and_available_values_independently_checked"] == 666
        assert not audit["source_outcomes_pooled_or_converted_to_native"]
        assert audit["synthetic_rows"] == audit["artificial_history_views"] == audit["invented_source_times_or_rest_baselines"] == 0
        status.update(completed_studies=48,evaluated_configurations_including_controls=1776)
        status.pop("running_study",None)
        status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
        result = status["latest_complete_results"]
        result.update(furukawa_pre_report_hr_best_source_cv=audit["best_source_cv_accuracy"],
            furukawa_pre_report_hr_best_mlp_cv=audit["best_source_by_member"]["core"]["accuracy_mean"],
            furukawa_pre_report_hr_best_catboost_cv=audit["best_source_by_member"]["cat"]["accuracy_mean"],
            furukawa_pre_report_hr_measured_mlp_cv=audit["matched_measured_controls"]["core"]["accuracy_mean"],
            furukawa_pre_report_hr_measured_catboost_cv=audit["matched_measured_controls"]["cat"]["accuracy_mean"],
            furukawa_pre_report_hr_best_overall_cv=audit["best_cv_accuracy"])
        for field in ("furukawa_pre_report_hr_opportunity","next_furukawa_hr_proposal"):
            status[field]["model_study_completed"] = True
        test = audit["new_test_evaluation"]
        if test and test["correct"] > status["best_verified_test_correct"]:
            status.update(best_verified_test_correct=test["correct"],best_verified_test_accuracy=test["test_accuracy"],
                best_verified_test_artifact=str(study.DIRECTORY/"evaluation/model.joblib"))
        status["goal_achieved"] = status["best_verified_test_correct"] >= 144
        status["next_evidence_based_direction"] = (
            "Study48completed14recipes/50new native folds plus4independent source fits and30independent native refits observing actual source/native targets,person weights,fold-only preprocessing,frozen source functions and input-only reload. "
            "Original runner experiment2provided252state targets/168actual within-condition deltas with12fitting people;84responses/4otherpeople remain reserved. Original source point outcomes were not converted or pooled with native Borg0-10. "
            "Inspect the paired source-state/delta and measured-HR controls,then choose a bounded untested hyperparameter mechanism from fitting-person CVevidence instead of repeating this grid. "
            "Keep original487/179native cases,the predeclared.65CVtest gate,natural missing histories and original source clocks/sensors.80percent requires144of179from a frozen reloaded artifact;do not invent source rest,age,cross-experiment people,labels or training rows.")
        summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
            "input_verification_sha256":digest(study.INPUT_AUDIT),"configurations":14,"inherited_controls":4,"new_native_recipes":10,
            "new_native_person_fold_fits":50,"actual_source_state_fitting_targets":252,"actual_source_delta_fitting_targets":168,
            "source_fitting_people":12,"reserved_source_targets_not_fitted":84,"source_reserved_people":4,
            "independent_source_function_refits":4,"independent_native_refits":30,"winner_id":selection["winner_id"],
            "best_cv_accuracy":selection["best_cv_accuracy"],"best_source_by_member":audit["best_source_by_member"],
            "best_source_by_task_and_member":audit["best_source_by_task_and_member"],"matched_measured_controls":audit["matched_measured_controls"],
            "results":[{k:r[k] for k in ("candidate","accuracy_mean","fold_accuracy")} for r in selection["results"]],
            "original_training_cases":487,"original_test_cases":179,"test_used_for_selection":False,"new_test_evaluation":test,
            "retained_test_correct":status["best_verified_test_correct"],"retained_test_accuracy":status["best_verified_test_accuracy"],
            "public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],"target_accuracy":.8,"achieved":status["goal_achieved"]}
        (study.DOCS/"furukawa-pre-report-hr-transfer.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
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
