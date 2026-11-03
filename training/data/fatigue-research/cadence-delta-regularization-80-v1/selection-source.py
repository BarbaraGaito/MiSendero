"""Stronger native full-delta residual regularization on real public observations."""
from __future__ import annotations
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import joblib
import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
import fatigue_cadence_full_delta as previous
from public_sources import digest

DIRECTORY = previous.DIRECTORY.parent/'cadence-delta-regularization-80-v1'
DOCS = previous.DOCS
PROPOSAL = DOCS/'cadence-delta-regularization-plan.json'
PARENT_AUDIT = DOCS/'cadence-full-delta-verification.json'
DIAGNOSTIC = DOCS/'cadence-full-delta-generalization-diagnostic.json'
INPUT_AUDIT = previous.INPUT_AUDIT
native,prepared,source,COUNTS,added = previous.native,previous.prepared,previous.source,previous.COUNTS,previous.added
state_values,FullDeltaNetwork = previous.state_values,previous.FullDeltaNetwork
_RUNTIME = None


class FullDeltaCadenceBorg(previous.FullDeltaCadenceBorg):
    """Frozen objective and architecture;candidate supplies the stronger penalty."""


def plan():
    result = [{'id':f'delta-regularization-{n:03d}','algorithm':'previous_real_control',
        'parent_candidate_id':f'cadence-full-delta-{key:03d}'} for n,key in enumerate((0,1,7,9,11,13))]
    for member in ('core','cat'):
        for weight in (0.,.1):
            for penalty in (10.,100.):
                result.append({'id':f'delta-regularization-{len(result):03d}','algorithm':'cadence_delta_regularization',
                    'member':member,'auxiliary_weight':weight,'epochs':80,'learning_rate':.003,'weight_decay':.1,
                    'correction_penalty':penalty,'random_seed':42,'source_target':'actual_current_unequal_prior_original6to20',
                    'native_target':'original_integer_delta_cross_entropy_21','residual_outputs':21})
    return result


def load_inputs():
    old = previous.load_inputs()
    path = previous.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==14
    assert all(selected.get(k)==v for k,v in previous.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(path)
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_full_delta.py'))
    diagnostic = json.loads(DIAGNOSTIC.read_text())
    assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(path)
    assert diagnostic['verification_sha256']==digest(PARENT_AUDIT)
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_cadence_full_delta_generalization.py'))
    assert len(diagnostic['regularization_trends'])==4 and all(r['penalty1_outperformed_point1'] for r in diagnostic['regularization_trends'])
    assert all(r['mean_fit_corrected_nll']<r['mean_fit_original_nll'] and r['mean_validation_corrected_nll']>r['mean_validation_original_nll'] for r in diagnostic['metrics'].values())
    declared = json.loads(PROPOSAL.read_text())
    assert declared['implementation_code_sha256']==digest(Path(__file__)) and declared['plan']==plan()
    return {**old,'previous_inputs':old,'previous_selection':selected}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':previous.fingerprint(inputs['previous_inputs']),
        'previous_selection_sha256':digest(previous.DIRECTORY/'selection.json'),'previous_verification_sha256':digest(PARENT_AUDIT),
        'input_audit_sha256':digest(INPUT_AUDIT),'proposal_sha256':digest(PROPOSAL),'diagnostic_sha256':digest(DIAGNOSTIC),
        'frozen_full_delta_implementation_sha256':digest(Path(previous.__file__)),
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),'worker_processes':2}


def read_cache(inputs,member,number,fit,val):
    return previous.read_cache(inputs['previous_inputs'],member,number,fit,val)



def initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)



def fit_group(job):
    member,n,fit,val = job
    inputs,signature = _RUNTIME
    fitting,validation = inputs['train'].iloc[fit],inputs['train'].iloc[val]
    assert set(fitting.group_key).isdisjoint(validation.group_key)
    cache = read_cache(inputs,member,n,fit,val)
    for c in (c for c in plan()[6:] if c['member']==member):
        path = DIRECTORY/'folds'/f"{c['id']}-fold-{n}.json"
        artifact = path.with_suffix('.joblib')
        if path.exists():
            saved = json.loads(path.read_text())
            assert saved['signature']==signature and saved['candidate']==c and saved['model_sha256']==digest(artifact)
            assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
            continue
        model = FullDeltaCadenceBorg(c).fit(fitting,inputs['gate_source'],inputs['specifications'][member],inputs['context_features'],cache)
        predicted = model.predict(validation[model.input_features]).tolist()
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(validation[model.input_features]),predicted)
        saved = {'signature':signature,'candidate':c,'fold':n,'fit_row_keys':fitting.row_key.tolist(),
            'validation_row_keys':validation.row_key.tolist(),'predicted':predicted,'model_sha256':digest(artifact),
            'training_summary':model.training_summary,'normalization_summary':model.normalization_summary,'loss_endpoints':model.loss_endpoints}
        path.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(f"Actual stronger delta regularization fit:{c['id']} fold{n+1}/5",flush=True)



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
        'new_joint_network_fits':40,'new_native_base_fits':0,'frozen_native_base_caches_reused':10,
        'actual_source_fitting_pairs_available':851,'source_reserved_pairs_not_fitted':206,'synthetic_rows':0,
        'policy':'Fixed14recipes:6inherited global/penalty1controls plus2native bases*source0/.1*penalty10/100. Only the declared residual penalty changes;keep frozen study58fit/architecture,851source pairs,11shared inputs,16private native inputs,80epochs/seed42/AdamW.003/decay.1 and10old base caches. Exact native Borg scoring on original487/179,.65CVtestgate,no synthetic examples or fabricated source context.'}
    if path.exists():
        report = json.loads(path.read_text())
        assert all(report.get(k)==v for k,v in signature.items()) and report['plan']==plan()
    else:
        (DIRECTORY/'selection-source.py').write_bytes(Path(__file__).read_bytes())
        save(report)
    if report['status']=='complete':
        return report
    folds = list(GroupKFold(5).split(train,groups=train.group_key))
    with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
        jobs = [(m,n,fit,val) for m in ('core','cat') for n,(fit,val) in enumerate(folds)]
        for future in as_completed([pool.submit(fit_group,job) for job in jobs]):
            future.result()
    for c in plan():
        if any(r['candidate']==c for r in report['results']):
            continue
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['previous_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])
            predicted,details = np.asarray(old['oof_predictions']),[]
        else:
            predicted,details = np.empty(487,object),[]
            for n,(_,val) in enumerate(folds):
                saved = json.loads((DIRECTORY/'folds'/f"{c['id']}-fold-{n}.json").read_text())
                assert saved['signature']==signature and saved['candidate']==c
                predicted[val] = saved['predicted']
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report['results'].append({'candidate':c,'accuracy_mean':float(np.mean(scores)),'fold_accuracy':scores,
            'pooled_oof_accuracy':float(accuracy_score(train.label,predicted)),
            'oof_predictions':predicted.tolist(),'folds':details})
        winner = max(report['results'],key=lambda r:r['accuracy_mean'])
        report.update(winner_id=winner['candidate']['id'],best_cv_accuracy=winner['accuracy_mean'])
        save(report)
        print(f"Actual stronger delta regularization recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report



if __name__=='__main__':
    import fatigue_cadence_delta_regularization as implementation
    implementation.select()
