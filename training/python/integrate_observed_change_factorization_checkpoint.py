"""Register the audited two-stage exact-Borg family in the historical registry."""
import json
from pathlib import Path
import fatigue_observed_change_factorization as study
from public_sources import digest

audit = json.loads((study.DOCS/'observed-change-factorization-verification.json').read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_observed_change_factorization.py'))
path = Path(__file__).with_name('fatigue_80_checkpoint.py')
code = path.read_text()
old = 'for name in ("causal-transition-memory-80-v1",'
new = 'for name in ("observed-change-factorization-80-v1", "causal-transition-memory-80-v1",'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
branch = '''        if name == "observed-change-factorization-80-v1":
            from audit_fatigue_observed_change_factorization import validate as validate_observed_change_factorization
            change_audit = validate_observed_change_factorization()
            result["observed_change_factorization"] = change_audit
            if change_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": change_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    change_audit["new_test_evaluation"]["test_accuracy"])
                continue
'''
marker = '        if name == "causal-transition-memory-80-v1":\n'
if branch not in code:
    assert code.count(marker)==1
    code = code.replace(marker,branch+marker)
compile(code,str(path),'exec')
path.write_text(code,encoding='utf-8')
print('Registered audited study53without refitting historical models',flush=True)
