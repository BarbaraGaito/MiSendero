"""Read-only current native and expanded public-source evidence checkpoint."""
import json
from pathlib import Path
import check_cadence_ordered_residual_checkpoint_integrity as native_checkpoint
import rpe_expanded_binary_history_inputs as combined
from public_sources import digest


def validate():
    native_checkpoint.validate()
    status = json.loads((combined.DOCS/'current-research-status.json').read_text())
    summary = json.loads((combined.DOCS/'rpe-expanded-binary-history.json').read_text())
    fitting,reserved,manifest = combined.load()
    gait_pairs,gait_reports,gait_manifest = combined.gait.load()
    gait_audit_path = combined.AUDITS['gait_forecasting']
    union_audit_path = combined.DOCS/'rpe-expanded-binary-history-input-verification.json'
    gait_audit,union_audit = [json.loads(path.read_text()) for path in (gait_audit_path,union_audit_path)]
    assert gait_audit['verification']==union_audit['verification']=='passed'
    assert gait_audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_rpe_forecasting_history_inputs.py'))
    assert union_audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_rpe_expanded_binary_history_inputs.py'))
    assert gait_audit['preparation_code_sha256']==digest(Path(combined.gait.__file__))
    assert union_audit['preparation_code_sha256']==digest(Path(combined.__file__))
    assert gait_audit['provenance_sha256']==digest(combined.gait.DIRECTORY/'provenance.json')
    assert gait_audit['pairs_sha256']==digest(combined.gait.DIRECTORY/'pairs.csv')
    assert gait_audit['reports_sha256']==digest(combined.gait.DIRECTORY/'reports.csv')
    assert union_audit['provenance_sha256']==summary['combined_provenance_sha256']==digest(combined.DIRECTORY/'provenance.json')
    assert union_audit['dataset_sha256']==digest(combined.DIRECTORY/'dataset.csv')
    assert summary['source_raw_input_verification_sha256']==digest(gait_audit_path)
    assert summary['combined_input_verification_sha256']==digest(union_audit_path)
    for name,value in gait_audit['original_source_artifact_hashes'].items():
        assert digest(combined.gait.RAW/'workbooks'/name)==value
    assert len(gait_audit['original_source_artifact_hashes'])==38
    assert {path.name for path in (combined.gait.RAW/'workbooks').glob('*.xlsx')}=={
        f'ID{person}GaitFeatures.xlsx' for person in gait_manifest['source_file_summaries'] for person in [person['person']]}
    assert all(digest(combined.AUDITS[name])==value for name,value in union_audit['parent_input_verifications_sha256'].items())
    assert len(gait_reports)==434 and gait_reports.current_rpe.notna().sum()==432
    assert len(gait_pairs)==410 and gait_pairs.second.notna().sum()==388
    assert len(fitting)==3548 and len(reserved)==518 and fitting.second.notna().sum()==3042
    assert fitting.groupby('source_domain').size().to_dict()==combined.COUNTS
    assert fitting.current_rpe.eq(fitting.prior).sum()==1354 and fitting.current_rpe.ne(fitting.prior).sum()==2194
    assert summary['new_predictive_estimator_fits']==summary['new_test_predictions_computed']==0
    assert not summary['model_comparison_predeclared'] and not summary['native_target_merge_approved']
    assert not manifest['source_instrument_scales_converted'] and manifest['source_specific_binary_heads_required']
    assert manifest['synthetic_rows']==manifest['synthetic_targets']==0
    assert status['rpe_forecasting_candidate']['original_workbooks_verified']==19
    assert status['rpe_forecasting_candidate']['source_binary_head_eligibility_approved']
    assert not status['rpe_forecasting_candidate']['native_target_merge_approved']
    assert status['expanded_public_binary_histories']['verification_sha256']==digest(union_audit_path)
    assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed'])==(60,1956,322)
    assert status['best_verified_test_correct']==108 and status['required_correct_for_80_percent']==144
    assert status['goal_status']=='active' and not status['goal_achieved']
    print(json.dumps({'integrity':'passed','original_workbooks_and_receipts_verified':38,
        'source_original_trial_reports':434,'source_unambiguous_reports':432,'new_actual_gait_pairs':410,
        'combined_actual_auxiliary_fitting_pairs':3548,'actual_second_priors':3042,'stored_reserved_pairs':518,
        'reserved_gait_workbooks_received':0,'model_studies_completed':60,'completed_model_configurations':1956,
        'distinct_tests_passed':322,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
        'retained_test_correct':108,'retained_test_accuracy':108/179,'goal_achieved':False}),flush=True)


if __name__=='__main__':
    validate()
