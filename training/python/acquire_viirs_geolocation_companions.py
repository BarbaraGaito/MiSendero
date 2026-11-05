#!/usr/bin/env python3
"""Acquire the 61 exact-time VIIRS full-pixel geolocation companions for Barda.

Files are stored under the ignored private research-data directory. NASA
Earthdata credentials are read from process environment or local .env only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
MASK_PLAN = BASE / 'fire-viirs-full-swath-coverage-barda-2026-jan.json'
OUTPUT_PLAN = BASE / 'fire-viirs-geolocation-companion-readiness-2026-jan.json'
# Reuse the existing pilot directory so its verified 142 MB granule is not duplicated.
OUT_DIR = ROOT / 'training/data/environmental/private/viirs-geolocation-pilot-barda-2026-jan'
CMR = 'https://cmr.earthdata.nasa.gov/search/granules.json'
MASK_TO_GEO = {'VNP14IMG': 'VNP03IMG', 'VJ114IMG': 'VJ103IMG', 'VJ214IMG': 'VJ203IMG'}
ID_PATTERNS = {
    'VNP03IMG': re.compile(r'^VNP03IMG\.A\d{7}\.\d{4}\.\d{3}\.\d{13}\.nc$'),
    'VJ103IMG': re.compile(r'^VJ103IMG\.A\d{7}\.\d{4}\.\d{3}\.\d{13}\.nc$'),
    'VJ203IMG': re.compile(r'^VJ203IMG\.A\d{7}\.\d{4}\.\d{3}\.\d{13}\.nc$'),
}
URL_PREFIX = 'https://data.laadsdaac.earthdatacloud.nasa.gov/prod-lads/'


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


def cmr_rows(product: str, start: str, end: str, longitude: float,
             latitude: float) -> tuple[dict[str, dict], str]:
    params = urllib.parse.urlencode({
        'short_name': product,
        'temporal[]': f'{start},{end}',
        'point': f'{longitude:.6f},{latitude:.6f}',
        'page_size': 2000,
    })
    request = urllib.request.Request(
        f'{CMR}?{params}',
        headers={'Accept': 'application/json', 'User-Agent': 'MiSenderoResearch/1.0'},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    entries = json.loads(raw).get('feed', {}).get('entry')
    if not isinstance(entries, list):
        raise RuntimeError(f'Unexpected CMR response for {product}.')
    by_time: dict[str, dict] = {}
    for row in entries:
        stamp = row.get('time_start')
        if stamp not in by_time or row.get('updated', '') > by_time[stamp].get('updated', ''):
            by_time[stamp] = row
    return by_time, hashlib.sha256(raw).hexdigest()


def build_plan() -> tuple[list[dict], dict[str, str]]:
    plan = json.loads(MASK_PLAN.read_text(encoding='utf-8'))
    point = plan['target_incident']
    all_times = sorted(
        row['acquisition_start_utc']
        for detail in plan['granules_by_product'].values()
        for row in detail['overpasses']
    )
    result: list[dict] = []
    source_hashes: dict[str, str] = {}
    for mask_product, geo_product in MASK_TO_GEO.items():
        expected = sorted(
            row['acquisition_start_utc']
            for row in plan['granules_by_product'][mask_product]['overpasses']
        )
        rows, response_hash = cmr_rows(
            geo_product, all_times[0], all_times[-1],
            float(point['snmf_point_longitude']), float(point['snmf_point_latitude']),
        )
        source_hashes[geo_product] = response_hash
        for stamp in expected:
            row = rows.get(stamp)
            if row is None:
                raise RuntimeError(f'No exact-time {geo_product} granule found for {stamp}.')
            granule_id = row.get('producer_granule_id')
            url = next((link.get('href') for link in row.get('links', [])
                        if link.get('rel', '').endswith('/data#')), None)
            if not isinstance(granule_id, str) or not ID_PATTERNS[geo_product].fullmatch(granule_id):
                raise RuntimeError(f'Unexpected granule identifier from CMR for {geo_product}.')
            if not isinstance(url, str) or not url.startswith(URL_PREFIX + geo_product + '/'):
                raise RuntimeError(f'Unexpected protected data URL from CMR for {geo_product}.')
            result.append({
                'product': geo_product,
                'acquisition_start_utc': stamp,
                'granule_id': granule_id,
                'reported_size_mb': float(row['granule_size']) if row.get('granule_size') else None,
                'url': url,
                'latest_metadata_update': row.get('updated'),
            })
    result.sort(key=lambda row: (row['acquisition_start_utc'], row['product']))
    return result, source_hashes


def download_one(row: dict, token: str) -> dict:
    destination = OUT_DIR / row['granule_id']
    if destination.exists() and destination.stat().st_size > 0:
        return {'granule_id': row['granule_id'], 'product': row['product'],
                'acquisition_start_utc': row['acquisition_start_utc'],
                'status': 'already_downloaded', 'bytes': destination.stat().st_size,
                'sha256': sha256(destination)}
    temporary = destination.with_suffix('.nc.part')
    request = urllib.request.Request(
        row['url'],
        headers={'Authorization': f'Bearer {token}', 'User-Agent': 'MiSenderoResearch/1.0'},
    )
    for attempt in range(5):
        digest = hashlib.sha256()
        size = 0
        try:
            with urllib.request.urlopen(request, timeout=240) as response, temporary.open('wb') as stream:
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
            return {'granule_id': row['granule_id'], 'product': row['product'],
                    'acquisition_start_utc': row['acquisition_start_utc'],
                    'status': 'downloaded', 'bytes': size, 'sha256': digest.hexdigest()}
        except urllib.error.HTTPError as error:
            temporary.unlink(missing_ok=True)
            if error.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise RuntimeError(f'NASA LAADS returned HTTP {error.code} for {row["granule_id"]}.') from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            temporary.unlink(missing_ok=True)
            if attempt == 4:
                raise RuntimeError(f'NASA LAADS connection failed for {row["granule_id"]}: {error}.') from None
        time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f'NASA LAADS download failed for {row["granule_id"]}.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Query and validate CMR metadata only.')
    parser.add_argument('--limit', type=int, help='Download only the first N planned granules.')
    parser.add_argument('--pause-seconds', type=float, default=0.2)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')

    rows, cmr_hashes = build_plan()
    if args.limit is not None:
        rows = rows[:args.limit]
    estimate = sum(row['reported_size_mb'] or 0 for row in rows)
    print(json.dumps({
        'granules_in_plan': len(rows),
        'reported_size_mb': round(estimate, 2),
        'products': sorted({row['product'] for row in rows}),
        'output_is_private': 'training/data/environmental/private/' in OUT_DIR.as_posix(),
        'dry_run': args.dry_run,
    }, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        return
    token = local_token()
    if not token:
        parser.error('Set NASA_EARTHDATA_TOKEN in ignored .env or process environment; never pass it on the command line.')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / 'download-manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if not isinstance(manifest.get('granules'), list):
            pilot = manifest.get('geolocation_granule')
            if not isinstance(pilot, dict):
                raise RuntimeError('Existing geolocation manifest has an unexpected format.')
            manifest = {
                'experiment_id': 'viirs-geolocation-barda-2026-jan',
                'expected_granules': 61,
                'synthetic_observations': 0,
                'granules': [{
                    'granule_id': pilot['granule_id'],
                    'product': 'VNP03IMG',
                    'acquisition_start_utc': '2026-01-07T04:24:00.000Z',
                    'status': pilot['status'],
                    'bytes': pilot['bytes'],
                    'sha256': pilot['sha256'],
                }],
            }
    else:
        manifest = {
        'experiment_id': 'viirs-geolocation-barda-2026-jan',
        'cmr_response_sha256_by_product': cmr_hashes,
        'expected_granules': 61,
        'synthetic_observations': 0,
        'granules': [],
        }
    completed = {row['granule_id']: row for row in manifest['granules']
                 if row.get('status') in {'downloaded', 'already_downloaded'}}
    for index, row in enumerate(rows, start=1):
        existing = completed.get(row['granule_id'])
        destination = OUT_DIR / row['granule_id']
        if existing and destination.exists():
            if destination.stat().st_size != existing.get('bytes') or sha256(destination) != existing.get('sha256'):
                raise RuntimeError(f'Existing granule failed local manifest verification: {row["granule_id"]}.')
            print(json.dumps({'completed': index, 'granule_id': row['granule_id'],
                              'status': 'verified_existing'}, ensure_ascii=False), flush=True)
            continue
        result = download_one(row, token)
        manifest['granules'] = [item for item in manifest['granules']
                                if item.get('granule_id') != row['granule_id']]
        manifest['granules'].append(result)
        manifest['cmr_response_sha256_by_product'] = cmr_hashes
        temporary_manifest = manifest_path.with_suffix('.json.tmp')
        temporary_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary_manifest.replace(manifest_path)
        completed[row['granule_id']] = result
        print(json.dumps({'completed': index, **result}, ensure_ascii=False), flush=True)
        time.sleep(max(0.0, args.pause_seconds))
    del token
    print(json.dumps({'manifest': manifest_path.relative_to(ROOT).as_posix(),
                      'completed_granules': len(completed)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
