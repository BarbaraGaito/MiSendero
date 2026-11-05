"""Register audited study55 without rerunning historical model families."""
import json
from pathlib import Path
import fatigue_change_gate_regularization as study
from public_sources import digest

audit = json.loads((study.DOCS/'change-gate-regularization-verification.json').read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_change_gate_regularization.py'))
path = Path(__file__).with_name('fatigue_80_checkpoint.py')
code = path.read_text()
old = 'for name in ("public-change-gate-transfer-80-v1",'
new = 'for name in ("change-gate-regularization-80-v1", "public-change-gate-transfer-80-v1",'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
branch = '''        if name == "change-gate-regularization-80-v1":
            from audit_fatigue_change_gate_regularization import validate as validate_change_gate_regularization
            gate_audit = validate_change_gate_regularization()
            result["change_gate_regularization_transfer"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
'''
marker = '        if name == "public-change-gate-transfer-80-v1":\n'
if branch not in code:
    assert code.count(marker)==1
    code = code.replace(marker,branch+marker)
compile(code,str(path),'exec')
path.write_text(code,encoding='utf-8')
print('Registered audited study55without historical refitting',flush=True)
