"""Small ordered21-delta correction with three learned coefficients."""
from __future__ import annotations
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import joblib
import numpy as np
import torch
from torch import nn
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
import fatigue_cadence_delta_regularization as previous
import fatigue_cadence_full_delta as full_reference
import fatigue_cadence_recent_gate as scalar_reference
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = previous.DIRECTORY.parent/'cadence-ordered-residual-80-v1'
DOCS = previous.DOCS
PROPOSAL = DOCS/'cadence-ordered-residual-plan.json'
PARENT_AUDIT = DOCS/'cadence-delta-regularization-verification.json'
REVIEW = DOCS/'cadence-ordered-residual-review.json'
INPUT_AUDIT = previous.INPUT_AUDIT
native,prepared,source,COUNTS,added = previous.native,previous.prepared,previous.source,previous.COUNTS,previous.added
state_values = previous.state_values
_RUNTIME = None


def plan():
    controls = [('previous',key) for key in (0,1,6,8,11,13)]
    controls += [('full',key) for key in range(6,14)]
    controls += [('scalar',key) for key in range(6,10)]
    prefix = {'previous':'delta-regularization','full':'cadence-full-delta','scalar':'recent-gate'}
    result = [{'id':f'ordered-residual-{n:03d}','algorithm':'previous_real_control','control_study':domain,
        'parent_candidate_id':f'{prefix[domain]}-{key:03d}'} for n,(domain,key) in enumerate(controls)]
    for member in ('core','cat'):
        for weight in (0.,.1):
            for penalty in (.1,1.):
                result.append({'id':f'ordered-residual-{len(result):03d}','algorithm':'cadence_ordered_residual',
                    'member':member,'auxiliary_weight':weight,'epochs':80,'learning_rate':.003,'weight_decay':.1,
                    'correction_penalty':penalty,'random_seed':42,'source_target':'actual_current_unequal_prior_original6to20',
                    'native_target':'original_integer_delta_cross_entropy_21','residual_coefficients':3})
    return result


def load_inputs():
    old = previous.load_inputs()
    selected = json.loads((previous.DIRECTORY/'selection.json').read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==14
    assert all(selected.get(k)==v for k,v in previous.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(previous.DIRECTORY/'selection.json')
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_delta_regularization.py'))
    selections = {'previous':selected}
    for key,module,inputs in [('full',full_reference,old['previous_inputs']),
                             ('scalar',scalar_reference,old['previous_inputs']['previous_inputs'])]:
        path = module.DIRECTORY/'selection.json'
        control = json.loads(path.read_text())
        assert control['status']=='complete' and all(control.get(k)==v for k,v in module.fingerprint(inputs).items())
        assert control['train_row_keys']==old['train'].row_key.tolist()
        selections[key] = control
    review = json.loads(REVIEW.read_text())
    assert review['review']=='passed' and review['verification_sha256']==digest(PARENT_AUDIT)
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_ordered_residual.py'))
    np.testing.assert_allclose(review['proposed_residual']['basis'],ordered_basis(),atol=1e-12)
    declared = json.loads(PROPOSAL.read_text())
    assert declared['implementation_code_sha256']==digest(Path(__file__)) and declared['plan']==plan()
    return {**old,'previous_inputs':old,'previous_selection':selected,'control_selections':selections}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':previous.fingerprint(inputs['previous_inputs']),
        'control_selections_sha256':{name:digest(module.DIRECTORY/'selection.json') for name,module in
            [('previous',previous),('full',full_reference),('scalar',scalar_reference)]},
        'previous_verification_sha256':digest(PARENT_AUDIT),'input_audit_sha256':digest(INPUT_AUDIT),
        'proposal_sha256':digest(PROPOSAL),'review_sha256':digest(REVIEW),
        'frozen_full_delta_code_sha256':digest(Path(full_reference.__file__)),
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),'worker_processes':2}


def ordered_basis():
    delta = np.arange(-10,11,dtype=float)
    raw = np.column_stack([delta,delta**2,delta==0])
    q,_ = np.linalg.qr(raw-raw.mean(axis=0,keepdims=True),mode='reduced')
    return q*np.sqrt(21.)


class FullDeltaNetwork(previous.FullDeltaNetwork):
    def __init__(self,context_width):
        # Preserve the exact shared encoder/first-layer/source-head seed initialization.
        super().__init__(context_width)
        self.corrector[-1] = nn.Linear(8,3)
        nn.init.zeros_(self.corrector[-1].weight)
        nn.init.zeros_(self.corrector[-1].bias)
        self.register_buffer('basis',torch.tensor(ordered_basis(),dtype=torch.float64))

    def coefficients(self,history,context,offsets):
        joined = torch.cat([self.encoder(history),context,torch.softmax(offsets,dim=1).float()],dim=1)
        return self.corrector(joined).to(offsets.dtype)

    def expand(self,coefficients):
        values = coefficients@self.basis.T
        return values-values.mean(dim=1,keepdim=True)

    def correction(self,history,context,offsets):
        return self.expand(self.coefficients(history,context,offsets))


class FullDeltaCadenceBorg(previous.FullDeltaCadenceBorg):
    def fit(self, frame, external, specification, context_features, cached=None, observer=None, step_observer=None):
        validate_calibration(frame)
        assert len(external) == 851 and external.groupby('source_domain').size().to_dict() == COUNTS
        assert external.source_partition.eq('fitting').all() and set(frame.group_key).isdisjoint(external.group_key)
        cached = native.prepare_base(frame, self.candidate['member'], specification) if cached is None else cached
        assert cached['fit_row_keys'] == frame.row_key.tolist() and cached['base'].member == self.candidate['member']
        assert cached['base'].specification == specification
        before = joblib.hash(cached)
        self.base = cached['base']
        self.context_features = list(context_features)
        self.input_features = list(dict.fromkeys(self.base.input_features + self.context_features + list(prepared.NATIVE_COLUMNS.values())))
        assert not set(self.input_features) & {'label', 'group_key', 'row_key'}
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(self.candidate['random_seed'])
        self.prepare_normalizers(frame, external)
        self.context_imputer = SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)
        self.context_scaler = StandardScaler().fit(self.context_imputer.fit_transform(frame[self.context_features]))
        history, context = (self.history_transform(frame), self.context_transform(frame))
        original_probabilities = torch.exp(cached['fit_logits'].detach())
        offsets = cached['fit_logits'].detach()
        current, prior = (frame.label.str.removeprefix('Borg ').to_numpy(int), frame.prior_borg.to_numpy(int))
        target = torch.tensor(current - prior + 10, dtype=torch.long)
        self.network = FullDeltaNetwork(context.shape[1])
        assert torch.count_nonzero(self.network.correction(history, context, offsets)) == 0
        torch.testing.assert_close(torch.softmax(offsets, dim=1), original_probabilities, rtol=1e-12, atol=1e-15)
        auxiliary = {}
        if self.candidate['auxiliary_weight']:
            for domain, part in external.groupby('source_domain'):
                actual, old = (part[source.TARGETS[domain]].to_numpy(float), part[source.PRIOR].to_numpy(float))
                assert np.isfinite(actual).all() and np.isfinite(old).all()
                y = torch.tensor(actual != old, dtype=torch.float32)
                assert set(y.tolist()) == {0.0, 1.0}
                weight = 1.0 / part.groupby('group_key').group_key.transform('size').to_numpy()
                weight *= len(part) / weight.sum()
                auxiliary[domain] = (self.history_transform(part, domain), y, torch.tensor(weight, dtype=torch.float32))
                if observer is not None:
                    observer('source', domain, part[prepared.FEATURES].copy(), actual.copy(), old.copy())
        else:
            self.network.source_heads.requires_grad_(False)
        if observer is not None:
            observer('native', 'native', frame[self.input_features].copy(), current.copy(), prior.copy())
        c = self.candidate
        optimizer = torch.optim.AdamW(self.network.parameters(), lr=c['learning_rate'], weight_decay=c['weight_decay'])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=c['epochs'], eta_min=0.0003)
        self.loss_endpoints = []
        initial_source_gradient, initial_native_output_gradient = (0.0, 0.0)
        for epoch in range(c['epochs']):
            optimizer.zero_grad(set_to_none=True)
            coefficients = self.network.coefficients(history, context, offsets)
            correction = self.network.expand(coefficients)
            native_logits = offsets + correction
            classification = nn.functional.cross_entropy(native_logits, target)
            source_batches = {domain: (self.network.source_logits(x, domain), y, w) for domain, (x, y, w) in auxiliary.items()}
            losses = {domain: (nn.functional.binary_cross_entropy_with_logits(z, y, reduction='none') * w).sum() / w.sum() for domain, (z, y, w) in source_batches.items()}
            source_loss = torch.stack(list(losses.values())).mean() if losses else torch.tensor(0.0)
            total = classification + c['auxiliary_weight'] * source_loss + c['correction_penalty'] * correction.square().mean()
            assert torch.isfinite(total)
            if epoch == 0:
                gradients = torch.autograd.grad(classification, tuple(self.network.corrector[-1].parameters()), retain_graph=True)
                initial_native_output_gradient = float(torch.sqrt(sum((g.square().sum() for g in gradients))))
                assert initial_native_output_gradient > 0
                if auxiliary:
                    gradients = torch.autograd.grad(c['auxiliary_weight'] * source_loss, tuple(self.network.encoder.parameters()), retain_graph=True)
                    initial_source_gradient = float(torch.sqrt(sum((g.square().sum() for g in gradients))))
                    assert initial_source_gradient > 0
            if step_observer is not None:
                step_observer(epoch, {'history': history, 'context': context, 'offset_probabilities': original_probabilities, 'native_logits': native_logits, 'native_target': target, 'native_delta': torch.tensor(current - prior + 10), 'correction': correction, 'native_coefficients': coefficients, 'source_batches': source_batches, 'total': total})
            total.backward()
            assert all((p.grad is None or torch.isfinite(p.grad).all() for p in self.network.parameters()))
            nn.utils.clip_grad_norm_(self.network.parameters(), 5.0)
            optimizer.step()
            scheduler.step()
            if epoch in (0, c['epochs'] - 1):
                self.loss_endpoints.append({'epoch': epoch, 'total': float(total.detach()), 'native_delta_nll': float(classification.detach()), 'source_binary_mean': float(source_loss.detach()), 'source_binary_losses': {d: float(v.detach()) for d, v in losses.items()}})
        self.network.requires_grad_(False).eval()
        for parameter in self.network.parameters():
            parameter.grad = None
        assert joblib.hash(cached) == before
        self.training_summary = {'actual_native_targets': len(frame), 'actual_native_people': frame.group_key.nunique(), 'source_fitting_pairs_available': 851, 'source_fitting_targets_in_objective': 851 if auxiliary else 0, 'source_targets_by_separate_head': COUNTS if auxiliary else {}, 'source_fitting_actual_second_priors': 727, 'other_source_domains_fitted': 0, 'source_reserved_pairs_not_fitted': 206, 'gradient_steps': c['epochs'], 'initial_source_only_encoder_gradient_l2': initial_source_gradient, 'initial_native_output_gradient_l2': initial_native_output_gradient, 'base_weights_frozen': True, 'nonzero_delta_relative_probabilities_frozen': False, 'native_objective': '21_delta_cross_entropy', 'native_delta_probability_residuals_fitted': True, 'source_current_values_or_context_used_as_predictors': False, 'synthetic_rows': 0, 'artificial_history_views': 0, 'invented_source_times_or_sensor_joins': 0}
        self.training_summary.update(native_residual_coefficients=3, native_residual_logits=21, native_output_parameters=27, fixed_basis_geometry='centered_QR_delta_delta_squared_zero')
        return self


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
    for c in (c for c in plan()[18:] if c['member']==member):
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
        print(f"Actual ordered three-coefficient residual fit:{c['id']} fold{n+1}/5",flush=True)



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
        'policy':'Fixed26recipes:18inherited global/free21/scalar/strong-penalty controls plus2native bases*source0/.1*penalty.1/1. The3coefficient output spans fixed centered orthonormal delta,delta-squared andzero mass geometry;all21native probabilities remain available. Shared encoder/source-head initialization matches the full residual. Keep actual851source pairs,11shared inputs,16private context,80epochs/seed42/AdamW.003/decay.1 and immutable native bases. Fixed mathematical basis is not a training observation or target. Original487/179,.65CVtestgate,no synthetic rows.'}
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
            old = next(r for r in inputs['control_selections'][c['control_study']]['results'] if r['candidate']['id']==c['parent_candidate_id'])
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
        print(f"Actual ordered three-coefficient residual recipe:{c['id']} CV={np.mean(scores):.6f}",flush=True)
    report['status'] = 'complete'
    save(report)
    return report



if __name__=='__main__':
    import fatigue_cadence_ordered_residual as implementation
    implementation.select()
