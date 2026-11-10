"""Retrieve only bounded official public dataset metadata, not archive bundles."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT/'training/data/raw/fatigue-research/bbex-dryad-fbg79cp45-v1'
URL = 'https://datadryad.org/api/v2/datasets/doi%3A10.5061%2Fdryad.fbg79cp45'


def main():
    DIRECTORY.mkdir(exist_ok=True)
    def bounded(url,name):
        assert urllib.parse.urlparse(url).hostname=='datadryad.org'
        path = DIRECTORY/name
        if path.exists():
            payload = path.read_bytes()
        else:
            request = urllib.request.Request(url,headers={'User-Agent':'MiSendero-public-research/1.0','Accept':'application/json'})
            with urllib.request.urlopen(request,timeout=25) as response:
                payload = response.read(2000001)
                assert len(payload)<=2000000,'Public metadata exceeds fixed bound'
                json.loads(payload)
            path.write_bytes(payload)
        return json.loads(payload)
    metadata = bounded(URL,'dataset-metadata.json')
    assert metadata['license']=='https://spdx.org/licenses/CC0-1.0.html'
    assert metadata['identifier']=='doi:10.5061/dryad.fbg79cp45'
    version_url = 'https://datadryad.org'+metadata['_links']['stash:version']['href']
    version = bounded(version_url,'version-metadata.json')
    file_url = 'https://datadryad.org'+version['_links']['stash:files']['href']
    files = bounded(file_url,'file-metadata.json')
    print(json.dumps({'license':metadata['license'],'version_links':version['_links'],
        'file_page_keys':list(files),'files':files.get('_embedded',{}),'dataset_bundles_downloaded':0}),flush=True)


if __name__=='__main__':
    main()
