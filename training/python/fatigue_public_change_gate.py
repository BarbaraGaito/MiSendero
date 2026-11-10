"""Separate public observed-change heads correct only the native change gate.

All native nonzero-delta relative probabilities and base weights stay frozen.
No source observations become native Borg labels or fabricated context rows.
"""
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

import fatigue_observed_change_factorization as predecessor
import fatigue_shoulder_history_inputs as source
import fatigue_two_history_joint as native
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = predecessor.DIRECTORY.parent/'public-change-gate-transfer-80-v1'
DOCS = predecessor.DOCS
PROPOSAL = DOCS/'public-change-gate-plan.json'
PARENT_AUDIT = DOCS/'observed-change-factorization-verification.json'
REVIEW = DOCS/'public-observed-change-support-review.json'
DIAGNOSTIC = DOCS/'observed-change-stage-diagnostic.json'
COUNTS = {'emap':248,'resistance':866,'shoulder':920,'worker':253}
_RUNTIME = None


def plan():
    result = [{'id':f'public-change-gate-{n:03d}','algorithm':'previous_real_control',
        'parent_candidate_id':key} for n,key in enumerate(['observed-change-000','observed-change-001',
            'observed-change-005','observed-change-007'])]
    for member in ('core','cat'):
        for weight in (0.,.1,1.):
            result.append({'id':f'public-change-gate-{len(result):03d}','algorithm':'joint_public_binary_change_gate',
                'member':member,'auxiliary_weight':weight,'epochs':80,'learning_rate':.003,
                'weight_decay':.1,'correction_penalty':10.,'random_seed':42,
                'source_target':'actual_current_unequal_actual_prior_on_original_instrument',
                'native_target':'original_integer_delta_distribution_with_frozen_nonzero_conditional'})
    return result


def load_inputs():
    old = predecessor.load_inputs()
    path = predecessor.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==10
    assert all(selected.get(k)==v for k,v in predecessor.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(path)
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_observed_change_factorization.py'))
    assert proof['all_40_fold_artifacts_recomputed'] and proof['independent_stage_estimator_refits']==30
    review = json.loads(REVIEW.read_text())
    assert review['review']=='passed' and review['review_code_sha256']==digest(Path(__file__).with_name('review_public_observed_change_support.py'))
    assert review['source_input_audit_sha256']==digest(DOCS/'shoulder-history-input-verification.json')
    assert review['native_stage_diagnostic_sha256']==digest(DIAGNOSTIC)
    assert not review['source_outcomes_pooled_into_native_labels'] and not review['source_scales_converted']
    fitting = old['source'][old['source'].source_domain.isin(COUNTS)].copy()
    excluded = old['source'][old['source'].source_domain.eq('sts')]
    assert fitting.groupby('source_domain').size().to_dict()==COUNTS and len(fitting)==2287
    assert len(excluded)==49 and excluded[source.TARGETS['sts']].ne(excluded[source.PRIOR]).all()
    assert fitting[source.SECOND].notna().sum()==1927 and len(old['reserved_source'])==312
    assert fitting.source_partition.eq('fitting').all() and set(fitting.group_key).isdisjoint(old['frame'].group_key)
    assert (len(old['train']),len(old['test']))==(487,179) and len(old['context_features'])==13
    declared = json.loads(PROPOSAL.read_text())
    assert declared['implementation_code_sha256']==digest(Path(__file__)) and declared['plan']==plan()
    return {**old,'previous_inputs':old,'previous_selection':selected,'gate_source':fitting}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':predecessor.fingerprint(inputs['previous_inputs']),
        'previous_selection_sha256':digest(predecessor.DIRECTORY/'selection.json'),
        'previous_verification_sha256':digest(PARENT_AUDIT),'source_change_review_sha256':digest(REVIEW),
        'stage_diagnostic_sha256':digest(DIAGNOSTIC),'proposal_sha256':digest(PROPOSAL),
        'source_provenance_sha256':digest(source.DIRECTORY/'provenance.json'),
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),
        'dependency_code_sha256':{name:digest(Path(__file__).with_name(name))
            for name in ('fatigue_two_history_joint.py','fatigue_shoulder_history_inputs.py','fatigue_probability.py')},
        'worker_processes':2}


def history_values(frame):
    columns = [source.PRIOR,source.SECOND] if source.PRIOR in frame else ['prior_borg','prior2_borg']
    values = frame[columns].copy()
    values.columns = ['prior','second']
    assert values.prior.notna().all()
    return values


def gate_logit(probabilities):
    p_zero = probabilities[:,10]
    assert torch.isfinite(probabilities).all() and ((p_zero>0)&(p_zero<1)).all()
    return torch.log1p(-p_zero)-torch.log(p_zero)


def recombine(probabilities,logits):
    conditional = probabilities.clone()
    conditional[:,10] = 0.
    conditional = conditional/conditional.sum(dim=1,keepdim=True)
    result = torch.sigmoid(logits)[:,None]*conditional
    # Avoid an in-place write to the graph needed for gradient verification.
    mask = torch.arange(21,device=logits.device).eq(10)[None,:]
    result = torch.where(mask,torch.sigmoid(-logits)[:,None],result)
    return result


class ChangeGateNetwork(nn.Module):
    def __init__(self,context_width):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(3,8),nn.Tanh(),nn.Linear(8,8),nn.Tanh())
        self.corrector = nn.Sequential(nn.Linear(context_width+9,8),nn.Tanh(),nn.Linear(8,1))
        self.source_heads = nn.ModuleDict({domain:nn.Linear(8,1) for domain in sorted(COUNTS)})
        nn.init.zeros_(self.corrector[-1].weight)
        nn.init.zeros_(self.corrector[-1].bias)

    def correction(self,history,context,offset):
        joined = torch.cat([self.encoder(history),context,torch.sigmoid(offset).float()[:,None]],dim=1)
        return self.corrector(joined).squeeze(1).to(offset.dtype)

    def source_logits(self,history,domain):
        return self.source_heads[domain](self.encoder(history)).squeeze(1)


class PublicChangeGateBorg:
    def __init__(self,candidate):
        self.candidate = copy.deepcopy(candidate)

    def prepare_normalizers(self,frame,external):
        self.history_normalizers,self.normalization_summary = {},{}
        parts = {'native':frame,**{name:part for name,part in external.groupby('source_domain')}}
        assert set(parts)=={'native',*COUNTS}
        for name,part in parts.items():
            values = history_values(part)
            imputer = SimpleImputer(strategy='median',keep_empty_features=True)
            scaler = StandardScaler().fit(imputer.fit_transform(values))
            self.history_normalizers[name] = imputer,scaler
            self.normalization_summary[name] = {'fitting_rows':len(part),'fitting_people':part.group_key.nunique(),
                'actual_missing_second_priors':int(values.second.isna().sum()),'numeric_columns':2,'unscaled_availability_bits':1}

    def history_transform(self,frame,domain='native'):
        values = history_values(frame)
        imputer,scaler = self.history_normalizers[domain]
        transformed = np.column_stack([scaler.transform(imputer.transform(values)),values.second.isna().to_numpy(float)])
        assert np.isfinite(transformed).all() and np.isin(transformed[:,2],[0.,1.]).all()
        return torch.tensor(transformed,dtype=torch.float32)

    def context_transform(self,frame):
        return torch.tensor(self.context_scaler.transform(self.context_imputer.transform(frame[self.context_features])),dtype=torch.float32)

    def fit(self,frame,external,specification,context_features,cached=None,observer=None,step_observer=None):
        validate_calibration(frame)
        assert len(external)==2287 and external.groupby('source_domain').size().to_dict()==COUNTS
        assert external.source_partition.eq('fitting').all() and set(frame.group_key).isdisjoint(external.group_key)
        cached = native.prepare_base(frame,self.candidate['member'],specification) if cached is None else cached
        assert cached['fit_row_keys']==frame.row_key.tolist() and cached['base'].member==self.candidate['member']
        assert cached['base'].specification==specification
        before = joblib.hash(cached)
        self.base = cached['base']
        self.context_features = list(context_features)
        self.input_features = list(dict.fromkeys(self.base.input_features+self.context_features))
        assert not set(self.input_features)&{'label','group_key','row_key'}
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(self.candidate['random_seed'])
        self.prepare_normalizers(frame,external)
        self.context_imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)
        self.context_scaler = StandardScaler().fit(self.context_imputer.fit_transform(frame[self.context_features]))
        history,context = self.history_transform(frame),self.context_transform(frame)
        original_probabilities = torch.exp(cached['fit_logits'].detach())
        offsets = gate_logit(original_probabilities)
        current,prior = frame.label.str.removeprefix('Borg ').to_numpy(int),frame.prior_borg.to_numpy(int)
        target = torch.tensor(current!=prior,dtype=torch.float64)
        self.network = ChangeGateNetwork(context.shape[1])
        assert torch.count_nonzero(self.network.correction(history,context,offsets))==0
        torch.testing.assert_close(recombine(original_probabilities,offsets),original_probabilities,rtol=1e-12,atol=1e-15)
        auxiliary = {}
        if self.candidate['auxiliary_weight']:
            for domain,part in external.groupby('source_domain'):
                actual,old = part[source.TARGETS[domain]].to_numpy(float),part[source.PRIOR].to_numpy(float)
                assert np.isfinite(actual).all() and np.isfinite(old).all()
                y = torch.tensor(actual!=old,dtype=torch.float32)
                assert set(y.tolist())=={0.,1.}
                weight = 1./part.groupby('group_key').group_key.transform('size').to_numpy()
                weight *= len(part)/weight.sum()
                auxiliary[domain] = self.history_transform(part,domain),y,torch.tensor(weight,dtype=torch.float32)
                if observer is not None:
                    observer('source',domain,part[[source.PRIOR,source.SECOND]].copy(),actual.copy(),old.copy())
        else:
            self.network.source_heads.requires_grad_(False)
        if observer is not None:
            observer('native','native',frame[self.input_features].copy(),current.copy(),prior.copy())
        c = self.candidate
        optimizer = torch.optim.AdamW(self.network.parameters(),lr=c['learning_rate'],weight_decay=c['weight_decay'])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=c['epochs'],eta_min=.0003)
        self.loss_endpoints = []
        initial_source_gradient,initial_native_output_gradient = 0.,0.
        for epoch in range(c['epochs']):
            optimizer.zero_grad(set_to_none=True)
            correction = self.network.correction(history,context,offsets)
            native_logits = offsets+correction
            classification = nn.functional.binary_cross_entropy_with_logits(native_logits,target)
            source_batches = {domain:(self.network.source_logits(x,domain),y,w) for domain,(x,y,w) in auxiliary.items()}
            losses = {domain:(nn.functional.binary_cross_entropy_with_logits(z,y,reduction='none')*w).sum()/w.sum()
                for domain,(z,y,w) in source_batches.items()}
            source_loss = torch.stack(list(losses.values())).mean() if losses else torch.tensor(0.)
            total = classification+c['auxiliary_weight']*source_loss+c['correction_penalty']*correction.square().mean()
            assert torch.isfinite(total)
            if epoch==0:
                gradients = torch.autograd.grad(classification,tuple(self.network.corrector[-1].parameters()),retain_graph=True)
                initial_native_output_gradient = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
                assert initial_native_output_gradient>0
                if auxiliary:
                    gradients = torch.autograd.grad(c['auxiliary_weight']*source_loss,tuple(self.network.encoder.parameters()),retain_graph=True)
                    initial_source_gradient = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
                    assert initial_source_gradient>0
            if step_observer is not None:
                step_observer(epoch,{'history':history,'context':context,'offset_probabilities':original_probabilities,
                    'native_logits':native_logits,'native_target':target,'native_delta':torch.tensor(current-prior+10),
                    'correction':correction,'source_batches':source_batches,'total':total})
            total.backward()
            assert all(p.grad is None or torch.isfinite(p.grad).all() for p in self.network.parameters())
            nn.utils.clip_grad_norm_(self.network.parameters(),5.)
            optimizer.step()
            scheduler.step()
            if epoch in (0,c['epochs']-1):
                self.loss_endpoints.append({'epoch':epoch,'total':float(total.detach()),'native_binary_loss':float(classification.detach()),
                    'source_binary_mean':float(source_loss.detach()),'source_binary_losses':{d:float(v.detach()) for d,v in losses.items()}})
        self.network.requires_grad_(False).eval()
        for parameter in self.network.parameters():
            parameter.grad = None
        assert joblib.hash(cached)==before
        self.training_summary = {'actual_native_targets':len(frame),'actual_native_people':frame.group_key.nunique(),
            'source_fitting_pairs_available':2287,'source_fitting_targets_in_objective':2287 if auxiliary else 0,
            'source_targets_by_separate_head':COUNTS if auxiliary else {},'source_fitting_actual_second_priors':1927,
            'excluded_single_class_sts_pairs':49,'source_reserved_pairs_not_fitted':312,'gradient_steps':c['epochs'],
            'initial_source_only_encoder_gradient_l2':initial_source_gradient,
            'initial_native_output_gradient_l2':initial_native_output_gradient,'base_weights_frozen':True,
            'nonzero_delta_relative_probabilities_frozen':True,'native_loss_equivalent_to_joint_nll_up_to_frozen_conditional':True,
            'source_current_values_or_context_used_as_predictors':False,'synthetic_rows':0,'artificial_history_views':0,
            'invented_source_times_or_sensor_joins':0}
        return self

    def probabilities(self,frame):
        if list(frame)!=self.input_features:
            raise ValueError('Input-only causal features in their declared order are required')
        validate_calibration(frame)
        with torch.no_grad():
            base_probability = self.base.logits(frame).exp()
            offset = gate_logit(base_probability)
            correction = self.network.correction(self.history_transform(frame),self.context_transform(frame),offset)
            probability = recombine(base_probability,offset+correction)
        assert torch.isfinite(probability).all()
        torch.testing.assert_close(probability.sum(dim=1),torch.ones(len(frame),dtype=torch.float64),rtol=1e-12,atol=1e-15)
        return probability

    def predict(self,frame):
        probability = self.probabilities(frame)
        order = torch.as_tensor(self.base.priority,dtype=torch.long)
        delta = order[probability[:,order].argmax(dim=1)].numpy()-10
        return np.asarray([f'Borg {int(x)}' for x in np.clip(delta+frame.prior_borg.to_numpy(int),0,10)])


def read_cache(inputs,member,number,fit,val):
    return native.read_base_cache(inputs['base_inputs']['previous_inputs'],member,number,fit,val)


def initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def fit_group(job):
    member,number,fit,val = job
    inputs,signature = _RUNTIME
    fitting,validation = inputs['train'].iloc[fit],inputs['train'].iloc[val]
    assert set(fitting.group_key).isdisjoint(validation.group_key)
    cached = read_cache(inputs,member,number,fit,val)
    before = joblib.hash(cached)
    for c in (c for c in plan()[4:] if c['member']==member):
        path = DIRECTORY/'folds'/f"{c['id']}-fold-{number}.json"
        model_path = path.with_suffix('.joblib')
        if path.exists():
            stored = json.loads(path.read_text())
            assert stored['signature']==signature and stored['candidate']==c
            assert stored['fit_row_keys']==fitting.row_key.tolist() and stored['validation_row_keys']==validation.row_key.tolist()
            assert stored['model_sha256']==digest(model_path)
            continue
        model = PublicChangeGateBorg(c).fit(fitting,inputs['gate_source'],inputs['specifications'][member],inputs['context_features'],cached)
        predicted = model.predict(validation[model.input_features]).tolist()
        joblib.dump(model,model_path)
        np.testing.assert_array_equal(joblib.load(model_path).predict(validation[model.input_features]),predicted)
        stored = {'signature':signature,'candidate':c,'fold':number,'fit_row_keys':fitting.row_key.tolist(),
            'validation_row_keys':validation.row_key.tolist(),'predicted':predicted,'model_sha256':digest(model_path),
            'training_summary':model.training_summary,'normalization_summary':model.normalization_summary,'loss_endpoints':model.loss_endpoints}
        path.write_text(json.dumps(stored,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(f"Actual public binary-change joint fit:{c['id']} fold{number+1}/5",flush=True)
    assert joblib.hash(cached)==before


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
        'new_joint_network_fits':30,'new_native_base_fits':0,'frozen_native_base_caches_reused':10,
        'actual_source_fitting_pairs_available':2287,'excluded_single_class_sts_pairs':49,'source_reserved_pairs_not_fitted':312,
        'synthetic_rows':0,'policy':'Fixed10recipes:4inherited controls and2frozen native bases*3binary-source weights0/.1/1. '
            'Only scalar change-vs-no-change logit is corrected; all original nonzero delta ratios and base weights stay frozen. '
            'Reuse inner-person OOF offsets. Four source binary heads use actual equal/unequal report pairs on original '
            'instruments,not native Borg labels. Native13feature context is never fabricated for source rows. '
            'Fitting-only per-domain numeric history normalization keeps real missing-second bits binary. '
            'Fixed80epochs,penalty10,AdamW.003,original487/179native cohort and exact Borg scoring. No test-directed tuning.'}
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
    jobs = [(m,n,fit,val) for m in ('core','cat') for n,(fit,val) in enumerate(folds)]
    with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
        for future in as_completed([pool.submit(fit_group,job) for job in jobs]):
            future.result()
    for c in plan():
        if any(row['candidate']==c for row in report['results']):
            continue
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['previous_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])
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
        winner = max(report['results'],key=lambda r:r['accuracy_mean'])
        report.update(winner_id=winner['candidate']['id'],best_cv_accuracy=winner['accuracy_mean'])
        save(report)
        print(f"Actual public binary-change recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report


if __name__=='__main__':
    import fatigue_public_change_gate as implementation
    implementation.select()
