"""Cache only original left-wrist walking segments of DUO-GAIT, not whole ZIPs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import zlib

from duo_gait_remote import RemoteZipBytes, archive_url, read_member
import zipfile

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'training/data/raw/duo-gait'
SIZE = 3025750473


def manifest() -> list[dict]:
    with zipfile.ZipFile(RemoteZipBytes(archive_url('interim.zip'), SIZE)) as source:
        return [{'name': i.filename, 'size': i.file_size, 'compressed_size': i.compress_size,
                 'crc32': f'{i.CRC:08x}'} for i in source.infolist()]


def fetch(entry: dict) -> dict:
    match = re.fullmatch(r'interim/OG_(st|dt)_(control|fatigue)/(sub_\d{2})/LW.csv', entry['name'])
    if not match:
        raise ValueError('Unexpected member path')
    task, condition, person = match.groups()
    destination = RAW / 'wrist' / f'{person}-{task}-{condition}-LW.csv'
    if destination.exists():
        data = destination.read_bytes()
    else:
        data, _ = read_member('interim.zip', SIZE, entry['name'])
    if len(data) != entry['size'] or f'{zlib.crc32(data):08x}' != entry['crc32']:
        raise ValueError(f"ZIP CRC32/size mismatch for {entry['name']}")
    destination.write_bytes(data)
    print(destination.name, len(data), flush=True)
    return {'person': person, 'task': task, 'condition': condition, 'member': entry['name'],
            'cache_name': destination.name, 'bytes': len(data), 'zip_crc32': entry['crc32'],
            'sha256': hashlib.sha256(data).hexdigest()}


def main() -> None:
    (RAW / 'wrist').mkdir(parents=True, exist_ok=True)
    listing = manifest()
    entries = sorted((i for i in listing if re.fullmatch(
        r'interim/OG_(?:st|dt)_(?:control|fatigue)/sub_\d{2}/LW.csv', i['name'])), key=lambda x: x['name'])
    if len(entries) != 64:
        raise ValueError('Expected 16 people x 4 left-wrist walking recordings')
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(fetch, entries))
    (RAW / 'wrist-manifest.json').write_text(json.dumps({
        'source': 'https://zenodo.org/records/8244887', 'archive': 'interim.zip',
        'archive_size': SIZE, 'official_archive_md5': 'de9ffa7ed1d9ea91e0b6b2e3af5ecda1',
        'complete_archive_md5_verified': False,
        'integrity': 'Selected complete members checked against CRC32 in remote ZIP central directory; SHA256 recorded locally. Entire ZIP not downloaded.',
        'records': records}, indent=2) + '\n', encoding='utf-8')
    print('Cached and checked', len(records), 'left-wrist segments', flush=True)


if __name__ == '__main__':
    main()
