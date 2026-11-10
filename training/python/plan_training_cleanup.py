"""Identify disposable installer caches and exact, completed checkpoint copies."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAINING = ROOT / 'training'
entries = []
preserved = []
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

for base, directories, files in os.walk(TRAINING, followlinks=False):
    folder = Path(base)
    directories[:] = [name for name in directories if not (folder/name).is_symlink()]
    disposable = folder.name in ('pip-cache', '__pycache__')
    if disposable:
        for path in folder.rglob('*'):
            if path.is_file() and not path.is_symlink():
                resolved = path.resolve()
                assert resolved.is_relative_to(TRAINING.resolve())
                entries.append({'path':str(resolved), 'bytes':path.stat().st_size,
                                'reason':'installer_download_cache' if folder.name == 'pip-cache' else 'regenerable_python_bytecode'})
        directories.clear()
        continue
    for name in files:
        if name != 'selection.tmp':
            continue
        temporary, final = folder/name, folder/'selection.json'
        if final.exists() and not temporary.is_symlink():
            try:
                complete = json.loads(final.read_text(encoding='utf-8')).get('status') == 'complete'
                if complete and temporary.stat().st_size == final.stat().st_size and sha(temporary) == sha(final):
                    entries.append({'path':str(temporary.resolve()),'bytes':temporary.stat().st_size,
                                    'sha256':sha(temporary),'retained_identical_copy':str(final.resolve()),
                                    'reason':'exact_temporary_copy_of_completed_selection'})
                else:
                    preserved.append(str(temporary.relative_to(ROOT)))
            except (ValueError,OSError):
                preserved.append(str(temporary.relative_to(ROOT)))

assert len({row['path'] for row in entries}) == len(entries)
report = {'created_at':datetime.now(timezone.utc).isoformat(),'workspace':str(ROOT),
          'scope':str(TRAINING),'files':entries,'file_count':len(entries),
          'bytes':sum(row['bytes'] for row in entries),
          'temporary_checkpoints_preserved_without_identical_complete_copy':preserved,
          'datasets_models_and_final_results_deleted':False}
target = ROOT/'docs/training-cleanup-2026-10-29.json'
target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'plan':str(target),'files':len(entries),'bytes':report['bytes'],
                  'preserved_temporary_checkpoints':len(preserved)}))
