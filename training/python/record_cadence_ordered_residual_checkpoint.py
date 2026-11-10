"""Record audited study60 and its fitting-only error evidence."""
import json
from pathlib import Path
import fatigue_cadence_ordered_residual as study
from public_sources import digest

status_path = study.DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed']) in (
    (59,1930,315),(60,1956,322))
inputs = study.load_inputs()
path = study.DIRECTORY/'selection.json'
selected = json.loads(path.read_text())
assert selected['status']=='complete' and len(selected['results'])==26 and selected['plan']==study.plan()
assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
audit_path = study.DOCS/'cadence-ordered-residual-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(path)
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_ordered_residual.py'))
assert audit['all_26_oof_recipes_recomputed'] and audit['all_40_fold_artifacts_recomputed']
assert audit['independent_joint_refits']==len(audit['native_joint_refits'])==40
assert audit['prior_inner_native_models_independently_verified']==30 and audit['synthetic_rows']==audit['new_native_base_fits']==0
for row in audit['native_joint_refits']:
    assert row['actual_native_target_steps']==row['actual_losses_independently_checked']==row['actual_total_backward_calls']==80
    assert row['actual_source_target_steps'] in (0,80) and row['initial_parameters_verified']
    assert row['native_delta_cross_entropy_gradient_verified'] and row['source_targets_from_original_pairs']
    assert row['actual_coefficient_chain_gradient_verified'] and row['fixed_ordered_basis_verified'] and row['shared_initialization_matched_full_residual']
    assert row['base_weights_frozen'] and not row['nonzero_delta_ratios_frozen'] and row['input_only_reload_verified']
for field,directory in [('fold_artifact_hashes',study.DIRECTORY/'folds'),('native_base_cache_artifact_hashes',study.native.DIRECTORY/'bases')]:
    assert all(digest(directory/name)==value for name,value in audit[field].items())
input_audit = json.loads(study.INPUT_AUDIT.read_text())
assert input_audit['verification']=='passed' and input_audit['native_cells_independently_rebuilt']==input_audit['native_clocks_verified']==666
assert input_audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_recent_gate_inputs.py'))
assert input_audit['preparation_code_sha256']==digest(Path(study.added.__file__))
tests_path = study.DOCS/'cadence-ordered-residual-tests.log'
tests = tests_path.read_text()
assert 'Ran 7 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
diagnostic_path = study.DOCS/'cadence-ordered-residual-diagnostic.json'
diagnostic = json.loads(diagnostic_path.read_text())
assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(path)
assert diagnostic['verification_sha256']==digest(audit_path)
assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_cadence_ordered_residual.py'))
assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_test_predictions_computed']==0 and not diagnostic['test_labels_inspected']
assert (len(inputs['train']),len(inputs['test']),len(inputs['gate_source']),len(inputs['reserved_gate_source']))==(487,179,851,206)
status.update(completed_studies=60,evaluated_configurations_including_controls=1956,python_tests_passed=322)
status.pop('running_study',None)
status['additional_scoped_verifications'][audit_path.name] = digest(audit_path)
status['additional_data_audits'][study.INPUT_AUDIT.name] = digest(study.INPUT_AUDIT)
status['cadence_ordered_residual_proposal'] = {'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
    'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'configurations':26,
    'new_joint_network_fits':40,'independent_joint_refits':40,'new_native_base_fits_for_cv':0,
    'source_fitting_actual_pairs':851,'source_reserved_pairs_not_fitted':206,'native_private_features':16,
    'shared_encoder_features':11,'source_current_hr_introduced':False,'source_private_context_fabricated':False}
status['latest_complete_results'].update(cadence_ordered_residual_best_source_cv=audit['best_positive_cv_accuracy'],
    cadence_ordered_residual_mlp_source_cv=audit['best_positive_by_member']['core']['accuracy_mean'],
    cadence_ordered_residual_catboost_source_cv=audit['best_positive_by_member']['cat']['accuracy_mean'],
    cadence_ordered_residual_zero_source_mlp_cv=audit['matched_zero_source_controls']['core']['accuracy_mean'],
    cadence_ordered_residual_zero_source_catboost_cv=audit['matched_zero_source_controls']['cat']['accuracy_mean'],
    cadence_ordered_residual_best_overall_cv=audit['best_cv_accuracy'])
test = audit['new_test_evaluation']
if test and test['test_correct']>status['best_verified_test_correct']:
    status.update(best_verified_test_correct=test['test_correct'],best_verified_test_accuracy=test['test_accuracy'],
        best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
status['goal_achieved'] = status['best_verified_test_correct']>=144
status['cadence_ordered_residual_diagnostic'] = {'document':diagnostic_path.name,'sha256':digest(diagnostic_path),
    'fitting_queries':487,'fitting_only':True,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}
review_path = study.DOCS/'cadence-ordered-residual-review.json'
review = json.loads(review_path.read_text())
assert review['review']=='passed' and review['selection_sha256']==digest(study.previous.DIRECTORY/'selection.json') and review['verification_sha256']==digest(study.PARENT_AUDIT)
assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_ordered_residual.py'))
assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0 and not review['model_comparison_predeclared']
status['cadence_ordered_residual_review'] = {'document':review_path.name,'sha256':digest(review_path),
    'fitting_only':True,'model_comparison_predeclared':True,'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'new_predictive_estimator_fits':0}
access_path = study.DOCS/'treadmill-cr10-access-refresh.json'
access = json.loads(access_path.read_text())
assert access['inspection']=='passed' and access['inspection_code_sha256']==digest(Path(__file__).with_name('record_treadmill_cr10_access_refresh.py'))
assert access['previous_access_conditions_unchanged'] and not access['training_merge_approved']
assert access['public_file_count']==0 and not access['source_data_downloaded']
status['additional_public_candidate_inspections'][access_path.name] = digest(access_path)
status['treadmill_cr10_access_refresh'] = {'document':access_path.name,'sha256':digest(access_path),
    'access':'embargoed','until':'2027-04-07','public_file_count':0,'training_merge_approved':False}

candidate_path = study.DOCS/'rpe-forecasting-candidate-inspection.json'
candidate = json.loads(candidate_path.read_text())
assert candidate['inspection']=='passed' and candidate['inspection_code_sha256']==digest(Path(__file__).with_name('review_rpe_forecasting_candidate.py'))
assert candidate['participant_split_frozen_before_original_target_review'] and candidate['case2_available_people']==24
assert len(candidate['case2_fitting_people'])==19 and len(candidate['case2_reserved_people'])==5
assert not candidate['case1_use_for_fitting_approved'] and not candidate['case2_training_merge_approved']
assert candidate['new_predictive_estimator_fits']==candidate['new_test_predictions_computed']==0
status['additional_public_candidate_inspections'][candidate_path.name] = digest(candidate_path)
status['rpe_forecasting_candidate'] = {'document':candidate_path.name,'sha256':digest(candidate_path),
    'revision':candidate['revision'],'fitting_people':19,'reserved_people':5,'case2_training_merge_approved':False}
status['next_evidence_based_direction'] = (
    'Study60 completed26recipes(18inherited controls/8new),40networks and40independent refits. '
    'Fixed3basis/27output parameters,shared initialization,actual coefficient-chain gradients and '
    '80native/source backward steps were verified. Best new core/source.610047CV;Cat/source.609810, '
    'below global.637972. Core/source corrected8/spoiled6vs matching free21and17/spoiled16vs global; '
    'Cat/source corrected7/spoiled9vs matching free21and7/spoiled21vs global. All8new residuals '
    'again reduced fitNLL but increased outer-person validationNLL. Smaller output geometry did '
    'not solve generalization. Pivot to raw evidence for the public RPE_ForecastingCase2candidate '
    'at pinned2e2233a6a755b05dc4dc0404d580d401ff7d520e. Its author context describes24participants '
    'with one RPE per squatting/walking trial. Freeze19fitting/5reserved people before raw target '
    'review(already recorded),retrieve only19fitting workbooks and verify Git blob identities, '
    'original report cells,scale and actual trial order. Do not count repeated strides as separate '
    'reports. Case1percentile-rescaled/median-filtered data stays excluded. Case2has no approved '
    'training merge or downloaded raw workbooks yet;do not invent clocks/HR/labels or equate scales. '
    'Original487/179,.65CVtestgate and144/179exact reloaded artifact matches remain required. '
    'No newtest qualified;retained108/179and goal active.')
summary = {'version':1,'status':'complete','selection_sha256':digest(path),'verification_sha256':digest(audit_path),
    'input_verification_sha256':digest(study.INPUT_AUDIT),'configurations':26,'new_joint_network_fits':40,
    'independent_joint_refits':40,'new_native_base_fits_for_cv':0,'source_fitting_actual_pairs':851,
    'source_reserved_pairs':206,'native_private_features':16,'best_positive_by_member':audit['best_positive_by_member'],
    'matched_zero_source_controls':audit['matched_zero_source_controls'],'winner_id':selected['winner_id'],
    'best_cv_accuracy':selected['best_cv_accuracy'],
    'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_cadence_ordered_residual.py')),
    'real_tests_log_sha256':digest(tests_path),'error_diagnostic_sha256':digest(diagnostic_path),
        'rpe_forecasting_candidate_sha256':digest(candidate_path),'ordered_residual_review_sha256':digest(review_path),'treadmill_access_refresh_sha256':digest(access_path),
    'paired_oof_comparisons':diagnostic['paired_oof_comparisons'],'new_test_evaluation':test,
    'retained_test_correct':status['best_verified_test_correct'],'retained_test_accuracy':status['best_verified_test_accuracy'],
    'target_accuracy':.8,'achieved':status['goal_achieved'],
    'results':[{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for r in selected['results']]}
(study.DOCS/'cadence-ordered-residual.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(study.DOCS/name)==value for name,value in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'completed_studies':60,'completed_configurations':1956,'distinct_tests':322,
    'retained_test_correct':status['best_verified_test_correct'],'goal_achieved':status['goal_achieved']}),flush=True)
