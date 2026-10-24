#!/usr/bin/env python3
"""Download one bounded NASA VIIRS geolocation companion for a mask-grid pilot.

The Earthdata token is read from process environment or ignored local .env. It
is never accepted on the command line, printed, or written to output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
PLAN = BASE / 'fire-viirs-full-swath-coverage-barda-2026-jan.json'
MASK_MANIFEST = ROOT / 'training/data/environmental/private/viirs-full-swath-barda-2026-jan/download-manifest.json'
OUT_DIR = ROOT / 'training/data/environmental/private/viirs-geolocation-pilot-barda-2026-jan'
CMR = 'https://cmr.earthdata.nasa.gov/search/granules.json'
TARGET_TIME = '2026-01-07T04:24:00.000Z'
PRODUCT = 'VNP03IMG'
GRANULE_RE = re.compile(r'^VNP03IMG\.A\d{7}\.\d{4}\.002\.\d{13}\.nc$')
ALLOWED_URL_PREFIX = 'https://data.laadsdaac.earthdatacloud.nasa.gov/prod-lads/VNP03IMG/'


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
        key, sep, value = line.partition('=')
        if sep and key.strip() == 'NASA_EARTHDATA_TOKEN':
            return value.strip().strip('"').strip("'") or None
    return None


def query_granule() -> tuple[dict, bytes]:
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    lon = float(plan['target_incident']['snmf_point_longitude'])
    lat = float(plan['target_incident']['snmf_point_latitude'])
    params = urllib.parse.urlencode({
        'short_name': PRODUCT,
        'temporal[]': f'{TARGET_TIME},{TARGET_TIME}',
        'point': f'{lon:.6f},{lat:.6f}',
        'page_size': 100,
    })
    request = urllib.request.Request(
        f'{CMR}?{params}',
        headers={'Accept': 'application/json', 'User-Agent': 'MiSenderoResearch/1.0'},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    entries = json.loads(raw).get('feed', {}).get('entry')
    if not isinstance(entries, list):
        raise RuntimeError('NASA CMR returned an unexpected response.')
    matches = [row for row in entries if row.get('time_start') == TARGET_TIME]
    if not matches:
        raise RuntimeError('NASA CMR has no exact-time geolocation companion for the selected fire-mask granule.')
    return max(matches, key=lambda row: row.get('updated', '')), raw


def download(row: dict, token: str, output: Path) -> dict:
    granule_id = row.get('producer_granule_id')
    if not isinstance(granule_id, str) or not GRANULE_RE.fullmatch(granule_id):
        raise RuntimeError('NASA returned an unexpected granule identifier; refusing path construction.')
    url = next((
        link.get('href') for link in row.get('links', [])
        if link.get('rel', '').endswith('/data#')
    ), None)
    if not isinstance(url, str) or not url.startswith(ALLOWED_URL_PREFIX):
        raise RuntimeError('NASA returned an unexpected data URL; refusing download.')

    destination = output / granule_id
    if destination.exists() and destination.stat().st_size > 0:
        return {'granule_id': granule_id, 'status': 'already_downloaded',
                'bytes': destination.stat().st_size, 'sha256': sha256(destination)}

    temporary = destination.with_suffix('.nc.part')
    request = urllib.request.Request(
        url,
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
            raise RuntimeError('NASA returned an empty geolocation granule.')
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {'granule_id': granule_id, 'status': 'downloaded', 'bytes': size,
            'sha256': digest.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Query CMR metadata without downloading.')
    args = parser.parse_args()
    row, raw_cmr = query_granule()
    granule_id = row.get('producer_granule_id')
    if not isinstance(granule_id, str) or not GRANULE_RE.fullmatch(granule_id):
        parser.error('NASA returned an unexpected granule identifier.')
    url = next((link.get('href') for link in row.get('links', [])
                if link.get('rel', '').endswith('/data#')), None)
    if not isinstance(url, str) or not url.startswith(ALLOWED_URL_PREFIX):
        parser.error('NASA returned an unexpected data URL.')
    estimate_mb = float(row.get('granule_size') or 0)
    print(json.dumps({
        'product': PRODUCT,
        'matched_fire_mask_acquisition_utc': TARGET_TIME,
        'geolocation_granule_id': granule_id,
        'reported_size_mb': round(estimate_mb, 2),
        'cmr_response_sha256': hashlib.sha256(raw_cmr).hexdigest(),
        'private_output_directory': 'training/data/environmental/private/' in OUT_DIR.as_posix(),
        'dry_run': args.dry_run,
    }, ensure_ascii=False, indent=2))
    if args.dry_run:
        return
    token = local_token()
    if not token:
        parser.error('Set NASA_EARTHDATA_TOKEN in ignored .env or process environment; do not pass it on the command line.')

    mask_manifest = json.loads(MASK_MANIFEST.read_text(encoding='utf-8'))
    mask_id = 'VNP14IMG.A2026007.0424.002.2026013204154'
    if not any(x.get('granule_id') == mask_id and x.get('status') in {'downloaded', 'already_downloaded'}
               for x in mask_manifest.get('granules', [])):
        parser.error('The matching VNP14IMG fire-mask granule is not verified locally.')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = download(row, token, OUT_DIR)
    manifest = {
        'experiment_id': 'viirs-geolocation-pilot-barda-2026-jan',
        'selected_fire_mask_granule': mask_id,
        'matched_acquisition_utc': TARGET_TIME,
        'cmr_response_sha256': hashlib.sha256(raw_cmr).hexdigest(),
        'geolocation_granule': result,
        'synthetic_observations': 0,
    }
    manifest_path = OUT_DIR / 'download-manifest.json'
    temporary_manifest = manifest_path.with_suffix('.json.tmp')
    temporary_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary_manifest.replace(manifest_path)
    del token
    print(json.dumps({'download_status': result['status'], 'downloaded_bytes': result['bytes'],
                      'sha256': result['sha256'], 'manifest': manifest_path.relative_to(ROOT).as_posix()},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
