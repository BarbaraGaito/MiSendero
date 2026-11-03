"""Record concrete evidence for the separate-output shoulder transfer study."""
import argparse
import json
from pathlib import Path
import fatigue_shoulder_history_joint as study
from public_sources import digest


def update(phase):
    path = study.DOCS/'current-research-status.json'
    status = json.loads(path.read_text())
    assert (status['completed_studies'],status['evaluated_configurations_including_controls']) in ((49,1792),(50,1802))
    assert status['python_tests_passed'] in (264,268) and status['goal_status']=='active'
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/'selection.json'
    selection = json.loads(selection_path.read_text())
    assert selection['plan']==study.plan() and all(selection.get(k)==v for k,v in study.fingerprint(inputs).items())
    tests_path = study.DOCS/'shoulder-history-joint-tests.log'
    tests = tests_path.read_text()
    assert 'Ran 4 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
    status['python_tests_passed'] = 268
    for name in ('wsd4fedsrm-history-input-verification.json','shoulder-history-input-verification.json'):
        proof_path = study.DOCS/name
        assert json.loads(proof_path.read_text())['verification']=='passed'
        status['additional_data_audits'][name] = digest(proof_path)
    status['wsd4fedsrm_history_preparation'].update(independent_adapter_verification_completed=True,
        model_fitting_started=True,used_in_study=study.DIRECTORY.name)
    status['wsd4fedsrm_original_opportunity'].update(adapter_prepared=True,model_fitting_started=True)
    status['shoulder_history_joint_proposal'] = {'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
        'implementation_started':True,'model_fitting_started':True,'used_in_study':study.DIRECTORY.name,
        'planned_configurations_including_controls':10,'new_joint_network_fits':30,'new_native_base_fits':0}
    if phase in ('start','pending'):
        assert status['completed_studies']==49
        status['running_study'] = {'directory':study.DIRECTORY.name,'planned_configurations_including_controls':10,
            'new_joint_network_fits':30,'native_base_caches_reused':10,'cached_native_base_models':40,
            'new_native_base_fits':0,'actual_source_fitting_targets':2336,'new_shoulder_fitting_targets':920,
            'new_shoulder_fitting_people':27,'source_fitting_actual_second_priors':1927,
            'source_reserved_targets_not_fitted':312,'shoulder_weights':[0.,.1,1.],'fixed_epochs':80,
            'training_log':'shoulder-history-joint-training.log','counted_as_complete':False,
            'phase':'training_selection' if phase=='start' else 'independent_actual_loss_gradient_verification',
            'training_selection_complete':selection['status']=='complete'}
        if phase=='pending':
            assert selection['status']=='complete' and len(selection['results'])==10
            status['running_study'].update(training_process_terminal=True,verification_log='shoulder-history-joint-verification.log')
        status['next_evidence_based_direction'] = (
            'Study50completed actualpublic source preparation and four real-loss tests,now verifying the10fixed recipes/30new joint networks. '
            'All2336source fitting targets remain original and separate;312stored source targets reserved. '
            'Actual920new6-20shoulder pairs/27people supervise a fifth source delta head;758have second genuine timed priors. '
            'Weightzero reproduces preceding47positive controls exactly;positiveweights.1/1observed originaltargets,personweights,mixedloss,backward and source-only gradients. '
            'Original487/179native cases and.65CVtest gate unchanged. Finish20independent joint refits before counting50;80percent needs144of179from a frozen reloaded artifact,retained108. No synthetic rows,clock/phase guesses,sensor joins or source-native target pooling.')
    else:
        assert selection['status']=='complete' and len(selection['results'])==10
        audit_path = study.DOCS/'shoulder-history-joint-verification.json'
        audit = json.loads(audit_path.read_text())
        assert audit['verification']=='passed' and audit['selection_sha256']==digest(selection_path)
        assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_shoulder_history_joint.py'))
        assert audit['input_verification_sha256']==digest(study.INPUT_AUDIT) and audit['previous_verification_sha256']==digest(study.PARENT_AUDIT)
        assert audit['all_10_oof_recipes_recomputed'] and audit['original_native_rows_and_targets_preserved']
        assert audit['actual_native_joint_refits']==len(audit['joint_refits'])==20
        for key in ('actual_source_and_native_losses_and_weights_observed','actual_shoulder_to_encoder_gradients_verified',
            'zero_new_weight_excludes_shoulder_labels','old_initial_parameters_and_matched_control_predictions_preserved',
            'native_base_weights_frozen','matched_preprocessing_fitting_rows_only'):
            assert audit[key],key
        assert not audit['source_outcomes_pooled'] and audit['synthetic_rows']==audit['new_native_base_fits']==0
        for row in audit['joint_refits']:
            assert row['actual_native_target_calls']==row['actual_total_losses_independently_checked']==80
            assert row['actual_source_targets_per_step'] in (1416,2336)
            assert row['actual_shoulder_targets_per_step'] in (0,920)
        status.update(completed_studies=50,evaluated_configurations_including_controls=1802)
        status.pop('running_study',None)
        status['additional_scoped_verifications'][audit_path.name] = digest(audit_path)
        status['shoulder_history_joint_proposal']['model_study_completed'] = True
        status['latest_complete_results'].update(shoulder_history_joint_best_positive_cv=audit['best_positive_cv_accuracy'],
            shoulder_history_joint_best_positive_mlp_cv=audit['best_positive_by_member']['core']['accuracy_mean'],
            shoulder_history_joint_best_positive_catboost_cv=audit['best_positive_by_member']['cat']['accuracy_mean'],
            shoulder_history_joint_zero_mlp_cv=audit['matched_zero_new_source_controls']['core']['accuracy_mean'],
            shoulder_history_joint_zero_catboost_cv=audit['matched_zero_new_source_controls']['cat']['accuracy_mean'],
            shoulder_history_joint_best_overall_cv=audit['best_cv_accuracy'])
        test = audit['new_test_evaluation']
        if test and test['correct']>status['best_verified_test_correct']:
            status.update(best_verified_test_correct=test['correct'],best_verified_test_accuracy=test['test_accuracy'],
                best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
        status['goal_achieved'] = status['best_verified_test_correct']>=144
        range_path = study.DOCS/'shoulder-history-range-diagnostic.json'
        diagnostic = json.loads(range_path.read_text())
        assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(selection_path)
        assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_shoulder_history_ranges.py'))
        assert diagnostic['new_predictive_estimator_fits']==diagnostic['native_test_predictions_computed']==0
        support = diagnostic['fold_only_preprocessing_support'][0]['source_support']['shoulder'][study.source.PRIOR]
        status['shoulder_history_range_diagnostic'] = {'document':range_path.name,'sha256':digest(range_path),
            'fitting_only':True,'first_fold_source_priors_outside_native_fit_range':support['observed_values_outside_native_fitting_range'],
            'source_prior_count':920,'new_predictive_estimator_fits':0,'native_test_predictions_computed':0}
        status['next_evidence_based_direction'] = (
            'Study50completed10recipes/30new joint networks plus20independent refits observing actual source/native losses,weights,gradients,frozen bases and runtime reload. '
            'Keep2336actual source fitting targets with1927genuine second histories and312stored reserved targets,separate source outcomes and original487/179native cases. '
            'New shoulder supervision did not beat the matched native controls; do not repeat these source-weight or epoch grids. '
            'The fitting-only range diagnostic found853of920shoulder priors outside the first native fitting-fold range and87.39percent beyond3pooled standard deviations;encoder saturation was not measured. '
            'Next predeclare predictor representation alignment with per-domain fitting-only statistics and matched zero-source controls;do not repeat raw-source weights or epoch grids. '
            'Any alignment must transform predictors only,keep original source targets in separate heads,and use fitting-only statistics;no physiological scaleequivalence or invented clocks. '
            'The.65CVtest gate remains;80percent requires144of179from a frozen reloaded artifact. No synthetic rows,source-native label pooling or reserved-test-directed tuning.')
        summary = {'version':1,'status':'complete','selection_sha256':digest(selection_path),'verification_sha256':digest(audit_path),
            'input_verification_sha256':digest(study.INPUT_AUDIT),'configurations':10,'new_joint_network_fits':30,
            'independent_joint_refits':20,'new_native_base_fits':0,'source_fitting_targets':2336,
            'source_fitting_actual_second_priors':1927,'source_reserved_targets':312,
            'best_positive_by_member':audit['best_positive_by_member'],'matched_zero_new_source_controls':audit['matched_zero_new_source_controls'],
            'winner_id':selection['winner_id'],'best_cv_accuracy':selection['best_cv_accuracy'],
            'results':[{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for r in selection['results']],
            'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_shoulder_history_joint.py')),
            'real_tests_log_sha256':digest(tests_path),'new_test_evaluation':test,'retained_test_correct':status['best_verified_test_correct'],
            'fitting_only_range_diagnostic_sha256':digest(range_path),
            'retained_test_accuracy':status['best_verified_test_accuracy'],'target_accuracy':.8,'achieved':status['goal_achieved']}
        (study.DOCS/'shoulder-history-joint-transfer.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
        assert all(digest(study.DOCS/name)==expected for name,expected in status[field].items())
    path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'phase':phase,'completed_studies':status['completed_studies'],
        'completed_configurations':status['evaluated_configurations_including_controls'],'distinct_tests':status['python_tests_passed'],
        'best_verified_test_accuracy':status['best_verified_test_accuracy'],'goal_achieved':status['goal_achieved']}),flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['start','pending','complete'],default='complete')
    update(parser.parse_args().phase)
