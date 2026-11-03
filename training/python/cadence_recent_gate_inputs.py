"""Native-only measured recent HR; source inputs remain those of study56."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import cadence_association_inputs as recent
from fatigue_features import RESEARCH
from public_sources import ROOT,digest

DIRECTORY = RESEARCH/'cadence-recent-gate-inputs-80-v1'
DOCS = ROOT/'docs/fatigue-80-2026-10-25'
REVIEW = DOCS/'cadence-gate-recent-native-state-review.json'
EXISTING_AUDIT = DOCS/'cadence-association-input-verification.json'
COLUMNS = ['recent_gate_current_hr_bpm','recent_gate_current_minus_prior_hr_bpm',
           'recent_gate_current_over_prior_hr_ratio']


def dependencies():
    return {name:digest(path) for name,path in {
        'preparation_code':Path(__file__),'recent_native_csv':recent.NATIVE_DIRECTORY/'dataset.csv',
        'recent_native_provenance':recent.NATIVE_DIRECTORY/'provenance.json',
        'existing_input_verification':EXISTING_AUDIT,
        'existing_input_audit_code':Path(__file__).with_name('audit_cadence_association_inputs.py'),
        'eligibility_review':REVIEW,
        'eligibility_review_code':Path(__file__).with_name('review_cadence_gate_recent_state.py'),
        'public_real_data_policy':DOCS/'public-real-data-policy.json'}.items()}


def original_native():
    evidence = json.loads(EXISTING_AUDIT.read_text())
    assert evidence['verification']=='passed' and evidence['native_pulse_at_query_completed_by_query']
    assert evidence['native_provenance_sha256']==digest(recent.NATIVE_DIRECTORY/'provenance.json')
    assert evidence['native_dataset_sha256']==digest(recent.NATIVE_DIRECTORY/'dataset.csv')
    assert evidence['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_association_inputs.py'))
    review = json.loads(REVIEW.read_text())
    assert review['review']=='passed' and review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_gate_recent_state.py'))
    cache = pd.read_csv(recent.NATIVE_DIRECTORY/'dataset.csv')
    manifest = json.loads((recent.NATIVE_DIRECTORY/'provenance.json').read_text())
    assert manifest['dataset_sha256']==digest(recent.NATIVE_DIRECTORY/'dataset.csv')
    assert len(cache)==666 and cache.row_key.is_unique
    lines = {line['row_key']:line for line in manifest['lineage']}
    assert set(lines)==set(cache.row_key)
    for row in cache.itertuples():
        line = lines[row.row_key]
        assert row.group_key==line['group_key']
        assert line['current_hr_minute_end'] is not None
        assert pd.Timestamp(line['current_hr_minute_end'])<=pd.Timestamp(line['prediction_time_us'],unit='us',tz='UTC')
        if line['lag_hr_minute_end'] is not None:
            assert pd.Timestamp(line['lag_hr_minute_end'])<=pd.Timestamp(line['prior_report_time_us'],unit='us',tz='UTC')
    return cache,manifest


def prepare():
    assert not DIRECTORY.exists(),'Preserve frozen inputs'
    cache,manifest = original_native()
    values = cache[['row_key','group_key']].copy()
    values[COLUMNS[0]] = cache.current_hr_bpm
    values[COLUMNS[1]] = cache.current_hr_bpm-cache.prior_hr_bpm
    values[COLUMNS[2]] = cache.current_hr_bpm/cache.prior_hr_bpm
    assert values[COLUMNS[0]].notna().all() and not np.isinf(values[COLUMNS].to_numpy()).any()
    assert values[COLUMNS].isna().sum().tolist()==[0,3,3]
    DIRECTORY.mkdir()
    values.to_csv(DIRECTORY/'native.csv',index=False)
    report = {'version':1,'dependencies_sha256':dependencies(),'dataset_sha256':digest(DIRECTORY/'native.csv'),
        'original_native_cases':666,'original_fit_cases':487,'original_test_cases':179,'features':COLUMNS,
        'missing_counts':values[COLUMNS].isna().sum().astype(int).to_dict(),
        'source_current_bout_hr_used':False,'source_native_context_fabricated':False,
        'synthetic_values':0,'filtered_cases':0,'targets_read_or_generated':False,
        'lineage':manifest['lineage']}
    (DIRECTORY/'provenance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('lineage','dependencies_sha256')}),flush=True)


def load():
    report = json.loads((DIRECTORY/'provenance.json').read_text())
    assert report['dependencies_sha256']==dependencies() and report['dataset_sha256']==digest(DIRECTORY/'native.csv')
    data = pd.read_csv(DIRECTORY/'native.csv')
    assert len(data)==666 and data.row_key.is_unique and list(data)==['row_key','group_key',*COLUMNS]
    return data,report


if __name__=='__main__':
    prepare()
