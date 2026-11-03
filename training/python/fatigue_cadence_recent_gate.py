"""Measured recent native HR extends only the native-private gate context."""
from __future__ import annotations
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
import fatigue_cadence_binary_gate as previous
import cadence_recent_gate_inputs as added
from public_sources import digest

DIRECTORY = previous.DIRECTORY.parent/'cadence-recent-native-gate-80-v1'
DOCS = previous.DOCS
PROPOSAL = DOCS/'cadence-recent-native-gate-plan.json'
PARENT_AUDIT = DOCS/'cadence-binary-gate-verification.json'
INPUT_AUDIT = DOCS/'cadence-recent-gate-input-verification.json'
native,prepared,source,COUNTS = previous.native,previous.prepared,previous.source,previous.COUNTS
ChangeGateNetwork,state_values = previous.ChangeGateNetwork,previous.state_values
gate_logit,recombine = previous.gate_logit,previous.recombine
_RUNTIME = None


class CadenceBinaryGateBorg(previous.CadenceBinaryGateBorg):
    """Reuse the frozen851-pair objective with sixteen private context inputs."""


def plan():
    result = [{'id':f'recent-gate-{n:03d}','algorithm':'previous_real_control',
        'parent_candidate_id':f'cadence-binary-gate-{n:03d}'} for n in range(6)]
    for member in ('core','cat'):
        for weight in (0.,.1):
            result.append({'id':f'recent-gate-{len(result):03d}','algorithm':'cadence_recent_native_gate',
                'member':member,'auxiliary_weight':weight,'epochs':80,'learning_rate':.003,'weight_decay':.1,
                'correction_penalty':1.,'random_seed':42,'source_target':'actual_current_unequal_prior_original6to20',
                'native_target':'original_integer_delta_distribution_with_frozen_nonzero_conditional'})
    return result


def enrich(frame,cache):
    matched = cache.set_index('row_key').loc[frame.row_key]
    np.testing.assert_array_equal(matched.group_key.to_numpy(),frame.group_key.to_numpy())
    result = frame.copy()
    for name in added.COLUMNS:
        assert name not in result
        result[name] = matched[name].to_numpy()
    pd.testing.assert_frame_equal(result[frame.columns],frame)
    return result


def load_inputs():
    old = previous.load_inputs()
    path = previous.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==6
    assert all(selected.get(k)==v for k,v in previous.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(path)
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_binary_gate.py'))
    cache,manifest = added.load()
    audit = json.loads(INPUT_AUDIT.read_text())
    assert audit['verification']=='passed' and audit['native_cells_independently_rebuilt']==audit['native_clocks_verified']==666
    assert audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_recent_gate_inputs.py'))
    assert audit['preparation_code_sha256']==digest(Path(added.__file__))
    assert audit['provenance_sha256']==digest(added.DIRECTORY/'provenance.json')
    assert audit['native_dataset_sha256']==digest(added.DIRECTORY/'native.csv')
    declared = json.loads(PROPOSAL.read_text())
    assert declared['implementation_code_sha256']==digest(Path(__file__)) and declared['plan']==plan()
    context = old['context_features']+added.COLUMNS
    assert len(old['context_features'])==13 and len(context)==16
    return {**old,'previous_inputs':old,'previous_selection':selected,'context_features':context,
        'frame':enrich(old['frame'],cache),'train':enrich(old['train'],cache),'test':enrich(old['test'],cache),
        'recent_input_manifest':manifest}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':previous.fingerprint(inputs['previous_inputs']),
        'previous_selection_sha256':digest(previous.DIRECTORY/'selection.json'),'previous_verification_sha256':digest(PARENT_AUDIT),
        'recent_input_provenance_sha256':digest(added.DIRECTORY/'provenance.json'),'input_audit_sha256':digest(INPUT_AUDIT),
        'recent_input_dataset_sha256':digest(added.DIRECTORY/'native.csv'),
        'proposal_sha256':digest(PROPOSAL),'recent_preparation_code_sha256':digest(Path(added.__file__)),
        'frozen_gate_implementation_sha256':digest(Path(previous.__file__)),
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
        model = CadenceBinaryGateBorg(c).fit(fitting,inputs['gate_source'],inputs['specifications'][member],inputs['context_features'],cache)
        predicted = model.predict(validation[model.input_features]).tolist()
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(validation[model.input_features]),predicted)
        saved = {'signature':signature,'candidate':c,'fold':n,'fit_row_keys':fitting.row_key.tolist(),
            'validation_row_keys':validation.row_key.tolist(),'predicted':predicted,'model_sha256':digest(artifact),
            'training_summary':model.training_summary,'normalization_summary':model.normalization_summary,'loss_endpoints':model.loss_endpoints}
        path.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(f"Actual recent native-context fit:{c['id']} fold{n+1}/5",flush=True)



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
        'new_joint_network_fits':20,'new_native_base_fits':0,'frozen_native_base_caches_reused':10,
        'actual_source_fitting_pairs_available':851,'source_reserved_pairs_not_fitted':206,'synthetic_rows':0,
        'policy':'Fixed10recipes:6inherited controls plus2frozen native bases*source weights0/.1. Add only3measured recent native HR/context inputs to the old13private inputs. The851source pairs,shared encoder and source normalization remain unchanged. Source current-bout HR or native-private rows are not fabricated. Keep80epochs,penalty1,optimizer.003/decay.1,all487/179and exact Borg scoring.'}
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
        print(f"Actual recent native-context recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report



if __name__=='__main__':
    import fatigue_cadence_recent_gate as implementation
    implementation.select()
