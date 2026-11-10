"""Register audited study56 and its real physiology inputs."""
import json
from pathlib import Path
import fatigue_cadence_binary_gate as study
from public_sources import digest

status_path = study.DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed']) in (
    (55,1886,292),(56,1892,297))
inputs = study.load_inputs()
path = study.DIRECTORY/'selection.json'
selected = json.loads(path.read_text())
assert selected['status']=='complete' and len(selected['results'])==6 and selected['plan']==study.plan()
assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
audit_path = study.DOCS/'cadence-binary-gate-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(path)
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_binary_gate.py'))
assert audit['all_6_oof_recipes_recomputed'] and audit['all_20_fold_artifacts_recomputed']
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
assert input_audit['verification']=='passed' and input_audit['actual_source_pairs_independently_rebuilt']==1057
assert input_audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_binary_gate_inputs.py'))
assert input_audit['preparation_code_sha256']==digest(Path(study.prepared.__file__))
tests_path = study.DOCS/'cadence-binary-gate-tests.log'
tests = tests_path.read_text()
assert 'Ran 5 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
review_path = study.DOCS/'cadence-gate-recent-native-state-review.json'
review = json.loads(review_path.read_text())
assert review['review']=='passed' and review['selection_sha256']==digest(path) and review['verification_sha256']==digest(audit_path)
assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_gate_recent_state.py'))
assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0
assert review['current_hr_completed_before_query'] and review['prior_hr_completed_before_genuine_prior_report']
status.update(completed_studies=56,evaluated_configurations_including_controls=1892,python_tests_passed=297)
status.pop('running_study',None)
status['additional_scoped_verifications'][audit_path.name] = digest(audit_path)
status['additional_data_audits'][study.INPUT_AUDIT.name] = digest(study.INPUT_AUDIT)
status['cadence_binary_physiology_review'].update(model_comparison_predeclared=True,model_study_completed=True,used_in_study=study.DIRECTORY.name)
status['cadence_binary_gate_proposal'] = {'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
    'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'configurations':6,'new_joint_network_fits':20,
    'independent_joint_refits':20,'new_native_base_fits_for_cv':0,'source_fitting_actual_pairs':851,
    'source_reserved_pairs_not_fitted':206,'source_actual_second_priors':727,'numeric_state_inputs':6,
    'actual_missing_value_indicators':5,'source_labels_pooled_as_native_borg':False}
status['latest_complete_results'].update(cadence_binary_gate_best_source_cv=audit['best_positive_cv_accuracy'],
    cadence_binary_gate_mlp_source_cv=audit['best_positive_by_member']['core']['accuracy_mean'],
    cadence_binary_gate_catboost_source_cv=audit['best_positive_by_member']['cat']['accuracy_mean'],
    cadence_binary_gate_zero_source_mlp_cv=audit['matched_zero_source_controls']['core']['accuracy_mean'],
    cadence_binary_gate_zero_source_catboost_cv=audit['matched_zero_source_controls']['cat']['accuracy_mean'],
    cadence_binary_gate_best_overall_cv=audit['best_cv_accuracy'])
test = audit['new_test_evaluation']
if test and test['test_correct']>status['best_verified_test_correct']:
    status.update(best_verified_test_correct=test['test_correct'],best_verified_test_accuracy=test['test_accuracy'],
        best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
status['goal_achieved'] = status['best_verified_test_correct']>=144
status['cadence_gate_recent_native_state_review'] = {'document':review_path.name,'sha256':digest(review_path),
    'fitting_only':True,'native_queries':487,'current_hr_missing':0,'current_vs_prior_hr_features_missing':2,
    'new_predictive_estimator_fits':0,'model_comparison_predeclared':False}
status['next_evidence_based_direction'] = (
    'Study56completed6recipes/20joint networks and20independent refits. Original1057source pairs were '
    'independently rebuilt(851fit/206reserved,727fitsecond priors,299equal/552unequal,4decreases);all666native '
    'cases/clocks preserved. Six numeric history/prior-HR inputs and5real availability flags were checked '
    'against fitting-only source/native stats;source BCE/loss/backward/gradients verified. CatBoost source '
    '.634051CV beat its measured zero-source.630129control,but not global.637972. Paired OOFdiagnostic '
    'shows2measured-control errors recovered and0spoiled,while no global-control error was corrected '
    'and2global correct answers were lost. No new test qualified. Do not call this a global improvement. '
    'The shared encoder now has actual prior physiology,while the native-private context remains old13history '
    'inputs. Recent native HR/current-minus-prior/current-over-prior are measured and completed before query '
    'on487fitting cases;current HRmissing0and2natural missing contrasts. Next predeclare a distinct native '
    'current-state context comparison with matched source-zero/source-positive controls,unchanged851source '
    'pairs/encoder/optimizer and frozen native weights/nonzero ratios. Do not fabricate recent context for '
    'source rows or introduce source current-bout HR. Original487/179,.65CVgate and144/179exact frozen '
    'artifact matches remain required. Only real public observations,no synthetic histories or labels. '
    'The native recent-state comparison is not yet predeclared or fitted.')
summary = {'version':1,'status':'complete','selection_sha256':digest(path),'verification_sha256':digest(audit_path),
    'input_verification_sha256':digest(study.INPUT_AUDIT),'configurations':6,'new_joint_network_fits':20,
    'independent_joint_refits':20,'new_native_base_fits_for_cv':0,'source_fitting_actual_pairs':851,'source_reserved_pairs':206,
    'best_positive_by_member':audit['best_positive_by_member'],'matched_zero_source_controls':audit['matched_zero_source_controls'],
    'winner_id':selected['winner_id'],'best_cv_accuracy':selected['best_cv_accuracy'],
    'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_cadence_binary_gate.py')),
    'real_tests_log_sha256':digest(tests_path),'recent_native_state_review_sha256':digest(review_path),
    'paired_oof_comparisons':review['paired_oof_comparisons'],'new_test_evaluation':test,
    'retained_test_correct':status['best_verified_test_correct'],'retained_test_accuracy':status['best_verified_test_accuracy'],
    'target_accuracy':.8,'achieved':status['goal_achieved'],
    'results':[{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for r in selected['results']]}
(study.DOCS/'cadence-binary-physiology-gate.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(study.DOCS/name)==value for name,value in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'completed_studies':56,'completed_configurations':1892,'distinct_tests':297,
    'retained_test_correct':status['best_verified_test_correct'],'goal_achieved':status['goal_achieved']}),flush=True)
