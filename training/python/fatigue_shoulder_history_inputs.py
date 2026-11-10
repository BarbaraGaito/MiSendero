"""Combine audited real histories while retaining five separate source outcomes."""
import json
from pathlib import Path
import pandas as pd

import fatigue_resistance_history_inputs as previous
import wsd4fedsrm_history_inputs as shoulder
from public_sources import digest

DIRECTORY = previous.DIRECTORY.parent/'shoulder-expanded-history-inputs-80-v1'
DOCS = previous.DOCS
PRIOR,SECOND = previous.PRIOR,previous.SECOND
TARGETS = {**previous.TARGETS,'shoulder':'original_shoulder_rpe'}
AUDIT = DOCS/'wsd4fedsrm-history-input-verification.json'


def dependencies():
    return {key:digest(path) for key,path in {
        'preparation_code':Path(__file__),'previous_preparation_code':Path(previous.__file__),
        'previous_provenance':previous.DIRECTORY/'provenance.json',
        'previous_source_audit':DOCS/'resistance-history-input-verification.json',
        'shoulder_preparation_code':Path(shoulder.__file__),
        'shoulder_provenance':shoulder.DIRECTORY/'provenance.json',
        'shoulder_source_audit':AUDIT,'shoulder_source_audit_code':Path(__file__).with_name('audit_wsd4fedsrm_history_inputs.py'),
        'public_real_data_policy':DOCS/'public-real-data-policy.json'}.items()}


def build():
    old,old_manifest = previous.load()
    proof = json.loads(AUDIT.read_text())
    assert proof['verification'] == 'passed' and proof['all_original_pairs_independently_rebuilt'] == 1107
    assert proof['audit_code_sha256'] == digest(Path(__file__).with_name('audit_wsd4fedsrm_history_inputs.py'))
    assert proof['source_preparation_code_sha256'] == digest(Path(shoulder.__file__))
    assert proof['source_provenance_sha256'] == digest(shoulder.DIRECTORY/'provenance.json')
    assert proof['source_dataset_sha256'] == digest(shoulder.DIRECTORY/'dataset.csv')
    new = pd.read_csv(shoulder.DIRECTORY/'dataset.csv')
    new = new.rename(columns={'original_rpe_points':TARGETS['shoulder'],'prior_rpe_points':PRIOR,'second_prior_rpe_points':SECOND})
    new['source_domain'] = 'shoulder'
    assert new[TARGETS['shoulder']].between(6,20).all() and new[PRIOR].between(6,20).all()
    assert not set(old.row_key)&set(new.row_key) and not set(old.group_key)&set(new.group_key)
    combined = pd.concat([old,new],ignore_index=True,sort=False)
    assert len(combined) == combined.row_key.nunique() == 2648
    pd.testing.assert_frame_equal(combined[combined.source_domain.ne('shoulder')][old.columns].reset_index(drop=True),old,
        check_dtype=False,rtol=0,atol=0)
    return combined


def prepare():
    assert not DIRECTORY.exists(),'Preserve the frozen combined actual-source inputs'
    frame = build()
    fitting,reserved = frame[frame.source_partition.eq('fitting')],frame[frame.source_partition.eq('reserved')]
    assert (len(fitting),len(reserved),fitting[SECOND].notna().sum()) == (2336,312,1927)
    DIRECTORY.mkdir()
    frame.to_csv(DIRECTORY/'dataset.csv',index=False)
    counts = {domain:len(part) for domain,part in fitting.groupby('source_domain')}
    assert counts['shoulder'] == 920 and counts['resistance'] == 866
    report = {'version':1,'dependencies_sha256':dependencies(),'dataset_sha256':digest(DIRECTORY/'dataset.csv'),
        'actual_source_fitting_targets':2336,'stored_reserved_targets':312,'source_fitting_actual_second_priors':1927,
        'source_counts':counts,'source_current_target_columns':TARGETS,'common_measured_history_features':[PRIOR,SECOND],
        'additional_shoulder_fitting_targets':920,'additional_shoulder_reserved_targets':187,
        'additional_shoulder_fitting_people':27,'additional_shoulder_reserved_people':7,
        'source_outcomes_must_remain_separate':True,'native_target_merge':False,'new_native_borg_targets':0,
        'synthetic_rows':0,'imputed_targets':0,'invented_source_ages_or_phase_mapping':0,'new_sensor_joins':0,
        'model_fitting_started_at_preparation':False,
        'scope':'Original1541public source pairs plus1107actual within-trial timed shoulder pairs. All1416previous fitting targets preserved;920newfitting/187reserved fixed by whole original person. Shoulder6-20points use a separate output; do not convert or pool them into native0-10labels. Preserve absent second histories; no terminal/before-task clocks,between-task order or sensor joins inferred.'}
    (DIRECTORY/'provenance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)


def load():
    report = json.loads((DIRECTORY/'provenance.json').read_text())
    assert report['dependencies_sha256'] == dependencies()
    assert report['dataset_sha256'] == digest(DIRECTORY/'dataset.csv')
    frame = pd.read_csv(DIRECTORY/'dataset.csv')
    pd.testing.assert_frame_equal(frame,build(),check_dtype=False,rtol=0,atol=1e-12)
    return frame,report


if __name__ == '__main__':
    prepare()
