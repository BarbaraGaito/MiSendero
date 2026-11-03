"""Register audited study60 without historical refitting."""
import json
from pathlib import Path
import fatigue_cadence_ordered_residual as study
from public_sources import digest

audit = json.loads((study.DOCS/'cadence-ordered-residual-verification.json').read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_ordered_residual.py'))
path = Path(__file__).with_name('fatigue_80_checkpoint.py')
code = path.read_text()
old = f'for name in ("{study.previous.DIRECTORY.name}",'
new = f'for name in ("{study.DIRECTORY.name}", "{study.previous.DIRECTORY.name}",'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
branch = f'''        if name == "{study.DIRECTORY.name}":
            from audit_fatigue_cadence_ordered_residual import validate as validate_delta_regularization
            gate_audit = validate_delta_regularization()
            result["cadence_ordered_residual"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {{"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
'''
marker = f'        if name == "{study.previous.DIRECTORY.name}":\n'
if branch not in code:
    assert code.count(marker)==1
    code = code.replace(marker,branch+marker)
compile(code,str(path),'exec')
path.write_text(code,encoding='utf-8')
print('Registered audited study60without historical refits',flush=True)
