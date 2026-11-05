"""Fitting-only descriptive diagnosis of actual earlier transition support."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fatigue_causal_transition_memory as study
from fatigue_dynamics import load_inputs
from public_sources import digest


def diagnose():
    _,train,_,manifest,_ = load_inputs()
    assert len(train)==487 and train.group_key.nunique()==28
    path = study.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    assert selected['status']=='complete' and selected['train_row_keys']==train.row_key.tolist()
    meta = study.temporal_metadata(train.drop(columns='label'),manifest)
    current = train.label.str.removeprefix('Borg ').to_numpy(int)
    delta = current-train.prior_borg.to_numpy(int)
    scopes = {}
    memberships = {}
    for scope in ('task','session'):
        rows = []
        for n,query in meta.iterrows():
            mask = (meta.group_key.eq(query.group_key)&meta.session_start.eq(query.session_start)
                &meta.response_time.le(query.response_time-pd.Timedelta(minutes=1)))
            if scope=='task':
                mask &= meta.task_start.eq(query.task_start)
            positions = meta[mask].sort_values('response_time').index.to_numpy()
            observed = delta[positions]
            rows.append({'count':len(positions),'query_delta_seen_earlier':bool(delta[n] in observed),
                'observed_deltas':sorted(set(observed.tolist())),
                'latest_delta_matches':bool(len(positions) and observed[-1]==delta[n]),
                'query_delta':int(delta[n]),'query_minus_prior_support_mean':float(delta[n]-observed.mean()) if len(positions) else None})
        supported = [r for r in rows if r['count']]
        no_support = len(rows)-len(supported)
        unseen = sum(not r['query_delta_seen_earlier'] for r in supported)
        scopes[scope] = {'queries':487,'queries_with_support':len(supported),'queries_without_support':no_support,
            'supported_queries_with_no_matching_prior_delta':unseen,
            'supported_queries_with_matching_prior_delta':len(supported)-unseen,
            'supported_queries_with_latest_matching_delta':sum(r['latest_delta_matches'] for r in supported),
            'supported_queries_with_multiple_distinct_prior_deltas':sum(len(r['observed_deltas'])>1 for r in supported),
            'mean_current_minus_unweighted_prior_support_delta':float(np.mean([r['query_minus_prior_support_mean'] for r in supported])),
            'interpretation':'True query deltas are consulted only for this fitting-only diagnostic. '
                'Presence of a matching earlier delta is an optimistic representability check, not an achieved prediction.'}
        memberships[scope] = rows
    comparisons = {}
    for member in ('core','cat'):
        positive = [r for r in selected['results'] if r['candidate'].get('member')==member and r['candidate'].get('strength',0)>0]
        best = max(positive,key=lambda r:r['accuracy_mean'])
        control = next(r for r in selected['results'] if r['candidate'].get('member')==member and r['candidate'].get('strength')==0)
        base_ok = np.asarray(control['oof_predictions'])==train.label.to_numpy()
        memory_ok = np.asarray(best['oof_predictions'])==train.label.to_numpy()
        memory_delta = np.asarray([int(label.removeprefix('Borg ')) for label in best['oof_predictions']])-train.prior_borg.to_numpy(int)
        scope = best['candidate']['scope']
        prior_seen = np.asarray([r['query_delta_seen_earlier'] for r in memberships[scope]])
        supported = np.asarray([r['count']>0 for r in memberships[scope]])
        lost = base_ok&~memory_ok
        gained = ~base_ok&memory_ok
        comparisons[member] = {'candidate':best['candidate'],'cv_accuracy':best['accuracy_mean'],
            'matched_control_cv_accuracy':control['accuracy_mean'],
            'control_correct_queries':int(base_ok.sum()),'memory_correct_queries':int(memory_ok.sum()),
            'correct_control_queries_displaced_by_memory':int(lost.sum()),
            'incorrect_control_queries_corrected_by_memory':int(gained.sum()),
            'displaced_queries_with_no_matching_prior_delta':int((lost&~prior_seen).sum()),
            'gained_queries_with_matching_prior_delta':int((gained&prior_seen).sum()),
            'unsupported_predictions_equal_control':bool(np.array_equal(np.asarray(best['oof_predictions'])[~supported],np.asarray(control['oof_predictions'])[~supported])),
            'displaced_mean_prediction_delta_error':float(np.mean((memory_delta-delta)[lost])) if lost.any() else None}
        assert comparisons[member]['unsupported_predictions_equal_control']
    report = {'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(path),'fitting_queries':487,'fitting_people':28,
        'scope_support':scopes,'best_recipe_comparisons':comparisons,
        'original_query_delta_counts':{str(int(k)):int(v) for k,v in zip(*np.unique(delta,return_counts=True))},
        'new_predictive_estimator_fits':0,'new_preprocessor_fits':0,'new_test_predictions_computed':0,
        'test_labels_inspected':False,'synthetic_rows':0,'hyperparameters_selected_for_another_study':0,
        'limitation':'This is a post-selection diagnostic on fitting participants only. '
            'It neither establishes an attainable80percent nor justifies tuning on the original179test cases.'}
    (study.DOCS/'causal-transition-memory-error-diagnostic.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    diagnose()
