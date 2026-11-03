"""Create the readable physiology-gate implementation from the frozen gate fit."""
import ast
from pathlib import Path
import fatigue_public_change_gate as frozen

root = Path(__file__).parent
old = Path(frozen.__file__).read_text()
tree = ast.parse(old)
cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PublicChangeGateBorg')
fit_node = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='fit')
fit = '\n'.join(old.splitlines()[fit_node.lineno-1:fit_node.end_lineno])+'\n'
changes = {
    '2287':'851','1927':'727',"'excluded_single_class_sts_pairs':49":"'other_source_domains_fitted':0",
    "'source_reserved_pairs_not_fitted':312":"'source_reserved_pairs_not_fitted':206",
    'self.base.input_features+self.context_features':'self.base.input_features+self.context_features+list(prepared.NATIVE_COLUMNS.values())',
    'part[[source.PRIOR,source.SECOND]].copy()':'part[prepared.FEATURES].copy()',
}
for before,after in changes.items():
    assert before in fit,before
    fit = fit.replace(before,after)
header = '''"""Actual history and prior physiology learn a separate CADENCE change head."""
from __future__ import annotations
import copy
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from types import SimpleNamespace
import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from torch import nn
import cadence_binary_gate_inputs as prepared
import fatigue_change_gate_regularization as previous
import fatigue_public_change_gate as frozen
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = previous.DIRECTORY.parent/'cadence-binary-physiology-gate-80-v1'
DOCS = previous.DOCS
PROPOSAL = DOCS/'cadence-binary-physiology-gate-plan.json'
PARENT_AUDIT = DOCS/'change-gate-regularization-verification.json'
INPUT_AUDIT = DOCS/'cadence-binary-gate-input-verification.json'
COUNTS = {'cadence':851}
native = previous.native
source = SimpleNamespace(TARGETS={'cadence':'current_rpe'},PRIOR='prior',SECOND='second')
gate_logit,recombine = frozen.gate_logit,frozen.recombine
_RUNTIME = None


def plan():
    result = [{'id':f'cadence-binary-gate-{n:03d}','algorithm':'previous_real_control',
        'parent_candidate_id':key} for n,key in enumerate(['gate-regularization-000','gate-regularization-001'])]
    for member in ('core','cat'):
        for weight in (0.,.1):
            result.append({'id':f'cadence-binary-gate-{len(result):03d}','algorithm':'cadence_physiology_binary_gate',
                'member':member,'auxiliary_weight':weight,'epochs':80,'learning_rate':.003,'weight_decay':.1,
                'correction_penalty':1.,'random_seed':42,'source_target':'actual_current_unequal_prior_original6to20',
                'native_target':'original_integer_delta_distribution_with_frozen_nonzero_conditional'})
    return result


def enrich(frame,cache):
    matched = cache.set_index('row_key').loc[frame.row_key]
    np.testing.assert_array_equal(matched.group_key.to_numpy(),frame.group_key.to_numpy())
    result = frame.copy()
    for name in prepared.NATIVE_COLUMNS.values():
        assert name not in result
        result[name] = matched[name].to_numpy()
    pd.testing.assert_frame_equal(result[frame.columns],frame)
    return result


def load_inputs():
    old = previous.load_inputs()
    path = previous.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==18
    assert all(selected.get(k)==v for k,v in previous.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(path)
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_change_gate_regularization.py'))
    fitting,reserved,cache,manifest = prepared.load()
    audit = json.loads(INPUT_AUDIT.read_text())
    assert audit['verification']=='passed' and audit['actual_source_pairs_independently_rebuilt']==1057
    assert audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_binary_gate_inputs.py'))
    assert audit['preparation_code_sha256']==digest(Path(prepared.__file__))
    assert audit['provenance_sha256']==digest(prepared.DIRECTORY/'provenance.json')
    assert audit['source_dataset_sha256']==digest(prepared.DIRECTORY/'source.csv')
    assert audit['native_dataset_sha256']==digest(prepared.DIRECTORY/'native.csv')
    declared = json.loads(PROPOSAL.read_text())
    assert declared['implementation_code_sha256']==digest(Path(__file__)) and declared['plan']==plan()
    return {**old,'previous_inputs':old,'previous_selection':selected,
        'frame':enrich(old['frame'],cache),'train':enrich(old['train'],cache),'test':enrich(old['test'],cache),
        'gate_source':fitting,'reserved_gate_source':reserved,'gate_input_manifest':manifest}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':previous.fingerprint(inputs['previous_inputs']),
        'previous_selection_sha256':digest(previous.DIRECTORY/'selection.json'),'previous_verification_sha256':digest(PARENT_AUDIT),
        'input_provenance_sha256':digest(prepared.DIRECTORY/'provenance.json'),'input_audit_sha256':digest(INPUT_AUDIT),
        'proposal_sha256':digest(PROPOSAL),'source_preparation_code_sha256':digest(Path(prepared.__file__)),
        'frozen_gate_implementation_sha256':digest(Path(frozen.__file__)),
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),'worker_processes':2}


def state_values(frame):
    columns = prepared.FEATURES if 'prior' in frame else ['prior_borg','prior2_borg',*prepared.NATIVE_COLUMNS.values()]
    result = frame[columns].copy()
    result.columns = prepared.FEATURES
    assert result.prior.notna().all()
    return result


class ChangeGateNetwork(frozen.ChangeGateNetwork):
    def __init__(self,context_width):
        nn.Module.__init__(self)
        self.encoder = nn.Sequential(nn.Linear(11,8),nn.Tanh(),nn.Linear(8,8),nn.Tanh())
        self.corrector = nn.Sequential(nn.Linear(context_width+9,8),nn.Tanh(),nn.Linear(8,1))
        self.source_heads = nn.ModuleDict({'cadence':nn.Linear(8,1)})
        nn.init.zeros_(self.corrector[-1].weight)
        nn.init.zeros_(self.corrector[-1].bias)


class CadenceBinaryGateBorg(frozen.PublicChangeGateBorg):
    def prepare_normalizers(self,frame,external):
        self.history_normalizers,self.normalization_summary = {},{}
        for name,part in {'native':frame,'cadence':external}.items():
            values = state_values(part)
            imputer = SimpleImputer(strategy='median',keep_empty_features=True)
            scaler = StandardScaler().fit(imputer.fit_transform(values))
            self.history_normalizers[name] = imputer,scaler
            self.normalization_summary[name] = {'fitting_rows':len(part),'fitting_people':part.group_key.nunique(),
                'actual_missing_inputs':values.isna().sum().astype(int).to_dict(),'numeric_columns':6,'unscaled_availability_bits':5}

    def history_transform(self,frame,domain='native'):
        values = state_values(frame)
        imputer,scaler = self.history_normalizers[domain]
        result = np.column_stack([scaler.transform(imputer.transform(values)),values.iloc[:,1:].isna().to_numpy(float)])
        assert result.shape[1]==11 and np.isfinite(result).all() and np.isin(result[:,6:],[0.,1.]).all()
        return torch.tensor(result,dtype=torch.float32)

'''
# The fit method keeps the fully inspected optimizer and gate probability code.
tail = '''

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
    for c in (c for c in plan()[2:] if c['member']==member):
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
        path.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\\n',encoding='utf-8')
        print(f"Actual CADENCE physiology-binary fit:{c['id']} fold{n+1}/5",flush=True)


def save(report):
    path = DIRECTORY/'selection.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\\n',encoding='utf-8')
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
        'policy':'Fixed6recipes:2inherited global controls plus2frozen native bases*source weights0/.1. '
            'Add actually observed prior physiology to the shared actual-two-prior encoder. Numeric6inputs '
            'use separate fitting-only native/source normalizers;5real availability flags stay binary. '
            'Source current-bout HR,exact response ages/native phases and scale equivalence are not assumed. '
            'Keep80epochs,penalty1,optimizer.003/decay.1,original487/179and exact native Borg scoring.'}
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
        print(f"Actual CADENCE physiology-binary recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report


if __name__=='__main__':
    import fatigue_cadence_binary_gate as implementation
    implementation.select()
'''
code = header+fit+tail
compile(code,'fatigue_cadence_binary_gate.py','exec')
path = root/'fatigue_cadence_binary_gate.py'
if path.exists():
    assert path.read_text()==code
else:
    path.write_text(code,encoding='utf-8')
print('Prepared static CADENCE gate with six numeric inputs and five observed availability flags',flush=True)
