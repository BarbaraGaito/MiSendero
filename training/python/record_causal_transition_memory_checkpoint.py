"""Register independently verified study52; preserve the actual goal."""
import json
from pathlib import Path
import fatigue_causal_transition_memory as study
from public_sources import digest

status_path = study.DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed']) in (
    (51,1812,272),(52,1848,277))
inputs = study.load_inputs()
selection_path = study.DIRECTORY/'selection.json'
selected = json.loads(selection_path.read_text())
assert selected['status']=='complete' and len(selected['results'])==36 and selected['plan']==study.plan()
assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
audit_path = study.DOCS/'causal-transition-memory-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(selection_path)
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_causal_transition_memory.py'))
assert audit['all_36_oof_recipes_recomputed'] and audit['independent_preprocessor_refits']==170
assert audit['independent_fold_comparisons']==170 and audit['memory_free_population_artifact_reloads']==20
assert len(audit['fold_audits'])==10 and audit['new_native_base_fits']==audit['synthetic_rows']==0
assert audit['preprocessing_fit_people_only'] and audit['current_and_future_labels_excluded']
for name,expected in audit['native_base_cache_artifact_hashes'].items():
    assert digest(study.native.DIRECTORY/'bases'/name)==expected
tests_path = study.DOCS/'causal-transition-memory-tests.log'
tests = tests_path.read_text()
assert 'Ran 5 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
status.update(completed_studies=52,evaluated_configurations_including_controls=1848,python_tests_passed=277)
status.pop('running_study',None)
status['additional_scoped_verifications'][audit_path.name] = digest(audit_path)
status['causal_transition_memory_proposal'] = {'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
    'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'configurations':36,
    'new_native_base_fits':0,'native_full_base_classifiers_reused':10,'preprocessor_fits':170,
    'independent_preprocessor_refits':170,'personal_memory_stored_in_population_artifact':False,
    'past_real_self_reports_required_at_inference':True}
status['latest_complete_results'].update(causal_transition_memory_best_positive_cv=audit['best_positive_cv_accuracy'],
    causal_transition_memory_best_mlp_cv=audit['best_positive_by_member']['core']['accuracy_mean'],
    causal_transition_memory_best_catboost_cv=audit['best_positive_by_member']['cat']['accuracy_mean'],
    causal_transition_memory_zero_mlp_cv=audit['matched_zero_memory_controls']['core']['accuracy_mean'],
    causal_transition_memory_zero_catboost_cv=audit['matched_zero_memory_controls']['cat']['accuracy_mean'],
    causal_transition_memory_best_overall_cv=audit['best_cv_accuracy'])
test = audit['new_test_evaluation']
if test and test['test_correct']>status['best_verified_test_correct']:
    status.update(best_verified_test_correct=test['test_correct'],best_verified_test_accuracy=test['test_accuracy'],
        best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
status['goal_achieved'] = status['best_verified_test_correct']>=144
diagnostic_path = study.DOCS/'causal-transition-memory-error-diagnostic.json'
diagnostic = json.loads(diagnostic_path.read_text())
assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(selection_path)
assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_causal_transition_memory_errors.py'))
assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_preprocessor_fits']==0
assert diagnostic['new_test_predictions_computed']==0 and not diagnostic['test_labels_inspected']
status['causal_transition_memory_error_diagnostic'] = {'document':diagnostic_path.name,'sha256':digest(diagnostic_path),
    'fitting_only':True,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'best_catboost_correct_queries_displaced':diagnostic['best_recipe_comparisons']['cat']['correct_control_queries_displaced_by_memory'],
    'best_catboost_incorrect_queries_corrected':diagnostic['best_recipe_comparisons']['cat']['incorrect_control_queries_corrected_by_memory']}
review_path = study.DOCS/'native-change-factorization-review.json'
review = json.loads(review_path.read_text())
assert review['review']=='passed' and review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0
assert review['review_code_sha256']==digest(Path(__file__).with_name('review_native_change_factorization.py'))
assert (review['observed_unchanged_queries'],review['observed_nonzero_queries'],review['observed_negative_changes'])==(229,258,2)
assert all(digest(Path(__file__).with_name(name))==row['sha256'] for name,row in review['prior_code_review'].items())
status['native_change_factorization_review'] = {'document':review_path.name,'sha256':digest(review_path),
    'fitting_only':True,'new_predictive_estimator_fits':0,'next_comparison_predeclared':False}
status['next_evidence_based_direction'] = (
    'Study52completed all36predeclared causal kernel transition-memory recipes and170fitting-only preprocessors; '
    'independent170recipe-fold recomputations and20memory-free artifact reloads verified actual same-session/person '
    'support reports at least1minute earlier. The32positive memory recipes did not beat their population-only controls '
    'or qualify for a new native test. Do not repeat bandwidth/strength/scope grids without new evidence. '
    'The fitting-only error diagnostic found174of391task-supported queries had no matching earlier delta; '
    'prior task-support deltas exceeded current query deltas by1.277points on average. The best CatBoost memory '
    'displaced10correct population decisions and corrected2; a simple local transition histogram is not sufficient. '
    'Next investigate the observed change-vs-plateau structure:229of487native fitting transitions are exactly zero, '
    'while258are nonzero(including2negative). The native-change-factorization review verified that earlier '
    'continuous ordinal/delta regressors and residual-zero correction did not fit a separate observed-change '
    'gate with conditional nonzero magnitude. Next predeclare a distinct hierarchical '
    'binary-change/conditional-magnitude mechanism with matched flat-class controls, or identify a compatible '
    'public observation source. Do not use '
    'test errors, invent labels or enlarge a failed grid. WSD sensor onset remains unverified and BBEX workbook '
    'access remains unavailable. Retain original487/179cohort,.65CVtestgate and144/179exact accuracy target.')
summary = {'version':1,'status':'complete','selection_sha256':digest(selection_path),
    'verification_sha256':digest(audit_path),'configurations':36,'preprocessor_fits':170,
    'independent_preprocessor_refits':170,'memory_free_artifact_reloads':20,'new_native_base_fits':0,
    'best_positive_by_member':audit['best_positive_by_member'],
    'matched_zero_memory_controls':audit['matched_zero_memory_controls'],
    'winner_id':selected['winner_id'],'best_cv_accuracy':selected['best_cv_accuracy'],
    'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_causal_transition_memory.py')),
    'real_tests_log_sha256':digest(tests_path),'new_test_evaluation':test,
    'retained_test_correct':status['best_verified_test_correct'],'retained_test_accuracy':status['best_verified_test_accuracy'],
    'target_accuracy':.8,'achieved':status['goal_achieved'],
    'results':[{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for r in selected['results']]}
(study.DOCS/'causal-transition-memory.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(study.DOCS/name)==expected for name,expected in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'completed_studies':52,'completed_configurations':1848,'distinct_tests':277,
    'retained_test_correct':status['best_verified_test_correct'],'goal_achieved':status['goal_achieved']}),flush=True)
