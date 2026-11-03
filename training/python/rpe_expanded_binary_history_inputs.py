"""Combine six compatible actual-history tasks;retain original outcome domains."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fatigue_shoulder_history_inputs as old
import cadence_binary_gate_inputs as cadence
import rpe_forecasting_history_inputs as gait
from fatigue_features import RESEARCH
from public_sources import digest

DIRECTORY = RESEARCH/'rpe-expanded-binary-history-inputs-80-v1'
DOCS = old.DOCS
COUNTS = {'cadence':851,'emap':248,'gait_forecasting':410,'resistance':866,'shoulder':920,'worker':253}
COLUMNS = ['row_key','group_key','source_domain','source_partition','current_rpe','prior','second']
AUDITS = {'old':DOCS/'shoulder-history-input-verification.json',
    'cadence':DOCS/'cadence-binary-gate-input-verification.json',
    'gait_forecasting':DOCS/'rpe-forecasting-history-input-verification.json'}


def dependencies():
    paths = {'preparation_code':Path(__file__),'old_preparation_code':Path(old.__file__),
        'cadence_preparation_code':Path(cadence.__file__),'gait_preparation_code':Path(gait.__file__),
        'old_provenance':old.DIRECTORY/'provenance.json','old_dataset':old.DIRECTORY/'dataset.csv',
        'cadence_provenance':cadence.DIRECTORY/'provenance.json','cadence_dataset':cadence.DIRECTORY/'source.csv',
        'gait_provenance':gait.DIRECTORY/'provenance.json','gait_dataset':gait.DIRECTORY/'pairs.csv',
        'old_audit_code':Path(__file__).with_name('audit_shoulder_history_inputs.py'),
        'cadence_audit_code':Path(__file__).with_name('audit_cadence_binary_gate_inputs.py'),
        'gait_audit_code':Path(__file__).with_name('audit_rpe_forecasting_history_inputs.py'),
        'public_real_data_policy':DOCS/'public-real-data-policy.json',**AUDITS}
    return {name:digest(path) for name,path in paths.items()}


def build():
    prior,prior_manifest = old.load()
    audit = json.loads(AUDITS['old'].read_text())
    assert audit['verification']=='passed' and audit['source_preparation_code_sha256']==digest(Path(old.__file__))
    assert audit['source_dataset_sha256']==digest(old.DIRECTORY/'dataset.csv') and audit['source_provenance_sha256']==digest(old.DIRECTORY/'provenance.json')
    assert audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_shoulder_history_inputs.py'))
    parts = []
    for name in ('emap','resistance','shoulder','worker'):
        part = prior[prior.source_domain.eq(name)].copy()
        normalized = part[['row_key','group_key','source_domain','source_partition']].copy()
        normalized['current_rpe'] = part[old.TARGETS[name]]
        normalized['prior'],normalized['second'] = part[old.PRIOR],part[old.SECOND]
        parts.append(normalized[COLUMNS])
    cadence_fit,cadence_reserved,_,cadence_manifest = cadence.load()
    audit = json.loads(AUDITS['cadence'].read_text())
    assert audit['verification']=='passed' and audit['actual_source_pairs_independently_rebuilt']==1057
    assert audit['preparation_code_sha256']==digest(Path(cadence.__file__))
    assert audit['source_dataset_sha256']==digest(cadence.DIRECTORY/'source.csv')
    assert audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_binary_gate_inputs.py'))
    parts.append(pd.concat([cadence_fit,cadence_reserved],ignore_index=True)[COLUMNS])
    gait_fit,_,gait_manifest = gait.load()
    audit = json.loads(AUDITS['gait_forecasting'].read_text())
    assert audit['verification']=='passed' and audit['approved_for_separate_original_unequal_binary_head']
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_rpe_forecasting_history_inputs.py'))
    assert audit['preparation_code_sha256']==digest(Path(gait.__file__)) and audit['pairs_sha256']==digest(gait.DIRECTORY/'pairs.csv')
    parts.append(gait_fit[COLUMNS])
    combined = pd.concat(parts,ignore_index=True)
    assert combined.row_key.is_unique and combined[['current_rpe','prior']].notna().all().all()
    assert np.isfinite(combined[['current_rpe','prior']].to_numpy()).all()
    fitting,reserved = combined[combined.source_partition.eq('fitting')],combined[combined.source_partition.eq('reserved')]
    assert len(fitting)==3548 and fitting.groupby('source_domain').size().to_dict()==COUNTS
    assert fitting.second.notna().sum()==3042 and set(fitting.group_key).isdisjoint(reserved.group_key)
    assert all(set(part.current_rpe.ne(part.prior))=={False,True} for _,part in fitting.groupby('source_domain'))
    assert len(prior[prior.source_domain.eq('sts')&prior.source_partition.eq('fitting')])==49
    return combined


def prepare():
    assert not DIRECTORY.exists(),'Preserve frozen combined source histories'
    combined = build()
    fitting,reserved = combined[combined.source_partition.eq('fitting')],combined[combined.source_partition.eq('reserved')]
    DIRECTORY.mkdir()
    combined.to_csv(DIRECTORY/'dataset.csv',index=False)
    counts = {name:{'fitting_pairs':len(part),'fitting_people':part.group_key.nunique(),
        'equal_pairs':int(part.current_rpe.eq(part.prior).sum()),'unequal_pairs':int(part.current_rpe.ne(part.prior).sum()),
        'actual_second_priors':int(part.second.notna().sum()),'naturally_missing_second_priors':int(part.second.isna().sum())}
        for name,part in fitting.groupby('source_domain')}
    report = {'version':1,'dependencies_sha256':dependencies(),'dataset_sha256':digest(DIRECTORY/'dataset.csv'),
        'fitting_actual_pairs':3548,'previous_four_domain_fitting_pairs':2287,'cadence_fitting_pairs':851,
        'additional_gait_fitting_pairs':410,'additional_gait_fitting_people':19,'gait_reserved_people_not_received':5,
        'actual_second_priors':3042,'stored_reserved_source_pairs':len(reserved),'domains':counts,
        'single_class_sts_fitting_pairs_excluded':49,'source_current_and_prior_values_unchanged':True,
        'source_instrument_scales_converted':False,'source_targets_pooled_as_native_borg':False,
        'approved_shared_inputs':['actual_prior_rpe','actual_second_prior_rpe','actual_second_prior_missing_indicator'],
        'source_specific_binary_heads_required':True,'domain_specific_fitting_normalization_required':True,
        'source_sensor_or_native_context_fabricated':False,'source_ages_or_phases_assumed':False,
        'synthetic_rows':0,'synthetic_targets':0,'new_native_borg_cases':0,'new_predictive_estimator_fits':0,
        'model_comparison_predeclared':False,'native_training_cases':487,'native_test_cases':179,
        'scope':'Real source current/prior equality tasks share measured history structure. Original point '
            'values and domains remain separate. No source outcomes become native0-10labels,no invented '
            'sensor/context columns,ages,phase equivalence or extra history views. All native487/179cases '
            'are unchanged. The new corpus requires a separately predeclared model comparison and cannot '
            'be silently passed into the frozen851-pair physiology models.'}
    (DIRECTORY/'provenance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='dependencies_sha256'}),flush=True)


def load():
    report = json.loads((DIRECTORY/'provenance.json').read_text())
    assert report['dependencies_sha256']==dependencies() and report['dataset_sha256']==digest(DIRECTORY/'dataset.csv')
    frame = pd.read_csv(DIRECTORY/'dataset.csv')
    fitting,reserved = frame[frame.source_partition.eq('fitting')].copy(),frame[frame.source_partition.eq('reserved')].copy()
    assert len(fitting)==3548 and fitting.groupby('source_domain').size().to_dict()==COUNTS
    assert fitting.second.notna().sum()==3042 and frame.row_key.is_unique
    return fitting,reserved,report


if __name__=='__main__':
    prepare()
