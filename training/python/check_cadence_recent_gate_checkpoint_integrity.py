"""Read-only current-state evidence for audited study57."""
import ast
import json
from pathlib import Path
import fatigue_cadence_recent_gate as study
from public_sources import digest


def validate():
    status = json.loads((study.DOCS/'current-research-status.json').read_text())
    assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed'])==(57,1902,303)
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
    assert len(counts)==57 and sum(counts)==1902
    inputs = study.load_inputs()
    path = study.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    assert selected['status']=='complete' and selected['plan']==study.plan()
    assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
    assert digest(study.DIRECTORY/'selection-source.py')==selected['code_sha256']
    audit_path = study.DOCS/'cadence-recent-gate-verification.json'
    audit = json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(path)
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_recent_gate.py'))
    assert audit['previous_verification_sha256']==digest(study.PARENT_AUDIT)
    assert audit['all_10_oof_recipes_recomputed'] and audit['all_20_fold_artifacts_recomputed']
    assert audit['independent_joint_refits']==len(audit['native_joint_refits'])==20
    assert audit['prior_inner_native_models_independently_verified']==30 and audit['new_native_base_fits']==audit['synthetic_rows']==0
    assert audit['source_fitting_actual_pairs']==851 and audit['source_reserved_pairs_not_fitted']==206
    for row in audit['native_joint_refits']:
        assert row['actual_native_target_steps']==row['actual_losses_independently_checked']==row['actual_total_backward_calls']==80
        assert row['actual_source_target_steps'] in (0,80) and row['initial_parameters_verified']
        assert row['native_joint_nll_gradient_equivalence_verified'] and row['source_targets_from_original_pairs']
        assert row['base_weights_frozen'] and row['nonzero_delta_ratios_frozen'] and row['input_only_reload_verified']
    for field,directory,count in [('fold_artifact_hashes',study.DIRECTORY/'folds',40),
            ('native_base_cache_artifact_hashes',study.native.DIRECTORY/'bases',20)]:
        assert len(audit[field])==count
        assert all(digest(directory/name)==value for name,value in audit[field].items())
    gate_path = study.DOCS/'cadence-recent-gate-test-gate.json'
    assert audit['test_gate_sha256']==digest(gate_path)
    gate = json.loads(gate_path.read_text())
    assert gate['selection_sha256']==digest(path) and gate['gate_passed']==audit['new_test_gate_passed']
    assert gate['evaluator_code_sha256']==digest(Path(__file__).with_name('evaluate_fatigue_cadence_recent_gate.py'))
    assert gate['pretest_verifier_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_recent_gate.py'))
    if gate['gate_passed']:
        test = audit['new_test_evaluation']
        assert test==gate['new_test_evaluation'] and test['test_cases']==179 and audit['independent_full_test_artifact_audit']
        assert digest(study.DIRECTORY/'evaluation/model.joblib')==test['model_sha256']
        assert status['best_verified_test_correct']==max(108,test['test_correct'])
    else:
        assert audit['new_test_evaluation'] is None and audit['independent_full_test_artifact_audit'] is None
        assert not (study.DIRECTORY/'evaluation').exists() and status['best_verified_test_correct']==108
    summary = json.loads((study.DOCS/'cadence-recent-native-gate.json').read_text())
    assert summary['selection_sha256']==digest(path) and summary['verification_sha256']==digest(audit_path)
    assert summary['input_verification_sha256']==digest(study.INPUT_AUDIT)
    input_audit = json.loads(study.INPUT_AUDIT.read_text())
    assert input_audit['verification']=='passed'
    assert input_audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_recent_gate_inputs.py'))
    assert input_audit['preparation_code_sha256']==digest(Path(study.added.__file__))
    assert input_audit['provenance_sha256']==digest(study.added.DIRECTORY/'provenance.json')
    assert input_audit['native_dataset_sha256']==digest(study.added.DIRECTORY/'native.csv')
    assert input_audit['native_cells_independently_rebuilt']==input_audit['native_clocks_verified']==666
    source_audit = json.loads(study.previous.INPUT_AUDIT.read_text())
    assert source_audit['verification']=='passed' and source_audit['actual_source_pairs_independently_rebuilt']==1057
    assert source_audit['preparation_code_sha256']==digest(Path(study.prepared.__file__))
    assert source_audit['source_dataset_sha256']==digest(study.prepared.DIRECTORY/'source.csv')
    assert source_audit['native_dataset_sha256']==digest(study.prepared.DIRECTORY/'native.csv')
    assert summary['real_tests_code_sha256']==digest(Path(__file__).with_name('test_fatigue_cadence_recent_gate.py'))
    tests_path = study.DOCS/'cadence-recent-gate-tests.log'
    assert summary['real_tests_log_sha256']==digest(tests_path)
    assert 'Ran 6 tests' in tests_path.read_text() and 'OK' in tests_path.read_text()
    diagnostic_path = study.DOCS/'cadence-recent-gate-error-diagnostic.json'
    assert summary['error_diagnostic_sha256']==status['cadence_recent_gate_diagnostic']['sha256']==digest(diagnostic_path)
    diagnostic = json.loads(diagnostic_path.read_text())
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_cadence_recent_gate_errors.py'))
    assert diagnostic['selection_sha256']==digest(path) and diagnostic['verification_sha256']==digest(audit_path)
    assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_test_predictions_computed']==0 and not diagnostic['test_labels_inspected']
    review_path = study.DOCS/'cadence-full-delta-residual-review.json'
    assert summary['full_delta_residual_review_sha256']==status['cadence_full_delta_residual_review']['sha256']==digest(review_path)
    review = json.loads(review_path.read_text())
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_full_delta_residual.py'))
    assert review['selection_sha256']==digest(path) and review['verification_sha256']==digest(audit_path)
    assert all(digest(Path(__file__).with_name(name))==value for name,value in review['implementation_sha256'].items())
    assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0 and not review['model_comparison_predeclared']
    preparation = json.loads((study.DOCS/'cadence-recent-gate-verifier-preparation.json').read_text())
    assert preparation['preparation_code_sha256']==digest(Path(__file__).with_name('prepare_cadence_recent_gate_verifiers.py'))
    for name,value in {**preparation['frozen_sources_sha256'],**preparation['derived_files_sha256']}.items():
        assert digest(Path(__file__).with_name(name))==value
    assert status['best_verified_test_accuracy']==status['best_verified_test_correct']/179
    assert status['goal_achieved']==(status['best_verified_test_correct']>=144)
    assert status['cadence_recent_native_gate_proposal']['sha256']==digest(study.PROPOSAL) and status['cadence_recent_native_gate_proposal']['model_study_completed']
    assert (len(inputs['train']),len(inputs['test']),len(inputs['gate_source']),len(inputs['reserved_gate_source']))==(487,179,851,206)
    print(json.dumps({'integrity':'passed','completed_studies':57,'completed_configurations':1902,'distinct_tests':303,
        'scoped_evidence_hashes_checked':checked,'new_fold_artifact_hashes_checked':40,'native_base_cache_artifact_hashes_checked':20,
        'independent_joint_refits':20,'source_original_pairs_rebuilt':1057,'source_fitting_pairs':851,
        'native_original_cases_and_clocks_verified':666,'retained_test_correct':status['best_verified_test_correct'],
        'retained_test_accuracy':status['best_verified_test_accuracy'],'goal_achieved':status['goal_achieved'],
        'historical_refitting_performed':False}),flush=True)


if __name__=='__main__':
    validate()
