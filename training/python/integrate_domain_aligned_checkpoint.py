"""Register the completed alignment study without historical model refits."""
import json
from pathlib import Path
import fatigue_domain_aligned_history as study
from public_sources import digest

audit = json.loads((study.DOCS/'domain-aligned-history-verification.json').read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_domain_aligned_history.py'))
path = Path(__file__).with_name('fatigue_80_checkpoint.py')
code = path.read_text()
old = 'for name in ("shoulder-history-joint-transfer-80-v1",'
new = 'for name in ("domain-aligned-history-transfer-80-v1", "shoulder-history-joint-transfer-80-v1",'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
branch = '''        if name == "domain-aligned-history-transfer-80-v1":
            from audit_fatigue_domain_aligned_history import validate as validate_domain_aligned_history
            result["domain_aligned_history_transfer"] = validate_domain_aligned_history()
'''
marker = '        if name == "shoulder-history-joint-transfer-80-v1":\n'
if branch not in code:
    assert code.count(marker)==1
    code = code.replace(marker,branch+marker)
compile(code,str(path),'exec')
path.write_text(code,encoding='utf-8')
print('Registered audited study51without refitting historical models',flush=True)
