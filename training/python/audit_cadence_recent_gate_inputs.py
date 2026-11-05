"""Independently compare all native cells/clocks with verified measured HR."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import cadence_recent_gate_inputs as prepared
import cadence_association_inputs as recent
from public_sources import digest


def verify():
    proof = json.loads(prepared.EXISTING_AUDIT.read_text())
    assert proof['verification']=='passed' and proof['native_pulse_at_query_completed_by_query']
    assert proof['native_provenance_sha256']==digest(recent.NATIVE_DIRECTORY/'provenance.json')
    assert proof['native_dataset_sha256']==digest(recent.NATIVE_DIRECTORY/'dataset.csv')
    assert proof['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_association_inputs.py'))
    raw = pd.read_csv(recent.NATIVE_DIRECTORY/'dataset.csv')
    original = json.loads((recent.NATIVE_DIRECTORY/'provenance.json').read_text())
    output,manifest = prepared.load()
    pd.testing.assert_frame_equal(output[['row_key','group_key']],raw[['row_key','group_key']])
    current,prior = raw.current_hr_bpm.to_numpy(),raw.prior_hr_bpm.to_numpy()
    expected = np.column_stack([current,np.subtract(current,prior),np.divide(current,prior)])
    np.testing.assert_allclose(output[prepared.COLUMNS],expected,atol=1e-12,equal_nan=True)
    assert np.isnan(expected).sum(axis=0).tolist()==[0,3,3] and not np.isinf(expected).any()
    assert manifest['lineage']==original['lineage'] and len(original['lineage'])==666
    lines = {line['row_key']:line for line in original['lineage']}
    for row in raw.itertuples():
        line = lines[row.row_key]
        assert row.group_key==line['group_key']
        query = pd.Timestamp(line['prediction_time_us'],unit='us',tz='UTC')
        assert pd.Timestamp(line['current_hr_minute_end'])<=query
        if line['lag_hr_minute_end'] is not None:
            assert pd.Timestamp(line['lag_hr_minute_end'])<=pd.Timestamp(line['prior_report_time_us'],unit='us',tz='UTC')
        else:
            assert np.isnan(row.prior_hr_bpm)
    assert not set(output)&{'label','current_rpe','rpe_native','prior_borg','prior2_borg'}
    report = {'verification':'passed','audit_code_sha256':digest(Path(__file__)),
        'preparation_code_sha256':digest(Path(prepared.__file__)),
        'provenance_sha256':digest(prepared.DIRECTORY/'provenance.json'),
        'native_dataset_sha256':digest(prepared.DIRECTORY/'native.csv'),
        'existing_raw_input_verification_sha256':digest(prepared.EXISTING_AUDIT),
        'native_cells_independently_rebuilt':666,'native_clocks_verified':666,
        'native_inputs_only':True,'current_hr_before_query':True,'prior_hr_before_genuine_report':True,
        'source_current_hr_used':False,'source_context_fabricated':False,'synthetic_values':0,
        'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}
    path = prepared.DOCS/'cadence-recent-gate-input-verification.json'
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    verify()
