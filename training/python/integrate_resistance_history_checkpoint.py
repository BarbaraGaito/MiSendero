"""Register the completed resistance comparison in the historical verifier."""
from pathlib import Path

path = Path(__file__).with_name("fatigue_80_checkpoint.py")
text = path.read_text()
old = 'for name in ("two-history-joint-transfer-80-v1",'
new = 'for name in ("resistance-history-joint-transfer-80-v1", "two-history-joint-transfer-80-v1",'
if new not in text:
    assert text.count(old) == 1
    text = text.replace(old,new)
branch = '''        if name == "resistance-history-joint-transfer-80-v1":
            from audit_fatigue_resistance_history_joint import validate as validate_resistance_history
            result["resistance_history_joint_transfer"] = validate_resistance_history()
'''
marker = '        if name == "two-history-joint-transfer-80-v1":\n'
if branch not in text:
    assert text.count(marker) == 1
    text = text.replace(marker,branch+marker)
compile(text,str(path),"exec")
path.write_text(text,encoding="utf-8")
print("Registered completed study47without running/refitting historical studies",flush=True)
