"""Register the audited public runner HR study without refitting history."""
import json
from pathlib import Path

import fatigue_furukawa_hr_transfer as study
from public_sources import digest

audit_path = study.DOCS/"furukawa-hr-transfer-verification.json"
audit = json.loads(audit_path.read_text())
assert audit["verification"] == "passed" and audit["selection_sha256"] == digest(study.DIRECTORY/"selection.json")
assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_furukawa_hr_transfer.py"))
path = Path(__file__).with_name("fatigue_80_checkpoint.py")
text = path.read_text()
old = 'for name in ("resistance-history-joint-transfer-80-v1",'
new = 'for name in ("furukawa-pre-report-hr-transfer-80-v1", "resistance-history-joint-transfer-80-v1",'
if new not in text:
    assert text.count(old) == 1
    text = text.replace(old,new)
branch = '''        if name == "furukawa-pre-report-hr-transfer-80-v1":
            from audit_fatigue_furukawa_hr_transfer import validate as validate_furukawa_hr
            result["furukawa_pre_report_hr_transfer"] = validate_furukawa_hr()
'''
marker = '        if name == "resistance-history-joint-transfer-80-v1":\n'
if branch not in text:
    assert text.count(marker) == 1
    text = text.replace(marker,branch+marker)
compile(text,str(path),"exec")
path.write_text(text,encoding="utf-8")
print("Registered audited study48without running/refitting historical models",flush=True)
