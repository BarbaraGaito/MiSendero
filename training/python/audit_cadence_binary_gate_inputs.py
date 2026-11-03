"""Independent original-cell and causal native-clock checks for the new adapter."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import cadence_binary_gate_inputs as prepared
import cadence_lagged_rpe as original
import fatigue_cadence_native_inputs as physiology
from fatigue_dynamics import load_inputs
from public_sources import digest


def validate():
    fitting,reserved,native,manifest = prepared.load()
    old_fit,old_reserved,old_manifest = original.load()
    old = pd.concat([old_fit,old_reserved]).set_index('row_key')
    raw = pd.read_csv(original.DATA)
    stages = raw.Stage.str.removeprefix('T').astype(int)
    lookup = {(int(raw.iloc[n].ID),int(stage)):n for n,stage in enumerate(stages)}
    source = pd.concat([fitting,reserved])
    by_key = source.set_index('row_key')
    count,seconds = 0,0
    for line in old_manifest['lineage']:
        current,prior = raw.iloc[line['original_current_row']],raw.iloc[line['original_previous_row']]
        row = by_key.loc[line['row_key']]
        assert row.group_key==line['group_key'] and row.source_partition==line['source_partition']
        assert row.current_rpe==current.RPE and row.prior==prior.RPE
        assert current.ID==prior.ID and stages.iloc[line['original_current_row']]==stages.iloc[line['original_previous_row']]+1
        assert pd.isna(prior.TermCode)
        older_index = lookup.get((int(current.ID),int(stages.iloc[line['original_current_row']])-2))
        if older_index is None:
            assert pd.isna(row.second)
        else:
            assert row.second==raw.iloc[older_index].RPE
            seconds += int(row.source_partition=='fitting')
        assert row.lag_hr_bpm==prior.HR_bpm and row.baseline_hr_bpm==prior.RestHR_bpm
        np.testing.assert_allclose([row.hr_delta_baseline,row.hr_ratio_baseline],
            [prior.HR_bpm-prior.RestHR_bpm,prior.HR_bpm/prior.RestHR_bpm],atol=1e-12)
        assert row.current_rpe==old.loc[row.name,'rpe_native'] and row.prior==old.loc[row.name,'prior_rpe_native']
        count += 1
    assert count==1057 and seconds==727
    assert fitting.current_rpe.eq(fitting.prior).sum()==299 and fitting.current_rpe.ne(fitting.prior).sum()==552
    assert fitting.current_rpe.lt(fitting.prior).sum()==4
    old_native,native_manifest = physiology.load()
    expected = old_native[['row_key','group_key',*physiology.FEATURES]].rename(columns=prepared.NATIVE_COLUMNS)
    pd.testing.assert_frame_equal(native,expected,check_dtype=False,rtol=0,atol=1e-12)
    frame,train,test,_,_ = load_inputs()
    assert native.row_key.tolist()==frame.row_key.tolist() and (len(train),len(test))==(487,179)
    clocks = 0
    for line in native_manifest['lineage']:
        if line['lag_hr_minute_end'] is not None:
            assert pd.Timestamp(line['lag_hr_minute_end'])<=pd.Timestamp(line['prior_report_time_us'],unit='us',tz='UTC')
        if line['latest_baseline_minute_end'] is not None:
            assert pd.Timestamp(line['latest_baseline_minute_end'])<=pd.Timestamp(line['task_start_us'],unit='us',tz='UTC')
        clocks += 1
    assert clocks==666
    report = {'verification':'passed','audit_code_sha256':digest(Path(__file__)),
        'preparation_code_sha256':digest(Path(prepared.__file__)),
        'provenance_sha256':digest(prepared.DIRECTORY/'provenance.json'),
        'source_dataset_sha256':digest(prepared.DIRECTORY/'source.csv'),'native_dataset_sha256':digest(prepared.DIRECTORY/'native.csv'),
        'actual_source_pairs_independently_rebuilt':count,'source_fitting_pairs':851,'source_reserved_pairs':206,
        'source_fitting_actual_second_priors':727,'source_fitting_equal_pairs':299,'source_fitting_unequal_pairs':552,
        'source_fitting_decreases_preserved':4,'native_original_cases_verified':666,'native_clocks_verified':clocks,
        'original_native_fit_cases':487,'original_native_test_cases':179,'source_current_bout_hr_used':False,
        'source_exact_clocks_or_ages_assumed':False,'source_native_borg_labels_pooled':False,
        'missing_inputs_preserved':True,'synthetic_rows':0,'new_predictive_estimator_fits':0}
    (prepared.DOCS/'cadence-binary-gate-input-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    validate()
