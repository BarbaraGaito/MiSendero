"""Read-only eligibility review of real CADENCE change pairs and past HR."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import cadence_lagged_rpe as prepared
import fatigue_cadence_native_inputs as native_physiology
import fatigue_change_gate_regularization as previous
from public_sources import digest


def review():
    inputs = previous.load_inputs()
    selection_path = previous.DIRECTORY/'selection.json'
    selected = json.loads(selection_path.read_text())
    audit_path = previous.DOCS/'change-gate-regularization-verification.json'
    audit = json.loads(audit_path.read_text())
    assert selected['status']=='complete' and audit['verification']=='passed'
    assert audit['selection_sha256']==digest(selection_path) and audit['all_60_fold_artifacts_recomputed']
    fitting,reserved,manifest = prepared.load()
    evidence_path = previous.DOCS/'cadence-lagged-input-verification.json'
    evidence = json.loads(evidence_path.read_text())
    assert evidence['verification']=='passed'
    assert evidence['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_lagged_inputs.py'))
    assert evidence['source_provenance_sha256']==digest(prepared.DIRECTORY/'provenance.json')
    assert evidence['source_dataset_sha256']==digest(prepared.DIRECTORY/'dataset.csv')
    assert (len(fitting),len(reserved))==(851,206)
    assert set(fitting.group_key).isdisjoint(reserved.group_key)
    raw = prepared.checked_original()
    lookup = {(int(row.ID),int(row.stage_number)):(index,row) for index,row in raw.iterrows()}
    lineage = {row['row_key']:row for row in manifest['lineage'] if row['source_partition']=='fitting'}
    changed,second,decreasing = [],0,0
    for row in fitting.itertuples():
        original = lineage[row.row_key]
        current = raw.iloc[original['original_current_row']]
        prior = raw.iloc[original['original_previous_row']]
        assert current.ID==prior.ID and int(current.stage_number)==int(prior.stage_number)+1
        assert pd.isna(prior.TermCode) and original['hr_input_row']==original['original_previous_row']
        assert float(row.rpe_native)==float(current.RPE) and float(row.prior_rpe_native)==float(prior.RPE)
        assert float(row.lag_hr_bpm)==float(prior.HR_bpm) and float(row.baseline_hr_bpm)==float(prior.RestHR_bpm)
        assert np.isclose(row.hr_delta_baseline,float(prior.HR_bpm-prior.RestHR_bpm),atol=1e-12)
        assert np.isclose(row.hr_ratio_baseline,float(prior.HR_bpm/prior.RestHR_bpm),atol=1e-12)
        older = lookup.get((int(current.ID),int(current.stage_number)-2))
        if older is not None:
            assert np.isfinite(float(older[1].RPE)) and 6<=float(older[1].RPE)<=20
            second += 1
        changed.append(bool(current.RPE!=prior.RPE))
        decreasing += int(current.RPE<prior.RPE)
    assert len(changed)==851 and set(changed)=={False,True}
    cache,native_manifest = native_physiology.load()
    assert evidence['native_provenance_sha256']==digest(native_physiology.DIRECTORY/'provenance.json')
    train = inputs['train']
    matched = cache.set_index('row_key').loc[train.row_key]
    np.testing.assert_array_equal(matched.group_key.to_numpy(),train.group_key.to_numpy())
    by_key = {row['row_key']:row for row in native_manifest['lineage']}
    for key in train.row_key:
        row = by_key[key]
        if row['lag_hr_minute_end'] is not None:
            assert pd.Timestamp(row['lag_hr_minute_end'])<=pd.Timestamp(row['prior_report_time_us'],unit='us',tz='UTC')
        if row['latest_baseline_minute_end'] is not None:
            assert pd.Timestamp(row['latest_baseline_minute_end'])<=pd.Timestamp(row['task_start_us'],unit='us',tz='UTC')
    assert set(fitting.group_key).isdisjoint(inputs['frame'].group_key)
    report = {'review':'passed','review_code_sha256':digest(Path(__file__)),
        'preceding_selection_sha256':digest(selection_path),'preceding_verification_sha256':digest(audit_path),
        'existing_input_verification_sha256':digest(evidence_path),'source_original_table_sha256':digest(prepared.DATA),
        'source_provenance_sha256':digest(prepared.DIRECTORY/'provenance.json'),
        'source_fitting_actual_pairs':851,'source_fitting_people':fitting.group_key.nunique(),
        'source_original_fitting_people_before_eligibility':124,'source_reserved_pairs_not_used':206,
        'source_original_reserved_people':32,'source_actual_unchanged_pairs':len(changed)-sum(changed),
        'source_actual_changed_pairs':sum(changed),'source_actual_decreasing_pairs':decreasing,
        'source_actual_second_priors_recoverable':second,'source_missing_second_priors_preserved':851-second,
        'source_hr_from_completed_prior_bout_only':True,'source_current_bout_hr_used':False,
        'native_fitting_cases':487,'native_prior_hr_and_baseline_clocks_verified':True,
        'native_fitting_missing_counts':matched[native_physiology.FEATURES].isna().sum().astype(int).to_dict(),
        'native_physiology_provenance_sha256':digest(native_physiology.DIRECTORY/'provenance.json'),
        'source_target_scale':'original6-20;actual unchanged-vs-changed predicate only for a separate auxiliary head',
        'source_native_baseline_definitions_identical':False,'source_labels_pooled_into_native_labels':False,
        'exact_source_response_ages_or_native_phases_assumed':False,
        'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,'synthetic_rows':0,
        'model_comparison_predeclared':False,
        'interpretation':'Prior history-only gate transfer and its penalty tuning did not beat the native '
            'control. A distinct candidate can test actual lagged physiological state plus actual prior '
            'reports,using an instrument-specific binary source head and causal native prior HR. All source '
            'features here come from a completed preceding bout,not current-bout measurements. Exact source '
            'response clocks/ages are unknown. Source rest HR is lowest seated HR;native rest is a pre-task '
            'mean. Shared units/order are not physiological or Borg-scale equivalence. A bounded matched '
            'comparison and independent source-cell/native-clock audit are needed before model adoption. '
            'This profile alone demonstrates no accuracy improvement.'}
    path = previous.DOCS/'cadence-binary-physiology-review.json'
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    review()
