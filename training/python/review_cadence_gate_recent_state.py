"""Paired fitting-only gate errors and genuine recent native-HR availability."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import cadence_association_inputs as recent
import fatigue_cadence_binary_gate as study
from public_sources import digest


def review():
    inputs = study.load_inputs()
    selected_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selected_path.read_text())
    audit_path = study.DOCS/'cadence-binary-gate-verification.json'
    audit = json.loads(audit_path.read_text())
    assert selected['status']=='complete' and audit['verification']=='passed'
    assert audit['selection_sha256']==digest(selected_path) and audit['all_20_fold_artifacts_recomputed']
    train = inputs['train']
    rows = {row['candidate']['id']:row for row in selected['results']}
    comparisons = {}
    for member,global_id,zero_id,positive_id in [('core','cadence-binary-gate-000','cadence-binary-gate-002','cadence-binary-gate-003'),
            ('cat','cadence-binary-gate-001','cadence-binary-gate-004','cadence-binary-gate-005')]:
        truth = train.label.to_numpy()
        original = np.asarray(rows[global_id]['oof_predictions'])==truth
        measured = np.asarray(rows[zero_id]['oof_predictions'])==truth
        source = np.asarray(rows[positive_id]['oof_predictions'])==truth
        comparisons[member] = {'global_correct':int(original.sum()),'measured_zero_source_correct':int(measured.sum()),
            'source_positive_correct':int(source.sum()),'source_corrected_vs_measured':int((source&~measured).sum()),
            'source_spoiled_vs_measured':int((~source&measured).sum()),'source_corrected_vs_global':int((source&~original).sum()),
            'source_spoiled_vs_global':int((~source&original).sum())}
    _,_,cache,manifests = recent.load()
    evidence_path = study.DOCS/'cadence-association-input-verification.json'
    evidence = json.loads(evidence_path.read_text())
    assert evidence['verification']=='passed' and evidence['native_pulse_at_query_completed_by_query']
    assert evidence['native_provenance_sha256']==digest(recent.NATIVE_DIRECTORY/'provenance.json')
    assert evidence['native_dataset_sha256']==digest(recent.NATIVE_DIRECTORY/'dataset.csv')
    assert evidence['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_association_inputs.py'))
    matched = cache.set_index('row_key').loc[train.row_key]
    np.testing.assert_array_equal(matched.group_key.to_numpy(),train.group_key.to_numpy())
    np.testing.assert_allclose(matched.prior_hr_bpm,train[study.prepared.NATIVE_COLUMNS['lag_hr_bpm']],atol=1e-12,equal_nan=True)
    lines = {line['row_key']:line for line in manifests['native']['lineage']}
    for key in train.row_key:
        line = lines[key]
        assert line['current_hr_minute_end'] is not None
        assert pd.Timestamp(line['current_hr_minute_end'])<=pd.Timestamp(line['prediction_time_us'],unit='us',tz='UTC')
        if line['lag_hr_minute_end'] is not None:
            assert pd.Timestamp(line['lag_hr_minute_end'])<=pd.Timestamp(line['prior_report_time_us'],unit='us',tz='UTC')
    features = pd.DataFrame({'current_hr_bpm':matched.current_hr_bpm,
        'current_minus_prior_hr_bpm':matched.current_hr_bpm-matched.prior_hr_bpm,
        'current_over_prior_hr_ratio':matched.current_hr_bpm/matched.prior_hr_bpm})
    assert len(features)==487 and features.current_hr_bpm.notna().all()
    assert not np.isinf(features.to_numpy()).any()
    report = {'review':'passed','review_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(selected_path),'verification_sha256':digest(audit_path),
        'native_recent_input_verification_sha256':digest(evidence_path),
        'native_recent_provenance_sha256':digest(recent.NATIVE_DIRECTORY/'provenance.json'),
        'native_recent_dataset_sha256':digest(recent.NATIVE_DIRECTORY/'dataset.csv'),
        'original_fitting_queries':487,'original_fitting_people':28,'paired_oof_comparisons':comparisons,
        'candidate_native_private_features':list(features),'fitting_missing_counts':features.isna().sum().astype(int).to_dict(),
        'current_hr_completed_before_query':True,'prior_hr_completed_before_genuine_prior_report':True,
        'source_current_bout_hr_to_be_introduced':False,'source_private_native_context_to_be_fabricated':False,
        'source_or_native_targets_to_be_rescaled':False,'new_predictive_estimator_fits':0,
        'new_test_predictions_computed':0,'test_labels_inspected':False,'synthetic_rows':0,
        'model_comparison_predeclared':False,
        'interpretation':'The new shared encoder uses actual prior physiology,while its native-private '
            'context remains the old13history/context inputs. Recent native HR and deterministic change '
            'from genuine prior HR are already measured and causally available on fitting queries. '
            'A distinct comparison can add those3native-private inputs,with matched source-zero/source '
            'controls and unchanged shared source inputs/weights. They must not be fabricated for the '
            'source domain. Paired error counts are fitting-participant diagnostics;current-state availability '
            'does not establish improved accuracy. All179original test cases remain outside this review.'}
    path = study.DOCS/'cadence-gate-recent-native-state-review.json'
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    review()
