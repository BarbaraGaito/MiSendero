"""Read-only scoped evidence; no historical refits or repeated native test."""
import ast
import json
from pathlib import Path
import fatigue_observed_change_factorization as study
from public_sources import digest


def validate():
    status = json.loads((study.DOCS/'current-research-status.json').read_text())
    assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed'])==(53,1858,282)
    assert status['goal_status']=='active' and 'running_study' not in status
    assert (status['original_training_cases'],status['original_test_cases'],status['required_correct_for_80_percent'])==(487,179,144)
    checked = 0
    for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
        for name,expected in status[field].items():
            assert digest(study.DOCS/name)==expected,(field,name)
            checked += 1
    tree = ast.parse(Path(__file__).with_name('fatigue_80_checkpoint.py').read_text())
    names = next(ast.literal_eval(node.iter) for node in ast.walk(tree) if isinstance(node,ast.For)
        and isinstance(node.target,ast.Name) and node.target.id=='name' and isinstance(node.iter,ast.Tuple)
        and any(isinstance(x,ast.Constant) and x.value==study.DIRECTORY.name for x in node.iter.elts))
    counts = []
    for name in names:
        selection = json.loads((study.DIRECTORY.parent/name/'selection.json').read_text())
        assert selection['status']=='complete',name
        counts.append(len(selection['results']))
    assert len(counts)==53 and sum(counts)==1858
    inputs = study.load_inputs()
    path = study.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    assert selected['status']=='complete' and selected['plan']==study.plan()
    assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
    assert digest(study.DIRECTORY/'selection-source.py')==selected['code_sha256']
    audit_path = study.DOCS/'observed-change-factorization-verification.json'
    audit = json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(path)
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_observed_change_factorization.py'))
    assert audit['previous_verification_sha256']==digest(study.PARENT_AUDIT)
    assert audit['all_10_oof_recipes_recomputed'] and audit['all_40_fold_artifacts_recomputed']
    assert audit['actual_original_targets_and_subset_preprocessing_verified'] and audit['original_negative_changes_preserved']
    assert audit['synthetic_rows']==0 and audit['current_and_future_labels_excluded'] and audit['original_native_cases_preserved']
    assert len(audit['fold_artifact_hashes'])==80
    for name,expected in audit['fold_artifact_hashes'].items():
        assert digest(study.DIRECTORY/'folds'/name)==expected
    expected_ids = {row['candidate']['id'] for row in [*audit['best_factorized_by_member'].values(),*audit['matched_flat_controls'].values()]}
    winner = max(selected['results'],key=lambda r:r['accuracy_mean'])
    if winner['candidate']['algorithm']=='observed_change_distribution':
        expected_ids.add(winner['candidate']['id'])
    assert audit['independent_candidate_fold_refits']==len(audit['actual_refit_calls'])==5*len(expected_ids)
    assert {row['candidate_id'] for row in audit['actual_refit_calls']}==expected_ids
    assert {(row['candidate_id'],row['fold']) for row in audit['actual_refit_calls']}=={(key,n) for key in expected_ids for n in range(5)}
    assert audit['input_only_artifact_reloads']==audit['independent_candidate_fold_refits']
    assert audit['independent_stage_estimator_refits']==sum(len(row['actual_stage_target_calls']) for row in audit['actual_refit_calls'])
    for row in audit['actual_refit_calls']:
        assert row['actual_input_rows_and_targets_independently_observed'] and row['fitting_people_only'] and row['reload_without_current_truth_or_ids']
    gate_path = study.DOCS/'observed-change-factorization-test-gate.json'
    assert audit['test_gate_sha256']==digest(gate_path)
    gate = json.loads(gate_path.read_text())
    assert gate['selection_sha256']==digest(path) and gate['gate_passed']==audit['new_test_gate_passed']
    assert gate['evaluator_code_sha256']==digest(Path(__file__).with_name('evaluate_fatigue_observed_change_factorization.py'))
    assert gate['pretest_verifier_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_observed_change_factorization.py'))
    test = audit['new_test_evaluation']
    if test:
        assert test==gate['new_test_evaluation'] and test['test_cases']==179
        assert digest(study.DIRECTORY/'evaluation/model.joblib')==test['model_sha256']
        assert status['best_verified_test_correct']==max(108,test['test_correct'])
        assert gate['pretest_winner_fold_artifacts_verified']==5 and audit['independent_full_test_refit_stage_calls']
    else:
        assert not gate['gate_passed'] and not (study.DIRECTORY/'evaluation').exists()
        assert status['best_verified_test_correct']==108
        assert gate['pretest_winner_fold_artifacts_verified']==0 and not audit['independent_full_test_refit_stage_calls']
    summary = json.loads((study.DOCS/'observed-change-factorization.json').read_text())
    assert summary['selection_sha256']==digest(path) and summary['verification_sha256']==digest(audit_path)
    assert summary['real_tests_code_sha256']==digest(Path(__file__).with_name('test_fatigue_observed_change_factorization.py'))
    tests_path = study.DOCS/'observed-change-factorization-tests.log'
    assert summary['real_tests_log_sha256']==digest(tests_path)
    assert 'Ran 5 tests' in tests_path.read_text() and 'OK' in tests_path.read_text()
    assert status['best_verified_test_accuracy']==status['best_verified_test_correct']/179
    assert status['goal_achieved']==(status['best_verified_test_correct']>=144)
    assert status['observed_change_factorization_proposal']['sha256']==digest(study.PROPOSAL)
    assert status['observed_change_factorization_proposal']['model_study_completed']
    diagnostic_path = study.DOCS/'observed-change-stage-diagnostic.json'
    assert status['observed_change_stage_diagnostic']['sha256']==summary['stage_diagnostic_sha256']==digest(diagnostic_path)
    diagnostic = json.loads(diagnostic_path.read_text())
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_observed_change_stages.py'))
    assert diagnostic['selection_sha256']==digest(path) and diagnostic['new_test_predictions_computed']==0
    assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_preprocessor_fits']==0
    for name,expected in diagnostic['fold_model_hashes'].items():
        assert audit['fold_artifact_hashes'][name]==expected
    source_review_path = study.DOCS/'public-observed-change-support-review.json'
    assert status['public_observed_change_support_review']['sha256']==summary['source_change_support_review_sha256']==digest(source_review_path)
    source_review = json.loads(source_review_path.read_text())
    assert source_review['review_code_sha256']==digest(Path(__file__).with_name('review_public_observed_change_support.py'))
    assert source_review['native_stage_diagnostic_sha256']==digest(diagnostic_path)
    import fatigue_shoulder_history_inputs as source
    assert source_review['source_provenance_sha256']==digest(source.DIRECTORY/'provenance.json')
    assert source_review['source_input_audit_sha256']==digest(study.DOCS/'shoulder-history-input-verification.json')
    for domain,frame in inputs['source'].groupby('source_domain'):
        equal = frame[source.TARGETS[domain]].eq(frame[source.PRIOR])
        reported = source_review['source_domains'][domain]
        assert reported['actually_equal_current_and_prior_reports']==int(equal.sum())
        assert reported['actually_different_current_and_prior_reports']==int((~equal).sum())
        assert reported['both_classes_available_for_binary_discrimination']==bool(equal.any() and (~equal).any())
    initial = source_review['initial_unfitted_preflight_correction']
    assert initial['original_source_sha256']==digest(study.DOCS/'public-observed-change-support-review-initial-source.py')
    assert initial['original_failure_log_sha256']==digest(study.DOCS/'public-observed-change-support-review-initial-two-class-assumption.log')
    assert source_review['new_predictive_estimator_fits']==source_review['new_test_predictions_computed']==0
    print(json.dumps({'integrity':'passed','completed_studies':53,'completed_configurations':1858,'distinct_tests':282,
        'scoped_evidence_hashes_checked':checked,'new_fold_artifact_hashes_checked':80,
        'independent_candidate_fold_refits':audit['independent_candidate_fold_refits'],
        'independent_stage_estimator_refits':audit['independent_stage_estimator_refits'],
        'retained_test_correct':status['best_verified_test_correct'],'retained_test_accuracy':status['best_verified_test_accuracy'],
        'goal_achieved':status['goal_achieved'],'historical_refitting_performed':False}),flush=True)


if __name__=='__main__':
    validate()
