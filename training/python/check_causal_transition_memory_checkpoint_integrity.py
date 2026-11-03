"""Read-only current evidence audit; no historical estimator fits."""
import ast
import json
from pathlib import Path
import fatigue_causal_transition_memory as study
from public_sources import digest


def validate():
    status = json.loads((study.DOCS/'current-research-status.json').read_text())
    assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed'])==(52,1848,277)
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
    assert len(counts)==52 and sum(counts)==1848
    inputs = study.load_inputs()
    selected_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selected_path.read_text())
    assert selected['plan']==study.plan() and selected['status']=='complete'
    assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
    assert digest(study.DIRECTORY/'selection-source.py')==selected['code_sha256']
    audit_path = study.DOCS/'causal-transition-memory-verification.json'
    audit = json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selected_path)
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_causal_transition_memory.py'))
    assert audit['previous_verification_sha256']==digest(study.PARENT_AUDIT)
    assert audit['independent_preprocessor_refits']==audit['independent_fold_comparisons']==170
    assert audit['all_36_oof_recipes_recomputed'] and audit['memory_free_population_artifact_reloads']==20
    assert audit['actual_metadata_independently_resolved'] and audit['current_and_future_labels_excluded']
    assert audit['preprocessing_fit_people_only'] and audit['original_native_cases_preserved']
    assert audit['synthetic_rows']==audit['new_native_base_fits']==0 and len(audit['fold_audits'])==10
    for fold in audit['fold_audits']:
        assert fold['recipes_independently_recomputed']==17 and fold['query_labels_excluded_from_inference']
        assert fold['support_times_and_actual_labels_verified'] and fold['base_weights_unchanged']
    for name,expected in audit['native_base_cache_artifact_hashes'].items():
        assert digest(study.native.DIRECTORY/'bases'/name)==expected
    gate_path = study.DOCS/'causal-transition-memory-test-gate.json'
    assert audit['test_gate_sha256']==digest(gate_path)
    gate = json.loads(gate_path.read_text())
    assert gate['selection_sha256']==digest(selected_path)
    assert gate['evaluator_code_sha256']==digest(Path(__file__).with_name('evaluate_fatigue_causal_transition_memory.py'))
    assert gate['gate_passed']==audit['new_test_gate_passed']
    if not gate['gate_passed']:
        assert audit['new_test_evaluation'] is None and not (study.DIRECTORY/'evaluation').exists()
        assert status['best_verified_test_correct']==108
    else:
        assert status['best_verified_test_correct']==max(108,audit['new_test_evaluation']['test_correct'])
    summary = json.loads((study.DOCS/'causal-transition-memory.json').read_text())
    assert summary['selection_sha256']==digest(selected_path) and summary['verification_sha256']==digest(audit_path)
    assert summary['real_tests_code_sha256']==digest(Path(__file__).with_name('test_fatigue_causal_transition_memory.py'))
    tests_path = study.DOCS/'causal-transition-memory-tests.log'
    assert summary['real_tests_log_sha256']==digest(tests_path)
    assert 'Ran 5 tests' in tests_path.read_text() and 'OK' in tests_path.read_text()
    assert status['best_verified_test_accuracy']==status['best_verified_test_correct']/179
    assert status['goal_achieved']==(status['best_verified_test_correct']>=144)
    assert status['causal_transition_memory_proposal']['sha256']==digest(study.PROPOSAL)
    assert status['causal_transition_memory_proposal']['model_study_completed']
    diagnostic_path = study.DOCS/'causal-transition-memory-error-diagnostic.json'
    assert status['causal_transition_memory_error_diagnostic']['sha256']==digest(diagnostic_path)
    diagnostic = json.loads(diagnostic_path.read_text())
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_causal_transition_memory_errors.py'))
    assert diagnostic['selection_sha256']==digest(selected_path) and diagnostic['new_test_predictions_computed']==0
    assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_preprocessor_fits']==0
    review_path = study.DOCS/'native-change-factorization-review.json'
    assert status['native_change_factorization_review']['sha256']==digest(review_path)
    review = json.loads(review_path.read_text())
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_native_change_factorization.py'))
    assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0
    assert all(digest(Path(__file__).with_name(name))==r['sha256'] for name,r in review['prior_code_review'].items())
    assert (len(inputs['source']),len(inputs['reserved_source']))==(2336,312)
    print(json.dumps({'integrity':'passed','completed_studies':52,'completed_configurations':1848,'distinct_tests':277,
        'scoped_evidence_hashes_checked':checked,'native_base_artifact_hashes_checked':len(audit['native_base_cache_artifact_hashes']),
        'independent_preprocessor_refits':170,'independent_recipe_fold_recomputations':170,
        'memory_free_population_artifact_reloads':20,'retained_test_correct':status['best_verified_test_correct'],
        'retained_test_accuracy':status['best_verified_test_accuracy'],'goal_achieved':status['goal_achieved'],
        'historical_refitting_performed':False}),flush=True)


if __name__=='__main__':
    validate()
