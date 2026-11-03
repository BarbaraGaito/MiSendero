"""Bounded public Zenodo metadata retrieval;no sensor downloads or model fitting."""
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT/'training/data/raw/fatigue-research/treadmill-cr10-23208045-v1'
URL = 'https://zenodo.org/api/records/23208045'


def fetch():
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    result = {'checked_at':datetime.now(timezone.utc).isoformat(),'url':URL,
        'discovery_only_secondary_url':'https://chatppg.com/research/datasets/alfaro-treadmill-fatigue-polar-ppg-eda',
        'original_metadata_verified':False,'source_data_downloaded':False,'model_fitting_started':False,
        'secondary_license_description_conflicts':True}
    request = urllib.request.Request(URL,headers={'User-Agent':'MiSendero public original-dataset eligibility review'})
    try:
        with urllib.request.urlopen(request,timeout=35) as response:
            payload = response.read(2_000_001)
            assert len(payload)<=2_000_000 and response.url.startswith('https://')
            metadata = json.loads(payload)
            assert str(metadata['id'])=='23208045'
            path = DIRECTORY/'metadata.json'
            if path.exists():
                assert path.read_bytes()==payload,'Preserve original metadata before fetching another version'
            else:
                path.write_bytes(payload)
            result.update(original_metadata_verified=True,http_status=response.status,
                final_url=response.url,metadata_bytes=len(payload),metadata_sha256=hashlib.sha256(payload).hexdigest(),
                title=metadata.get('metadata',{}).get('title'),access=metadata.get('metadata',{}).get('access_right'),
                license=metadata.get('metadata',{}).get('license'),
                files=[{'key':row.get('key'),'size':row.get('size'),'checksum':row.get('checksum'),
                    'links':row.get('links')} for row in metadata.get('files',[])])
    except urllib.error.HTTPError as error:
        result.update(http_status=error.code,error_type='HTTPError',error=str(error))
    except (urllib.error.URLError,TimeoutError) as error:
        result.update(error_type=type(error).__name__,error=str(error))
    path = DIRECTORY/'metadata-access-result.json'
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)
    return result


if __name__=='__main__':
    fetch()
