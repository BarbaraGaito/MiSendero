"""Prepare a static full native residual while preserving the scalar-gate studies."""
import ast
import json
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent
gate_path = root/'fatigue_cadence_binary_gate.py'
gate_text = gate_path.read_text()
gate_tree = ast.parse(gate_text)
fit_node = next(node for node in ast.walk(gate_tree) if isinstance(node,ast.FunctionDef) and node.name=='fit')
fit = ast.get_source_segment(gate_text,fit_node)
changes = {
    'offsets = gate_logit(original_probabilities)':"offsets = cached['fit_logits'].detach()",
    'target = torch.tensor(current!=prior,dtype=torch.float64)':'target = torch.tensor(current-prior+10,dtype=torch.long)',
    'self.network = ChangeGateNetwork(context.shape[1])':'self.network = FullDeltaNetwork(context.shape[1])',
    'recombine(original_probabilities,offsets)':'torch.softmax(offsets,dim=1)',
    'classification = nn.functional.binary_cross_entropy_with_logits(native_logits,target)':
        'classification = nn.functional.cross_entropy(native_logits,target)',
    "'native_binary_loss'":"'native_delta_nll'",
    "'nonzero_delta_relative_probabilities_frozen':True,'native_loss_equivalent_to_joint_nll_up_to_frozen_conditional':True":
        "'nonzero_delta_relative_probabilities_frozen':False,'native_objective':'21_delta_cross_entropy','native_delta_probability_residuals_fitted':True"}
for old,new in changes.items():
    assert old in fit,old
    fit = fit.replace(old,new)
fit = '    '+fit.replace('\n','\n    ')+'\n'

header = '''"""Full21-delta native residual with actual physiology and separate source BCE."""
from __future__ import annotations
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
import fatigue_cadence_recent_gate as previous
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = previous.DIRECTORY.parent/'cadence-full-delta-residual-80-v1'
DOCS = previous.DOCS
PROPOSAL = DOCS/'cadence-full-delta-residual-plan.json'
PARENT_AUDIT = DOCS/'cadence-recent-gate-verification.json'
INPUT_AUDIT = previous.INPUT_AUDIT
REVIEW = DOCS/'cadence-full-delta-residual-review.json'
native,prepared,source,COUNTS,added = previous.native,previous.prepared,previous.source,previous.COUNTS,previous.added
state_values = previous.state_values
_RUNTIME = None


def plan():
    result = [{'id':f'cadence-full-delta-{n:03d}','algorithm':'previous_real_control',
        'parent_candidate_id':f'recent-gate-{key:03d}'} for n,key in enumerate((0,1,6,7,8,9))]
    for member in ('core','cat'):
        for weight in (0.,.1):
            for penalty in (.1,1.):
                result.append({'id':f'cadence-full-delta-{len(result):03d}','algorithm':'cadence_full_delta_residual',
                    'member':member,'auxiliary_weight':weight,'epochs':80,'learning_rate':.003,'weight_decay':.1,
                    'correction_penalty':penalty,'random_seed':42,'source_target':'actual_current_unequal_prior_original6to20',
                    'native_target':'original_integer_delta_cross_entropy_21','residual_outputs':21})
    return result


def load_inputs():
    old = previous.load_inputs()
    path = previous.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    assert selected['status']=='complete' and len(selected['results'])==10
    assert all(selected.get(k)==v for k,v in previous.fingerprint(old).items())
    assert proof['verification']=='passed' and proof['selection_sha256']==digest(path)
    assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_recent_gate.py'))
    review = json.loads(REVIEW.read_text())
    assert review['review']=='passed' and review['verification_sha256']==digest(PARENT_AUDIT)
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_full_delta_residual.py'))
    declared = json.loads(PROPOSAL.read_text())
    assert declared['implementation_code_sha256']==digest(Path(__file__)) and declared['plan']==plan()
    assert len(old['context_features'])==16 and len(old['gate_source'])==851
    return {**old,'previous_inputs':old,'previous_selection':selected}


def fingerprint(inputs):
    return {'code_sha256':digest(Path(__file__)),'previous_signature':previous.fingerprint(inputs['previous_inputs']),
        'previous_selection_sha256':digest(previous.DIRECTORY/'selection.json'),'previous_verification_sha256':digest(PARENT_AUDIT),
        'input_audit_sha256':digest(INPUT_AUDIT),'proposal_sha256':digest(PROPOSAL),'review_sha256':digest(REVIEW),
        'frozen_gate_implementation_sha256':digest(Path(previous.previous.__file__)),
        'public_real_data_policy_sha256':digest(DOCS/'public-real-data-policy.json'),'worker_processes':2}


class FullDeltaNetwork(previous.ChangeGateNetwork):
    def __init__(self,context_width):
        nn.Module.__init__(self)
        self.encoder = nn.Sequential(nn.Linear(11,8),nn.Tanh(),nn.Linear(8,8),nn.Tanh())
        self.corrector = nn.Sequential(nn.Linear(context_width+29,8),nn.Tanh(),nn.Linear(8,21))
        self.source_heads = nn.ModuleDict({'cadence':nn.Linear(8,1)})
        nn.init.zeros_(self.corrector[-1].weight)
        nn.init.zeros_(self.corrector[-1].bias)

    def correction(self,history,context,offsets):
        joined = torch.cat([self.encoder(history),context,torch.softmax(offsets,dim=1).float()],dim=1)
        values = self.corrector(joined).to(offsets.dtype)
        # A common logit translation cannot alter predictions; penalize only centered residuals.
        return values-values.mean(dim=1,keepdim=True)


class FullDeltaCadenceBorg(previous.CadenceBinaryGateBorg):
'''
probabilities = '''
    def probabilities(self,frame):
        if list(frame)!=self.input_features:
            raise ValueError('Input-only causal features in their declared order are required')
        validate_calibration(frame)
        with torch.no_grad():
            offsets = self.base.logits(frame)
            correction = self.network.correction(self.history_transform(frame),self.context_transform(frame),offsets)
            probability = torch.softmax(offsets+correction,dim=1)
        assert torch.isfinite(probability).all()
        torch.testing.assert_close(probability.sum(dim=1),torch.ones(len(frame),dtype=torch.float64),rtol=1e-12,atol=1e-15)
        return probability
'''
old = (root/'fatigue_cadence_recent_gate.py').read_text()
old_lines = old.splitlines(keepends=True)
old_tree = ast.parse(old)
body = []
for name in ('read_cache','initialize','fit_group','save','select'):
    node = next(node for node in old_tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
    body.append(''.join(old_lines[node.lineno-1:node.end_lineno])+'\n')
body = '\n\n'.join(body).replace('CadenceBinaryGateBorg(c)','FullDeltaCadenceBorg(c)')
body = body.replace("'new_joint_network_fits':20","'new_joint_network_fits':40")
body = body.replace('Actual recent native-context','Actual full native-delta residual')
start = body.index("'policy':'Fixed10recipes:")
end = body.index("'}",start)
body = body[:start]+"'policy':'Fixed14recipes:6inherited global/scalar controls plus2native bases*source0/.1*penalty.1/1. Shared11measured history/prior-physiology inputs and16native private context inputs stay unchanged. A centered21delta residual,zero initialized,learns exact native delta cross-entropy;separate CADENCE851change BCE stays original-scale independent. Frozen base weights,80epochs,AdamW.003/decay.1,no fabricated source context or extra rows. Original487/179and.65CVgate.'"+body[end+1:]
text = header+fit+probabilities+'\n\n'+body+"\n\nif __name__=='__main__':\n    import fatigue_cadence_full_delta as implementation\n    implementation.select()\n"
compile(text,'fatigue_cadence_full_delta.py','exec')
path = root/'fatigue_cadence_full_delta.py'
if path.exists():
    assert path.read_text()==text
else:
    path.write_text(text,encoding='utf-8')
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_sources_sha256':{p.name:digest(p) for p in (gate_path,root/'fatigue_cadence_recent_gate.py')},
    'model_code_sha256':digest(path),'historical_sources_modified':False,'new_predictive_estimator_fits':0}
(ROOT/'docs/fatigue-80-2026-10-25/cadence-full-delta-model-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
