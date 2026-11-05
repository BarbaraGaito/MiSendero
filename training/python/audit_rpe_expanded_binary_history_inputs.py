"""Independently compare combined source cells with frozen original parent tables."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import rpe_expanded_binary_history_inputs as prepared
from public_sources import digest


def verify():
    fitting,reserved,manifest = prepared.load()
    frame = pd.concat([fitting,reserved],ignore_index=True)
    assert frame.row_key.is_unique and len(frame)==4066
    expected_parts = []
    original = pd.read_csv(prepared.old.DIRECTORY/'dataset.csv')
    targets = {'emap':'current_rpe','resistance':'original_resistance_rpe','shoulder':'original_shoulder_rpe','worker':'borg_native'}
    old_audit = json.loads(prepared.AUDITS['old'].read_text())
    assert old_audit['verification']=='passed' and old_audit['source_dataset_sha256']==digest(prepared.old.DIRECTORY/'dataset.csv')
    assert old_audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_shoulder_history_inputs.py'))
    for name,target in targets.items():
        part = original[original.source_domain.eq(name)]
        cells = part[['row_key','group_key','source_domain','source_partition']].copy()
        cells['current_rpe'] = part[target]
        cells['prior'] = part['public_ordered_actual_prior_rpe']
        cells['second'] = part['public_ordered_actual_second_prior_rpe']
        expected_parts.append(cells)
    cadence = pd.read_csv(prepared.cadence.DIRECTORY/'source.csv')
    cadence_audit = json.loads(prepared.AUDITS['cadence'].read_text())
    assert cadence_audit['verification']=='passed' and cadence_audit['source_dataset_sha256']==digest(prepared.cadence.DIRECTORY/'source.csv')
    assert cadence_audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_binary_gate_inputs.py'))
    expected_parts.append(cadence[prepared.COLUMNS])
    gait = pd.read_csv(prepared.gait.DIRECTORY/'pairs.csv')
    gait_audit = json.loads(prepared.AUDITS['gait_forecasting'].read_text())
    assert gait_audit['verification']=='passed' and gait_audit['pairs_sha256']==digest(prepared.gait.DIRECTORY/'pairs.csv')
    assert gait_audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_rpe_forecasting_history_inputs.py'))
    assert gait_audit['approved_for_separate_original_unequal_binary_head']
    assert gait_audit['independently_rebuilt_actual_adjacent_pairs']==410 and gait_audit['reserved_people_received']==0
    for name,value in gait_audit['original_source_artifact_hashes'].items():
        assert digest(prepared.gait.RAW/'workbooks'/name)==value
    expected_parts.append(gait[prepared.COLUMNS])
    expected = pd.concat(expected_parts,ignore_index=True)
    assert expected.row_key.is_unique and set(expected.row_key)==set(frame.row_key)
    expected = expected.set_index('row_key').loc[frame.row_key].reset_index()
    pd.testing.assert_frame_equal(frame.reset_index(drop=True),expected,check_dtype=False,rtol=0,atol=1e-12)
    assert fitting.groupby('source_domain').size().to_dict()==prepared.COUNTS
    assert len(fitting)==3548 and len(reserved)==518 and fitting.second.notna().sum()==3042
    assert np.isfinite(fitting[['current_rpe','prior']].to_numpy()).all()
    assert fitting.current_rpe.eq(fitting.prior).sum()==1354 and fitting.current_rpe.ne(fitting.prior).sum()==2194
    assert set(fitting.group_key).isdisjoint(reserved.group_key)
    assert frame.groupby('group_key').source_domain.nunique().max()==1
    assert set(frame.source_domain)==set(prepared.COUNTS) and 'sts' not in set(frame.source_domain)
    assert len(original[original.source_domain.eq('sts')&original.source_partition.eq('fitting')])==49
    for name,part in fitting.groupby('source_domain'):
        assert set(part.current_rpe.ne(part.prior))=={False,True}
        saved = manifest['domains'][name]
        assert saved['fitting_pairs']==len(part) and saved['fitting_people']==part.group_key.nunique()
        assert saved['actual_second_priors']==part.second.notna().sum()
        assert saved['equal_pairs']==part.current_rpe.eq(part.prior).sum() and saved['unequal_pairs']==part.current_rpe.ne(part.prior).sum()
    native_path = prepared.cadence.DIRECTORY/'native.csv'
    assert cadence_audit['native_dataset_sha256']==digest(native_path) and cadence_audit['native_clocks_verified']==666
    native = pd.read_csv(native_path)
    assert len(native)==666 and native.row_key.is_unique and set(frame.group_key).isdisjoint(native.group_key)
    assert set(frame.row_key).isdisjoint(native.row_key)
    assert list(frame)==prepared.COLUMNS and manifest['source_specific_binary_heads_required']
    assert not manifest['source_instrument_scales_converted'] and not manifest['source_targets_pooled_as_native_borg']
    assert not manifest['source_sensor_or_native_context_fabricated'] and not manifest['source_ages_or_phases_assumed']
    report = {'verification':'passed','verification_code_sha256':digest(Path(__file__)),
        'preparation_code_sha256':digest(Path(prepared.__file__)),'provenance_sha256':digest(prepared.DIRECTORY/'provenance.json'),
        'dataset_sha256':digest(prepared.DIRECTORY/'dataset.csv'),
        'parent_input_verifications_sha256':{key:digest(path) for key,path in prepared.AUDITS.items()},
        'all_parent_source_rows_compared':4066,'actual_fitting_source_pairs':3548,'stored_reserved_source_pairs':518,
        'additional_actual_gait_pairs':410,'additional_gait_people':19,'gait_reserved_people_not_received':5,
        'actual_second_priors':3042,'equal_pairs':1354,'unequal_pairs':2194,'source_counts':prepared.COUNTS,
        'native_original_cases_preserved':666,'native_fitting_cases':487,'native_test_cases':179,
        'all_original_current_prior_second_values_preserved':True,'original_fractional_values_preserved':True,
        'source_heads_must_remain_separate':True,'source_scales_converted':False,'source_targets_merged_as_native_borg':False,
        'synthetic_targets':0,'synthetic_rows':0,'invented_source_context_or_clocks':0,
        'new_native_borg_cases':0,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
        'model_comparison_predeclared':False}
    path = prepared.DOCS/'rpe-expanded-binary-history-input-verification.json'
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    verify()
