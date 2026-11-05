"""Record independently verified four-source change-gate study55."""
import json
from pathlib import Path
import fatigue_change_gate_regularization as study
from public_sources import digest

status_path = study.DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed']) in (
    (54,1868,287),(55,1886,292))
inputs = study.load_inputs()
selection_path = study.DIRECTORY/'selection.json'
selected = json.loads(selection_path.read_text())
assert selected['status']=='complete' and len(selected['results'])==18 and selected['plan']==study.plan()
assert all(selected.get(k)==value for k,value in study.fingerprint(inputs).items())
audit_path = study.DOCS/'change-gate-regularization-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(selection_path)
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_change_gate_regularization.py'))
assert audit['all_18_oof_recipes_recomputed'] and audit['all_60_fold_artifacts_recomputed']
assert audit['independent_joint_refits']==len(audit['native_joint_refits'])==20
assert audit['prior_inner_native_models_independently_verified']==30 and audit['new_native_base_fits']==0
for row in audit['native_joint_refits']:
    assert row['actual_correction_penalty']==next(r['candidate']['correction_penalty'] for r in selected['results'] if r['candidate']['id']==row['candidate_id'])
    assert row['actual_native_target_steps']==row['actual_losses_independently_checked']==row['actual_total_backward_calls']==80
    assert row['actual_source_target_steps'] in (0,320) and row['initial_parameters_verified']
    assert row['native_joint_nll_gradient_equivalence_verified'] and row['source_targets_from_original_pairs']
    assert row['base_weights_frozen'] and row['nonzero_delta_ratios_frozen'] and row['input_only_reload_verified']
for field,directory in [('fold_artifact_hashes',study.DIRECTORY/'folds'),('native_base_cache_artifact_hashes',study.native.DIRECTORY/'bases')]:
    assert all(digest(directory/name)==value for name,value in audit[field].items())
tests_path = study.DOCS/'change-gate-regularization-tests.log'
tests = tests_path.read_text()
assert 'Ran 5 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
diagnostic_path = study.DOCS/'change-gate-regularization-margin-diagnostic.json'
diagnostic = json.loads(diagnostic_path.read_text())
assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(selection_path)
assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_change_gate_regularization_margins.py'))
assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_preprocessor_fits']==diagnostic['new_test_predictions_computed']==0
assert len(diagnostic['results'])==12 and not diagnostic['test_labels_inspected']
status.update(completed_studies=55,evaluated_configurations_including_controls=1886,python_tests_passed=292)
status.pop('running_study',None)
status['additional_scoped_verifications'][audit_path.name] = digest(audit_path)
status['change_gate_regularization_proposal'] = {'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
    'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'configurations':18,'new_joint_network_fits':60,
    'independent_joint_refits':20,'new_native_base_fits_for_cv':0,'native_base_caches_reused':10,
    'source_fitting_actual_pairs':2287,'source_reserved_pairs_not_fitted':312,'excluded_single_class_sts_pairs':49,
    'source_outcomes_pooled_as_native_labels':False,'nonzero_delta_relative_probabilities_frozen':True}
status['public_observed_change_support_review'].update(next_model_comparison_predeclared=True,
    used_in_study=study.DIRECTORY.name,model_comparison_completed=True)
status['latest_complete_results'].update(change_gate_regularization_best_positive_cv=audit['best_positive_cv_accuracy'],
    change_gate_regularization_best_mlp_cv=audit['best_positive_by_member']['core']['accuracy_mean'],
    change_gate_regularization_best_catboost_cv=audit['best_positive_by_member']['cat']['accuracy_mean'],
    change_gate_regularization_zero_source_mlp_cv=audit['matched_zero_source_controls']['core']['accuracy_mean'],
    change_gate_regularization_zero_source_catboost_cv=audit['matched_zero_source_controls']['cat']['accuracy_mean'],
    change_gate_regularization_best_overall_cv=audit['best_cv_accuracy'])
test = audit['new_test_evaluation']
if test and test['test_correct']>status['best_verified_test_correct']:
    status.update(best_verified_test_correct=test['test_correct'],best_verified_test_accuracy=test['test_accuracy'],
        best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
status['goal_achieved'] = status['best_verified_test_correct']>=144
status['change_gate_regularization_margin_diagnostic'] = {'document':diagnostic_path.name,'sha256':digest(diagnostic_path),
    'fitting_only':True,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,'recipes_checked':12,
    'native_borg_decision_changes':sum(row['final_native_borg_predictions_changed'] for row in diagnostic['results']),
    'oracle_bounds_are_not_achieved_accuracy':True}
review_path = study.DOCS/'cadence-binary-physiology-review.json'
review = json.loads(review_path.read_text())
assert review['review']=='passed' and review['preceding_selection_sha256']==digest(selection_path)
assert review['preceding_verification_sha256']==digest(audit_path)
assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_binary_physiology.py'))
assert review['source_fitting_actual_pairs']==851 and review['source_reserved_pairs_not_used']==206
assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0
status['cadence_binary_physiology_review'] = {'document':review_path.name,'sha256':digest(review_path),
    'fitting_only':True,'source_fitting_actual_pairs':851,'source_reserved_pairs_not_used':206,
    'actual_source_second_priors_recoverable':727,'source_actual_unchanged_pairs':299,'source_actual_changed_pairs':552,
    'model_comparison_predeclared':False,'new_predictive_estimator_fits':0}
status['public_change_gate_margin_diagnostic'].update(followup_comparison_completed=True,used_in_study=study.DIRECTORY.name)
status['next_evidence_based_direction'] = (
    'Study55completed18predeclared recipes/60joint networks,all60artifacts and18OOFmetrics independently '
    'verified,20networks refitted with actual losses/gradients/backward and unchanged native base weights. '
    'New penalties0/.1/1produced6to27decision changes,but best new CatBoost.633837CV did not beat.637972 '
    'global control. Source.1did not improve the best matching native-only recipe;no new test qualified. '
    'Do not extend pure-history source-weight/penalty grids. The shared encoder still observes only '
    'two past RPEreports,without physiological state. The read-only CADENCE review independently '
    'checked851actual adjacent-stage fitting pairs/123people,299unchanged/552changed,4decreases and '
    '727genuine second priors;206source reserved pairs were not used. Source HRcomes only from a '
    'completed preceding bout;native prior HR/baseline windows were verified on all487fitting cases '
    'without discarding missing inputs. Next predeclare a distinct actual-physiology-plus-history '
    'binary auxiliary representation with matched measured native-only controls and a separately '
    'audited prepared adapter. Earlier CADENCE representations used continuous RPE;history-only '
    'binary transfer55omitted physiology. No source current-bout HR,timestamps,ages,native phases '
    'or scale equivalence may be invented. Keep original487/179and.65CVgate,real public data only. '
    '80percent still requires144of179exact matches from a frozen reloaded model;retained108. '
    'The physiological binary comparison is not yet predeclared or fitted.')
summary = {'version':1,'status':'complete','selection_sha256':digest(selection_path),'verification_sha256':digest(audit_path),
    'configurations':18,'new_joint_network_fits':60,'independent_joint_refits':20,'new_native_base_fits_for_cv':0,
    'source_fitting_actual_pairs':2287,'source_reserved_pairs_not_fitted':312,'excluded_single_class_sts_pairs':49,
    'best_positive_by_member':audit['best_positive_by_member'],'matched_zero_source_controls':audit['matched_zero_source_controls'],
    'winner_id':selected['winner_id'],'best_cv_accuracy':selected['best_cv_accuracy'],
    'best_native_only_by_member':audit['best_native_only_by_member'],'cadence_binary_physiology_review_sha256':digest(review_path),
    'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_change_gate_regularization.py')),
    'real_tests_log_sha256':digest(tests_path),'margin_diagnostic_sha256':digest(diagnostic_path),
    'new_test_evaluation':test,'retained_test_correct':status['best_verified_test_correct'],
    'retained_test_accuracy':status['best_verified_test_accuracy'],'target_accuracy':.8,'achieved':status['goal_achieved'],
    'results':[{k:row[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for row in selected['results']]}
(study.DOCS/'change-gate-regularization.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(study.DOCS/name)==value for name,value in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'completed_studies':55,'completed_configurations':1886,'distinct_tests':292,
    'retained_test_correct':status['best_verified_test_correct'],'goal_achieved':status['goal_achieved']}),flush=True)
