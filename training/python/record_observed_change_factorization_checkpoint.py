"""Register study53 from independent artifact and original-target evidence."""
import json
from pathlib import Path
import fatigue_observed_change_factorization as study
from public_sources import digest

status_path = study.DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed']) in (
    (52,1848,277),(53,1858,282))
inputs = study.load_inputs()
selected_path = study.DIRECTORY/'selection.json'
selected = json.loads(selected_path.read_text())
assert selected['status']=='complete' and len(selected['results'])==10 and selected['plan']==study.plan()
assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
audit_path = study.DOCS/'observed-change-factorization-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(selected_path)
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_observed_change_factorization.py'))
assert audit['all_10_oof_recipes_recomputed'] and audit['all_40_fold_artifacts_recomputed']
assert audit['actual_original_targets_and_subset_preprocessing_verified'] and audit['original_negative_changes_preserved']
assert audit['current_and_future_labels_excluded'] and audit['original_native_cases_preserved'] and audit['synthetic_rows']==0
assert audit['independent_candidate_fold_refits'] in (20,25)
assert audit['input_only_artifact_reloads']==len(audit['actual_refit_calls'])==audit['independent_candidate_fold_refits']
assert audit['independent_stage_estimator_refits']==sum(len(r['actual_stage_target_calls']) for r in audit['actual_refit_calls'])
for name,expected in audit['fold_artifact_hashes'].items():
    assert digest(study.DIRECTORY/'folds'/name)==expected
tests_path = study.DOCS/'observed-change-factorization-tests.log'
tests = tests_path.read_text()
assert 'Ran 5 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
status.update(completed_studies=53,evaluated_configurations_including_controls=1858,python_tests_passed=282)
status.pop('running_study',None)
status['additional_scoped_verifications'][audit_path.name] = digest(audit_path)
status['observed_change_factorization_proposal'] = {'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
    'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'configurations':10,
    'candidate_fold_fits':40,'stage_estimator_fits':60,'original_negative_changes_preserved':True,
    'independent_candidate_fold_refits':audit['independent_candidate_fold_refits'],
    'independent_stage_estimator_refits':audit['independent_stage_estimator_refits'],
    'native_target_coarsening':False}
status['native_change_factorization_review'].update(next_comparison_predeclared=True,
    used_in_study=study.DIRECTORY.name,model_comparison_completed=True)
status['latest_complete_results'].update(observed_change_factorization_best_cv=audit['best_factorized_cv_accuracy'],
    observed_change_factorization_best_mlp_cv=audit['best_factorized_by_member']['core']['accuracy_mean'],
    observed_change_factorization_best_catboost_cv=audit['best_factorized_by_member']['cat']['accuracy_mean'],
    observed_change_factorization_matched_flat_mlp_cv=audit['matched_flat_controls']['core']['accuracy_mean'],
    observed_change_factorization_matched_flat_catboost_cv=audit['matched_flat_controls']['cat']['accuracy_mean'],
    observed_change_factorization_best_overall_cv=audit['best_cv_accuracy'])
test = audit['new_test_evaluation']
if test and test['test_correct']>status['best_verified_test_correct']:
    status.update(best_verified_test_correct=test['test_correct'],best_verified_test_accuracy=test['test_accuracy'],
        best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
status['goal_achieved'] = status['best_verified_test_correct']>=144
diagnostic_path = study.DOCS/'observed-change-stage-diagnostic.json'
diagnostic = json.loads(diagnostic_path.read_text())
assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(selected_path)
assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_observed_change_stages.py'))
assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_preprocessor_fits']==diagnostic['new_test_predictions_computed']==0
assert len(diagnostic['results'])==4 and not diagnostic['test_labels_inspected']
status['observed_change_stage_diagnostic'] = {'document':diagnostic_path.name,'sha256':digest(diagnostic_path),
    'fitting_only':True,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'component_metrics_do_not_replace_native_target':True}
source_review_path = study.DOCS/'public-observed-change-support-review.json'
source_review = json.loads(source_review_path.read_text())
assert source_review['review']=='passed' and source_review['native_stage_diagnostic_sha256']==digest(diagnostic_path)
assert source_review['review_code_sha256']==digest(Path(__file__).with_name('review_public_observed_change_support.py'))
assert source_review['new_predictive_estimator_fits']==source_review['new_test_predictions_computed']==0
assert source_review['actual_source_fitting_pairs']==2336 and source_review['actual_source_reserved_pairs_not_used']==312
eligible = {name:row for name,row in source_review['source_domains'].items() if row['both_classes_available_for_binary_discrimination']}
assert set(eligible)=={'emap','resistance','shoulder','worker'} and sum(row['original_fitting_rows'] for row in eligible.values())==2287
assert source_review['source_domains']['sts']['observed_change_classes']==[1]
status['public_observed_change_support_review'] = {'document':source_review_path.name,'sha256':digest(source_review_path),
    'fitting_only':True,'new_predictive_estimator_fits':0,'source_fitting_pairs_profiled':2336,
    'pairs_in_four_domains_with_both_classes':2287,'single_class_sts_pairs':49,
    'next_model_comparison_predeclared':False}
status['next_evidence_based_direction'] = (
    'Study53completed the fixed10recipe observed-change distribution comparison,40candidate-fold/60stage fits. '
    'Actual binary labels describe observed zero-vs-nonzero changes; conditional magnitude retains every observed '
    'nonzero class including negative changes. Original487/179cohort and exact native Borg scoring preserved. '
    'Best factorized MLP CV.611582 trails its flat feature-matched.619092control; best factorized CatBoost '
    '.585137 trails its flat.637972control. No new test qualified. Fitting-only stage diagnostics found the '
    'best MLP binary gate CV.719480 versus conditional nonzero-delta CV.787005; component scores cannot '
    'satisfy the complete native Borg objective. CatBoost binary-gate training/CV gaps show overfitting, '
    'so do not repeat tree/feature/structure grids. The real-public source change profile found2287pairs '
    'in4domains with actual equal/unequal report examples;49STS pairs contain only changes. Initial '
    'unfitted two-class assumption was corrected and preserved; no opposite-class observations invented. '
    'Next assess a distinct,predeclared source-binary auxiliary representation for the native change '
    'gate,with separate source heads,real priors and matched zero-source controls. Earlier auxiliary '
    'heads learned continuous deltas; do not pool source labels/scales or assume clocks/native phases. '
    'No such binary-source model has yet been predeclared or fitted. '
    'Keep only real public observations,no synthetic training data,.65CVgate for new test and144/179exact '
    'matches from a frozen reloaded artifact for80percent. WSD sensor clock origin is still unverified and '
    'BBEX original workbooks still inaccessible; neither permits invented sensor joins or supervision.')
summary = {'version':1,'status':'complete','selection_sha256':digest(selected_path),
    'verification_sha256':digest(audit_path),'configurations':10,'candidate_fold_fits':40,'stage_estimator_fits':60,
    'independent_candidate_fold_refits':audit['independent_candidate_fold_refits'],
    'independent_stage_estimator_refits':audit['independent_stage_estimator_refits'],
    'best_factorized_by_member':audit['best_factorized_by_member'],'matched_flat_controls':audit['matched_flat_controls'],
    'winner_id':selected['winner_id'],'best_cv_accuracy':selected['best_cv_accuracy'],
    'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_observed_change_factorization.py')),
    'real_tests_log_sha256':digest(tests_path),'new_test_evaluation':test,
    'stage_diagnostic_sha256':digest(diagnostic_path),
    'source_change_support_review_sha256':digest(source_review_path),
    'retained_test_correct':status['best_verified_test_correct'],'retained_test_accuracy':status['best_verified_test_accuracy'],
    'target_accuracy':.8,'achieved':status['goal_achieved'],
    'results':[{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for r in selected['results']]}
(study.DOCS/'observed-change-factorization.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(study.DOCS/name)==expected for name,expected in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'completed_studies':53,'completed_configurations':1858,'distinct_tests':282,
    'retained_test_correct':status['best_verified_test_correct'],'goal_achieved':status['goal_achieved']}),flush=True)
