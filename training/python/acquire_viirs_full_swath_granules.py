#!/usr/bin/env python3
"""Download a small, CMR-audited VIIRS full-swath case-study cohort.

The NASA Earthdata token is read from process environment or ignored local
.env; it is never accepted on the command line, printed, or written to output.
Use --dry-run to inspect the bounded plan without credentials or network access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
PLAN = BASE / 'fire-viirs-full-swath-coverage-barda-2026-jan.json'
OUT_DIR = ROOT / 'training/data/environmental/private/viirs-full-swath-barda-2026-jan'
GRANULE_NAME = re.compile(r'^[A-Z0-9]+\.A\d{7}\.\d{4}\.\d{3}\.\d{13}$')
ALLOWED_URL_PREFIX = 'https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def local_token() -> str | None:
    token = os.environ.get('NASA_EARTHDATA_TOKEN')
    if token:
        return token.strip().strip('"').strip("'")
    env_file = ROOT / '.env'
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding='utf-8').splitlines():
        if line.lstrip().startswith('NASA_EARTHDATA_TOKEN='):
            return line.split('=', 1)[1].strip().strip('"').strip("'") or None
    return None


def plan_rows(limit: int | None) -> list[dict]:
    data = json.loads(PLAN.read_text(encoding='utf-8'))
    rows = []
    for product, detail in sorted(data['granules_by_product'].items()):
        rows.extend({'product': product, **row} for row in detail['overpasses'])
    rows.sort(key=lambda row: (row['acquisition_start_utc'], row['product']))
    if limit is not None:
        rows = rows[:limit]
    for row in rows:
        name = row['producer_granule_id']
        if not GRANULE_NAME.fullmatch(name):
            raise ValueError('CMR returned an unexpected granule identifier; refusing path construction.')
        url = row.get('download_url')
        if not isinstance(url, str) or not url.startswith(ALLOWED_URL_PREFIX):
            raise ValueError('CMR did not return an expected protected NASA data URL; refusing download.')
    return rows


def download_one(row: dict, token: str, output_dir: Path) -> dict:
    name = row['producer_granule_id']
    destination = output_dir / f'{name}.nc'
    if destination.exists() and destination.stat().st_size > 0:
        return {
            'granule_id': name, 'status': 'already_downloaded',
            'bytes': destination.stat().st_size, 'sha256': sha256(destination),
        }
    temporary = destination.with_suffix('.nc.part')
    request = urllib.request.Request(
        row['download_url'],
        headers={'Authorization': f'Bearer {token}', 'User-Agent': 'MiSenderoResearch/1.0'},
    )
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open('wb') as stream:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                stream.write(block)
                digest.update(block)
                size += len(block)
        if size == 0:
            temporary.unlink(missing_ok=True)
            raise RuntimeError('NASA returned an empty granule.')
        temporary.replace(destination)
    except urllib.error.HTTPError as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f'NASA LAADS download failed: HTTP {error.code} for {name}') from None
    except urllib.error.URLError as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f'NASA LAADS connection failed for {name}: {error.reason}') from None
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {'granule_id': name, 'status': 'downloaded', 'bytes': size, 'sha256': digest.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Show the bounded CMR plan without downloading.')
    parser.add_argument('--limit', type=int, help='Download only the first N granules for a small credential/access pilot.')
    parser.add_argument('--pause-seconds', type=float, default=0.2)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    rows = plan_rows(args.limit)
    estimated_mb = sum(float(row.get('reported_granule_size_mb') or 0) for row in rows)
    print(json.dumps({
        'granules_in_plan': len(rows),
        'reported_size_mb': round(estimated_mb, 2),
        'products': sorted({row['product'] for row in rows}),
        'dry_run': args.dry_run,
        'output_dir_is_private': 'training/data/environmental/private/' in OUT_DIR.as_posix(),
    }, ensure_ascii=False, indent=2))
    if args.dry_run:
        return
    token = local_token()
    if not token:
        parser.error('Set NASA_EARTHDATA_TOKEN in ignored .env or process environment; do not pass it on the command line.')
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / 'download-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
        'experiment_id': 'viirs-full-swath-barda-2026-jan',
        'plan_sha256': sha256(PLAN),
        'synthetic_observations': 0,
        'granules': [],
    }
    completed = {row['granule_id'] for row in manifest['granules'] if row.get('status') in {'downloaded', 'already_downloaded'}}
    for index, row in enumerate(rows, start=1):
        if row['producer_granule_id'] in completed:
            continue
        result = download_one(row, token, OUT_DIR)
        manifest['granules'].append(result)
        temp = manifest_path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(manifest_path)
        print(json.dumps({'completed': index, **result}, ensure_ascii=False), flush=True)
        time.sleep(max(0.0, args.pause_seconds))
    # Keep the credential alive only for the duration of this process.
    del token


if __name__ == '__main__':
    main()
