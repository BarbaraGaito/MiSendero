"""Bounded correction-penalty tuning of the audited real-public change gate."""
from __future__ import annotations
import copy
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import joblib
import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_public_change_gate as parent
from public_sources import digest

DIRECTORY = parent.DIRECTORY.parent/'change-gate-regularization-80-v1'
DOCS = parent.DOCS
PROPOSAL = DOCS/'change-gate-regularization-plan.json'
PARENT_AUDIT = DOCS/'public-change-gate-verification.json'
DIAGNOSTIC = DOCS/'public-change-gate-margin-diagnostic.json'
native,source,COUNTS,ChangeGateNetwork = parent.native,parent.source,parent.COUNTS,parent.ChangeGateNetwork
history_values,gate_logit,recombine = parent.history_values,parent.gate_logit,parent.recombine
_RUNTIME = None


def plan():
    result = [{'id':f'gate-regularization-{n:03d}','algorithm':'previous_real_control',
        'parent_candidate_id':key} for n,key in enumerate(['public-change-gate-000','public-change-gate-001',
            'public-change-gate-004','public-change-gate-005','public-change-gate-007','public-change-gate-008'])]
    for member in ('core','cat'):
        for weight in (0.,.1):
            old = next(c for c in parent.plan()[4:] if c['member']==member and c['auxiliary_weight']==weight)
            for penalty in (0.,.1,1.):
                c = copy.deepcopy(old)
                c.update(id=f'gate-regularization-{len(result):03d}',algorithm='regularized_public_binary_change_gate',
                    correction_penalty=penalty)
                result.append(c)
    return result


def load_inputs():
    old = parent.load_inputs()
    path = parent.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==10
    assert all(selected.get(k)==value for k,value in parent.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(path)
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_public_change_gate.py'))
    assert proof['all_30_fold_artifacts_recomputed'] and proof['independent_joint_refits']==20
    diagnostic = json.loads(DIAGNOSTIC.read_text())
    assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(path)
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_public_change_gate_margins.py'))
    assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_test_predictions_computed']==0
    assert all(row['final_native_borg_predictions_changed']==0 for row in diagnostic['results'])
    declared = json.loads(PROPOSAL.read_text())
    assert declared['implementation_code_sha256']==digest(Path(__file__)) and declared['plan']==plan()
    return {**old,'parent_inputs':old,'parent_selection':selected}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'parent_signature':parent.fingerprint(inputs['parent_inputs']),
        'previous_selection_sha256':digest(parent.DIRECTORY/'selection.json'),
        'previous_verification_sha256':digest(PARENT_AUDIT),'margin_diagnostic_sha256':digest(DIAGNOSTIC),
        'proposal_sha256':digest(PROPOSAL),'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),
        'fitting_implementation_sha256':digest(Path(parent.__file__)),'worker_processes':2}


class RegularizedChangeGateBorg(parent.PublicChangeGateBorg):
    pass


def read_cache(inputs,member,number,fit,val):
    return parent.read_cache(inputs,member,number,fit,val)


def initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def fit_group(job):
    member,number,fit,val = job
    inputs,signature = _RUNTIME
    fitting,validation = inputs['train'].iloc[fit],inputs['train'].iloc[val]
    assert set(fitting.group_key).isdisjoint(validation.group_key)
    cache = read_cache(inputs,member,number,fit,val)
    before = joblib.hash(cache)
    for c in (c for c in plan()[6:] if c['member']==member):
        path = DIRECTORY/'folds'/f"{c['id']}-fold-{number}.json"
        artifact = path.with_suffix('.joblib')
        if path.exists():
            saved = json.loads(path.read_text())
            assert saved['signature']==signature and saved['candidate']==c
            assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
            assert saved['model_sha256']==digest(artifact)
            continue
        model = RegularizedChangeGateBorg(c).fit(fitting,inputs['gate_source'],inputs['specifications'][member],inputs['context_features'],cache)
        predicted = model.predict(validation[model.input_features]).tolist()
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(validation[model.input_features]),predicted)
        saved = {'signature':signature,'candidate':c,'fold':number,'fit_row_keys':fitting.row_key.tolist(),
            'validation_row_keys':validation.row_key.tolist(),'predicted':predicted,'model_sha256':digest(artifact),
            'training_summary':model.training_summary,'normalization_summary':model.normalization_summary,'loss_endpoints':model.loss_endpoints}
        path.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(f"Actual gate-penalty fit:{c['id']} fold{number+1}/5",flush=True)
    assert joblib.hash(cache)==before


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
        'test_used_for_selection':False,'minimum_cv_for_new_test_evaluation':.65,'target_accuracy':.8,
        'new_joint_network_fits':60,'new_native_base_fits':0,'frozen_native_base_caches_reused':10,
        'actual_source_fitting_pairs_available':2287,'excluded_single_class_sts_pairs':49,'source_reserved_pairs_not_fitted':312,
        'synthetic_rows':0,'policy':'Fixed18recipes:6inherited controls(global2and4matched penalty10controls), '
            '2native bases*2source weights0/.1*3new correction penalties0/.1/1. Only penalty changes from '
            'the frozen80epoch gate implementation. Same initialization/optimizer/preprocessing/crossfit '
            'offsets/native conditional probabilities and actual4source heads. Preserve487/179cases and '
            'exact native Borg scoring. No synthetic data,source pooling or test-directed expansion.'}
    if path.exists():
        report = json.loads(path.read_text())
        assert all(report.get(k)==value for k,value in signature.items()) and report['plan']==plan()
        assert report['train_row_keys']==train.row_key.tolist()
    else:
        (DIRECTORY/'selection-source.py').write_bytes(Path(__file__).read_bytes())
        save(report)
    if report['status']=='complete':
        return report
    folds = list(GroupKFold(5).split(train,groups=train.group_key))
    jobs = [(member,n,fit,val) for member in ('core','cat') for n,(fit,val) in enumerate(folds)]
    with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
        for future in as_completed([pool.submit(fit_group,job) for job in jobs]):
            future.result()
    for c in plan():
        if any(row['candidate']==c for row in report['results']):
            continue
        if c['algorithm']=='previous_real_control':
            old = next(row for row in inputs['parent_selection']['results'] if row['candidate']['id']==c['parent_candidate_id'])
            predicted,details = np.asarray(old['oof_predictions']),[]
        else:
            predicted,details = np.empty(487,object),[]
            for n,(_,val) in enumerate(folds):
                stored = json.loads((DIRECTORY/'folds'/f"{c['id']}-fold-{n}.json").read_text())
                assert stored['signature']==signature and stored['candidate']==c
                predicted[val] = stored['predicted']
                details.append(stored)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report['results'].append({'candidate':c,'accuracy_mean':float(np.mean(scores)),'fold_accuracy':scores,
            'pooled_oof_accuracy':float(accuracy_score(train.label,predicted)),
            'oof_predictions':predicted.tolist(),'folds':details})
        winner = max(report['results'],key=lambda row:row['accuracy_mean'])
        report.update(winner_id=winner['candidate']['id'],best_cv_accuracy=winner['accuracy_mean'])
        save(report)
        print(f"Actual gate-penalty recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report


if __name__=='__main__':
    import fatigue_change_gate_regularization as implementation
    implementation.select()
