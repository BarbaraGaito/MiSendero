"""Read-only evidence for the completed domain-alignment comparison."""
import ast
import json
from pathlib import Path
import fatigue_domain_aligned_history as study
from public_sources import digest


def validate():
    status = json.loads((study.DOCS/'current-research-status.json').read_text())
    assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed'])==(51,1812,272)
    assert status['goal_status']=='active' and 'running_study' not in status
    assert (status['original_training_cases'],status['original_test_cases'],status['required_correct_for_80_percent'])==(487,179,144)
    checked = 0
    for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
        for name,expected in status[field].items():
            assert digest(study.DOCS/name)==expected,(field,name)
            checked += 1
    tree = ast.parse(Path(__file__).with_name('fatigue_80_checkpoint.py').read_text())
    families = next(ast.literal_eval(node.iter) for node in ast.walk(tree) if isinstance(node,ast.For)
        and isinstance(node.target,ast.Name) and node.target.id=='name' and isinstance(node.iter,ast.Tuple)
        and any(isinstance(x,ast.Constant) and x.value==study.DIRECTORY.name for x in node.iter.elts))
    counts = []
    for name in families:
        selection = json.loads((study.DIRECTORY.parent/name/'selection.json').read_text())
        assert selection['status']=='complete',name
        counts.append(len(selection['results']))
    assert len(counts)==51 and sum(counts)==1812
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/'selection.json'
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k)==v for k,v in study.fingerprint(inputs).items()) and selection['plan']==study.plan()
    assert digest(study.DIRECTORY/'selection-source.py')==selection['code_sha256']
    audit_path = study.DOCS/'domain-aligned-history-verification.json'
    audit = json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selection_path)
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_domain_aligned_history.py'))
    assert audit['previous_verification_sha256']==digest(study.PARENT_AUDIT)
    assert audit['actual_native_joint_refits']==len(audit['joint_refits'])==20 and audit['all_10_oof_recipes_recomputed']
    assert audit['domain_specific_numeric_stats_and_binary_missing_indicators_verified'] and audit['old_initial_parameters_preserved']
    for row in audit['joint_refits']:
        assert row['actual_native_target_calls']==row['actual_total_losses_independently_checked']==80
        assert row['actual_source_target_calls'] in (320,400) and row['actual_shoulder_targets_per_step'] in (0,920)
        assert row['domain_normalizers_independently_checked']==6 and row['original_source_targets_untransformed']
        assert row['missing_indicators_binary_preserved'] and row['preprocessing_fitting_rows_only']
        assert row['native_base_weights_frozen'] and row['reload_without_current_truth_or_ids']
    for name,expected in audit['native_base_cache_artifact_hashes'].items():
        assert digest(study.base.previous.DIRECTORY/'bases'/name)==expected
    assert (len(inputs['source']),len(inputs['reserved_source']))==(2336,312)
    assert inputs['source'][study.source.SECOND].notna().sum()==1927
    assert not audit['source_outcomes_pooled'] and audit['synthetic_rows']==audit['new_native_base_fits']==0
    summary = json.loads((study.DOCS/'domain-aligned-history-transfer.json').read_text())
    assert summary['selection_sha256']==digest(selection_path) and summary['verification_sha256']==digest(audit_path)
    assert summary['real_tests_code_sha256']==digest(Path(__file__).with_name('test_fatigue_domain_aligned_history.py'))
    tests_path = study.DOCS/'domain-aligned-history-tests.log'
    assert summary['real_tests_log_sha256']==digest(tests_path)
    assert 'Ran 4 tests' in tests_path.read_text() and 'OK' in tests_path.read_text()
    if not audit['new_test_gate_passed']:
        assert audit['new_test_evaluation'] is None and not (study.DIRECTORY/'evaluation/metrics.json').exists()
        assert status['best_verified_test_correct']==108
    else:
        assert status['best_verified_test_correct']==max(108,audit['new_test_evaluation']['correct'])
    assert status['best_verified_test_accuracy']==status['best_verified_test_correct']/179
    assert status['goal_achieved']==(status['best_verified_test_correct']>=144)
    assert status['domain_aligned_history_proposal']['sha256']==digest(study.PROPOSAL)
    assert status['domain_aligned_history_proposal']['model_study_completed'] and not summary['source_targets_transformed']
    print(json.dumps({'integrity':'passed','completed_studies':51,'completed_configurations':1812,
        'distinct_tests':272,'scoped_evidence_hashes_checked':checked,'native_base_artifact_hashes_checked':len(audit['native_base_cache_artifact_hashes']),
        'actual_independent_joint_network_refits':20,'domain_normalizers_per_refit':6,'actual_source_fitting_targets':2336,
        'reserved_source_targets':312,'retained_test_correct':status['best_verified_test_correct'],
        'retained_test_accuracy':status['best_verified_test_accuracy'],'goal_achieved':status['goal_achieved'],
        'historical_refitting_performed':False}),flush=True)


if __name__=='__main__':
    validate()
