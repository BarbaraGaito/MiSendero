"""Check the source union against both separately audited original datasets."""
import json
from pathlib import Path
import pandas as pd
import fatigue_shoulder_history_inputs as source
from public_sources import digest


def verify():
    manifest = json.loads((source.DIRECTORY/'provenance.json').read_text())
    assert manifest['dependencies_sha256'] == source.dependencies()
    assert manifest['dataset_sha256'] == digest(source.DIRECTORY/'dataset.csv')
    old_proof = json.loads((source.DOCS/'resistance-history-input-verification.json').read_text())
    new_proof = json.loads(source.AUDIT.read_text())
    assert old_proof['verification'] == new_proof['verification'] == 'passed'
    assert new_proof['source_dataset_sha256'] == digest(source.shoulder.DIRECTORY/'dataset.csv')
    assert new_proof['audit_code_sha256'] == digest(Path(__file__).with_name('audit_wsd4fedsrm_history_inputs.py'))
    old = pd.read_csv(source.previous.DIRECTORY/'dataset.csv')
    shoulder = pd.read_csv(source.shoulder.DIRECTORY/'dataset.csv').rename(columns={
        'original_rpe_points':'original_shoulder_rpe','prior_rpe_points':source.PRIOR,'second_prior_rpe_points':source.SECOND})
    shoulder['source_domain'] = 'shoulder'
    union = pd.read_csv(source.DIRECTORY/'dataset.csv')
    assert len(union) == union.row_key.nunique() == 2648
    pd.testing.assert_frame_equal(union[union.source_domain.ne('shoulder')][old.columns].reset_index(drop=True),old,
        check_dtype=False,rtol=0,atol=1e-12)
    pd.testing.assert_frame_equal(union[union.source_domain.eq('shoulder')][shoulder.columns].reset_index(drop=True),shoulder,
        check_dtype=False,rtol=0,atol=1e-12)
    assert set(old.group_key).isdisjoint(shoulder.group_key) and set(old.row_key).isdisjoint(shoulder.row_key)
    fitting,held = union[union.source_partition.eq('fitting')],union[union.source_partition.eq('reserved')]
    assert len(fitting) == 2336 and len(held) == 312 and set(fitting.group_key).isdisjoint(held.group_key)
    assert fitting[source.SECOND].notna().sum() == 1927
    assert fitting.groupby('source_domain').size().to_dict() == {'emap':248,'worker':253,'sts':49,'resistance':866,'shoulder':920}
    for domain,part in union.groupby('source_domain'):
        target = source.TARGETS[domain]
        assert part[target].notna().all() and part[source.PRIOR].notna().all()
        for other in set(source.TARGETS.values())-{target}:
            assert part[other].isna().all(),'An incompatible source outcome was pooled'
    report = {'verification':'passed','audit_code_sha256':digest(Path(__file__)),
        'source_preparation_code_sha256':digest(Path(source.__file__)),
        'source_provenance_sha256':digest(source.DIRECTORY/'provenance.json'),
        'source_dataset_sha256':digest(source.DIRECTORY/'dataset.csv'),
        'shoulder_input_verification_sha256':digest(source.AUDIT),
        'previous_input_verification_sha256':digest(source.DOCS/'resistance-history-input-verification.json'),
        'old_original_rows_preserved':1541,'new_original_rows_preserved':1107,
        'actual_source_fitting_targets':2336,'source_fitting_actual_second_priors':1927,'source_reserved_targets':312,
        'source_counts':manifest['source_counts'],'source_outcomes_kept_separate':True,
        'native_target_merge':False,'synthetic_rows':0,'imputed_targets':0,'invented_source_times_or_sensor_joins':0,
        'model_fitting_started':False}
    (source.DOCS/'shoulder-history-input-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    verify()
