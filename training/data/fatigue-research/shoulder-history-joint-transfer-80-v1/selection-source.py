"""Joint transfer from original within-trial shoulder histories, separate outputs."""
from __future__ import annotations
import copy
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from torch import nn

import fatigue_resistance_history_joint as base
import fatigue_catboost_schedule as parent
import fatigue_shoulder_history_inputs as source
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = base.DIRECTORY.parent/'shoulder-history-joint-transfer-80-v1'
DOCS = base.DOCS
PARENT_AUDIT = DOCS/'catboost-schedule-verification.json'
BASE_AUDIT = DOCS/'resistance-history-joint-verification.json'
INPUT_AUDIT = DOCS/'shoulder-history-input-verification.json'
PROPOSAL = DOCS/'shoulder-history-joint-plan.json'
COMMON = base.COMMON
SOURCE_COUNTS = {**base.SOURCE_COUNTS,'shoulder':920}
BASE_IDS = {'core':'resistance-joint-011','cat':'resistance-joint-020'}
_RUNTIME = None


def plan():
    result = [{'id':f'shoulder-joint-{i:03d}','algorithm':'previous_real_control',
        'parent_study':'schedule' if i<2 else 'resistance',
        'parent_candidate_id':key} for i,key in enumerate(['catboost-schedule-000','catboost-schedule-001',BASE_IDS['core'],BASE_IDS['cat']])]
    for member in ('core','cat'):
        for weight in (0.,.1,1.):
            result.append({'id':f'shoulder-joint-{len(result):03d}','algorithm':'joint_original_shoulder_history_residual',
                'member':member,'previous_candidate_id':BASE_IDS[member],'auxiliary_weight':.1 if member=='core' else 1.,
                'resistance_weight':.1,'shoulder_weight':weight,'correction_penalty':10.,'epochs':80,
                'learning_rate':.003,'weight_decay':.1,'random_seed':42,'base_probability_floor':base.previous.FLOOR,
                'source_target':'separate_original_continuous_current_minus_actual_prior','native_target':'original_integer_delta_class'})
    return result


def load_inputs():
    native = parent.load_inputs()
    schedule_path = parent.DIRECTORY/'selection.json'
    schedule = json.loads(schedule_path.read_text())
    parent_proof = json.loads(PARENT_AUDIT.read_text())
    assert schedule['status']=='complete' and len(schedule['results'])==16
    assert parent_proof['verification']=='passed' and parent_proof['selection_sha256']==digest(schedule_path)
    assert parent_proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_catboost_schedule.py'))
    old = base.load_inputs()
    old_selection = json.loads((base.DIRECTORY/'selection.json').read_text())
    old_proof = json.loads(BASE_AUDIT.read_text())
    assert old_proof['verification']=='passed' and old_proof['selection_sha256']==digest(base.DIRECTORY/'selection.json')
    assert old_proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_resistance_history_joint.py'))
    for member,key in BASE_IDS.items():
        chosen = old_proof['best_positive_by_member'][member]['candidate']
        assert chosen['id']==key and chosen['resistance_weight']==.1 and chosen['correction_penalty']==10. and chosen['epochs']==80
    for part in ('train','test'):
        pd.testing.assert_frame_equal(native[part][old[part].columns],old[part])
    external,manifest = source.load()
    proof = json.loads(INPUT_AUDIT.read_text())
    assert proof['verification']=='passed' and proof['audit_code_sha256']==digest(Path(__file__).with_name('audit_shoulder_history_inputs.py'))
    assert proof['source_preparation_code_sha256']==digest(Path(source.__file__))
    assert proof['source_provenance_sha256']==digest(source.DIRECTORY/'provenance.json')
    assert proof['source_dataset_sha256']==digest(source.DIRECTORY/'dataset.csv')
    fitting,reserved = external[external.source_partition.eq('fitting')].copy(),external[external.source_partition.eq('reserved')].copy()
    assert (len(fitting),len(reserved),fitting[source.SECOND].notna().sum())==(2336,312,1927)
    assert fitting.groupby('source_domain').size().to_dict()==SOURCE_COUNTS
    assert set(fitting.group_key).isdisjoint(reserved.group_key) and set(external.group_key).isdisjoint(old['frame'].group_key)
    pd.testing.assert_frame_equal(fitting[fitting.source_domain.ne('shoulder')][old['source'].columns].reset_index(drop=True),old['source'].reset_index(drop=True),check_dtype=False,rtol=0,atol=1e-12)
    declaration = json.loads(PROPOSAL.read_text())
    assert declaration['implementation_code_sha256']==digest(Path(__file__)) and declaration['plan']==plan()
    return {**old,'source':fitting,'reserved_source':reserved,'source_manifest':manifest,
        'base_inputs':old,'schedule_inputs':native,'schedule_selection':schedule,'base_selection':old_selection}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'preceding_schedule_signature':parent.fingerprint(inputs['schedule_inputs']),
        'preceding_schedule_selection_sha256':digest(parent.DIRECTORY/'selection.json'),'preceding_schedule_verification_sha256':digest(PARENT_AUDIT),
        'original_base_signature':base.fingerprint(inputs['base_inputs']),'original_joint_verification_sha256':digest(BASE_AUDIT),
        'source_provenance_sha256':digest(source.DIRECTORY/'provenance.json'),'source_input_verification_sha256':digest(INPUT_AUDIT),
        'source_dataset_sha256':inputs['source_manifest']['dataset_sha256'],'proposal_sha256':digest(PROPOSAL),
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),'worker_processes':2}


class ShoulderHistoryNetwork(base.ResistanceHistoryNetwork):
    def __init__(self,n_history,n_context):
        super().__init__(n_history,n_context)
        self.source_heads['shoulder'] = nn.Linear(8,1)


class ShoulderHistoryBorg(base.previous.JointHistoryBorg):
    def fit(self,frame,external,specification,context_features,cached=None,observer=None,batch_observer=None):
        validate_calibration(frame)
        assert len(external)==2336 and external.source_partition.eq('fitting').all()
        assert external.groupby('source_domain').size().to_dict()==SOURCE_COUNTS
        assert set(frame.group_key).isdisjoint(external.group_key)
        assert cached is not None and cached['fit_row_keys']==frame.row_key.tolist()
        assert cached['base'].member==self.candidate['member'] and cached['base'].specification==specification
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        c = self.candidate
        self.base,self.context_features = cached['base'],list(context_features)
        self.input_features = list(dict.fromkeys(self.base.input_features+self.context_features))
        before = joblib.hash(cached)
        torch.manual_seed(c['random_seed'])
        oldest = external[~external.source_domain.isin(['resistance','shoulder'])]
        assert len(oldest)==550
        union = pd.concat([base.previous.history_query(frame),base.previous.history_query(oldest)],ignore_index=True)
        self.history_imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)
        self.history_scaler = StandardScaler().fit(self.history_imputer.fit_transform(union))
        self.context_imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)
        self.context_scaler = StandardScaler().fit(self.context_imputer.fit_transform(frame[self.context_features]))
        history,context = self.history_transform(frame),self.context_transform(frame)
        offsets = cached['fit_logits'].detach()
        current,prior = frame.label.str.removeprefix('Borg ').to_numpy(int),frame.prior_borg.to_numpy(int)
        target = torch.as_tensor(current-prior+10,dtype=torch.long)
        self.domains = sorted(base.previous.SOURCE_COUNTS)+['resistance','shoulder']
        self.network = ShoulderHistoryNetwork(history.shape[1],context.shape[1])
        assert torch.count_nonzero(self.network.correction(history,context,offsets))==0
        active = self.domains if c['shoulder_weight'] else self.domains[:-1]
        auxiliary = {}
        for domain in active:
            part = external[external.source_domain.eq(domain)]
            actual,old = part[source.TARGETS[domain]].to_numpy(float),part[source.PRIOR].to_numpy(float)
            lower,upper = (6,20) if domain=='shoulder' else ((1,10) if domain=='resistance' else (0,10))
            assert np.isfinite([actual,old]).all() and ((actual>=lower)&(actual<=upper)&(old>=lower)&(old<=upper)).all()
            weight = 1./part.groupby('group_key').group_key.transform('size').to_numpy()
            weight *= len(part)/weight.sum()
            auxiliary[domain] = self.history_transform(part),torch.as_tensor(actual-old,dtype=torch.float32),torch.as_tensor(weight,dtype=torch.float32)
            if observer is not None:
                observer('source',domain,part[COMMON].copy(),actual.copy(),old.copy())
        if not c['shoulder_weight']:
            self.network.source_heads['shoulder'].requires_grad_(False)
        if observer is not None:
            observer('native','native',frame[self.input_features].copy(),current.copy(),prior.copy())
        optimizer = torch.optim.AdamW(self.network.parameters(),lr=c['learning_rate'],weight_decay=c['weight_decay'])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=c['epochs'],eta_min=.0003)
        self.loss_endpoints = []
        new_gradient = 0.
        initial_gradient = None
        for epoch in range(c['epochs']):
            optimizer.zero_grad(set_to_none=True)
            correction = self.network.correction(history,context,offsets)
            classification = nn.functional.cross_entropy(offsets+correction,target)
            losses = {d:(nn.functional.smooth_l1_loss(self.network.source_prediction(x,d),y,beta=1.,reduction='none')*w).sum()/w.sum()
                for d,(x,y,w) in auxiliary.items()}
            old_mean = torch.stack([losses[d] for d in self.domains[:-2]]).mean()
            previous_loss = (3*old_mean+c['resistance_weight']*losses['resistance'])/(3+c['resistance_weight'])
            source_loss = previous_loss if not c['shoulder_weight'] else (
                (3+c['resistance_weight'])*previous_loss+c['shoulder_weight']*losses['shoulder'])/(3+c['resistance_weight']+c['shoulder_weight'])
            total = classification+c['auxiliary_weight']*source_loss+c['correction_penalty']*correction.square().mean()
            assert torch.isfinite(total)
            if batch_observer is not None:
                batch_observer(epoch,history.detach().numpy().copy(),target.numpy().copy(),
                    {d:(x.numpy().copy(),y.numpy().copy(),w.numpy().copy()) for d,(x,y,w) in auxiliary.items()})
            if epoch==0 and c['shoulder_weight']:
                gradients = torch.autograd.grad(c['auxiliary_weight']*c['shoulder_weight']*losses['shoulder']/(3+c['resistance_weight']+c['shoulder_weight']),
                    tuple(self.network.encoder.parameters()),retain_graph=True)
                new_gradient = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
                assert new_gradient>0
            total.backward()
            assert all(p.grad is None or torch.isfinite(p.grad).all() for p in self.network.parameters())
            if epoch==0:
                initial_gradient = float(torch.sqrt(sum(p.grad.square().sum() for p in self.network.encoder.parameters() if p.grad is not None)))
                assert initial_gradient>0
            nn.utils.clip_grad_norm_(self.network.parameters(),5.)
            optimizer.step()
            scheduler.step()
            if epoch in (0,c['epochs']-1):
                self.loss_endpoints.append({'epoch':epoch,'total':float(total.detach()),'native_classification':float(classification.detach()),
                    'source_delta_mean':float(source_loss.detach()),'source_losses':{d:float(v.detach()) for d,v in losses.items()}})
        self.network.requires_grad_(False).eval()
        for parameter in self.network.parameters():
            parameter.grad = None
        assert joblib.hash(cached)==before
        self.training_summary = {'actual_native_targets':len(frame),'source_input_rows_for_shared_preprocessing':550,
            'source_fitting_targets_available':2336,'actual_source_targets_in_objective':2336 if c['shoulder_weight'] else 1416,
            'source_targets_by_separate_head':{d:SOURCE_COUNTS[d] for d in active},
            'shoulder_source_targets_in_objective':920 if c['shoulder_weight'] else 0,
            'source_fitting_actual_second_priors':1927,'native_actual_second_priors':int(frame.prior2_borg.notna().sum()),
            'gradient_steps':c['epochs'],'initial_encoder_gradient_l2':initial_gradient,
            'initial_shoulder_only_encoder_gradient_l2':new_gradient,'native_base_weights_frozen':True,
            'source_reserved_targets_not_fitted':312,'synthetic_rows':0,'artificial_history_views':0,
            'invented_source_times_or_sensor_joins':0}
        return self


def initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def fit_group(job):
    member,number,fit,val = job
    inputs,signature = _RUNTIME
    cache = base.previous.read_base_cache(inputs['base_inputs']['previous_inputs'],member,number,fit,val)
    fitting,validation = inputs['train'].iloc[fit],inputs['train'].iloc[val]
    assert set(fitting.group_key).isdisjoint(validation.group_key)
    for candidate in (c for c in plan()[4:] if c['member']==member):
        path = DIRECTORY/'folds'/f"{candidate['id']}-fold-{number}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            assert saved['signature']==signature and saved['candidate']==candidate
            assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
            continue
        model = ShoulderHistoryBorg(candidate).fit(fitting,inputs['source'],inputs['specifications'][member],inputs['context_features'],cached=cache)
        predicted = model.predict(validation[model.input_features]).tolist()
        if not candidate['shoulder_weight']:
            old = next(r for r in inputs['base_selection']['results'] if r['candidate']['id']==BASE_IDS[member])
            np.testing.assert_array_equal(predicted,np.asarray(old['oof_predictions'])[val])
            assert model.loss_endpoints==old['folds'][number]['loss_endpoints']
        saved = {'signature':signature,'candidate':candidate,'fold_number':number,'fit_row_keys':fitting.row_key.tolist(),
            'validation_row_keys':validation.row_key.tolist(),'predicted':predicted,
            'training_summary':model.training_summary,'loss_endpoints':model.loss_endpoints}
        path.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(f"Actual shoulder joint fold:{candidate['id']} {number+1}/5",flush=True)


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
        'policy':'Fixed10recipes:4inherited controls,2native bases times shoulder weights0/.1/1. Preserve matched original normalization/initialization and zero-source exactold predictions/losses. Actual920shoulder fitting pairs/27people,187reserved/7people;five separate original-point delta heads. Preserve all1416old fitting targets and125oldreserved targets. Only actual timed histories,no before_task/terminalclock assumptions,between-task order,sensor joins,synthetic rows or scaleconversion. Original487/179cases and5native personfolds unchanged;80epochs,AdamW.003/decay.1,correctionpenalty10;no epoch extension following overfit diagnosis.'}
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
    jobs = [(member,n,fit,val) for member in ('core','cat') for n,(fit,val) in enumerate(folds)
        if any(not (DIRECTORY/'folds'/f"{c['id']}-fold-{n}.json").exists() for c in plan()[4:] if c['member']==member)]
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
            for future in as_completed([pool.submit(fit_group,job) for job in jobs]):
                future.result()
    for candidate in plan():
        if any(r['candidate']==candidate for r in report['results']):
            continue
        if candidate['algorithm']=='previous_real_control':
            parent_rows = inputs['schedule_selection' if candidate['parent_study']=='schedule' else 'base_selection']['results']
            old = next(r for r in parent_rows if r['candidate']['id']==candidate['parent_candidate_id'])
            predicted,details = np.asarray(old['oof_predictions']),[]
        else:
            predicted,details = np.empty(len(train),dtype=object),[]
            for n,(_,val) in enumerate(folds):
                stored = json.loads((DIRECTORY/'folds'/f"{candidate['id']}-fold-{n}.json").read_text())
                assert stored['signature']==signature and stored['candidate']==candidate
                predicted[val] = stored['predicted']
                details.append(stored)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report['results'].append({'candidate':candidate,'accuracy_mean':float(np.mean(scores)),'fold_accuracy':scores,
            'pooled_oof_accuracy':float(accuracy_score(train.label,predicted)),'oof_predictions':predicted.tolist(),'folds':details})
        winner = max(report['results'],key=lambda r:r['accuracy_mean'])
        report.update(winner_id=winner['candidate']['id'],best_cv_accuracy=winner['accuracy_mean'])
        save(report)
        print(f"Actual shoulder joint recipe:{candidate['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report


if __name__=='__main__':
    import fatigue_shoulder_history_joint as implementation
    implementation.select()
