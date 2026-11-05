"""Prepare a static three-coefficient ordered native residual,with real inputs."""
import ast
import json
import textwrap
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent
old_path = root/'fatigue_cadence_full_delta.py'
old = old_path.read_text()
tree = ast.parse(old)
fit = ast.unparse(next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='fit'))
needle = 'correction = self.network.correction(history, context, offsets)'
assert fit.count(needle)==1
fit = fit.replace(needle,'coefficients = self.network.coefficients(history, context, offsets)\n        correction = self.network.expand(coefficients)')
needle = "'correction': correction, 'source_batches': source_batches"
assert needle in fit
fit = fit.replace(needle,"'correction': correction, 'native_coefficients': coefficients, 'source_batches': source_batches")
needle = '    return self'
assert fit.count(needle)==1
fit = fit.replace(needle,"    self.training_summary.update(native_residual_coefficients=3, native_residual_logits=21, native_output_parameters=27, fixed_basis_geometry='centered_QR_delta_delta_squared_zero')\n    return self")
fit = textwrap.indent(fit,'    ')+'\n'

header = '''"""Small ordered21-delta correction with three learned coefficients."""
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
'''
lines = old.splitlines(keepends=True)
body = []
for name in ('read_cache','initialize','fit_group','save','select'):
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    body.append(''.join(lines[node.lineno-1:node.end_lineno])+'\n')
body = '\n\n'.join(body).replace('plan()[6:]','plan()[18:]')
body = body.replace('Actual full native-delta residual','Actual ordered three-coefficient residual')
needle = "inputs['previous_selection']['results']"
assert body.count(needle)==1
body = body.replace(needle,"inputs['control_selections'][c['control_study']]['results']")
start = body.index("'policy':'Fixed14recipes:")
end = body.index("'}",start)
body = body[:start]+"'policy':'Fixed26recipes:18inherited global/free21/scalar/strong-penalty controls plus2native bases*source0/.1*penalty.1/1. The3coefficient output spans fixed centered orthonormal delta,delta-squared andzero mass geometry;all21native probabilities remain available. Shared encoder/source-head initialization matches the full residual. Keep actual851source pairs,11shared inputs,16private context,80epochs/seed42/AdamW.003/decay.1 and immutable native bases. Fixed mathematical basis is not a training observation or target. Original487/179,.65CVtestgate,no synthetic rows.'"+body[end+1:]
text = header+fit+'\n\n'+body+"\n\nif __name__=='__main__':\n    import fatigue_cadence_ordered_residual as implementation\n    implementation.select()\n"
compile(text,'fatigue_cadence_ordered_residual.py','exec')
path = root/'fatigue_cadence_ordered_residual.py'
if path.exists():
    assert path.read_text()==text
else:
    path.write_text(text,encoding='utf-8')
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_full_delta_code_sha256':digest(old_path),'model_code_sha256':digest(path),
    'historical_sources_modified':False,'new_predictive_estimator_fits':0}
(ROOT/'docs/fatigue-80-2026-10-25/cadence-ordered-residual-model-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
