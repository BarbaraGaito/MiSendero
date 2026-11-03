"""Record audited study57 and its fitting-only error evidence."""
import json
from pathlib import Path
import fatigue_cadence_recent_gate as study
from public_sources import digest

status_path = study.DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed']) in (
    (56,1892,297),(57,1902,303))
inputs = study.load_inputs()
path = study.DIRECTORY/'selection.json'
selected = json.loads(path.read_text())
assert selected['status']=='complete' and len(selected['results'])==10 and selected['plan']==study.plan()
assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
audit_path = study.DOCS/'cadence-recent-gate-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(path)
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_recent_gate.py'))
assert audit['all_10_oof_recipes_recomputed'] and audit['all_20_fold_artifacts_recomputed']
assert audit['independent_joint_refits']==len(audit['native_joint_refits'])==20
assert audit['prior_inner_native_models_independently_verified']==30 and audit['synthetic_rows']==audit['new_native_base_fits']==0
for row in audit['native_joint_refits']:
    assert row['actual_native_target_steps']==row['actual_losses_independently_checked']==row['actual_total_backward_calls']==80
    assert row['actual_source_target_steps'] in (0,80) and row['initial_parameters_verified']
    assert row['native_joint_nll_gradient_equivalence_verified'] and row['source_targets_from_original_pairs']
    assert row['base_weights_frozen'] and row['nonzero_delta_ratios_frozen'] and row['input_only_reload_verified']
for field,directory in [('fold_artifact_hashes',study.DIRECTORY/'folds'),('native_base_cache_artifact_hashes',study.native.DIRECTORY/'bases')]:
    assert all(digest(directory/name)==value for name,value in audit[field].items())
input_audit = json.loads(study.INPUT_AUDIT.read_text())
assert input_audit['verification']=='passed' and input_audit['native_cells_independently_rebuilt']==input_audit['native_clocks_verified']==666
assert input_audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_recent_gate_inputs.py'))
assert input_audit['preparation_code_sha256']==digest(Path(study.added.__file__))
tests_path = study.DOCS/'cadence-recent-gate-tests.log'
tests = tests_path.read_text()
assert 'Ran 6 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
diagnostic_path = study.DOCS/'cadence-recent-gate-error-diagnostic.json'
diagnostic = json.loads(diagnostic_path.read_text())
assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(path)
assert diagnostic['verification_sha256']==digest(audit_path)
assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_cadence_recent_gate_errors.py'))
assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_test_predictions_computed']==0 and not diagnostic['test_labels_inspected']
review_path = study.DOCS/'cadence-full-delta-residual-review.json'
review = json.loads(review_path.read_text())
assert review['review']=='passed' and review['selection_sha256']==digest(path) and review['verification_sha256']==digest(audit_path)
assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_full_delta_residual.py'))
assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0 and not review['model_comparison_predeclared']
assert (len(inputs['train']),len(inputs['test']),len(inputs['gate_source']),len(inputs['reserved_gate_source']))==(487,179,851,206)
status.update(completed_studies=57,evaluated_configurations_including_controls=1902,python_tests_passed=303)
status.pop('running_study',None)
status['additional_scoped_verifications'][audit_path.name] = digest(audit_path)
status['additional_data_audits'][study.INPUT_AUDIT.name] = digest(study.INPUT_AUDIT)
status['cadence_gate_recent_native_state_review'].update(model_comparison_predeclared=True,
    model_study_completed=True,used_in_study=study.DIRECTORY.name)
status['cadence_recent_native_gate_proposal'] = {'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
    'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'configurations':10,
    'new_joint_network_fits':20,'independent_joint_refits':20,'new_native_base_fits_for_cv':0,
    'source_fitting_actual_pairs':851,'source_reserved_pairs_not_fitted':206,'native_private_features':16,
    'shared_encoder_features':11,'source_current_hr_introduced':False,'source_private_context_fabricated':False}
status['latest_complete_results'].update(cadence_recent_gate_best_source_cv=audit['best_positive_cv_accuracy'],
    cadence_recent_gate_mlp_source_cv=audit['best_positive_by_member']['core']['accuracy_mean'],
    cadence_recent_gate_catboost_source_cv=audit['best_positive_by_member']['cat']['accuracy_mean'],
    cadence_recent_gate_zero_source_mlp_cv=audit['matched_zero_source_controls']['core']['accuracy_mean'],
    cadence_recent_gate_zero_source_catboost_cv=audit['matched_zero_source_controls']['cat']['accuracy_mean'],
    cadence_recent_gate_best_overall_cv=audit['best_cv_accuracy'])
test = audit['new_test_evaluation']
if test and test['test_correct']>status['best_verified_test_correct']:
    status.update(best_verified_test_correct=test['test_correct'],best_verified_test_accuracy=test['test_accuracy'],
        best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
status['goal_achieved'] = status['best_verified_test_correct']>=144
status['cadence_recent_gate_diagnostic'] = {'document':diagnostic_path.name,'sha256':digest(diagnostic_path),
    'fitting_queries':487,'fitting_only':True,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}
status['cadence_full_delta_residual_review'] = {'document':review_path.name,'sha256':digest(review_path),
    'fitting_only':True,'new_predictive_estimator_fits':0,'model_comparison_predeclared':False}
status['next_evidence_based_direction'] = (
    'Study57completed10recipes/20networks and20independent refits,all666recent-native cells/clocks verified. '
    'Adding3measured recent private HRinputs to13history inputs did not beat global.637972CV;best new '
    'native-only Cat.632090,source Cat.631877. Source Cat corrected1/spoiled1vs matched zero and '
    'corrected0/spoiled3vs global. Its validation gate BCE.521586improved slightly over original.522336, '
    'while exact Borg accuracy fell. A binary-only gate cannot change relative nonzero delta predictions. '
    'The fitting-only review distinguishes earlier full-delta residuals with2history inputs/13native context '
    'and continuous source heads from a proposed residual with11measured shared inputs/16native context '
    'and a separate CADENCE851binary head. Next predeclare a matched full-native-delta residual comparison '
    'with zero-source controls and penalties before fitting. Do not repeat a known family or call '
    'component loss improvement a global gain. Keep existing bases immutable and preserve actual851source '
    'pairs,source original6-20scale/no fabricated current context. Original487/179,.65CVtestgate and '
    '144/179exact frozen artifact matches remain required. Only real public observations,no synthetic '
    'histories or labels. No newtest qualified;retained108/179and80percent goal remains active.')
summary = {'version':1,'status':'complete','selection_sha256':digest(path),'verification_sha256':digest(audit_path),
    'input_verification_sha256':digest(study.INPUT_AUDIT),'configurations':10,'new_joint_network_fits':20,
    'independent_joint_refits':20,'new_native_base_fits_for_cv':0,'source_fitting_actual_pairs':851,
    'source_reserved_pairs':206,'native_private_features':16,'best_positive_by_member':audit['best_positive_by_member'],
    'matched_zero_source_controls':audit['matched_zero_source_controls'],'winner_id':selected['winner_id'],
    'best_cv_accuracy':selected['best_cv_accuracy'],
    'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_cadence_recent_gate.py')),
    'real_tests_log_sha256':digest(tests_path),'error_diagnostic_sha256':digest(diagnostic_path),
    'full_delta_residual_review_sha256':digest(review_path),
    'paired_oof_comparisons':diagnostic['paired_oof_comparisons'],'new_test_evaluation':test,
    'retained_test_correct':status['best_verified_test_correct'],'retained_test_accuracy':status['best_verified_test_accuracy'],
    'target_accuracy':.8,'achieved':status['goal_achieved'],
    'results':[{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for r in selected['results']]}
(study.DOCS/'cadence-recent-native-gate.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(study.DOCS/name)==value for name,value in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'completed_studies':57,'completed_configurations':1902,'distinct_tests':303,
    'retained_test_correct':status['best_verified_test_correct'],'goal_achieved':status['goal_achieved']}),flush=True)
