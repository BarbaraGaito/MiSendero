"""Record audited compact-source results and real temporal-input evidence."""
import json
from pathlib import Path

import fatigue_cadence_compact as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    audit_path = folder/"cadence-compact-verification.json"
    audit = json.loads(audit_path.read_text())
    assert selection["status"] == "complete" and len(selection["plan"]) == len(selection["results"]) == 32
    assert selection["code_sha256"] == digest(Path(study.__file__)) and audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_compact.py"))
    assert audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["native_delta_targets_verified_at_actual_estimator"] and audit["all_original_native_rows_and_labels_preserved"]
    assert audit["compact_native_features_exclude_redundant_raw_fields"] and not audit["fresh_source_fitting_performed"]
    assert not audit["achieved"] and not audit["new_test_gate_passed"] and audit["best_verified_test_correct"] == 108
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((40,1602),(41,1634))
    tests = (folder/"cadence-compact-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    assert status["python_tests_passed"] == 232
    status.update(completed_studies=41,evaluated_configurations_including_controls=1634)
    status.pop("running_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["latest_complete_results"].update({"cadence_compact_best_source_cv":audit["best_source_cv_accuracy"],
        "cadence_compact_best_mlp_cv":audit["best_source_by_member"]["core"]["accuracy_mean"],
        "cadence_compact_best_catboost_cv":audit["best_source_by_member"]["cat"]["accuracy_mean"],
        "cadence_compact_measured_relative_mlp_cv":audit["measured_relative_controls"]["core"]["accuracy_mean"],
        "cadence_compact_measured_relative_catboost_cv":audit["measured_relative_controls"]["cat"]["accuracy_mean"],
        "cadence_compact_best_overall_cv":audit["best_cv_accuracy"]})
    temporal_path = folder/"cadence-temporal-eligibility.json"
    temporal = json.loads(temporal_path.read_text())
    assert temporal["code_sha256"] == digest(Path(__file__).with_name("diagnose_cadence_temporal_eligibility.py"))
    assert temporal["status"] == "eligibility_screen_completed" and temporal["source_actual_three_stage_targets"] == 901
    assert temporal["source_partitions"] == {"fitting":727,"reserved":174} and not temporal["model_fitting_started"]
    assert temporal["independent_input_audit_still_required_before_model_fitting"]
    assert temporal["native_actual_input_availability"]["all"]["original_cases"] == 666
    assert temporal["native_actual_input_availability"]["all"]["both_past_hr_measured"] == 618
    assert temporal["source_provenance_sha256"] == digest(study.parent.source.DIRECTORY/"provenance.json")
    assert temporal["native_physiology_provenance_sha256"] == digest(study.parent.physiology.DIRECTORY/"provenance.json")
    status["additional_data_audits"][temporal_path.name] = digest(temporal_path)
    status["cadence_temporal_input_opportunity"] = {"verification":temporal_path.name,"actual_source_three_stage_targets":901,
        "source_fitting_targets":727,"source_reserved_targets":174,"source_fitting_people":123,"source_reserved_people":32,
        "native_original_cases":666,"native_actual_second_prior_responses":623,"native_both_past_hr_measured":618,
        "native_both_past_hr_and_baseline_measured":612,"original_cases_dropped":0,"model_fitting_started":False,
        "independent_input_cache_audit_required":True,"source6to20_conversion_approved":False,"exact_source_report_clocks_known":False}
    association_path = folder/"cadence-association-task-review.json"
    association = json.loads(association_path.read_text())
    assert association["review_code_sha256"] == digest(Path(__file__).with_name("review_cadence_association_task.py"))
    assert association["source_original_table_sha256"] == digest(study.parent.source.DATA)
    assert association["source_fitting_targets"] == 976 and association["source_reserved_targets"] == 238
    assert association["auxiliary_association_review_eligible"] and association["all_native_used_minutes_completed_by_query"]
    assert not association["source_current_bout_hr_strictly_before_rpe_claim_approved"] and not association["model_fitting_started"]
    assert not association["frozen_original_native_features_modified"] and association["versioned_adapter_and_independent_raw_input_audit_required"]
    assert association["native_newer_current_minutes_recovered"] == association["native_current_hr_values_changed_from_newer_observed_minutes"] == 2
    status["additional_data_audits"][association_path.name] = digest(association_path)
    status["cadence_retrospective_association_opportunity"] = {"verification":association_path.name,
        "task":"Retrospective source physiology/RPE association; source real-time forecasting claim remains prohibited",
        "source_actual_targets":1214,"source_fitting_targets":976,"source_reserved_targets":238,
        "source_fitting_people":124,"source_reserved_people":32,"source_original_instrument":"6-20",
        "native_current_hr_measured_before_query":666,"native_current_hr_and_baseline_available":658,
        "native_current_prior_hr_and_baseline_available":655,"newer_real_current_hr_minutes_recovered":2,
        "native_original_cases_dropped":0,"synthetic_data":0,"native_target_conversion":False,
        "independent_adapter_audit_required":True,"model_fitting_started":False}
    receipt_path = ROOT/"training/data/raw/fatigue-research/light-exercise-article-v1/receipt.json"
    article = json.loads(receipt_path.read_text())
    assert article["code_sha256"] == digest(Path(__file__).with_name("fetch_light_exercise_article.py"))
    assert article["status"] == "not_retrieved" and not article["dataset_to_article_link_confirmed"] and not article["training_approved"]
    followup = {"version":1,"retrieval_receipt_sha256":digest(receipt_path),"retrieval_code_sha256":article["code_sha256"],
        "candidate_article_doi":article["candidate_article_doi"],"dataset_doi":article["dataset_doi"],"url_attempted":article["url"],
        "status":"Article candidate could not be obtained as a public bounded PDF; no challenge page was treated as documentation.",
        "dataset_to_article_link_confirmed":False,"scale_and_column_codebook_resolved":False,"new_training_rows":0,
        "used_for_training":False,"existing_eligibility_sha256":digest(folder/"light-exercise-eligibility.json"),
        "decision":"The suspected author/protocol connection is insufficient to map the workbook. Keep this source excluded; no invented scale, pulse units or response clocks."}
    followup_path = folder/"light-exercise-documentation-followup.json"
    followup_path.write_text(json.dumps(followup,indent=2)+"\n",encoding="utf-8")
    status["additional_data_audits"][followup_path.name] = digest(followup_path)
    status["next_evidence_based_direction"] = (
        "Compact CADENCE representation/regularization completed32 configurations and scoped actual-fitter refits, without a new native test qualification. "
        "Prioritize a distinct retrospective source physiology/RPE association task before another lagged-static-proxy grid. Current source boutHR cannot be claimed strictly pre-RPE, but an explicitly retrospective auxiliary function may learn a concurrent association from1214 actual source6-20 targets(976 fitting/124 people,238 reserved/32 people) without converting labels. "
        "Native queries must still use only actual sensor minutes completed before prediction. The review reconstructed all666 currentHR cases and found2 newer actual cross-midnight minutes; freeze a separate source/native input adapter and independently verify raw cells/windows before any model fitting. "
        "A second candidate is genuine past physiological change: eligibility screening found901 source targets with two actual completed antecedent bouts,727 fitting/174 reserved on the same123/32 source people. "
        "Native original666 cases retain623 genuine second-prior reports and618 measured HR pairs(612 also have baseline). Prepare a versioned input cache and independently reconstruct raw source cells and native completed-minute windows before fitting. "
        "Use raw HR changes without invented source clocks; source6-20 RPE levels/differences remain a separate auxiliary task and never native0-10 labels. Preserve naturally unavailable inputs and every original487/179 case. "
        "The light-exercise workbook remains excluded: its suspected article could not be obtained as a verified public PDF and no instrument/column mapping was established. Public real observations only; no synthetic data or test tuning. Goal80percent remains active.")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "configurations":32,"new_mlp_source_proxy_configurations":18,"new_catboost_proxy_configurations":6,
        "new_measured_relative_controls":2,"inherited_controls":6,"source_functions_refitted":False,
        "source_fitting_targets":851,"source_reserved_targets":206,"source_original_scale":"6-20","native_original_scale":"0-10",
        "natural_missing_representation_pairs":11,"public_real_data_policy_sha256":audit["public_real_data_policy_sha256"],
        "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],"best_source_id":audit["best_source_candidate_id"],
        "best_source_cv_accuracy":audit["best_source_cv_accuracy"],"best_source_by_member":audit["best_source_by_member"],
        "measured_relative_controls":audit["measured_relative_controls"],"best_core_matching_16_8_alpha10_id":audit["best_core_matching_16_8_alpha10_id"],
        "best_core_matching_16_8_alpha10_cv":audit["best_core_matching_16_8_alpha10_cv"],"convergence_warning_folds":audit["convergence_warning_folds_in_grid"],
        "results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"new_test_gate_passed":False,"test_used_for_selection":False,
        "retained_test_correct":108,"retained_test_accuracy":audit["best_verified_test_accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Only real public measured cases. Compact source-only representations and a fixed capacity/L2 grid evaluated by original participant CV; natural missing data retained. No synthetic examples, source refits, target conversion, changed denominator or native test tuning."}
    (folder/"cadence-compact-representation.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"studies":41,"configurations":1634,"best_source_cv":audit["best_source_cv_accuracy"],
        "best_proxy_mlp_cv":audit["best_source_by_member"]["core"]["accuracy_mean"],"best_proxy_cat_cv":audit["best_source_by_member"]["cat"]["accuracy_mean"],
        "best_overall_cv":audit["best_cv_accuracy"],"retained_test":audit["best_verified_test_accuracy"],"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
