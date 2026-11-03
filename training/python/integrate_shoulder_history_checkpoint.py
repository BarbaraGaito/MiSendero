"""Register the completed real-shoulder study without historical refits."""
import json
from pathlib import Path
import fatigue_shoulder_history_joint as study
from public_sources import digest

proof = json.loads((study.DOCS/'shoulder-history-joint-verification.json').read_text())
assert proof['verification']=='passed' and proof['selection_sha256']==digest(study.DIRECTORY/'selection.json')
assert proof['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_shoulder_history_joint.py'))
path = Path(__file__).with_name('fatigue_80_checkpoint.py')
code = path.read_text()
old = 'for name in ("catboost-schedule-80-v1",'
new = 'for name in ("shoulder-history-joint-transfer-80-v1", "catboost-schedule-80-v1",'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
branch = '''        if name == "shoulder-history-joint-transfer-80-v1":
            from audit_fatigue_shoulder_history_joint import validate as validate_shoulder_history
            result["shoulder_history_joint_transfer"] = validate_shoulder_history()
'''
marker = '        if name == "catboost-schedule-80-v1":\n'
if branch not in code:
    assert code.count(marker)==1
    code = code.replace(marker,branch+marker)
compile(code,str(path),'exec')
path.write_text(code,encoding='utf-8')
print('Registered audited study50without refitting historical models',flush=True)
