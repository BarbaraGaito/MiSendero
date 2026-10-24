"""Acquire research-only SMN WRF forecasts for 2025 SNMF route-event dates.

The current Windows session cannot complete TLS handshakes to the public S3
archive. This explicitly uses its HTTP endpoint and checks the AWS-provided
CRC64NVME checksum plus NetCDF valid times. HTTP checksums are not authenticated
against a network intermediary; these files must not support a final accuracy
claim until independently re-acquired over HTTPS.
"""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import json
import struct
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

from environmental_sources import PUBLIC, ROOT, sha256
from acquire_smn_wrf_modis_weather import extract, nearest_grid
from fire_sources import REPORT_DIR

SOURCE_EVENTS = REPORT_DIR / 'fire-snmf-route-event-coverage-2025.json'
GEOGRAPHY = PUBLIC / 'geography.json'
OUT_DIR = PUBLIC / 'private' / 'smnf-wrf-official-event-2025'
BUCKET = 'http://smn-ar-wrf.s3.us-west-2.amazonaws.com'
POLY_REFLECTED = 0x9A6C9329AC4BC9B5
MASK64 = 0xFFFFFFFFFFFFFFFF


def crc_table() -> tuple[int, ...]:
    values = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = (value >> 1) ^ (POLY_REFLECTED if value & 1 else 0)
        values.append(value)
    return tuple(values)


CRC_TABLE = crc_table()


def crc64nvme(path: Path) -> str:
    value = MASK64
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            for byte in block:
                value = (value >> 8) ^ CRC_TABLE[(value ^ byte) & 0xFF]
    value ^= MASK64
    return base64.b64encode(struct.pack('>Q', value)).decode('ascii')


def url_for(target_day: date, daily: bool) -> str:
    issue = target_day - timedelta(days=1)
    prefix = f'DATA/WRF/DET/{issue:%Y/%m/%d}/12/'
    name = (f'WRFDETAR_24H_{issue:%Y%m%d}_12_001.nc' if daily else
            f'WRFDETAR_01H_{issue:%Y%m%d}_12_027.nc')
    return f'{BUCKET}/{prefix}{name}'


def download(url: str, path: Path) -> dict:
    request = Request(url, headers={'User-Agent': 'MiSendero-research/1.0',
                                    'x-amz-checksum-mode': 'ENABLED'})
    with urlopen(request, timeout=180) as response, path.open('wb') as output:
        if response.status != 200:
            raise RuntimeError(f'Unexpected status {response.status}')
        if not response.geturl().startswith('http://'):
            raise RuntimeError('Expected explicit HTTP endpoint for this fallback run')
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            output.write(block)
        headers = response.headers
    expected = headers.get('x-amz-checksum-crc64nvme')
    checksum_type = headers.get('x-amz-checksum-type')
    if not expected or checksum_type != 'FULL_OBJECT':
        path.unlink(missing_ok=True)
        raise RuntimeError('S3 did not provide a full-object CRC64NVME checksum')
    actual = crc64nvme(path)
    if actual != expected:
        path.unlink(missing_ok=True)
        raise RuntimeError('Downloaded bytes do not match S3 CRC64NVME checksum')
    return {'url': url, 'transport': 'http', 'bytes': path.stat().st_size,
            'sha256': sha256(path), 'crc64nvme': actual,
            'etag': headers.get('ETag'), 'last_modified': headers.get('Last-Modified'),
            'crc64nvme_verified': True}


def main() -> None:
    events = json.loads(SOURCE_EVENTS.read_text(encoding='utf-8'))
    targets = events['results']['10']['route_sector_start_days']
    geography = json.loads(GEOGRAPHY.read_text(encoding='utf-8'))
    by_name = {row['name']: (float(row['latitude']), float(row['longitude']))
               for row in geography['fire_regions']}
    points = {event['route_sector']: by_name[event['route_sector']] for event in targets}
    dates = sorted({date.fromisoformat(event['target_date']) for event in targets})
    # Use the active environment; the archived private dependency cache can be
    # for another Python ABI.
    import numpy as np
    from netCDF4 import Dataset, num2date
    from scipy.spatial import cKDTree
    output_dir = OUT_DIR.resolve()
    downloads = output_dir / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / 'manifest.json'
    manifest = {'experiment_id': 'smn-wrf-forecast-at-official-snmf-2025-route-events',
        'official_event_source': SOURCE_EVENTS.relative_to(ROOT).as_posix(),
        'official_event_source_sha256': sha256(SOURCE_EVENTS),
        'geography_sha256': sha256(GEOGRAPHY),
        'source': 'SMN Argentina public WRF DET archive on AWS S3',
        'transport': 'HTTP fallback because HTTPS connections are reset in this session; payload CRC64NVME is checked but not authenticated over HTTP.',
        'forecast_protocol': {'issue_time_utc': '12:00 on previous calendar day',
            'lead_hours': 27, 'hourly_valid_time_utc': '15:00 target date',
            'daily_valid_time_utc': '00:00 target date'},
        'events': targets, 'files': {}, 'synthetic_observations': 0,
        'deployment_approved': False}
    for target_day in dates:
        key = target_day.isoformat()
        out_csv = output_dir / f'{key}.csv.gz'
        old = manifest['files'].get(key)
        if old and old.get('status') == 'ok' and out_csv.is_file() and sha256(out_csv) == old.get('output_sha256'):
            continue
        hourly_path = downloads / f'{key}-hourly.nc.part'
        daily_path = downloads / f'{key}-daily.nc.part'
        hourly_url, daily_url = url_for(target_day, False), url_for(target_day, True)
        try:
            hourly_meta = download(hourly_url, hourly_path)
            daily_meta = download(daily_url, daily_path)
            with Dataset(hourly_path, 'r') as hourly_ds:
                grid = nearest_grid(hourly_ds, points, np, cKDTree)
            rows = extract(hourly_path, daily_path, target_day, points, grid, np, Dataset, num2date)
            with out_csv.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as packed:
                import io
                with io.TextIOWrapper(packed, encoding='utf-8', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            manifest['files'][key] = {'status': 'ok', 'hourly': hourly_meta,
                'daily': daily_meta, 'route_points': len(rows),
                'valid_points': sum(row['T2'] is not None and row['HR2'] is not None
                    and row['magViento10'] is not None and row['PP'] is not None for row in rows),
                'output_sha256': sha256(out_csv), 'output_bytes': out_csv.stat().st_size}
            print(json.dumps({'date': key, 'status': 'ok', 'valid_points': manifest['files'][key]['valid_points']}), flush=True)
        except Exception as error:
            out_csv.unlink(missing_ok=True)
            manifest['files'][key] = {'status': 'error', 'reason': f'{type(error).__name__}: {error}'}
            print(json.dumps({'date': key, 'status': 'error', 'reason': manifest['files'][key]['reason']}), flush=True)
        finally:
            hourly_path.unlink(missing_ok=True)
            daily_path.unlink(missing_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': manifest_path.relative_to(ROOT).as_posix(),
        'dates': len(dates), 'successful': sum(row.get('status') == 'ok' for row in manifest['files'].values()),
        'deployment_approved': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
