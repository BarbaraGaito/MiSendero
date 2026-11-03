"""Fitting-only range/support diagnostic; no predictive model fits or test reads."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
import fatigue_shoulder_history_joint as study
from public_sources import digest


def diagnose():
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/'selection.json'
    selection = json.loads(selection_path.read_text())
    assert selection['status']=='complete'
    train,external = inputs['train'],inputs['source']
    before = [joblib.hash(x) for x in (train,external)]
    columns = study.COMMON
    native = pd.DataFrame({columns[0]:train.prior_borg.to_numpy(float),columns[1]:train.prior2_borg.to_numpy(float)})
    sources = {domain:part[columns].reset_index(drop=True) for domain,part in external.groupby('source_domain')}
    stats = {}
    for name,part in {'native':native,**sources}.items():
        stats[name] = {column:{'observed_values':int(part[column].notna().sum()),'missing_values':int(part[column].isna().sum()),
            'minimum':float(part[column].min()) if part[column].notna().any() else None,
            'maximum':float(part[column].max()) if part[column].notna().any() else None,
            'mean':float(part[column].mean()) if part[column].notna().any() else None}
            for column in columns}
    original_pool = external[~external.source_domain.isin(['resistance','shoulder'])][columns]
    folds = []
    for number,(fit,val) in enumerate(GroupKFold(n_splits=5).split(train,groups=train.group_key)):
        fitting = native.iloc[fit]
        union = pd.concat([fitting,original_pool],ignore_index=True)
        assert len(original_pool)==550
        imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)
        scaler = StandardScaler().fit(imputer.fit_transform(union))
        domains = {}
        for name,part in sources.items():
            scaled = scaler.transform(imputer.transform(part))
            domains[name] = {column:{'observed_values_outside_native_fitting_range':int(((part[column]<fitting[column].min())|(part[column]>fitting[column].max())).sum()),
                'observed_fraction_outside_native_fitting_range':float(((part[column]<fitting[column].min())|(part[column]>fitting[column].max())).sum()/part[column].notna().sum()) if part[column].notna().any() else None,
                'observed_fraction_abs_z_greater_than_3':float((np.abs(scaled[part[column].notna().to_numpy(),index])>3).mean()) if part[column].notna().any() else None}
                for index,column in enumerate(columns)}
        folds.append({'fold':number,'native_fit_rows':len(fit),'native_validation_people_not_used_for_statistics':train.iloc[val].group_key.nunique(),
            'normalizer_source_rows':550,'source_support':domains})
    assert before==[joblib.hash(x) for x in (train,external)]
    report = {'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'study_code_sha256':digest(Path(study.__file__)),'selection_sha256':digest(selection_path),
        'source_input_verification_sha256':digest(study.INPUT_AUDIT),'original_native_fitting_rows':487,
        'actual_source_fitting_rows':2336,'source_reserved_rows_used':0,'native_test_predictions_computed':0,
        'current_native_labels_used_for_statistics':False,'new_predictive_estimator_fits':0,
        'measured_prior_statistics_by_domain':stats,'fold_only_preprocessing_support':folds,
        'source_labels_converted_or_pooled':False,'synthetic_rows':0,
        'interpretation':'Different documented instruments occupy different measured-history ranges under the preserved pooled normalizer. This is fitting-only evidence for testing predictor representation alignment; it does not establish physiological scaleequivalence,encoder saturation or a native accuracy gain. Keep original source targets separate,derive any statistics only from fitting rows,and compare matched zero-source controls.'}
    (study.DOCS/'shoulder-history-range-diagnostic.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'diagnostic':'passed','shoulder_prior_statistics':stats['shoulder'],
        'first_fold_shoulder_support':folds[0]['source_support']['shoulder'],'new_predictive_estimator_fits':0}),flush=True)


if __name__=='__main__':
    diagnose()
