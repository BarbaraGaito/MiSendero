"""Domain-specific fitting-only predictor normalization; original outcomes intact."""
from __future__ import annotations
import copy
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

import fatigue_shoulder_history_joint as parent
from public_sources import digest

DIRECTORY = parent.DIRECTORY.parent/'domain-aligned-history-transfer-80-v1'
DOCS = parent.DOCS
PARENT_AUDIT = DOCS/'shoulder-history-joint-verification.json'
DIAGNOSTIC = DOCS/'shoulder-history-range-diagnostic.json'
PROPOSAL = DOCS/'domain-aligned-history-plan.json'
base,source,COMMON,SOURCE_COUNTS = parent.base,parent.source,parent.COMMON,parent.SOURCE_COUNTS
ShoulderHistoryNetwork = parent.ShoulderHistoryNetwork
_RUNTIME = None


def plan():
    result = [{'id':f'aligned-history-{i:03d}','algorithm':'previous_real_control','parent_candidate_id':key}
        for i,key in enumerate(['shoulder-joint-000','shoulder-joint-001','shoulder-joint-004','shoulder-joint-007'])]
    for old in parent.plan()[4:]:
        candidate = copy.deepcopy(old)
        candidate.update(id=f'aligned-history-{len(result):03d}',algorithm='joint_domain_aligned_history_residual',
            predictor_normalization='domain_fitting_numeric_zscore_binary_missing_indicators')
        result.append(candidate)
    return result


def load_inputs():
    inputs = parent.load_inputs()
    path = parent.DIRECTORY/'selection.json'
    selection = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selection['status']=='complete' and len(selection['results'])==10
    assert all(selection.get(k)==v for k,v in parent.fingerprint(inputs).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(path)
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_shoulder_history_joint.py'))
    assert proof['actual_native_joint_refits']==20 and proof['zero_new_weight_excludes_shoulder_labels']
    diagnostic = json.loads(DIAGNOSTIC.read_text())
    assert diagnostic['diagnostic']=='passed' and diagnostic['selection_sha256']==digest(path)
    assert diagnostic['new_predictive_estimator_fits']==diagnostic['native_test_predictions_computed']==0
    declaration = json.loads(PROPOSAL.read_text())
    assert declaration['implementation_code_sha256']==digest(Path(__file__)) and declaration['plan']==plan()
    return {**inputs,'previous_inputs':inputs,'previous_selection':selection}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':parent.fingerprint(inputs['previous_inputs']),
        'previous_selection_sha256':digest(parent.DIRECTORY/'selection.json'),'previous_verification_sha256':digest(PARENT_AUDIT),
        'range_diagnostic_sha256':digest(DIAGNOSTIC),'proposal_sha256':digest(PROPOSAL),
        'dependency_code_sha256':{'fatigue_shoulder_history_joint.py':digest(Path(parent.__file__))},
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),'worker_processes':2}


def numeric_history(frame):
    return parent.base.previous.history_query(frame)


class AlignedHistoryBorg(parent.ShoulderHistoryBorg):
    def prepare_normalizers(self,frame,external):
        assert len(external)==2336 and external.source_partition.eq('fitting').all()
        assert external.groupby('source_domain').size().to_dict()==SOURCE_COUNTS
        assert set(frame.group_key).isdisjoint(external.group_key)
        parts = {'native':frame,**{domain:part for domain,part in external.groupby('source_domain')}}
        self.domain_normalizers,self.normalization_summary = {},{}
        for domain,part in parts.items():
            history = numeric_history(part)
            assert len(history.columns)==2 and history.iloc[:,0].notna().all()
            imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)
            imputed = imputer.fit_transform(history)
            scaler = StandardScaler().fit(imputed[:,:2])
            assert imputed.shape[1]==3,'Every domain must retain its measured second-history availability bit'
            self.domain_normalizers[domain] = imputer,scaler
            self.normalization_summary[domain] = {'fitting_rows':len(part),'fitting_people':part.group_key.nunique(),
                'missing_second_histories':int(history.iloc[:,1].isna().sum()),'numeric_columns_scaled':2,'binary_availability_columns':1}
        return self

    def history_transform(self,frame):
        domain = 'native'
        if 'source_domain' in frame:
            names = frame.source_domain.unique().tolist()
            assert len(names)==1 and names[0] in SOURCE_COUNTS
            domain = names[0]
        imputer,scaler = self.domain_normalizers[domain]
        imputed = imputer.transform(numeric_history(frame))
        transformed = np.column_stack([scaler.transform(imputed[:,:2]),imputed[:,2:]])
        assert np.isfinite(transformed).all() and np.isin(transformed[:,2:],[0.,1.]).all()
        return torch.as_tensor(transformed,dtype=torch.float32)

    def fit(self,frame,external,specification,context_features,cached=None,observer=None,batch_observer=None):
        self.prepare_normalizers(frame,external)
        super().fit(frame,external,specification,context_features,cached=cached,observer=observer,batch_observer=batch_observer)
        self.training_summary.update(predictor_normalization='domain_fitting_numeric_zscore_binary_missing_indicators',
            source_input_rows_for_shared_preprocessing=0,source_input_rows_for_domain_preprocessing=2336,
            domain_normalization=self.normalization_summary,source_targets_transformed=False)
        return self


def initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def fit_group(job):
    member,number,fit,val = job
    inputs,signature = _RUNTIME
    train = inputs['train']
    fitting,validation = train.iloc[fit],train.iloc[val]
    assert set(fitting.group_key).isdisjoint(validation.group_key)
    cache = base.previous.read_base_cache(inputs['base_inputs']['previous_inputs'],member,number,fit,val)
    for c in (c for c in plan()[4:] if c['member']==member):
        path = DIRECTORY/'folds'/f"{c['id']}-fold-{number}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            assert saved['signature']==signature and saved['candidate']==c
            assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
            continue
        model = AlignedHistoryBorg(c).fit(fitting,inputs['source'],inputs['specifications'][member],inputs['context_features'],cached=cache)
        saved = {'signature':signature,'candidate':c,'fold_number':number,'fit_row_keys':fitting.row_key.tolist(),
            'validation_row_keys':validation.row_key.tolist(),'predicted':model.predict(validation[model.input_features]).tolist(),
            'training_summary':model.training_summary,'loss_endpoints':model.loss_endpoints}
        path.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(f"Actual domain-aligned joint fold:{c['id']} {number+1}/5",flush=True)


def save(report):
    (DIRECTORY/'selection.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def select():
    inputs = load_inputs()
    signature = fingerprint(inputs)
    train = inputs['train']
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY/'folds').mkdir(exist_ok=True)
    report = {**signature,'version':1,'status':'running','plan':plan(),'results':[],
        'train_row_keys':train.row_key.tolist(),'evaluation_denominator':487,'test_denominator':179,
        'test_used_for_selection':False,'minimum_cv_for_new_test_evaluation':.65,'target_accuracy':.8,
        'actual_source_fitting_targets_available':2336,'actual_source_fitting_second_priors':1927,
        'reserved_source_targets_not_fitted':312,'new_native_base_fits':0,'native_base_caches_reused':10,
        'new_native_borg_targets':0,'synthetic_training_rows':0,'source_targets_pooled_across_instruments':False,
        'policy':'Fixed10recipes:4inherited controls plus2native bases times shoulderweights0/.1/1. Only predictor preprocessing changes: native numeric histories fit their own outer-fitting-person imputer/scaler,and each source its own fitting-only numeric imputer/scaler. Keep second-history missing indicators binary and original current-minus-prior target points in five separate heads. Preserve2336actual source fitting rows,312reserved,original487/179native cases,5personfolds,80epochs,penalty10,oldnative caches and all networkinitialization. No synthetic histories,label conversion,clock assumptions,sensor joins or physiological scaleequivalence claim.'}
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
    jobs = [(m,n,fit,val) for m in ('core','cat') for n,(fit,val) in enumerate(folds)
        if any(not (DIRECTORY/'folds'/f"{c['id']}-fold-{n}.json").exists() for c in plan()[4:] if c['member']==m)]
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
            for future in as_completed([pool.submit(fit_group,job) for job in jobs]):
                future.result()
    for c in plan():
        if any(r['candidate']==c for r in report['results']):
            continue
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['previous_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])
            predicted,details = np.asarray(old['oof_predictions']),[]
        else:
            predicted,details = np.empty(len(train),dtype=object),[]
            for n,(_,val) in enumerate(folds):
                stored = json.loads((DIRECTORY/'folds'/f"{c['id']}-fold-{n}.json").read_text())
                assert stored['signature']==signature and stored['candidate']==c
                predicted[val] = stored['predicted']
                details.append(stored)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report['results'].append({'candidate':c,'accuracy_mean':float(np.mean(scores)),'fold_accuracy':scores,
            'pooled_oof_accuracy':float(accuracy_score(train.label,predicted)),'oof_predictions':predicted.tolist(),'folds':details})
        winner = max(report['results'],key=lambda r:r['accuracy_mean'])
        report.update(winner_id=winner['candidate']['id'],best_cv_accuracy=winner['accuracy_mean'])
        save(report)
        print(f"Actual domain-aligned recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report


if __name__=='__main__':
    import fatigue_domain_aligned_history as implementation
    implementation.select()
