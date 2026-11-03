"""Actual within-trial public Borg histories; original source points preserved."""
import io
import json
from pathlib import Path

import pandas as pd
from public_sources import digest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT/'docs/fatigue-80-2026-10-25'
AUDIT = DOCS/'wsd4fedsrm-timed-report-verification.json'
DIRECTORY = ROOT/'training/data/fatigue-research/wsd4fedsrm-timed-histories-80-v1'


def build():
    proof = json.loads(AUDIT.read_text())
    assert proof['verification'] == 'passed' and proof['person_partition_before_pair_eligibility']
    assert proof['verification_code_sha256'] == digest(Path(__file__).with_name('audit_wsd4fedsrm_timed_reports.py'))
    rows = []
    for cell in proof['original_timed_cell_lineage']:
        previous,second = cell['prior_timed_report'],cell['second_prior_timed_report']
        if previous is None:
            continue
        assert previous['elapsed_seconds'] < cell['elapsed_seconds']
        if second:
            assert second['elapsed_seconds'] < previous['elapsed_seconds']
        rows.append({'row_key':f"wsd:{cell['person']}:{cell['task']}:{cell['original_header'].strip()}",
            'group_key':'wsd:'+cell['person'],'task_key':cell['task'],'source_partition':cell['partition'],
            'original_rpe_points':cell['original_borg_points'],
            'prior_rpe_points':previous['original_borg_points'],
            'second_prior_rpe_points':second['original_borg_points'] if second else None,
            'elapsed_seconds':cell['elapsed_seconds'],'prior_elapsed_seconds':previous['elapsed_seconds'],
            'second_prior_elapsed_seconds':second['elapsed_seconds'] if second else None,
            'prior_age_minutes':(cell['elapsed_seconds']-previous['elapsed_seconds'])/60.,
            'second_prior_age_minutes':(cell['elapsed_seconds']-second['elapsed_seconds'])/60. if second else None,
            'original_csv_line':cell['csv_line'],'current_original_header':cell['original_header'],
            'prior_original_header':previous['original_header'],
            'second_prior_original_header':second['original_header'] if second else None})
    frame = pd.DataFrame(rows)
    assert len(frame) == frame.row_key.nunique() == 1107 and frame.group_key.nunique() == 34
    fit,held = frame[frame.source_partition.eq('fitting')],frame[frame.source_partition.eq('reserved')]
    assert (len(fit),len(held),fit.group_key.nunique(),held.group_key.nunique()) == (920,187,27,7)
    assert not set(fit.group_key)&set(held.group_key)
    assert fit.second_prior_rpe_points.notna().sum() == 758 and held.second_prior_rpe_points.notna().sum() == 146
    assert frame.original_rpe_points.between(6,20).all() and frame.prior_rpe_points.between(6,20).all()
    return frame


def prepare():
    frame = build()
    DIRECTORY.mkdir(exist_ok=True)
    payload = frame.to_csv(index=False)
    data_path = DIRECTORY/'dataset.csv'
    if data_path.exists():
        assert data_path.read_text() == payload,'Preserve frozen original-source histories'
    else:
        data_path.write_text(payload,encoding='utf-8')
    pd.testing.assert_frame_equal(pd.read_csv(data_path),pd.read_csv(io.StringIO(payload)))
    manifest = {'version':1,'preparation_code_sha256':digest(Path(__file__)),'input_audit_sha256':digest(AUDIT),
        'dataset_sha256':digest(data_path),'actual_source_pairs':1107,'fitting_pairs':920,'reserved_pairs':187,
        'fitting_people':27,'reserved_people':7,'fitting_actual_second_priors':758,'reserved_actual_second_priors':146,
        'original_outcome':'Borg6-20_points_separate_from_native0-10','synthetic_rows':0,
        'terminal_or_before_task_rows_added':0,'cross_task_histories_created':0,'sensor_join_created':False,
        'native_target_merge':False,'model_fitting_started':False,
        'scope':'Actual timed reports only. Person partition frozen before pair eligibility; natural absent second priors remain absent. Recorded 10-second clocks retained without inventing between-task order or terminal report times. No source values converted into native labels.'}
    path = DIRECTORY/'provenance.json'
    if path.exists():
        assert json.loads(path.read_text()) == manifest
    else:
        path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest),flush=True)


if __name__ == '__main__':
    prepare()
