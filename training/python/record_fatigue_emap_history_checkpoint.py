"""Record the real public ordered-history comparison and its independent audit."""
import argparse
import json
from pathlib import Path

import fatigue_emap_history_transfer as study
from public_sources import digest


def read_common():
    folder = study.source.DOCS
    path = folder/"current-research-status.json"
    status = json.loads(path.read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((43,1698),(44,1714))
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["plan"] == study.plan() and all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    tests = (folder/"emap-history-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    audit = json.loads(study.INPUT_AUDIT.read_text())
    assert audit["verification"] == "passed" and audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_emap_history_inputs.py"))
    assert audit["source_provenance_sha256"] == digest(study.source.DIRECTORY/"provenance.json")
    status["additional_data_audits"][study.INPUT_AUDIT.name] = digest(study.INPUT_AUDIT)
    diagnostic_path = folder/"emap-ordered-history-context-diagnostic.json"
    diagnostic = json.loads(diagnostic_path.read_text())
    assert diagnostic["code_sha256"] == digest(Path(__file__).with_name("diagnose_emap_ordered_history_context.py"))
    assert diagnostic["source_provenance_sha256"] == digest(study.source.DIRECTORY/"provenance.json")
    assert not diagnostic["emap_reserved_targets_used"] and not diagnostic["native_test_targets_used"] and not diagnostic["source_model_fitting_started"]
    assert diagnostic["emap_fitting_all_slots"]["actual_pairs"] == 248 and diagnostic["native_fitting_changes"]["actual_pairs"] == 487
    status["additional_data_audits"][diagnostic_path.name] = digest(diagnostic_path)
    return folder,path,status,selection_path,selection,inputs


def save(path,status,folder):
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def start():
    folder,path,status,_,selection,inputs = read_common()
    assert status["completed_studies"] == 43 and status["python_tests_passed"] in (240,244)
    status["python_tests_passed"] = 244
    status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":16,
        "new_native_recipes":12,"predeclared_native_folds":60,"new_actual_emap_fitting_targets":248,
        "new_actual_emap_reserved_targets_not_fitted":57,"existing_worker_sts_fitting_targets":302,
        "source_outcomes_kept_separate":True,"invented_source_clocks_or_sensor_joins":0,
        "training_log":"emap-history-training.log","counted_as_complete":False,"phase":"training_selection",
        "training_selection_complete":selection["status"] == "complete"}
    status["emap_real_cr10_history_opportunity"].update(model_fitting_started=True,
        input_directory=study.source.DIRECTORY.name,input_verification=study.INPUT_AUDIT.name,
        combined_fitting_pairs_across_separate_outcomes=550,used_in_study=study.DIRECTORY.name)
    status["next_evidence_based_direction"] = (
        "Study44is running16fixed ordered-history recipes:4audited controls and12 new native recipes over3regressors,EMAPalone or separateEMAP/Worker/STS heads andMLP/CatBoost. "
        "Actual fitting targets are248newEMAP/83people plus253Worker/31people and49STS/45people,with57newEMAPtargets/19people reserved. "
        "The source adapter was independently rebuilt from original XML,407individual observed cells and305ordered pairs.4newactual-public tests passed;244distinct cumulative tests are not a rerun of all historical suites. "
        "Wait for this specific60fold selection,then independently reproduce source supervision and paired native winners. Preserve original487/179native exact labels, source-outcome separation, genuine prior values, missing cells and fixed.65CVgate. No generated data, invented ages/phases, mean/MICEtargets or new source sensor joins.")
    save(path,status,folder)
    print(json.dumps({"completed_studies":43,"completed_configurations":1698,"running_study":study.DIRECTORY.name,
        "planned_configurations":16,"new_native_folds":60,"cumulative_distinct_tests":244,"goal_achieved":False}),flush=True)


def pending():
    folder,path,status,_,selection,_ = read_common()
    assert status["completed_studies"] == 43 and status["python_tests_passed"] == 244
    assert selection["status"] == "complete" and len(selection["results"]) == 16 and selection["best_cv_accuracy"] < .65
    status["running_study"].update(phase="independent_source_and_native_verification",training_selection_complete=True,
        training_process_terminal=True,verification_log="emap-history-verification.log")
    status["next_evidence_based_direction"] = (
        "All16ordered-history recipes completed native5fold CV. No new recipe crossed the.65gate,so no original179test was opened. "
        "Independent verification is refitting9source functions and20paired native folds with actual-target observers and frozen source weights. "
        "Original407EMAPCR10cells/305adjacent pairs and550fitting targets across separate outcomes remain independently verified; no synthetic data or altered native targets. Wait on the specific audit before accepting this study.")
    save(path,status,folder)
    print(json.dumps({"selection":"complete","independent_verification":"running","best_overall_cv":selection["best_cv_accuracy"],"goal_achieved":False}),flush=True)


def complete():
    folder,path,status,selection_path,selection,_ = read_common()
    assert status["python_tests_passed"] == 244 and selection["status"] == "complete" and len(selection["results"]) == 16
    audit_path = folder/"emap-history-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_emap_history_transfer.py"))
    assert audit["selection_sha256"] == digest(selection_path) and audit["input_verification_sha256"] == digest(study.INPUT_AUDIT)
    assert audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["all_16_oof_recipes_recomputed"] and audit["original_native_rows_and_targets_preserved"]
    assert audit["source_verification_refits"] == len(audit["actual_source_functions_independently_refitted"]) == 9
    assert audit["actual_native_target_calls_observed"] == len(audit["actual_native_refits"]) == 20
    assert audit["original_source_delta_targets_observed_at_actual_fitter"] and audit["source_scaling_and_weights_fitting_people_only"]
    assert audit["native_delta_targets_observed_at_actual_fitter"] and audit["native_preprocessing_fitting_people_only"]
    assert audit["computed_history_changes_independently_verified"] and audit["source_weights_frozen_during_native_fitting"]
    assert audit["source_artifacts_unchanged_after_verification"] and not audit["source_target_pooling_performed"]
    assert audit["synthetic_rows"] == audit["invented_source_clocks_or_sensor_joins"] == 0
    assert not audit["new_test_gate_passed"] and not audit["achieved"] and audit["best_verified_test_correct"] == 108
    status.update(completed_studies=44,evaluated_configurations_including_controls=1714)
    status.pop("running_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["latest_complete_results"].update(emap_history_best_new_cv=audit["best_new_cv_accuracy"],
        emap_history_best_mlp_cv=audit["best_new_by_member"]["core"]["accuracy_mean"],
        emap_history_best_catboost_cv=audit["best_new_by_member"]["cat"]["accuracy_mean"],
        emap_history_matched_mlp_cv=audit["matched_single_or_combined_heads"]["core"]["accuracy_mean"],
        emap_history_matched_catboost_cv=audit["matched_single_or_combined_heads"]["cat"]["accuracy_mean"],
        emap_history_best_overall_cv=audit["best_cv_accuracy"])
    status["emap_real_cr10_history_opportunity"].update(model_study_completed=True)
    declaration_path = folder/"emap-ordered-functions-plan.json"
    declaration = json.loads(declaration_path.read_text())
    assert declaration["implementation_code_sha256"] == digest(Path(__file__).with_name("fatigue_emap_ordered_functions.py"))
    assert declaration["fitting_context_diagnostic_sha256"] == digest(folder/"emap-ordered-history-context-diagnostic.json")
    assert not declaration["source_or_native_fitting_started"] and declaration["planned_native_recipes"] == 6
    status["next_predeclared_study"] = {"directory":"emap-ordered-functions-80-v1",
        "plan":declaration_path.name,"plan_sha256":digest(declaration_path),
        "implementation":"training/python/fatigue_emap_ordered_functions.py",
        "implementation_code_sha256":declaration["implementation_code_sha256"],
        "planned_configurations_including_controls":10,"planned_new_native_folds":30,
        "model_fitting_started":False,"tests_executed":False,
        "prerequisite_completed_audit":"emap-history-verification.json"}
    status["next_evidence_based_direction"] = (
        "Study44completed16recipes; independent verification reproduced9actual source fits and20native paired-fold fits. "
        "Original407EMAPCR10responses,305ordered pairs,248new source-fitting targets and57reserved source targets are verified,with302previous Worker/STStargets kept as separate outcomes. "
        "No new nativeCVgate passed; retained original179test remains108correct. Fitting-only EMAPorder diagnostic found mean deltas+.9639/+.7470/-1.9634 forT2/T3/T4,versus+.8994 native and only2of487 decreasing native pairs. "
        "A bounded follow-up may preserve separate ordered-transition source functions rather than average opposing changes. T2has83actual fitting pairs with only one prior,T3has83with two priors,T4has82with two; never query an all-unobserved T2second-prior feature. Do not assume native phase equivalence or invent source clocks, ages or sensors. "
        "Any additional capacity/regularization trial must be predeclared and compared with matched real-data controls on unchanged participant CV. Public actual data only; no generated histories, labels or benchmark exclusions.80percent goal remains active.")
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "input_verification_sha256":digest(study.INPUT_AUDIT),"configurations":16,"inherited_controls":4,"new_native_recipes":12,
        "new_emap_fitting_targets":248,"new_emap_fitting_people":83,"new_emap_reserved_targets":57,"new_emap_reserved_people":19,
        "previous_worker_sts_fitting_targets":302,"source_fitting_targets_across_separate_outcomes":550,
        "source_verification_refits":9,"native_verification_refits":20,"source_targets_pooled":False,
        "public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],"winner_id":selection["winner_id"],
        "best_cv_accuracy":selection["best_cv_accuracy"],"best_new_id":audit["best_new_candidate_id"],"best_new_cv_accuracy":audit["best_new_cv_accuracy"],
        "best_new_by_member":audit["best_new_by_member"],"matched_single_or_combined_heads":audit["matched_single_or_combined_heads"],
        "convergence_warning_folds":audit["convergence_warning_folds_in_grid"],
        "results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"test_used_for_selection":False,"new_test_gate_passed":False,
        "retained_test_correct":108,"retained_test_accuracy":108/179,"target_accuracy":.8,"achieved":False,
        "scope":"Only original public individual CR10 observations and genuine measured earlier responses. Separate source functions, source-only fitting and genuine native prior queries. No inferred source ages/phase equivalence, new sensor joins, MICE/formula targets, synthetic examples, altered labels or changed native487/179cases."}
    (folder/"emap-history-transfer.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    save(path,status,folder)
    print(json.dumps({"completed_studies":44,"configurations":1714,"cumulative_distinct_tests":244,
        "best_new_cv":audit["best_new_cv_accuracy"],"best_overall_cv":audit["best_cv_accuracy"],"retained_test_accuracy":108/179,"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("start","pending","complete"),default="complete")
    args = parser.parse_args()
    {"start":start,"pending":pending,"complete":complete}[args.phase]()
