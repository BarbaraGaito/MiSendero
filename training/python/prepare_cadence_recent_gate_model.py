"""Prepare a distinct native recent-context comparison; do not mutate study56."""
import ast
import json
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent
parent_path = root/'fatigue_cadence_binary_gate.py'
parent = parent_path.read_text()
tree = ast.parse(parent)
lines = parent.splitlines(keepends=True)


def function(name):
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    return ''.join(lines[node.lineno-1:node.end_lineno])+'\n'


header = '''"""Measured recent native HR extends only the native-private gate context."""
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


'''
body = '\n\n'.join(function(name) for name in ('read_cache','initialize','fit_group','save','select'))
body = body.replace('plan()[2:]','plan()[6:]')
body = body.replace('Actual CADENCE physiology-binary','Actual recent native-context')
old_policy = """'policy':'Fixed6recipes:2inherited global controls plus2frozen native bases*source weights0/.1. '
            'Add actually observed prior physiology to the shared actual-two-prior encoder. Numeric6inputs '
            'use separate fitting-only native/source normalizers;5real availability flags stay binary. '
            'Source current-bout HR,exact response ages/native phases and scale equivalence are not assumed. '
            'Keep80epochs,penalty1,optimizer.003/decay.1,original487/179and exact native Borg scoring.'"""
assert old_policy in body
body = body.replace(old_policy,"'policy':'Fixed10recipes:6inherited controls plus2frozen native bases*source weights0/.1. Add only3measured recent native HR/context inputs to the old13private inputs. The851source pairs,shared encoder and source normalization remain unchanged. Source current-bout HR or native-private rows are not fabricated. Keep80epochs,penalty1,optimizer.003/decay.1,all487/179and exact Borg scoring.'")
text = header+body+"\n\nif __name__=='__main__':\n    import fatigue_cadence_recent_gate as implementation\n    implementation.select()\n"
compile(text,'fatigue_cadence_recent_gate.py','exec')
path = root/'fatigue_cadence_recent_gate.py'
if path.exists():
    assert path.read_text()==text
else:
    path.write_text(text,encoding='utf-8')
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_parent_code_sha256':digest(parent_path),'model_code_sha256':digest(path),
    'parent_modified':False,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}
(ROOT/'docs/fatigue-80-2026-10-25/cadence-recent-gate-model-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
