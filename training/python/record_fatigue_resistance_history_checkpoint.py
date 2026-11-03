"""Record only concrete selection/test/audit evidence for public resistance RPE."""
import argparse
import json
from pathlib import Path

import fatigue_resistance_history_joint as study
from public_sources import digest


def update(phase):
    path = study.DOCS/"current-research-status.json"
    status = json.loads(path.read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((46,1740),(47,1762))
    assert status["python_tests_passed"] in (252,256) and status["goal_status"] == "active"
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["plan"] == study.plan(inputs["previous_audit"]) and all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    tests = (study.DOCS/"resistance-history-joint-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    status["python_tests_passed"] = 256
    status["resistance_history_expansion_opportunity"].update(model_fitting_started=True,used_in_study=study.DIRECTORY.name)
    status["next_resistance_history_proposal"].update(implementation_started=True,model_fitting_started=True,used_in_study=study.DIRECTORY.name)
    if phase in ("start","pending"):
        assert status["completed_studies"] == 46
        status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":22,
            "new_native_recipes":18,"predeclared_native_joint_folds":90,"native_base_caches_reused":10,
            "cached_native_base_models_previously_verified":40,"new_native_base_fits":0,
            "actual_source_fitting_targets_available":1416,"additional_actual_resistance_targets":866,
            "actual_source_fitting_second_priors":1169,"source_reserved_targets_not_fitted":125,
            "resistance_loss_weights":[0,.1,1],"correction_penalties":[.1,1,10],"fixed_epochs":80,
            "training_log":"resistance-history-joint-training.log","counted_as_complete":False,
            "phase":"training_selection" if phase == "start" else "independent_real_loss_gradient_verification",
            "training_selection_complete":selection["status"] == "complete"}
        status["next_evidence_based_direction"] = (
            "Study47uses18new original-resistance joint networks plus4inherited controls,80epochs,correction penalties.1/1/10and new head weights0/.1/1. "
            "Actual manual-source fitting targets increased from550to1416while keeping125stored source targets reserved and outcomes separate. "
            "Ten frozen native-base caches/40previously verified models are reused without refitting. Normalization and old head initialization stay matched to46; zero-new-source/.1penalty controls exactly reproduce prior losses/predictions. "
            "Four new actual-public tests passed in6.654s,including actual866new targets,independent mixed losses and source-only gradients,zero-weight exclusion and runtime reload. Cumulative256distinct tests are not a joint rerun of historical suites. "
            "Complete selection and independent real-loss/gradient refits before counting47; keep original487/179native cases and the predeclared.65CVtest gate.80percent requires144of179from a frozen reloaded artifact. No synthetic rows,learned EMG labels,SMOTE/jitter,pooled source outcomes or guessed source clocks/sensors.")
        if phase == "pending":
            assert selection["status"] == "complete" and len(selection["results"]) == 22
            status["running_study"].update(training_process_terminal=True,verification_log="resistance-history-joint-verification.log")
    else:
        assert selection["status"] == "complete" and len(selection["results"]) == 22
        audit_path = study.DOCS/"resistance-history-joint-verification.json"
        audit = json.loads(audit_path.read_text())
        assert audit["verification"] == "passed" and audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_resistance_history_joint.py"))
        assert audit["selection_sha256"] == digest(selection_path) and audit["input_verification_sha256"] == digest(study.INPUT_AUDIT)
        assert audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT) and audit["all_22_oof_recipes_recomputed"]
        assert audit["actual_native_joint_refits"] == len(audit["joint_refits"]) == 5*len(audit["native_recipes_independently_refitted"])
        assert audit["actual_source_and_native_losses_and_weights_observed"] and audit["actual_resistance_to_encoder_gradients_verified"]
        assert audit["zero_new_weight_excludes_resistance_labels"] and audit["old_initial_parameters_and_matched_control_predictions_preserved"]
        assert audit["native_base_weights_frozen"] and audit["matched_preprocessing_fitting_rows_only"] and not audit["source_outcomes_pooled"]
        assert audit["synthetic_rows"] == audit["invented_source_times_or_sensor_joins"] == audit["new_native_base_fits"] == 0
        status.update(completed_studies=47,evaluated_configurations_including_controls=1762)
        status.pop("running_study",None)
        status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
        status["latest_complete_results"].update(resistance_history_joint_best_positive_cv=audit["best_positive_cv_accuracy"],
            resistance_history_joint_best_positive_mlp_cv=audit["best_positive_by_member"]["core"]["accuracy_mean"],
            resistance_history_joint_best_positive_catboost_cv=audit["best_positive_by_member"]["cat"]["accuracy_mean"],
            resistance_history_joint_matched_zero_mlp_cv=audit["matched_zero_new_source_controls"]["core"]["accuracy_mean"],
            resistance_history_joint_matched_zero_catboost_cv=audit["matched_zero_new_source_controls"]["cat"]["accuracy_mean"],
            resistance_history_joint_best_overall_cv=audit["best_cv_accuracy"])
        status["resistance_history_expansion_opportunity"].update(model_study_completed=True)
        status["next_resistance_history_proposal"].update(model_study_completed=True)
        test = audit["new_test_evaluation"]
        if test and test["correct"] > status["best_verified_test_correct"]:
            status.update(best_verified_test_correct=test["correct"],best_verified_test_accuracy=test["test_accuracy"],
                best_verified_test_artifact=str(study.DIRECTORY/"evaluation/model.joblib"))
        status["goal_achieved"] = status["best_verified_test_correct"] >= 144
        status["next_evidence_based_direction"] = (
            "Study47completed22recipes/90new joint-network folds plus selected independent refits observing actual native/source targets,person weights,mixed loss,backward and866manual-resistance targets. "
            "It preserved the10frozen base caches/40models,old550-source normalization,matched initial parameters and exact old predictions/losses for zero-new weight at penalty.1. "
            "Inspect paired positive-versus-zero source/penalty results before another mechanism; do not repeat the completed grid. "
            "Other inspected public sources include runners with HR/real chronological RPE,requiring cohort/scale/timing review before any adapter,and HIFT with instrument/protocol review pending. Motor-support workbook does not include released RPE. "
            "Retain original487/179cases,1416actual source fitting targets,125stored source reservation,natural missing histories and separate original outcomes. Original test remains retained unless a frozen reloaded artifact independently improves it;80percent needs144of179. No synthetic examples/weights,source label pooling or invented times/sensors.")
        summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
            "input_verification_sha256":digest(study.INPUT_AUDIT),"configurations":22,"inherited_controls":4,"new_native_recipes":18,
            "source_fitting_targets_available":1416,"additional_actual_resistance_fitting_targets":866,
            "source_fitting_actual_second_priors":1169,"reserved_source_targets_not_fitted":125,
            "native_base_caches_reused":10,"cached_native_base_models_previously_verified":40,"new_native_base_fits":0,
            "independent_native_joint_refits":audit["actual_native_joint_refits"],"winner_id":selection["winner_id"],
            "best_cv_accuracy":selection["best_cv_accuracy"],"best_positive_by_member":audit["best_positive_by_member"],
            "matched_zero_new_source_controls":audit["matched_zero_new_source_controls"],
            "results":[{k:r[k] for k in ("candidate","accuracy_mean","fold_accuracy")} for r in selection["results"]],
            "original_training_cases":487,"original_test_cases":179,"test_used_for_selection":False,"new_test_evaluation":test,
            "retained_test_correct":status["best_verified_test_correct"],"retained_test_accuracy":status["best_verified_test_accuracy"],
            "public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],"target_accuracy":.8,"achieved":status["goal_achieved"]}
        (study.DOCS/"resistance-history-joint-transfer.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
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
