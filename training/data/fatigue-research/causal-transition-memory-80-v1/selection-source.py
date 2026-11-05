"""Conditional memory of actual earlier native transitions, with frozen bases.

The population artifact contains no person's report memory. Runtime packets
contain only strictly earlier reports in the query's actual session/task.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

import fatigue_domain_aligned_history as predecessor
import fatigue_two_history_joint as native
from fatigue_dynamics import load_inputs as dynamics_inputs
from fatigue_online_calibration import temporal_metadata
from public_sources import digest, RAW

DIRECTORY = predecessor.DIRECTORY.parent/'causal-transition-memory-80-v1'
DOCS = predecessor.DOCS
PROPOSAL = DOCS/'causal-transition-memory-plan.json'
PARENT_AUDIT = DOCS/'domain-aligned-history-verification.json'
COVERAGE = DOCS/'causal-native-memory-coverage.json'
FEATURE_SETS = {
    'clock': ['prior_borg','prior_age_minutes','elapsed_minutes','task_order','prior_borg_slope',
              'terrain_stairs','terrain_ramp','terrain_flat_trail'],
    'physiology': ['prior_borg','prior_age_minutes','elapsed_minutes','hr_last',
                   'hr_change_after_prior','hr_recent_slope','terrain_stairs','terrain_ramp','terrain_flat_trail'],
}
META_COLUMNS = ['group_key','session_start','task_start','response_time']


def plan():
    result = [{'id':f'transition-memory-{n:03d}','algorithm':'previous_real_control',
               'parent_candidate_id':key} for n,key in enumerate(['aligned-history-000','aligned-history-001'])]
    for member in ('core','cat'):
        result.append({'id':f'transition-memory-{len(result):03d}','algorithm':'causal_transition_memory',
            'member':member,'retrieval_features':'clock','bandwidth':.5,'strength':0.,'scope':'session',
            'recency_minutes':10.,'mass_shrinkage':1.})
    for member in ('core','cat'):
        for features in FEATURE_SETS:
            for bandwidth in (.5,2.):
                for strength in (.25,.75):
                    for scope in ('task','session'):
                        result.append({'id':f'transition-memory-{len(result):03d}',
                            'algorithm':'causal_transition_memory','member':member,'retrieval_features':features,
                            'bandwidth':bandwidth,'strength':strength,'scope':scope,
                            'recency_minutes':10.,'mass_shrinkage':1.})
    return result


def load_inputs():
    old = predecessor.load_inputs()
    selection_path = predecessor.DIRECTORY/'selection.json'
    selection = json.loads(selection_path.read_text())
    audit = json.loads(PARENT_AUDIT.read_text())
    assert selection['status']=='complete' and len(selection['results'])==10
    assert all(selection.get(k)==v for k,v in predecessor.fingerprint(old).items())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selection_path)
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_domain_aligned_history.py'))
    _,train,_,manifest,_ = dynamics_inputs()
    assert train.row_key.tolist()==old['train'].row_key.tolist() and train.label.tolist()==old['train'].label.tolist()
    assert (len(old['train']),len(old['test']))==(487,179)
    assert not set(old['train'].group_key)&set(old['test'].group_key)
    assert set(sum(FEATURE_SETS.values(),[]))<=set(old['train'])
    proposal = json.loads(PROPOSAL.read_text())
    assert proposal['implementation_code_sha256']==digest(Path(__file__)) and proposal['plan']==plan()
    return {**old,'parent_inputs':old,'parent_selection':selection,'memory_manifest':manifest}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':predecessor.fingerprint(inputs['parent_inputs']),
        'previous_selection_sha256':digest(predecessor.DIRECTORY/'selection.json'),
        'previous_verification_sha256':digest(PARENT_AUDIT),'coverage_sha256':digest(COVERAGE),
        'proposal_sha256':digest(PROPOSAL),'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),
        'session_metadata_sha256':digest(RAW/'geofatigue/session_metadata.json'),
        'dependency_code_sha256':{name:digest(Path(__file__).with_name(name)) for name in
            ('fatigue_online_calibration.py','fatigue_two_history_joint.py')}}


def metadata_record(row):
    return {key:str(row[key]) for key in META_COLUMNS}


def make_episodes(queries,pool,manifest,scope,features,observer=None):
    """Resolve times and select keys before reading any support outcomes."""
    if 'label' in queries or scope not in ('task','session'):
        raise ValueError('Queries must be input-only; explicit task/session scope required')
    assert queries.row_key.is_unique and pool.row_key.is_unique
    query_meta = temporal_metadata(queries,manifest)
    pool_meta = temporal_metadata(pool[['row_key','group_key']],manifest)
    episodes = []
    for number,(_,query) in enumerate(queries.iterrows()):
        meta = query_meta.iloc[number]
        eligible = (pool_meta.group_key.eq(meta.group_key)&pool_meta.session_start.eq(meta.session_start)
                    &pool_meta.response_time.le(meta.response_time-pd.Timedelta(minutes=1)))
        if scope=='task':
            eligible &= pool_meta.task_start.eq(meta.task_start)
        indices = pool_meta[eligible].sort_values('response_time').index.to_numpy()
        # Only these observed earlier rows cross the inference boundary.
        support = pool.iloc[indices]
        if observer is not None:
            observer(query.row_key,support.row_key.tolist())
        episodes.append({'query_key':query.row_key,'query_metadata':metadata_record(meta),
            'query_features_hash':joblib.hash(queries.iloc[[number]][features]),'scope':scope,
            'support_features':support[features].copy(),'support_labels':support.label.tolist(),
            'support_keys':support.row_key.tolist(),
            'support_metadata':[metadata_record(pool_meta.iloc[i]) for i in indices]})
    return episodes


def validate_episode(query,episode,scope):
    required = {'query_key','query_metadata','query_features_hash','scope','support_features',
                'support_labels','support_keys','support_metadata'}
    if set(episode)!=required or episode['scope']!=scope or episode['query_features_hash']!=joblib.hash(query):
        raise ValueError('Memory packet does not match this input-only query')
    rows = episode['support_features']
    if list(rows)!=list(query) or len(rows)!=len(episode['support_labels']) or len(rows)!=len(episode['support_keys']):
        raise ValueError('Memory observations are incomplete')
    if len(rows)!=len(episode['support_metadata']) or len(set(episode['support_keys']))!=len(rows):
        raise ValueError('Memory keys/times are incomplete or repeated')
    meta = episode['query_metadata']
    if set(meta)!=set(META_COLUMNS):
        raise ValueError('Query clocks are incomplete')
    ages = []
    for key,old in zip(episode['support_keys'],episode['support_metadata']):
        if set(old)!=set(META_COLUMNS) or key==episode['query_key']:
            raise ValueError('Current response cannot be its own support')
        age = (pd.Timestamp(meta['response_time'])-pd.Timestamp(old['response_time'])).total_seconds()/60
        if (age<1 or not np.isfinite(age) or old['group_key']!=meta['group_key']
            or old['session_start']!=meta['session_start']
            or (scope=='task' and old['task_start']!=meta['task_start'])):
            raise ValueError('Memory must be strictly earlier in the actual person/session/task')
        ages.append(age)
    return np.asarray(ages,float)


class TransitionMemoryBorg:
    def __init__(self,candidate):
        self.candidate = copy.deepcopy(candidate)

    def fit(self,fitting,cached):
        self.base = cached['base']
        assert cached['fit_row_keys']==fitting.row_key.tolist()
        self.retrieval_features = list(FEATURE_SETS[self.candidate['retrieval_features']])
        self.input_features = list(dict.fromkeys(self.base.input_features+self.retrieval_features))
        self.imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)
        self.scaler = StandardScaler().fit(self.imputer.fit_transform(fitting[self.retrieval_features]))
        self.fitting_summary = {'actual_fitting_rows':len(fitting),'actual_fitting_people':fitting.group_key.nunique(),
            'new_native_base_fits':0,'fitting_row_keys':fitting.row_key.tolist(),
            'population_artifact_stored_personal_reports':0,'synthetic_rows':0}
        return self

    def transform(self,frame):
        return self.scaler.transform(self.imputer.transform(frame[self.retrieval_features]))

    def probabilities(self,queries,episodes):
        if list(queries)!=self.input_features or len(queries)!=len(episodes):
            raise ValueError('Predict requires exactly the input features and one causal packet per query')
        probabilities = np.exp(self.base.logits(queries).numpy())
        encoded = self.transform(queries)
        evidence = []
        c = self.candidate
        for n,episode in enumerate(episodes):
            ages = validate_episode(queries.iloc[[n]],episode,c['scope'])
            support = episode['support_features']
            mass,alpha = 0.,0.
            if len(support):
                observed = np.asarray([int(label.removeprefix('Borg ')) for label in episode['support_labels']])
                prior = support.prior_borg.to_numpy(float)
                if not np.isin(observed,np.arange(11)).all() or not np.isin(prior,np.arange(11)).all():
                    raise ValueError('Memory uses actual integer Borg reports on the native scale')
                delta = (observed-prior+10).astype(int)
                distance = np.mean((self.transform(support)-encoded[n])**2,axis=1)
                weights = np.exp(-distance/(2*c['bandwidth']**2)-ages/c['recency_minutes'])
                mass = float(weights.sum())
                if mass>0 and c['strength']:
                    histogram = np.bincount(delta,weights=weights,minlength=21)/mass
                    alpha = c['strength']*mass/(mass+c['mass_shrinkage'])
                    probabilities[n] = (1-alpha)*probabilities[n]+alpha*histogram
            evidence.append({'support_count':len(support),'weight_mass':mass,'mixture_weight':alpha})
        assert np.isfinite(probabilities).all()
        np.testing.assert_allclose(probabilities.sum(axis=1),1.,atol=1e-12)
        return probabilities,evidence

    def predict(self,queries,episodes):
        probabilities,_ = self.probabilities(queries,episodes)
        priority = self.base.priority
        delta = priority[probabilities[:,priority].argmax(axis=1)]-10
        current = np.clip(queries.prior_borg.to_numpy(int)+delta,0,10)
        return np.asarray([f'Borg {value}' for value in current])


def read_cache(inputs,member,number,fit,val):
    return native.read_base_cache(inputs['base_inputs']['previous_inputs'],member,number,fit,val)


def save(report):
    path = DIRECTORY/'selection.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(path)


def select():
    inputs = load_inputs()
    signature = fingerprint(inputs)
    train = inputs['train']
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY/'folds').mkdir(exist_ok=True)
    report = {**signature,'version':1,'status':'running','plan':plan(),'results':[],
        'train_row_keys':train.row_key.tolist(),'evaluation_denominator':487,'test_denominator':179,
        'test_used_for_selection':False,'minimum_cv_for_new_test_evaluation':.65,'target_accuracy':.8,
        'new_native_base_fits':0,'native_full_base_classifiers_reused':10,'synthetic_training_rows':0,
        'population_artifact_stored_personal_reports':0,'source_rows_fitted_in_this_study':0,
        'policy':'36fixed recipes:2inherited plus2fresh zero-memory controls and32personal kernel memories. '
            'Fit imputer/scaler only to outer-fitting people. Runtime observed transitions from same-person '
            'same-session reports at least1minute earlier; optional same task. Query outcome/future reports '
            'cannot cross inference boundary. Gaussian mean-squared standardized feature distance, '
            '10minute recency, mass/(mass+1) shrinkage; no learned residual or SGD repetition. '
            'Keep original integer delta argmax/tie order then clip Borg0-10,487/179cohort and5personfolds.'}
    path = DIRECTORY/'selection.json'
    if path.exists():
        report = json.loads(path.read_text())
        assert all(report.get(k)==v for k,v in signature.items()) and report['plan']==plan()
        assert report['train_row_keys']==train.row_key.tolist()
    else:
        (DIRECTORY/'selection-source.py').write_bytes(Path(__file__).read_bytes())
        save(report)
    if report['status']=='complete':
        return report
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    predictions = {c['id']:np.empty(len(train),object) for c in plan()[2:]}
    details = {c['id']:[] for c in plan()[2:]}
    for member in ('core','cat'):
        for number,(fit,val) in enumerate(folds):
            fitting,validation = train.iloc[fit],train.iloc[val]
            assert set(fitting.group_key).isdisjoint(validation.group_key)
            cache = read_cache(inputs,member,number,fit,val)
            before = joblib.hash(cache)
            episode_cache = {}
            for c in (c for c in plan()[2:] if c['member']==member):
                fold_path = DIRECTORY/'folds'/f"{c['id']}-fold-{number}.json"
                if fold_path.exists():
                    saved = json.loads(fold_path.read_text())
                    assert saved['signature']==signature and saved['candidate']==c
                    assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
                else:
                    model = TransitionMemoryBorg(c).fit(fitting,cache)
                    key = (c['scope'],c['retrieval_features'])
                    if key not in episode_cache:
                        episode_cache[key] = make_episodes(validation.drop(columns='label'),validation,
                            inputs['memory_manifest'],c['scope'],model.input_features)
                    episodes = episode_cache[key]
                    queries = validation[model.input_features]
                    predicted = model.predict(queries,episodes).tolist()
                    _,counts = model.probabilities(queries,episodes)
                    if not c['strength']:
                        np.testing.assert_array_equal(predicted,cache['base'].predict(queries))
                        old = inputs['parent_selection']['results'][0 if member=='core' else 1]
                        np.testing.assert_array_equal(predicted,np.asarray(old['oof_predictions'])[val])
                    saved = {'signature':signature,'candidate':c,'fold_number':number,
                        'fit_row_keys':fitting.row_key.tolist(),'validation_row_keys':validation.row_key.tolist(),
                        'predicted':predicted,'causal_memory_evidence':counts,'fitting_summary':model.fitting_summary}
                    fold_path.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\n',encoding='utf-8')
                predictions[c['id']][val] = saved['predicted']
                details[c['id']].append(saved)
            assert joblib.hash(cache)==before
            print(f'Actual causal-memory inference:{member} fold{number+1}/5,17recipes',flush=True)
    for c in plan():
        if any(r['candidate']==c for r in report['results']):
            continue
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['parent_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])
            predicted,fold_details = np.asarray(old['oof_predictions']),[]
        else:
            predicted,fold_details = predictions[c['id']],details[c['id']]
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report['results'].append({'candidate':c,'accuracy_mean':float(np.mean(scores)),
            'fold_accuracy':scores,'pooled_oof_accuracy':float(accuracy_score(train.label,predicted)),
            'oof_predictions':predicted.tolist(),'folds':fold_details})
        winner = max(report['results'],key=lambda r:r['accuracy_mean'])
        report.update(winner_id=winner['candidate']['id'],best_cv_accuracy=winner['accuracy_mean'])
        save(report)
        print(f"Actual causal-memory recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report


if __name__=='__main__':
    import fatigue_causal_transition_memory as implementation
    implementation.select()
