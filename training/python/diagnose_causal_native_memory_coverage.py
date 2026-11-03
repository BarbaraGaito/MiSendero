"""Measure genuine prior-report memory coverage using fitting participants only."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from fatigue_dynamics import load_inputs
from fatigue_meta_adaptation import context_keys
from fatigue_online_calibration import temporal_metadata
from public_sources import digest,RAW,ROOT
from fatigue_features import RESEARCH


def diagnose():
    _,train,_,manifest,_ = load_inputs()
    assert len(train)==487 and train.group_key.nunique()==28
    old_path = RESEARCH/'catboost-80-v1/selection.json'
    old = json.loads(old_path.read_text())
    assert old['status']=='complete' and old['train_row_keys']==train.row_key.tolist()
    row = next(r for r in old['results'] if r['candidate']['id']=='catboost-023')
    prediction = np.asarray(row['oof_predictions'])
    assert len(prediction)==487
    meta = temporal_metadata(train,manifest)
    by_key = {key:n for n,key in enumerate(train.row_key)}
    reports = {}
    for scope in ('task','session'):
        histories = context_keys(train,meta,scope)
        counts = np.asarray([len(histories[key]) for key in train.row_key])
        pairs = 0
        for position,key in enumerate(train.row_key):
            for entry in histories[key]:
                earlier = by_key[entry['row_key']]
                assert earlier!=position and meta.iloc[earlier].group_key==meta.iloc[position].group_key
                assert meta.iloc[earlier].session_start==meta.iloc[position].session_start
                assert meta.iloc[earlier].response_time<=meta.iloc[position].response_time-pd.Timedelta(minutes=1)
                assert entry['age_minutes']>=1
                if scope=='task':
                    assert meta.iloc[earlier].task_start==meta.iloc[position].task_start
                pairs += 1
        errors = prediction!=train.label.to_numpy()
        unsupported_errors = int((errors&(counts==0)).sum())
        reports[scope] = {'queries':487,'queries_without_earlier_eligible_report':int((counts==0).sum()),
            'queries_with_any_earlier_eligible_report':int((counts>0).sum()),
            'queries_with_at_least_two_earlier_reports':int((counts>=2).sum()),
            'genuine_prior_query_links':pairs,'maximum_prior_reports':int(counts.max()),
            'original_catboost_oof_errors_without_support':unsupported_errors,
            'optimistic_cv_upper_bound_if_all_supported_queries_were_correct':1-unsupported_errors/487,
            'history_index_sha256':hashlib.sha256(json.dumps(histories,sort_keys=True).encode()).hexdigest()}
    report = {'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'original_catboost_selection_sha256':digest(old_path),'original_fitting_rows':487,'original_fitting_people':28,
        'context_builder_code_sha256':digest(Path(__file__).with_name('fatigue_meta_adaptation.py')),
        'temporal_metadata_code_sha256':digest(Path(__file__).with_name('fatigue_online_calibration.py')),
        'session_metadata_sha256':digest(RAW/'geofatigue/session_metadata.json'),
        'scope_coverage':reports,'native_test_labels_inspected':False,'native_test_predictions_computed':0,
        'predictive_estimator_fits':0,'new_hyperparameters_selected':0,'synthetic_rows':0,
        'prior_implementation_review':'Existing KNeighborsClassifier appears only in fatigue_experiment.py as population sensor classification. Prior online ridge and SGD adaptations exist; this coverage check does not repeat those fits or prove a kernel-memory improvement.',
        'interpretation':'Past same-person self-reports may be available at deployment as authorized by the user. Every indexed link is strictly earlier and in the same actual session; no present/future outcomes or persistent person IDmay be a predictor. The optimistic bound is a diagnostic on fitting-participant OOFerrors,not an achieved accuracy. Any kernel-memory mechanism needs a predeclared comparison,matched population-only controls and independent causal/runtime verification.'}
    output = ROOT/'docs/fatigue-80-2026-10-25/causal-native-memory-coverage.json'
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'diagnostic':'passed','scope_coverage':reports,'predictive_estimator_fits':0,'native_test_predictions_computed':0}),flush=True)


if __name__=='__main__':
    diagnose()
