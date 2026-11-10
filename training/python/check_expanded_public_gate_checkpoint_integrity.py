"""Read-only evidence for study61; never refit historical model studies."""
import ast
import json
from pathlib import Path
import pandas as pd
import fatigue_expanded_public_gate as study
from public_sources import digest,OUTPUT,verify_source_snapshot


def evidence():
    inputs=study.load_inputs()
    selected_path=study.DIRECTORY/'selection.json'
    selected=json.loads(selected_path.read_text())
    assert selected['status']=='complete' and len(selected['results'])==24 and selected['plan']==study.plan()
    assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
    assert digest(study.DIRECTORY/'selection-source.py')==digest(Path(study.__file__))
    audit_path=study.DOCS/'expanded-public-gate-verification.json'
    audit=json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selected_path)
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_expanded_public_gate.py'))
    assert audit['previous_verification_sha256']==digest(study.PARENT_AUDIT) and audit['proposal_sha256']==digest(study.PROPOSAL)
    assert audit['all_24_oof_recipes_recomputed'] and audit['all_80_fold_artifacts_recomputed']
    assert audit['independent_joint_refits']==len(audit['native_joint_refits'])==80
    assert audit['prior_inner_native_models_independently_verified']==30
    assert audit['new_native_base_fits']==audit['synthetic_rows']==0
    assert audit['source_fitting_actual_pairs']==3548 and audit['source_reserved_pairs_not_fitted']==518
    assert audit['gait_reserved_people_not_received']==5 and audit['original_native_cases_preserved']
    by_id={c['id']:c for c in study.plan()[8:]}
    for row in audit['native_joint_refits']:
        c=by_id[row['candidate_id']]
        active=sum(w>0 for w in study.source_weights(c).values())
        assert row['actual_native_target_steps']==row['actual_losses_independently_checked']==row['actual_total_backward_calls']==80
        assert row['actual_source_target_steps']==80*active
        assert row['actual_new_gait_target_steps']==(80 if c['gait_weight'] else 0)
        assert (row['actual_new_gait_encoder_gradient']>0)==bool(c['gait_weight'])
        for name in ('initial_parameters_verified','native_joint_nll_gradient_equivalence_verified',
                     'source_weights_independently_verified','inactive_source_labels_excluded',
                     'source_context_not_fabricated','source_targets_from_original_pairs',
                     'base_weights_frozen','nonzero_delta_ratios_frozen','input_only_reload_verified'):
            assert row[name],name
    for field,folder,count in (('fold_artifact_hashes',study.DIRECTORY/'folds',160),
        ('native_base_cache_artifact_hashes',study.native.DIRECTORY/'bases',20)):
        assert len(audit[field])==count
        assert all(digest(folder/name)==value for name,value in audit[field].items())
    gate_path=study.DOCS/'expanded-public-gate-test-gate.json'
    gate=json.loads(gate_path.read_text())
    assert audit['test_gate_sha256']==digest(gate_path) and gate['selection_sha256']==digest(selected_path)
    assert gate['evaluator_code_sha256']==digest(Path(__file__).with_name('evaluate_fatigue_expanded_public_gate.py'))
    assert gate['pretest_verifier_code_sha256']==audit['verification_code_sha256']
    assert gate['gate_passed']==audit['new_test_gate_passed']
    if gate['gate_passed']:
        assert gate['new_test_evaluation']==audit['new_test_evaluation'] and audit['independent_full_test_artifact_audit']
        result=gate['new_test_evaluation']
        assert result['test_cases']==179 and result['frozen_artifact_reloaded_before_test']
        assert digest(study.DIRECTORY/'evaluation/model.joblib')==result['model_sha256']
    else:
        assert gate['new_test_evaluation'] is None and audit['new_test_evaluation'] is None
        assert audit['independent_full_test_artifact_audit'] is None and not (study.DIRECTORY/'evaluation').exists()
    verify_source_snapshot('fatigue')
    original=pd.read_csv(OUTPUT/'fatigue/dataset.csv',dtype={'label':str})
    lineage=json.loads((OUTPUT/'fatigue/provenance.json').read_text())['lineage']
    assert len(original)==len(inputs['frame'])==666
    assert inputs['train'].row_key.tolist()==selected['train_row_keys']
    assert inputs['frame'].row_key.tolist()==[r['row_key'] for r in lineage]
    assert inputs['frame'].group_key.tolist()==[r['group_key'] for r in lineage]
    assert inputs['frame'].label.tolist()==original.label.tolist()
    assert (len(inputs['train']),len(inputs['test']),len(inputs['gate_source']),len(inputs['reserved_gate_source']))==(487,179,3548,518)
    assert set(inputs['train'].group_key).isdisjoint(inputs['test'].group_key)
    assert inputs['gate_source'].groupby('source_domain').size().to_dict()==study.COUNTS
    assert inputs['gate_source'].second.notna().sum()==3042
    source_audit=json.loads(study.INPUT_AUDIT.read_text())
    gait_audit_path=study.prepared.AUDITS['gait_forecasting']
    gait_audit=json.loads(gait_audit_path.read_text())
    assert source_audit['verification']==gait_audit['verification']=='passed'
    assert len(gait_audit['original_source_artifact_hashes'])==38
    assert all(digest(study.prepared.gait.RAW/'workbooks'/name)==value for name,value in gait_audit['original_source_artifact_hashes'].items())
    assert all(digest(study.prepared.AUDITS[name])==value for name,value in source_audit['parent_input_verifications_sha256'].items())
    preparation=json.loads((study.DOCS/'expanded-public-gate-verifier-preparation.json').read_text())
    assert preparation['preparation_code_sha256']==digest(Path(__file__).with_name('prepare_expanded_public_gate_verifiers.py'))
    assert all(digest(Path(__file__).with_name(name))==value for name,value in {**preparation['frozen_sources_sha256'],**preparation['derived_files_sha256']}.items())
    tests_path=study.DOCS/'expanded-public-gate-tests.log'
    tests=tests_path.read_text()
    assert 'Ran 7 tests' in tests and 'OK' in tests and 'FAILED' not in tests and 'skipped' not in tests
    diagnostic_path=study.DOCS/'expanded-public-gate-diagnostic.json'
    diagnostic=json.loads(diagnostic_path.read_text())
    assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(selected_path)
    assert diagnostic['verification_sha256']==digest(audit_path)
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_expanded_public_gate.py'))
    assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_test_predictions_computed']==0
    assert not diagnostic['test_labels_inspected'] and len(diagnostic['all_16_gate_loss_comparisons'])==16
    assert len(diagnostic['all_80_fold_loss_comparisons'])==80
    return inputs,selected,audit,diagnostic


def validate():
    inputs,selected,audit,diagnostic=evidence()
    status=json.loads((study.DOCS/'current-research-status.json').read_text())
    assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed'])==(61,1980,329)
    assert status['goal_status']=='active' and 'running_study' not in status
    assert (status['original_training_cases'],status['original_test_cases'],status['required_correct_for_80_percent'])==(487,179,144)
    checked=0
    for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
        for name,value in status[field].items():
            assert digest(study.DOCS/name)==value,(field,name)
            checked+=1
    tree=ast.parse(Path(__file__).with_name('fatigue_80_checkpoint.py').read_text())
    names=next(ast.literal_eval(node.iter) for node in ast.walk(tree) if isinstance(node,ast.For)
        and isinstance(node.target,ast.Name) and node.target.id=='name' and isinstance(node.iter,ast.Tuple)
        and any(isinstance(item,ast.Constant) and item.value==study.DIRECTORY.name for item in node.iter.elts))
    counts=[]
    for name in names:
        historical=json.loads((study.DIRECTORY.parent/name/'selection.json').read_text())
        assert historical['status']=='complete',name
        counts.append(len(historical['results']))
    assert len(counts)==61 and sum(counts)==1980
    summary=json.loads((study.DOCS/'expanded-public-gate.json').read_text())
    assert summary['selection_sha256']==digest(study.DIRECTORY/'selection.json')
    assert summary['verification_sha256']==digest(study.DOCS/'expanded-public-gate-verification.json')
    assert summary['input_verification_sha256']==digest(study.INPUT_AUDIT)
    assert summary['error_diagnostic_sha256']==digest(study.DOCS/'expanded-public-gate-diagnostic.json')
    assert summary['real_tests_code_sha256']==digest(Path(__file__).with_name('test_fatigue_expanded_public_gate.py'))
    assert summary['real_tests_log_sha256']==digest(study.DOCS/'expanded-public-gate-tests.log')
    assert status['expanded_public_gate_proposal']['sha256']==digest(study.PROPOSAL)
    assert status['expanded_public_gate_proposal']['model_study_completed']
    if 'expanded_public_gate_geometry_review' in status:
        entry=status['expanded_public_gate_geometry_review']
        review_path=study.DOCS/entry['document']
        review=json.loads(review_path.read_text())
        assert entry['sha256']==digest(review_path) and review['review']=='passed'
        assert review['review_code_sha256']==digest(Path(__file__).with_name('review_expanded_gate_geometry.py'))
        assert review['selection_sha256']==digest(study.DIRECTORY/'selection.json')
        assert review['verification_sha256']==digest(study.DOCS/'expanded-public-gate-verification.json')
        assert review['diagnostic_sha256']==summary['error_diagnostic_sha256']
        assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0
        assert not review['test_labels_inspected'] and not review['model_comparison_predeclared']
        assert review['conditional_geometry_not_passed_to_current_corrector']
        assert len(review['proposed_native_private_geometry'])==6
        assert len(review['reviewed_fold_artifact_hashes'])==10
        assert all(digest(study.DIRECTORY/'folds'/name)==value for name,value in review['reviewed_fold_artifact_hashes'].items())
    result=audit['new_test_evaluation']
    assert status['best_verified_test_correct']==max(108,result['test_correct'] if result else 0)
    assert status['best_verified_test_accuracy']==status['best_verified_test_correct']/179
    assert status['goal_achieved']==(status['best_verified_test_correct']>=144)
    print(json.dumps({'integrity':'passed','completed_studies':61,'completed_configurations':1980,'distinct_tests':329,
        'scoped_evidence_hashes_checked':checked,'new_fold_artifact_hashes_checked':160,'native_base_cache_artifact_hashes_checked':20,
        'independent_joint_refits':80,'source_fitting_pairs':3548,'original_workbooks_and_receipts_verified':38,
        'additional_geometry_review_verified':'expanded_public_gate_geometry_review' in status,
        'original_native_cases_preserved':666,'retained_test_correct':status['best_verified_test_correct'],
        'retained_test_accuracy':status['best_verified_test_accuracy'],'goal_achieved':status['goal_achieved'],
        'historical_refitting_performed':False}),flush=True)


if __name__=='__main__':
    validate()
