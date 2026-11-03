"""Record primary metadata-only revalidation;embargoed files remain unused."""
import json
from pathlib import Path
import fetch_treadmill_cr10_metadata as fetch
from public_sources import digest

raw_path = fetch.DIRECTORY/'metadata.json'
access_path = fetch.DIRECTORY/'metadata-access-result.json'
raw = json.loads(raw_path.read_text())
access = json.loads(access_path.read_text())
meta = raw['metadata']
assert access['original_metadata_verified'] and access['metadata_sha256']==digest(raw_path)
assert str(raw['id'])=='23208045' and meta['access_right']=='embargoed' and meta['embargo_date']=='2027-04-07'
assert raw.get('files',[])==[] and not access['source_data_downloaded'] and not access['model_fitting_started']
assert meta['license']['id']=='cc-by-4.0' and 'CC BY-NC 4.0' in meta['description']
old_path = fetch.DIRECTORY.parent/'public-candidates-80-v1/treadmill.json'
old = json.loads(old_path.read_text())
same_access = all(old['metadata'].get(key)==meta.get(key) for key in ('access_right','embargo_date','license'))
assert same_access and old.get('files',[])==[]
report = {'inspection':'passed','inspection_code_sha256':digest(Path(__file__)),
    'fetch_code_sha256':digest(Path(fetch.__file__)),'official_url':fetch.URL,
    'official_record_url':'https://zenodo.org/records/23208045','checked_at':access['checked_at'],
    'primary_metadata_sha256':digest(raw_path),'access_receipt_sha256':digest(access_path),
    'previous_primary_snapshot_sha256':digest(old_path),'previous_access_conditions_unchanged':True,
    'access':'embargoed','embargo_until':'2027-04-07','public_file_count':0,
    'metadata_license':'cc-by-4.0','description_license':'CC BY-NC4.0',
    'license_description_conflict_unresolved':True,'source_data_downloaded':False,
    'training_merge_approved':False,'new_native_borg_cases':0,'new_predictive_estimator_fits':0,
    'new_test_predictions_computed':0,
    'interpretation':'The primary public record was revalidated;this is not a newly discovered usable '
        'source. It was already reviewed. No file access bypass or repeated download retry is warranted. '
        'The repository states Borg CR10 held until next report,so repeated sensor rows must never '
        'be counted as independent original ratings. Future eligibility would require original report '
        'event provenance and consistent license terms. Existing public training work can continue.'}
path = fetch.ROOT/'docs/fatigue-80-2026-10-25/treadmill-cr10-access-refresh.json'
path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
