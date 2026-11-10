"""Inspect bounded public ZIP directories to locate actual HR/RPE workbooks."""
import hashlib
import json
import re
import struct
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT/'training/data/raw/fatigue-research/bbex-dryad-fbg79cp45-v1'
DOCS = ROOT/'docs/fatigue-80-2026-10-25'


def main():
    metadata_path = RAW/'file-metadata.json'
    dataset = json.loads((RAW/'dataset-metadata.json').read_text())
    assert dataset['license']=='https://spdx.org/licenses/CC0-1.0.html'
    files = json.loads(metadata_path.read_text())['_embedded']['stash:files']
    directory = RAW/'zip-indices'
    directory.mkdir(exist_ok=True)
    inventories = []
    def fetch(entry,start,end,kind):
        assert 0<=start<=end<entry['size'] and end-start+1<=1048576
        name = entry['path']
        assert re.fullmatch(r'drive-download-\d{8}T\d{6}Z-\d{3}\.zip',name)
        path = directory/(name+'.'+kind+'.bin')
        if path.exists():
            payload = path.read_bytes()
            assert len(payload)==end-start+1
            return payload
        # The API download route requires OAuth. Use the public download route
        # linked by the dataset page; do not supply or infer credentials.
        identifier = entry['_links']['self']['href'].rsplit('/',1)[-1]
        assert identifier.isdigit()
        url = 'https://datadryad.org/downloads/file_stream/'+identifier
        request = urllib.request.Request(url,headers={'User-Agent':'MiSendero-public-research/1.0',
            'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'})
        with urllib.request.urlopen(request,timeout=30) as response:
            assert response.status==206,'Server did not honor bounded byte range; no full download requested'
            assert response.headers.get('Content-Range')==f"bytes {start}-{end}/{entry['size']}"
            payload = response.read(end-start+2)
        assert len(payload)==end-start+1
        path.write_bytes(payload)
        return payload
    for entry in sorted((x for x in files if x['path'].endswith('.zip')),key=lambda x:x['size']):
        size = entry['size']
        start = max(0,size-65557)
        tail = fetch(entry,start,size-1,'tail')
        endpos = tail.rfind(b'PK\x05\x06')
        assert endpos>=0
        eocd = struct.unpack_from('<4s4H2LH',tail,endpos)
        _,disk,central_disk,disk_entries,entries,central_size,central_offset,comment_length = eocd
        assert disk==central_disk==0 and disk_entries==entries and entries<20000 and central_size<=1048576
        assert endpos+22+comment_length==len(tail)
        if central_offset>=start:
            central = tail[central_offset-start:central_offset-start+central_size]
        else:
            central = fetch(entry,central_offset,central_offset+central_size-1,'central-directory')
        assert len(central)==central_size
        members,position = [],0
        for _ in range(entries):
            values = struct.unpack_from('<4s6H3L5H2L',central,position)
            assert values[0]==b'PK\x01\x02' and values[13]==0
            name_length,extra_length,comment_length = values[10:13]
            encoded = central[position+46:position+46+name_length]
            member = encoded.decode('utf-8' if values[3]&2048 else 'cp437')
            members.append({'member':member,'compression':values[4],'crc32':f'{values[7]:08x}',
                'compressed_bytes':values[8],'uncompressed_bytes':values[9],'local_header_offset':values[16]})
            position += 46+name_length+extra_length+comment_length
        assert position==len(central)
        targets = [m for m in members if Path(m['member']).name in ('Heart Rate_final.xlsx','RPE_final.xlsx')]
        inventories.append({'official_filename':entry['path'],'official_bytes':size,'official_sha256':entry['digest'],
            'tail_sha256':hashlib.sha256(tail).hexdigest(),'central_directory_sha256':hashlib.sha256(central).hexdigest(),
            'central_directory_entries':entries,'members':members,'requested_workbooks':targets,
            'complete_archive_checksum_verified':False})
        print(json.dumps({'archive':entry['path'],'index_entries':entries,'workbooks':[m['member'] for m in targets]}),flush=True)
        report = {'inspection':'partial','inspection_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'official_file_metadata_sha256':hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
            'public_license':dataset['license'],'inventories':inventories,'complete_archives_downloaded':0,
            'original_workbook_cells_inspected':0,'model_fitting_started':False,
            'scope':'Bounded ZIPdirectory bytes fetched only to locate released workbooks. Full official archive SHA256must be verified before using its original cells. No supplied code or weights executed.'}
        if targets:
            report['inspection'] = 'requested_workbooks_located'
        (DOCS/'bbex-archive-index-inspection.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        found = {Path(m['member']).name for item in inventories for m in item['requested_workbooks']}
        if found=={'Heart Rate_final.xlsx','RPE_final.xlsx'}:
            break


if __name__=='__main__':
    main()
