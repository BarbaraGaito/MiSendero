"""Actual adjacent-stage CADENCE histories plus completed prior-bout HR."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import cadence_lagged_rpe as original
import fatigue_cadence_native_inputs as physiology
from fatigue_features import RESEARCH
from public_sources import ROOT,digest

DIRECTORY = RESEARCH/'cadence-binary-gate-inputs-80-v1'
DOCS = ROOT/'docs/fatigue-80-2026-10-25'
REVIEW = DOCS/'cadence-binary-physiology-review.json'
PHYSIOLOGY = list(physiology.FEATURES)
NATIVE_COLUMNS = {name:'cadence_binary_gate_'+name for name in PHYSIOLOGY}
FEATURES = ['prior','second',*PHYSIOLOGY]


def dependencies():
    return {name:digest(path) for name,path in {
        'preparation_code':Path(__file__),'source_preparation_code':Path(original.__file__),
        'native_preparation_code':Path(physiology.__file__),'eligibility_review':REVIEW,
        'eligibility_review_code':Path(__file__).with_name('review_cadence_binary_physiology.py'),
        'raw_source_table':original.DATA,'source_provenance':original.DIRECTORY/'provenance.json',
        'source_dataset':original.DIRECTORY/'dataset.csv','native_provenance':physiology.DIRECTORY/'provenance.json',
        'native_dataset':physiology.DIRECTORY/'dataset.csv',
        'existing_input_audit':DOCS/'cadence-lagged-input-verification.json',
        'public_real_data_policy':DOCS/'public-real-data-policy.json'}.items()}


def prepare():
    assert not DIRECTORY.exists(),'Preserve existing prepared inputs'
    review = json.loads(REVIEW.read_text())
    assert review['review']=='passed' and review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_binary_physiology.py'))
    fitting,reserved,manifest = original.load()
    raw = original.checked_original()
    lookup = {(int(row.ID),int(row.stage_number)):(index,row) for index,row in raw.iterrows()}
    previous = pd.concat([fitting,reserved]).set_index('row_key')
    rows,lineage = [],[]
    for item in manifest['lineage']:
        current = raw.iloc[item['original_current_row']]
        prior = raw.iloc[item['original_previous_row']]
        older = lookup.get((int(current.ID),int(current.stage_number)-2))
        old = previous.loc[item['row_key']]
        assert pd.isna(prior.TermCode) and current.ID==prior.ID
        assert float(current.RPE)==old.rpe_native and float(prior.RPE)==old.prior_rpe_native
        rows.append({'row_key':item['row_key'],'group_key':item['group_key'],
            'source_domain':'cadence','source_partition':item['source_partition'],
            'current_rpe':float(current.RPE),'prior':float(prior.RPE),
            'second':float(older[1].RPE) if older is not None else np.nan,
            **{name:float(old[name]) for name in PHYSIOLOGY}})
        lineage.append({**item,'original_second_row':int(older[0]) if older is not None else None,
            'original_second_rpe':float(older[1].RPE) if older is not None else None,
            'source_current_bout_hr_used':False,'source_exact_report_age_assumed':False})
    source = pd.DataFrame(rows)
    fit = source[source.source_partition.eq('fitting')]
    assert len(source)==1057 and len(fit)==851 and fit.second.notna().sum()==727
    assert fit.current_rpe.eq(fit.prior).sum()==299 and fit.current_rpe.ne(fit.prior).sum()==552
    native,native_manifest = physiology.load()
    native = native[['row_key','group_key',*PHYSIOLOGY]].rename(columns=NATIVE_COLUMNS)
    assert len(native)==666 and native.row_key.is_unique
    DIRECTORY.mkdir()
    source.to_csv(DIRECTORY/'source.csv',index=False)
    native.to_csv(DIRECTORY/'native.csv',index=False)
    report = {'version':1,'dependencies_sha256':dependencies(),
        'source_dataset_sha256':digest(DIRECTORY/'source.csv'),'native_dataset_sha256':digest(DIRECTORY/'native.csv'),
        'source_actual_pairs':1057,'source_fitting_pairs':851,'source_reserved_pairs':206,
        'source_fitting_people':123,'source_reserved_people':32,'source_fitting_actual_second_priors':727,
        'source_fitting_equal_pairs':299,'source_fitting_unequal_pairs':552,'source_fitting_decreases':4,
        'source_target_instrument':'original Borg6-20 retained;binary equality predicate is a separate auxiliary task',
        'features':FEATURES,'native_physiology_columns':NATIVE_COLUMNS,'source_lineage':lineage,
        'native_original_input_provenance_sha256':digest(physiology.DIRECTORY/'provenance.json'),
        'native_original_input_lineage':native_manifest['lineage'],
        'source_current_bout_hr_used':False,'source_ages_or_native_phases_assumed':False,
        'source_native_baseline_definitions_identical':False,'source_labels_pooled_as_native_borg':False,
        'synthetic_rows':0,'imputed_source_targets':0,'missing_inputs_filled_in_snapshot':False,
        'native_cases_dropped':0,'model_fitting_started':False}
    (DIRECTORY/'provenance.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('source_actual_pairs','source_fitting_pairs','source_reserved_pairs',
        'source_fitting_actual_second_priors','native_cases_dropped','synthetic_rows')}),flush=True)


def load():
    report = json.loads((DIRECTORY/'provenance.json').read_text())
    assert report['dependencies_sha256']==dependencies()
    assert report['source_dataset_sha256']==digest(DIRECTORY/'source.csv')
    assert report['native_dataset_sha256']==digest(DIRECTORY/'native.csv')
    data,native = pd.read_csv(DIRECTORY/'source.csv'),pd.read_csv(DIRECTORY/'native.csv')
    fitting,reserved = data[data.source_partition.eq('fitting')],data[data.source_partition.eq('reserved')]
    assert (len(fitting),len(reserved),len(native))==(851,206,666)
    assert set(fitting.group_key).isdisjoint(reserved.group_key) and set(data.group_key).isdisjoint(native.group_key)
    return fitting.copy(),reserved.copy(),native,report


if __name__=='__main__':
    prepare()
