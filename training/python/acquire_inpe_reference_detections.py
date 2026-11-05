"""Acquire small public annual INPE South America reference-fire CSV archives."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'training/data/environmental/private/inpe-ams-satellite-reference'
BASE = 'https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/anual/AMS_sat_ref/'
MAX_BYTES = 25 * 1024 * 1024
DEFAULT_YEARS = tuple(range(2018, 2026))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def acquire(year: int, force: bool = False) -> dict:
    if not 2003 <= year <= 2025:
        raise ValueError(f'No annual archive is listed for {year}; expected 2003–2025.')
    filename = f'focos_ams_ref_{year}.zip'
    url = BASE + filename
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / filename
    if destination.is_file() and not force:
        size = destination.stat().st_size
        if size > MAX_BYTES:
            raise ValueError(f'Existing archive exceeds the {MAX_BYTES}-byte safety limit: {filename}')
        return {
            'year': year,
            'url': url,
            'filename': filename,
            'bytes': size,
            'sha256': sha256(destination),
            'status': 'cached',
        }

    request = urllib.request.Request(url, headers={'User-Agent': 'MiSendero-research/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            final_host = response.geturl().split('/')[2].casefold()
            if final_host != 'dataserver-coids.inpe.br':
                raise ValueError(f'Unexpected redirect host: {final_host}')
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_BYTES:
                raise ValueError(f'Remote archive exceeds the {MAX_BYTES}-byte safety limit: {filename}')
            descriptor, temporary_name = tempfile.mkstemp(prefix=f'.{filename}.', suffix='.part', dir=OUTPUT)
            temporary = Path(temporary_name)
            count = 0
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > MAX_BYTES:
                            raise ValueError(f'Download exceeded the {MAX_BYTES}-byte safety limit: {filename}')
                        stream.write(block)
                if content_length and count != int(content_length):
                    raise IOError(f'Incomplete response for {filename}: {count} of {content_length} bytes')
                temporary.replace(destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            return {
                'year': year,
                'url': url,
                'filename': filename,
                'bytes': count,
                'sha256': sha256(destination),
                'last_modified': response.headers.get('Last-Modified'),
                'status': 'downloaded',
            }
    except urllib.error.URLError as exc:
        raise RuntimeError(f'INPE download failed for {year}: {exc}') from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, action='append', help='Year to acquire; repeat to select several.')
    parser.add_argument('--force', action='store_true', help='Replace cached annual ZIPs.')
    parser.add_argument('--manifest', type=Path, default=OUTPUT / 'source-manifest.json')
    args = parser.parse_args()
    years = args.year or list(DEFAULT_YEARS)
    results = [acquire(year, args.force) for year in sorted(set(years))]
    manifest = {
        'source': 'INPE Programa Queimadas, public annual South America reference-satellite archives',
        'source_directory': BASE,
        'acquired_at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'max_archive_bytes': MAX_BYTES,
        'archives': results,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
