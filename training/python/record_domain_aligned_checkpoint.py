"""Register the audited domain-normalization experiment and exact evidence."""
import json
from pathlib import Path
import fatigue_domain_aligned_history as study
from public_sources import digest

status_path = study.DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls']) in ((50,1802),(51,1812))
assert status['python_tests_passed'] in (268,272) and status['goal_status']=='active'
inputs = study.load_inputs()
selection_path = study.DIRECTORY/'selection.json'
selection = json.loads(selection_path.read_text())
assert selection['status']=='complete' and selection['plan']==study.plan() and len(selection['results'])==10
assert all(selection.get(k)==v for k,v in study.fingerprint(inputs).items())
audit_path = study.DOCS/'domain-aligned-history-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_domain_aligned_history.py'))
assert audit['selection_sha256']==digest(selection_path) and audit['previous_verification_sha256']==digest(study.PARENT_AUDIT)
assert audit['actual_native_joint_refits']==len(audit['joint_refits'])==20 and audit['all_10_oof_recipes_recomputed']
assert audit['domain_specific_numeric_stats_and_binary_missing_indicators_verified']
assert audit['actual_source_and_native_losses_and_weights_observed'] and audit['zero_new_weight_excludes_shoulder_labels']
for row in audit['joint_refits']:
    assert row['actual_native_target_calls']==row['actual_total_losses_independently_checked']==80
    assert row['domain_normalizers_independently_checked']==6 and row['missing_indicators_binary_preserved']
    assert row['original_source_targets_untransformed'] and row['native_base_weights_frozen']
    assert row['reload_without_current_truth_or_ids']
tests_path = study.DOCS/'domain-aligned-history-tests.log'
tests = tests_path.read_text()
assert 'Ran 4 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
status.update(completed_studies=51,evaluated_configurations_including_controls=1812,python_tests_passed=272)
status.pop('running_study',None)
status['additional_scoped_verifications'][audit_path.name] = digest(audit_path)
status['domain_aligned_history_proposal'] = {'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
    'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'configurations':10,'new_joint_network_fits':30,
    'independent_joint_refits':20,'native_base_caches_reused':10,'new_native_base_fits':0,'source_targets_transformed':False}
raw_zero = {m:next(r for r in inputs['previous_selection']['results'] if r['candidate']['id']==key)
    for m,key in [('core','shoulder-joint-004'),('cat','shoulder-joint-007')]}
status['latest_complete_results'].update(domain_aligned_history_best_positive_cv=audit['best_positive_cv_accuracy'],
    domain_aligned_history_best_positive_mlp_cv=audit['best_positive_by_member']['core']['accuracy_mean'],
    domain_aligned_history_best_positive_catboost_cv=audit['best_positive_by_member']['cat']['accuracy_mean'],
    domain_aligned_history_zero_mlp_cv=audit['matched_zero_new_source_controls']['core']['accuracy_mean'],
    domain_aligned_history_zero_catboost_cv=audit['matched_zero_new_source_controls']['cat']['accuracy_mean'],
    domain_aligned_history_best_overall_cv=audit['best_cv_accuracy'])
test = audit['new_test_evaluation']
if test and test['correct']>status['best_verified_test_correct']:
    status.update(best_verified_test_correct=test['correct'],best_verified_test_accuracy=test['test_accuracy'],
        best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
status['goal_achieved'] = status['best_verified_test_correct']>=144
status['next_evidence_based_direction'] = (
    'Study51completed10domain-normalization recipes/30joint networks plus20independent refits. Six domainnormalizers verified against fitting-only stats; numeric prior inputs standardized separately and actual availability bits preservedbinary. '
    'Source original targetpoints/deltas were unchanged in five heads; native487/179cases,2336source fit/312reserved and all nativebasecaches preserved. '
    'Neither raw-history source expansion50nor predictor alignment51beat the inherited.637972CVcontrol; do not repeat their epoch,source-weight or normalization grids. '
    'The source-head history-only inputs omit actual concurrent physiological/motion state. Next inspect original released sensor clocks and documentation for a causally valid pre-report signal association; count only real fitting-person reports and do not assume timestamp alignment from sample rate or filenames. '
    'No sensor joins or sensor models have yet been validated for WSD. Keep source outcomes separate,original native487/179and.65CVtestgate.80percent needs144of179from a frozen reloaded artifact;retained108. No synthetic data or test-directed tuning.')
compact = lambda row:{k:row[k] for k in ('candidate','accuracy_mean','fold_accuracy')}
summary = {'version':1,'status':'complete','selection_sha256':digest(selection_path),'verification_sha256':digest(audit_path),
    'configurations':10,'new_joint_network_fits':30,'independent_joint_refits':20,'new_native_base_fits':0,
    'source_fitting_targets':2336,'source_fitting_actual_second_priors':1927,'source_reserved_targets':312,
    'best_positive_by_member':audit['best_positive_by_member'],'matched_zero_new_source_controls':audit['matched_zero_new_source_controls'],
    'previous_raw_zero_source_controls':{m:compact(r) for m,r in raw_zero.items()},
    'winner_id':selection['winner_id'],'best_cv_accuracy':selection['best_cv_accuracy'],
    'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_domain_aligned_history.py')),
    'real_tests_log_sha256':digest(tests_path),'source_targets_transformed':False,
    'results':[{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for r in selection['results']],
    'new_test_evaluation':test,'retained_test_correct':status['best_verified_test_correct'],
    'retained_test_accuracy':status['best_verified_test_accuracy'],'target_accuracy':.8,'achieved':status['goal_achieved']}
(study.DOCS/'domain-aligned-history-transfer.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(study.DOCS/name)==expected for name,expected in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'completed_studies':51,'completed_configurations':1812,'distinct_tests':272,
    'best_verified_test_accuracy':status['best_verified_test_accuracy'],'goal_achieved':status['goal_achieved']}),flush=True)
