"""Exact original delta distribution, flat versus observed-change factorization."""
from __future__ import annotations
import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import joblib
import numpy as np
from catboost import CatBoostClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

import fatigue_causal_transition_memory as predecessor
from fatigue_catboost import categorical_features
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = predecessor.DIRECTORY.parent/'observed-change-factorization-80-v1'
DOCS = predecessor.DOCS
PROPOSAL = DOCS/'observed-change-factorization-plan.json'
PARENT_AUDIT = DOCS/'causal-transition-memory-verification.json'
REVIEW = DOCS/'native-change-factorization-review.json'
PHYSIOLOGY = ['hr_last','hr_change_after_prior','hr_recent_slope']
FLOOR = .0001
_RUNTIME = None


def plan():
    result = [{'id':f'observed-change-{n:03d}','algorithm':'previous_real_control',
        'parent_candidate_id':key} for n,key in enumerate(['transition-memory-000','transition-memory-001'])]
    for member in ('core','cat'):
        for features in ('history','history_physiology'):
            for structure in ('flat','factorized'):
                result.append({'id':f'observed-change-{len(result):03d}','algorithm':'observed_change_distribution',
                    'member':member,'feature_set':features,'structure':structure,'probability_floor':FLOOR,
                    'native_target':'actual_current_minus_actual_prior_integer','random_seed':42,
                    'native_hyperparameters':'unchanged_original_member_specification'})
    return result


def load_inputs():
    old = predecessor.load_inputs()
    path = predecessor.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==36
    assert all(selected.get(k)==v for k,v in predecessor.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(path)
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_causal_transition_memory.py'))
    assert proof['all_36_oof_recipes_recomputed'] and proof['independent_fold_comparisons']==170
    review = json.loads(REVIEW.read_text())
    assert review['review']=='passed' and (review['observed_unchanged_queries'],review['observed_nonzero_queries'])==(229,258)
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_native_change_factorization.py'))
    proposal = json.loads(PROPOSAL.read_text())
    assert proposal['implementation_code_sha256']==digest(Path(__file__)) and proposal['plan']==plan()
    assert len(old['train'])==487 and len(old['test'])==179
    assert set(PHYSIOLOGY)<=set(old['train'])
    return {**old,'predecessor_inputs':old,'predecessor_selection':selected}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':predecessor.fingerprint(inputs['predecessor_inputs']),
        'previous_selection_sha256':digest(predecessor.DIRECTORY/'selection.json'),
        'previous_verification_sha256':digest(PARENT_AUDIT),'factorization_review_sha256':digest(REVIEW),
        'proposal_sha256':digest(PROPOSAL),'native_specifications':inputs['specifications'],
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),
        'worker_processes':2,'dependency_code_sha256':{name:digest(Path(__file__).with_name(name))
            for name in ('fatigue_catboost.py','fatigue_probability.py')}}


def actual_delta(frame):
    current = frame.label.str.removeprefix('Borg ').to_numpy(int)
    prior = frame.prior_borg.to_numpy(float)
    assert np.isin(current,np.arange(11)).all() and np.isin(prior,np.arange(11)).all()
    return current-prior.astype(int)


def features_for(candidate,specification):
    return list(dict.fromkeys(specification['features']+(PHYSIOLOGY if candidate['feature_set']=='history_physiology' else [])))


def estimator(member,specification,binary):
    if member=='core':
        return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),
            StandardScaler(),MLPClassifier(**specification['params'],random_state=42,early_stopping=False))
    return CatBoostClassifier(iterations=specification['iterations'],depth=specification['depth'],
        l2_leaf_reg=specification['l2_leaf_reg'],learning_rate=.03,loss_function='Logloss' if binary else 'MultiClass',
        boosting_type='Ordered',grow_policy='SymmetricTree',random_seed=42,thread_count=4,
        task_type='CPU',border_count=128,bootstrap_type='Bayesian',bagging_temperature=1.,
        random_strength=1.,nan_mode='Min',use_best_model=False,allow_writing_files=False,verbose=False)


class ObservedChangeBorg:
    def __init__(self,candidate):
        self.candidate = copy.deepcopy(candidate)

    def fit(self,frame,specification,observer=None):
        validate_calibration(frame)
        self.specification = copy.deepcopy(specification)
        self.input_features = features_for(self.candidate,specification)
        assert not set(self.input_features)&{'label','group_key','row_key'}
        delta = actual_delta(frame)
        self.models,self.stage_summary,self.convergence_warnings = {},{},[]
        if self.candidate['structure']=='flat':
            stages = [('flat',np.ones(len(frame),bool),delta,False)]
        else:
            changed = delta!=0
            assert changed.any() and (~changed).any()
            stages = [('change',np.ones(len(frame),bool),changed.astype(int),True),
                      ('magnitude',changed,delta[changed],False)]
        for name,mask,target,binary in stages:
            fitting = frame.loc[mask]
            model = estimator(self.candidate['member'],specification,binary)
            y = target.astype(str) if self.candidate['member']=='core' else target
            options = {'cat_features':categorical_features(self.input_features)} if self.candidate['member']=='cat' else {}
            with warnings.catch_warnings(record=True) as captured,threadpool_limits(limits=1):
                warnings.simplefilter('always',ConvergenceWarning)
                model.fit(fitting[self.input_features],y,**options)
            self.convergence_warnings.extend({'stage':name,'warning':str(w.message)} for w in captured if issubclass(w.category,ConvergenceWarning))
            self.models[name] = model
            self.stage_summary[name] = {'actual_fitting_rows':len(fitting),'actual_fitting_people':fitting.group_key.nunique(),
                'fit_row_keys':fitting.row_key.tolist(),'observed_target_classes':sorted(set(target.tolist())),
                'observed_target_counts':{str(int(k)):int(v) for k,v in zip(*np.unique(target,return_counts=True))}}
            if observer is not None:
                observer(name,fitting.copy(),np.asarray(target).copy())
        classes = self.models['flat'].classes_.astype(int) if 'flat' in self.models else np.sort(np.r_[0,self.models['magnitude'].classes_.astype(int)])
        self.priority = np.asarray((classes+10).tolist()+[i for i in range(21) if i not in classes+10],int)
        self.fitting_summary = {'actual_native_rows':len(frame),'actual_native_people':frame.group_key.nunique(),
            'actual_zero_changes':int((delta==0).sum()),'actual_nonzero_changes':int((delta!=0).sum()),
            'actual_negative_changes':int((delta<0).sum()),'estimator_fits':len(self.models),'synthetic_rows':0,
            'artificial_history_views':0,'test_outcomes_used':False,'separate_source_targets_fitted':0}
        return self

    def raw_probabilities(self,name,frame):
        model = self.models[name]
        with threadpool_limits(limits=1):
            if self.candidate['member']=='cat':
                return model.predict_proba(frame[self.input_features],thread_count=4)
            return model.predict_proba(frame[self.input_features])

    def probabilities(self,frame):
        if list(frame)!=self.input_features:
            raise ValueError('Prediction requires exactly the causal input features, without current truth or IDs')
        validate_calibration(frame)
        if 'flat' in self.models:
            values = np.full((len(frame),21),FLOOR)
            indices = self.models['flat'].classes_.astype(int)+10
            values[:,indices] = np.maximum(self.raw_probabilities('flat',frame),FLOOR)
            values /= values.sum(axis=1,keepdims=True)
        else:
            # Conditional probabilities occupy only nonzero original delta classes.
            conditional = np.full((len(frame),21),FLOOR)
            conditional[:,10] = 0.
            indices = self.models['magnitude'].classes_.astype(int)+10
            assert 10 not in indices
            conditional[:,indices] = np.maximum(self.raw_probabilities('magnitude',frame),FLOOR)
            conditional /= conditional.sum(axis=1,keepdims=True)
            gate = self.raw_probabilities('change',frame)
            gate_classes = self.models['change'].classes_.astype(int)
            assert set(gate_classes)=={0,1}
            values = gate[:,np.flatnonzero(gate_classes==1)[0],None]*conditional
            values[:,10] = gate[:,np.flatnonzero(gate_classes==0)[0]]
        np.testing.assert_allclose(values.sum(axis=1),1.,atol=1e-12)
        assert np.isfinite(values).all() and (values>=0).all()
        return values

    def predict(self,frame):
        probabilities = self.probabilities(frame)
        delta = self.priority[probabilities[:,self.priority].argmax(axis=1)]-10
        return np.asarray([f'Borg {int(borg)}' for borg in np.clip(frame.prior_borg.to_numpy(int)+delta,0,10)])


def initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def fit_fold(job):
    candidate,number,fit,val = job
    inputs,signature = _RUNTIME
    fitting,validation = inputs['train'].iloc[fit],inputs['train'].iloc[val]
    assert set(fitting.group_key).isdisjoint(validation.group_key)
    path = DIRECTORY/'folds'/f"{candidate['id']}-fold-{number}.json"
    model_path = path.with_suffix('.joblib')
    if path.exists():
        saved = json.loads(path.read_text())
        assert saved['signature']==signature and saved['candidate']==candidate
        assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
        assert saved['model_sha256']==digest(model_path)
        return
    model = ObservedChangeBorg(candidate).fit(fitting,inputs['specifications'][candidate['member']])
    predicted = model.predict(validation[model.input_features]).tolist()
    if candidate['feature_set']=='history' and candidate['structure']=='flat':
        old = inputs['predecessor_selection']['results'][0 if candidate['member']=='core' else 1]
        np.testing.assert_array_equal(predicted,np.asarray(old['oof_predictions'])[val])
    joblib.dump(model,model_path)
    np.testing.assert_array_equal(joblib.load(model_path).predict(validation[model.input_features]),predicted)
    saved = {'signature':signature,'candidate':candidate,'fold':number,'fit_row_keys':fitting.row_key.tolist(),
        'validation_row_keys':validation.row_key.tolist(),'predicted':predicted,'model_sha256':digest(model_path),
        'fitting_summary':model.fitting_summary,'stage_summary':model.stage_summary,
        'convergence_warnings':model.convergence_warnings}
    path.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f"Actual observed-change fit:{candidate['id']} fold{number+1}/5,stages{len(model.models)}",flush=True)


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
    path = DIRECTORY/'selection.json'
    report = {**signature,'version':1,'status':'running','plan':plan(),'results':[],
        'train_row_keys':train.row_key.tolist(),'evaluation_denominator':487,'test_denominator':179,
        'minimum_cv_for_new_test_evaluation':.65,'test_used_for_selection':False,'target_accuracy':.8,
        'new_candidate_fold_fits':40,'new_stage_estimator_fits':60,'synthetic_rows':0,
        'policy':'Fixed10recipes:2inherited controls and2members*2feature sets*2structures(flat/factorized). '
            'Use unchanged native member hyperparameters. Flat uses all original integer delta classes. '
            'Factorized uses actual binary nonzero-change labels on every outer-fitting report,then '
            'actual nonzero delta classes on that fitting subset. Preserve negative changes,actual priors, '
            'original487/179native cases,5whole-person folds,and exact delta argmax then Borg clipping. '
            'No generated examples,assumed zero labels,source pooling or test-directed tuning.'}
    if path.exists():
        report = json.loads(path.read_text())
        assert all(report.get(k)==v for k,v in signature.items()) and report['plan']==plan()
        assert report['train_row_keys']==train.row_key.tolist()
    else:
        (DIRECTORY/'selection-source.py').write_bytes(Path(__file__).read_bytes())
        save(report)
    if report['status']=='complete':
        return report
    folds = list(GroupKFold(5).split(train,groups=train.group_key))
    jobs = [(c,n,fit,val) for c in plan()[2:] for n,(fit,val) in enumerate(folds)]
    with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
        for future in as_completed([pool.submit(fit_fold,job) for job in jobs]):
            future.result()
    for c in plan():
        if any(r['candidate']==c for r in report['results']):
            continue
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['predecessor_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])
            predicted,details = np.asarray(old['oof_predictions']),[]
        else:
            predicted,details = np.empty(len(train),object),[]
            for n,(_,val) in enumerate(folds):
                stored = json.loads((DIRECTORY/'folds'/f"{c['id']}-fold-{n}.json").read_text())
                assert stored['signature']==signature and stored['candidate']==c
                predicted[val] = stored['predicted']
                details.append(stored)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report['results'].append({'candidate':c,'accuracy_mean':float(np.mean(scores)),
            'fold_accuracy':scores,'pooled_oof_accuracy':float(accuracy_score(train.label,predicted)),
            'oof_predictions':predicted.tolist(),'folds':details})
        winner = max(report['results'],key=lambda r:r['accuracy_mean'])
        report.update(winner_id=winner['candidate']['id'],best_cv_accuracy=winner['accuracy_mean'])
        save(report)
        print(f"Actual observed-change recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report


if __name__=='__main__':
    import fatigue_observed_change_factorization as implementation
    implementation.select()
