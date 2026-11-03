"""Prepare stronger penalties with the frozen full-delta objective unchanged."""
import ast
import json
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent
old_path = root/'fatigue_cadence_full_delta.py'
old = old_path.read_text()
old_lines = old.splitlines(keepends=True)
tree = ast.parse(old)
header = '''"""Stronger native full-delta residual regularization on real public observations."""
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


'''
body = []
for name in ('read_cache','initialize','fit_group','save','select'):
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    body.append(''.join(old_lines[node.lineno-1:node.end_lineno])+'\n')
body = '\n\n'.join(body).replace('Actual full native-delta residual','Actual stronger delta regularization')
start = body.index("'policy':'Fixed14recipes:")
end = body.index("'}",start)
body = body[:start]+"'policy':'Fixed14recipes:6inherited global/penalty1controls plus2native bases*source0/.1*penalty10/100. Only the declared residual penalty changes;keep frozen study58fit/architecture,851source pairs,11shared inputs,16private native inputs,80epochs/seed42/AdamW.003/decay.1 and10old base caches. Exact native Borg scoring on original487/179,.65CVtestgate,no synthetic examples or fabricated source context.'"+body[end+1:]
text = header+body+"\n\nif __name__=='__main__':\n    import fatigue_cadence_delta_regularization as implementation\n    implementation.select()\n"
compile(text,'fatigue_cadence_delta_regularization.py','exec')
path = root/'fatigue_cadence_delta_regularization.py'
if path.exists():
    assert path.read_text()==text
else:
    path.write_text(text,encoding='utf-8')
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_parent_code_sha256':digest(old_path),'model_code_sha256':digest(path),
    'historical_sources_modified':False,'new_predictive_estimator_fits':0}
(ROOT/'docs/fatigue-80-2026-10-25/cadence-delta-regularization-model-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
