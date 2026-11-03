"""Read-only verification of current study55 and its scoped evidence."""
import ast
import json
from pathlib import Path
import fatigue_change_gate_regularization as study
from public_sources import digest


def validate():
    status = json.loads((study.DOCS/'current-research-status.json').read_text())
    assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed'])==(55,1886,292)
    assert status['goal_status']=='active' and 'running_study' not in status
    assert (status['original_training_cases'],status['original_test_cases'],status['required_correct_for_80_percent'])==(487,179,144)
    checked = 0
    for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
        for name,value in status[field].items():
            assert digest(study.DOCS/name)==value,(field,name)
            checked += 1
    tree = ast.parse(Path(__file__).with_name('fatigue_80_checkpoint.py').read_text())
    names = next(ast.literal_eval(node.iter) for node in ast.walk(tree) if isinstance(node,ast.For)
        and isinstance(node.target,ast.Name) and node.target.id=='name' and isinstance(node.iter,ast.Tuple)
        and any(isinstance(item,ast.Constant) and item.value==study.DIRECTORY.name for item in node.iter.elts))
    counts = []
    for name in names:
        selected = json.loads((study.DIRECTORY.parent/name/'selection.json').read_text())
        assert selected['status']=='complete',name
        counts.append(len(selected['results']))
    assert len(counts)==55 and sum(counts)==1886
    inputs = study.load_inputs()
    selected_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selected_path.read_text())
    assert selected['status']=='complete' and selected['plan']==study.plan()
    assert all(selected.get(k)==value for k,value in study.fingerprint(inputs).items())
    assert digest(study.DIRECTORY/'selection-source.py')==selected['code_sha256']
    audit_path = study.DOCS/'change-gate-regularization-verification.json'
    audit = json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selected_path)
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_change_gate_regularization.py'))
    assert audit['previous_verification_sha256']==digest(study.PARENT_AUDIT)
    assert audit['all_18_oof_recipes_recomputed'] and audit['all_60_fold_artifacts_recomputed']
    assert audit['prior_inner_native_models_independently_verified']==30 and audit['independent_joint_refits']==20
    assert len(audit['native_joint_refits'])==20 and audit['new_native_base_fits']==audit['synthetic_rows']==0
    assert audit['source_targets_from_original_pairs'] and audit['current_and_future_native_labels_excluded_from_predictors']
    for row in audit['native_joint_refits']:
        assert row['actual_native_target_steps']==row['actual_losses_independently_checked']==row['actual_total_backward_calls']==80
        assert row['actual_source_target_steps'] in (0,320) and row['initial_parameters_verified']
        assert row['native_joint_nll_gradient_equivalence_verified'] and row['source_targets_from_original_pairs']
        assert row['base_weights_frozen'] and row['nonzero_delta_ratios_frozen'] and row['input_only_reload_verified']
    for field,directory,count in [('fold_artifact_hashes',study.DIRECTORY/'folds',120),
            ('native_base_cache_artifact_hashes',study.native.DIRECTORY/'bases',20)]:
        assert len(audit[field])==count
        assert all(digest(directory/name)==value for name,value in audit[field].items())
    gate_path = study.DOCS/'change-gate-regularization-test-gate.json'
    assert audit['test_gate_sha256']==digest(gate_path)
    gate = json.loads(gate_path.read_text())
    assert gate['selection_sha256']==digest(selected_path) and gate['gate_passed']==audit['new_test_gate_passed']
    assert gate['evaluator_code_sha256']==digest(Path(__file__).with_name('evaluate_fatigue_change_gate_regularization.py'))
    assert gate['pretest_verifier_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_change_gate_regularization.py'))
    if gate['gate_passed']:
        test = audit['new_test_evaluation']
        assert test==gate['new_test_evaluation'] and test['test_cases']==179
        assert gate['pretest_winner_fold_artifacts_verified']==5 and audit['independent_full_test_artifact_audit']
        assert digest(study.DIRECTORY/'evaluation/model.joblib')==test['model_sha256']
        assert status['best_verified_test_correct']==max(108,test['test_correct'])
    else:
        assert gate['pretest_winner_fold_artifacts_verified']==0 and audit['new_test_evaluation'] is None
        assert audit['independent_full_test_artifact_audit'] is None and not (study.DIRECTORY/'evaluation').exists()
        assert status['best_verified_test_correct']==108
    summary = json.loads((study.DOCS/'change-gate-regularization.json').read_text())
    assert summary['selection_sha256']==digest(selected_path) and summary['verification_sha256']==digest(audit_path)
    assert summary['real_tests_code_sha256']==digest(Path(__file__).with_name('test_fatigue_change_gate_regularization.py'))
    tests_path = study.DOCS/'change-gate-regularization-tests.log'
    assert summary['real_tests_log_sha256']==digest(tests_path)
    assert 'Ran 5 tests' in tests_path.read_text() and 'OK' in tests_path.read_text()
    diagnostic_path = study.DOCS/'change-gate-regularization-margin-diagnostic.json'
    assert summary['margin_diagnostic_sha256']==status['change_gate_regularization_margin_diagnostic']['sha256']==digest(diagnostic_path)
    diagnostic = json.loads(diagnostic_path.read_text())
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_change_gate_regularization_margins.py'))
    assert diagnostic['selection_sha256']==digest(selected_path)
    assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_preprocessor_fits']==diagnostic['new_test_predictions_computed']==0
    assert not diagnostic['test_labels_inspected'] and len(diagnostic['results'])==12
    for name,value in diagnostic['fold_model_hashes'].items():
        assert audit['fold_artifact_hashes'][name]==value
    assert status['best_verified_test_accuracy']==status['best_verified_test_correct']/179
    assert status['goal_achieved']==(status['best_verified_test_correct']>=144)
    assert status['change_gate_regularization_proposal']['sha256']==digest(study.PROPOSAL)
    assert status['change_gate_regularization_proposal']['model_study_completed']
    review_path = study.DOCS/'cadence-binary-physiology-review.json'
    assert status['cadence_binary_physiology_review']['sha256']==summary['cadence_binary_physiology_review_sha256']==digest(review_path)
    review = json.loads(review_path.read_text())
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_binary_physiology.py'))
    assert review['preceding_selection_sha256']==digest(selected_path) and review['preceding_verification_sha256']==digest(audit_path)
    assert review['source_fitting_actual_pairs']==851 and review['source_reserved_pairs_not_used']==206
    assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0
    prepared_path = study.DOCS/'change-gate-regularization-verifier-preparation.json'
    preparation = json.loads(prepared_path.read_text())
    assert preparation['preparation_code_sha256']==digest(Path(__file__).with_name('prepare_change_gate_regularization_verifiers.py'))
    for name,value in {**preparation['frozen_sources_sha256'],**preparation['derived_files_sha256']}.items():
        assert digest(Path(__file__).with_name(name))==value
    assert (len(inputs['gate_source']),len(inputs['reserved_source']))==(2287,312)
    print(json.dumps({'integrity':'passed','completed_studies':55,'completed_configurations':1886,'distinct_tests':292,
        'scoped_evidence_hashes_checked':checked,'new_fold_artifact_hashes_checked':120,'native_base_cache_artifact_hashes_checked':20,
        'independent_joint_refits':20,'prior_inner_native_forward_verifications':30,'source_fitting_actual_pairs':2287,
        'retained_test_correct':status['best_verified_test_correct'],'retained_test_accuracy':status['best_verified_test_accuracy'],
        'goal_achieved':status['goal_achieved'],'historical_refitting_performed':False}),flush=True)


if __name__=='__main__':
    validate()
