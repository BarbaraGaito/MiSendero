"""Prepare expanded-history transfer with native-private measured physiology."""
import ast
import json
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent
parent_path = root/'fatigue_cadence_ordered_residual.py'
parent = parent_path.read_text()
lines = parent.splitlines(keepends=True)
tree = ast.parse(parent)
frozen_path = root/'fatigue_public_change_gate.py'
frozen_text = frozen_path.read_text()
fit_node = next(node for node in ast.walk(ast.parse(frozen_text)) if isinstance(node,ast.FunctionDef) and node.name=='fit')
fit = ast.get_source_segment(frozen_text,fit_node)
fit = '    '+fit.replace('\n','\n    ')+'\n'
old = "assert len(external)==2287 and external.groupby('source_domain').size().to_dict()==COUNTS"
assert old in fit
fit = fit.replace(old,"assert len(external)==3548 and external.groupby('source_domain').size().to_dict()==COUNTS")
start = fit.index('            auxiliary = {}')
end = fit.index('            if observer is not None:\n                observer(\'native\'',start)
auxiliary = '''            auxiliary = {}
            weights = source_weights(self.candidate)
            for domain,part in external.groupby('source_domain'):
                if weights[domain]==0:
                    self.network.source_heads[domain].requires_grad_(False)
                    continue
                actual,old = part.current_rpe.to_numpy(float),part.prior.to_numpy(float)
                assert np.isfinite(actual).all() and np.isfinite(old).all()
                y = torch.tensor(actual!=old,dtype=torch.float32)
                assert set(y.tolist())=={0.,1.}
                weight = 1./part.groupby('group_key').group_key.transform('size').to_numpy()
                weight *= len(part)/weight.sum()
                auxiliary[domain] = self.history_transform(part,domain),y,torch.tensor(weight,dtype=torch.float32)
                if observer is not None:
                    observer('source',domain,part[['prior','second']].copy(),actual.copy(),old.copy())
'''
fit = fit[:start]+auxiliary+fit[end:]
fit = fit.replace('initial_source_gradient,initial_native_output_gradient = 0.,0.',
    'initial_source_gradient,initial_native_output_gradient,initial_gait_gradient = 0.,0.,0.')
fit = fit.replace("source_loss = torch.stack(list(losses.values())).mean() if losses else torch.tensor(0.)",
    "source_loss = sum((weights[d]*loss for d,loss in losses.items()),torch.tensor(0.))")
fit = fit.replace("total = classification+c['auxiliary_weight']*source_loss+c['correction_penalty']*correction.square().mean()",
    "total = classification+source_loss+c['correction_penalty']*correction.square().mean()")
fit = fit.replace("torch.autograd.grad(c['auxiliary_weight']*source_loss,tuple(self.network.encoder.parameters()),retain_graph=True)",
    "torch.autograd.grad(source_loss,tuple(self.network.encoder.parameters()),retain_graph=True)")
needle = '                        assert initial_source_gradient>0'
assert needle in fit
fit = fit.replace(needle,needle+'''
                    if 'gait_forecasting' in losses:
                        gradients = torch.autograd.grad(weights['gait_forecasting']*losses['gait_forecasting'],tuple(self.network.encoder.parameters()),retain_graph=True)
                        initial_gait_gradient = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
                        assert initial_gait_gradient>0''')
fit = fit.replace("'correction':correction,'source_batches':source_batches,'total':total}",
    "'correction':correction,'source_batches':source_batches,'source_weights':weights,'total':total}")
start = fit.index('            self.training_summary = ')
end = fit.index('            return self',start)
summary = '''            self.training_summary = {'actual_native_targets':len(frame),'actual_native_people':frame.group_key.nunique(),
                'source_fitting_pairs_available':3548,'source_fitting_actual_second_priors':3042,
                'source_fitting_targets_in_objective':sum(COUNTS[d] for d in auxiliary),
                'source_targets_by_separate_head':{d:COUNTS[d] for d in auxiliary},'source_loss_weights':weights,
                'actual_new_gait_targets_in_objective':410 if 'gait_forecasting' in auxiliary else 0,
                'source_reserved_pairs_not_fitted':518,'gait_reserved_people_not_received':5,
                'gradient_steps':c['epochs'],'initial_source_only_encoder_gradient_l2':initial_source_gradient,
                'initial_new_gait_only_encoder_gradient_l2':initial_gait_gradient,
                'initial_native_output_gradient_l2':initial_native_output_gradient,'base_weights_frozen':True,
                'nonzero_delta_relative_probabilities_frozen':True,'native_loss_equivalent_to_joint_nll_up_to_frozen_conditional':True,
                'native_private_context_features':20,'source_current_values_or_context_used_as_predictors':False,
                'synthetic_rows':0,'artificial_history_views':0,'invented_source_times_or_sensor_joins':0}
'''
fit = fit[:start]+summary+fit[end:]

header = '''"""Six actual-history source heads and private native measured physiology."""
from __future__ import annotations
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from types import SimpleNamespace
import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
import fatigue_cadence_ordered_residual as previous
import fatigue_public_change_gate as frozen
import rpe_expanded_binary_history_inputs as prepared
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = previous.DIRECTORY.parent/'expanded-public-history-gate-80-v1'
DOCS = previous.DOCS
PROPOSAL = DOCS/'expanded-public-history-gate-plan.json'
PARENT_AUDIT = DOCS/'cadence-ordered-residual-verification.json'
INPUT_AUDIT = DOCS/'rpe-expanded-binary-history-input-verification.json'
COUNTS = prepared.COUNTS
LEGACY = tuple(d for d in sorted(COUNTS) if d!='gait_forecasting')
source = SimpleNamespace(PRIOR='prior',SECOND='second',TARGETS={d:'current_rpe' for d in COUNTS})
native = previous.native
gate_logit,recombine = frozen.gate_logit,frozen.recombine
_RUNTIME = None


def source_weights(candidate):
    return {domain:float(candidate['gait_weight'] if domain=='gait_forecasting' else candidate['auxiliary_weight']/5.) for domain in sorted(COUNTS)}


def plan():
    result = [{'id':f'expanded-gate-{n:03d}','algorithm':'previous_real_control',
        'parent_candidate_id':f'ordered-residual-{key:03d}'} for n,key in enumerate((0,1,4,5,14,15,16,17))]
    settings = [('native_only',0.,0.),('legacy_sources',.1,0.),('expanded_sources',.1,.02),('matched_total_weight',.12,0.)]
    for member in ('core','cat'):
        for mode,weight,new_weight in settings:
            for penalty in (1.,10.):
                result.append({'id':f'expanded-gate-{len(result):03d}','algorithm':'expanded_public_history_gate',
                    'member':member,'source_mode':mode,'auxiliary_weight':weight,'gait_weight':new_weight,
                    'epochs':80,'learning_rate':.003,'weight_decay':.1,'correction_penalty':penalty,'random_seed':42,
                    'source_target':'actual_original_current_unequal_prior_per_domain',
                    'native_target':'original_integer_delta_distribution_with_frozen_nonzero_conditional'})
    return result


def load_inputs():
    old = previous.load_inputs()
    selected = json.loads((previous.DIRECTORY/'selection.json').read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==26
    assert all(selected.get(k)==v for k,v in previous.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(previous.DIRECTORY/'selection.json')
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_ordered_residual.py'))
    fitting,reserved,manifest = prepared.load()
    audit = json.loads(INPUT_AUDIT.read_text())
    assert audit['verification']=='passed' and audit['actual_fitting_source_pairs']==3548 and audit['stored_reserved_source_pairs']==518
    assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_rpe_expanded_binary_history_inputs.py'))
    assert audit['preparation_code_sha256']==digest(Path(prepared.__file__))
    assert audit['provenance_sha256']==digest(prepared.DIRECTORY/'provenance.json') and audit['dataset_sha256']==digest(prepared.DIRECTORY/'dataset.csv')
    context = old['context_features']+list(previous.prepared.NATIVE_COLUMNS.values())
    assert len(context)==len(set(context))==20 and set(fitting.group_key).isdisjoint(old['frame'].group_key)
    declaration = json.loads(PROPOSAL.read_text())
    assert declaration['implementation_code_sha256']==digest(Path(__file__)) and declaration['plan']==plan()
    return {**old,'previous_inputs':old,'previous_selection':selected,'context_features':context,
        'gate_source':fitting,'reserved_gate_source':reserved,'expanded_input_manifest':manifest}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':previous.fingerprint(inputs['previous_inputs']),
        'previous_selection_sha256':digest(previous.DIRECTORY/'selection.json'),'previous_verification_sha256':digest(PARENT_AUDIT),
        'input_audit_sha256':digest(INPUT_AUDIT),'input_provenance_sha256':digest(prepared.DIRECTORY/'provenance.json'),
        'input_dataset_sha256':digest(prepared.DIRECTORY/'dataset.csv'),'source_preparation_code_sha256':digest(Path(prepared.__file__)),
        'proposal_sha256':digest(PROPOSAL),'frozen_gate_code_sha256':digest(Path(frozen.__file__)),
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),'worker_processes':2}


def history_values(frame):
    values = frame[['prior','second'] if 'prior' in frame else ['prior_borg','prior2_borg']].copy()
    values.columns = ['prior','second']
    assert values.prior.notna().all()
    return values


class ChangeGateNetwork(frozen.ChangeGateNetwork):
    def __init__(self,context_width):
        nn.Module.__init__(self)
        self.encoder = nn.Sequential(nn.Linear(3,8),nn.Tanh(),nn.Linear(8,8),nn.Tanh())
        self.corrector = nn.Sequential(nn.Linear(context_width+9,8),nn.Tanh(),nn.Linear(8,1))
        self.source_heads = nn.ModuleDict({d:nn.Linear(8,1) for d in sorted(COUNTS)})
        nn.init.zeros_(self.corrector[-1].weight)
        nn.init.zeros_(self.corrector[-1].bias)


class ExpandedHistoryGateBorg(frozen.PublicChangeGateBorg):
    def prepare_normalizers(self,frame,external):
        self.history_normalizers,self.normalization_summary = {},{}
        parts = {'native':frame,**{domain:part for domain,part in external.groupby('source_domain')}}
        for domain,part in parts.items():
            values = history_values(part)
            imputer = SimpleImputer(strategy='median',keep_empty_features=True)
            scaler = StandardScaler().fit(imputer.fit_transform(values))
            self.history_normalizers[domain] = imputer,scaler
            self.normalization_summary[domain] = {'fitting_rows':len(part),'fitting_people':part.group_key.nunique(),
                'actual_missing_second_priors':int(values.second.isna().sum()),'numeric_columns':2,'unscaled_availability_bits':1}

    def history_transform(self,frame,domain='native'):
        values = history_values(frame)
        imputer,scaler = self.history_normalizers[domain]
        transformed = np.column_stack([scaler.transform(imputer.transform(values)),values.second.isna().to_numpy(float)])
        assert np.isfinite(transformed).all() and np.isin(transformed[:,2],[0.,1.]).all()
        return torch.tensor(transformed,dtype=torch.float32)

'''
body = []
for name in ('read_cache','initialize','fit_group','save','select'):
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    body.append(''.join(lines[node.lineno-1:node.end_lineno])+'\n')
body = '\n\n'.join(body).replace('plan()[18:]','plan()[8:]').replace('FullDeltaCadenceBorg(c)','ExpandedHistoryGateBorg(c)')
body = body.replace("inputs['control_selections'][c['control_study']]['results']","inputs['previous_selection']['results']")
body = body.replace("'new_joint_network_fits':40","'new_joint_network_fits':80")
body = body.replace("'actual_source_fitting_pairs_available':851,'source_reserved_pairs_not_fitted':206", "'actual_source_fitting_pairs_available':3548,'source_reserved_pairs_not_fitted':518")
body = body.replace('Actual ordered three-coefficient residual','Actual expanded public-history gate')
start = body.index("'policy':'Fixed26recipes:")
end = body.index("'}",start)
body = body[:start]+"'policy':'Fixed24recipes:8inherited controls plus2native bases*4source modes*penalty1/10. Shared3actual history inputs;20measured native-private context inputs. Six source heads;legacy5each weight old/5,gait weight0/.02;old.12control matches total.12auxiliary weight. Keep80epochs,seed42,AdamW.003/decay.1 and immutable native bases/nonzero ratios. Actual3548source fitting pairs/518reserved plus5gait people unreceived. No invented source physiology,scale conversion,clocks or synthetic examples. Original487/179,.65CVgate and exact Borg scoring.'"+body[end+1:]
text = header+fit+'\n\n'+body+"\n\nif __name__=='__main__':\n    import fatigue_expanded_public_gate as implementation\n    implementation.select()\n"
compile(text,'fatigue_expanded_public_gate.py','exec')
path = root/'fatigue_expanded_public_gate.py'
if path.exists():
    assert path.read_text()==text
else:
    path.write_text(text,encoding='utf-8')
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_sources_sha256':{p.name:digest(p) for p in (parent_path,frozen_path)},
    'model_code_sha256':digest(path),'historical_sources_modified':False,'new_predictive_estimator_fits':0}
(ROOT/'docs/fatigue-80-2026-10-25/expanded-public-gate-model-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
