"""Acquire a public INPE daily South America active-fire detections CSV."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'training/data/environmental/private/inpe-ams-satellite-reference/daily'
BASE = 'https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/America_Sul/'
MAX_BYTES = 25 * 1024 * 1024
COMPLETE_AFTER_UTC_HOUR = 6


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def acquire(target_date: date, force: bool = False) -> dict:
    compact = target_date.strftime('%Y%m%d')
    filename = f'focos_diario_{compact}.csv'
    url = BASE + filename
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / filename
    if destination.is_file() and not force:
        size = destination.stat().st_size
        if size > MAX_BYTES:
            raise ValueError(f'Existing file exceeds the {MAX_BYTES}-byte limit: {filename}')
        manifest_path = OUTPUT / f'{Path(filename).stem}.manifest.json'
        existing_manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
        current_sha256 = sha256(destination)
        same_download = existing_manifest.get('sha256') == current_sha256
        return {
            'target_date_utc': target_date.isoformat(),
            'url': url,
            'filename': filename,
            'bytes': size,
            'sha256': current_sha256,
            'last_modified': existing_manifest.get('last_modified') if same_download else None,
            'captured_at_utc': existing_manifest.get('captured_at_utc') if same_download else None,
            'complete_day_heuristic': f'HTTP Last-Modified >= {(target_date + timedelta(days=1)).isoformat()}T{COMPLETE_AFTER_UTC_HOUR:02d}:00:00Z',
            'status': 'cached' if same_download else 'cached_without_matching_manifest',
        }

    request = urllib.request.Request(url, headers={'User-Agent': 'MiSendero-research/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.geturl().split('/')[2].casefold() != 'dataserver-coids.inpe.br':
                raise ValueError('Unexpected redirect away from the official INPE data server.')
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_BYTES:
                raise ValueError(f'Remote file exceeds the {MAX_BYTES}-byte limit: {filename}')
            descriptor, temporary_name = tempfile.mkstemp(prefix=f'.{filename}.', suffix='.part', dir=OUTPUT)
            temporary = Path(temporary_name)
            count = 0
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > MAX_BYTES:
                            raise ValueError(f'Download exceeded the {MAX_BYTES}-byte limit: {filename}')
                        stream.write(block)
                if content_length and count != int(content_length):
                    raise IOError(f'Incomplete response: got {count} of {content_length} bytes')
                temporary.replace(destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            return {
                'target_date_utc': target_date.isoformat(),
                'url': url,
                'filename': filename,
                'bytes': count,
                'sha256': sha256(destination),
                'last_modified': response.headers.get('Last-Modified'),
                'captured_at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'complete_day_heuristic': f'HTTP Last-Modified >= {(target_date + timedelta(days=1)).isoformat()}T{COMPLETE_AFTER_UTC_HOUR:02d}:00:00Z',
                'status': 'downloaded',
            }
    except urllib.error.URLError as exc:
        raise RuntimeError(f'INPE daily CSV download failed for {target_date}: {exc}') from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True, help='Target observation date, YYYY-MM-DD UTC.')
    parser.add_argument('--force', action='store_true', help='Replace a cached file and refresh its HTTP timestamp.')
    args = parser.parse_args()
    result = acquire(date.fromisoformat(args.date), args.force)
    manifest_path = OUTPUT / f'{Path(result["filename"]).stem}.manifest.json'
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
