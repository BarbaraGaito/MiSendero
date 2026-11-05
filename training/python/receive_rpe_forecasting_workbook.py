"""Save a fitting-only GitHub workbook after independent original-byte verification."""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
import review_rpe_forecasting_candidate as candidate
from public_sources import digest


def receive(person,payload):
    inspection_path = candidate.DOCS/'rpe-forecasting-candidate-inspection.json'
    inspection = json.loads(inspection_path.read_text())
    assert inspection['inspection']=='passed' and inspection['inspection_code_sha256']==digest(Path(candidate.__file__))
    assert inspection['revision']==candidate.REVISION and inspection['participant_split_frozen_before_original_target_review']
    entry = next(row for row in inspection['case2_file_inventory'] if row['person']==person)
    assert entry['source_partition']=='fitting' and person in inspection['case2_fitting_people']
    assert person not in inspection['case2_reserved_people']
    assert payload['encoding']=='base64' and payload['sha']==entry['git_blob_sha1']
    data = base64.b64decode(''.join(payload['content'].split()),validate=True)
    assert len(data)==entry['bytes'] and candidate.git_blob(data)==entry['git_blob_sha1']
    directory = candidate.DIRECTORY/'workbooks'
    directory.mkdir(exist_ok=True)
    path = directory/f'ID{person}GaitFeatures.xlsx'
    assert path.resolve().is_relative_to(candidate.DIRECTORY.resolve())
    assert not path.is_symlink()
    if path.exists():
        assert path.read_bytes()==data,'Preserve original source bytes'
    else:
        path.write_bytes(data)
    report = {'version':1,'receiver_code_sha256':digest(Path(__file__)),'candidate_inspection_sha256':digest(inspection_path),
        'repository':inspection['repository'],'revision':inspection['revision'],'original_repository_path':entry['path'],
        'person':person,'group_key':entry['group_key'],'source_partition':'fitting','bytes':len(data),
        'published_git_blob_sha1':entry['git_blob_sha1'],'verified_git_blob_sha1':candidate.git_blob(data),
        'sha256':hashlib.sha256(data).hexdigest(),'relative_path':str(path.relative_to(candidate.DIRECTORY)).replace('\\','/'),
        'reserved_people_data_received':False,'source_target_cells_reviewed':False,'new_predictive_estimator_fits':0}
    receipt = path.with_suffix('.receipt.json')
    if receipt.exists():
        assert json.loads(receipt.read_text())==report
    else:
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'person':person,'original_bytes_verified':True,'bytes':len(data),'sha256':report['sha256']}),flush=True)
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--person',type=int,required=True)
    args = parser.parse_args()
    receive(args.person,json.load(sys.stdin))
