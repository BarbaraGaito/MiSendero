"""Acquire archived SMN WRF forecasts at fixed Argentine route-sector centers.

This research-only cohort contains forecast covariates only. It creates no fire
labels or observations and is stored separately from the MODIS training data.
Each day uses the SMN deterministic forecast issued at 12 UTC the prior day,
valid at 15 UTC (+27 h), with source and output SHA-256 recorded privately.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from datetime import date
from pathlib import Path

from environmental_sources import PUBLIC, ROOT, sha256
from acquire_smn_wrf_modis_weather import acquire_day, extract, nearest_grid

PRIVATE = PUBLIC / 'private'
OUT_DIR = PRIVATE / 'smn-wrf-route-event-study'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, type=date.fromisoformat)
    parser.add_argument('--end-exclusive', required=True, type=date.fromisoformat)
    parser.add_argument('--limit-days', type=int, default=0)
    args = parser.parse_args()
    if args.start >= args.end_exclusive:
        parser.error('--start must precede --end-exclusive')
    days = []
    current = args.start
    while current < args.end_exclusive:
        days.append(current)
        current = date.fromordinal(current.toordinal() + 1)
    if args.limit_days:
        days = days[:args.limit_days]

    geography_path = PUBLIC / 'geography.json'
    geography = json.loads(geography_path.read_text(encoding='utf-8'))
    regions = geography['fire_regions']
    points = {region['name']: (float(region['latitude']), float(region['longitude']))
              for region in regions}
    output = OUT_DIR.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
        'experiment_id': 'smn-wrf-forecast-only-at-argentina-trail-sector-centers',
        'source': 'SMN Argentina public WRF DET archive on AWS',
        'source_geography': geography_path.relative_to(ROOT).as_posix(),
        'geography_sha256': sha256(geography_path),
        'region_names': list(points),
        'issue_hour_utc': 12,
        'lead_hours': 27,
        'valid_hour_utc': 15,
        'variables': ['T2', 'HR2', 'magViento10', 'dirViento10', 'PP', 'Tmax', 'Tmin'],
        'maximum_grid_distance_km': 5,
        'synthetic_observations': 0,
        'fire_labels_included': False,
        'files': {},
        'deployment_approved': False,
    }
    # Use this active Python environment's compatible scientific stack. The
    # legacy private package cache may contain binaries for another Python ABI.
    import numpy as np
    from netCDF4 import Dataset, num2date
    from scipy.spatial import cKDTree
    downloads = output / 'downloads'
    downloads.mkdir(exist_ok=True)
    complete = []
    for day in days:
        day_key = day.isoformat()
        sample_path = output / f'{day_key}.csv.gz'
        old = manifest['files'].get(day_key)
        if old and old.get('status') == 'ok' and sample_path.is_file():
            if sha256(sample_path) != old.get('output_sha256'):
                raise ValueError(f'Existing output hash mismatch for {day_key}')
            complete.append(day_key)
            continue
        acquired = acquire_day(day, downloads)
        if acquired['error']:
            manifest['files'][day_key] = {
                'status': 'download_error',
                'hourly_url': acquired['hourly_url'],
                'daily_url': acquired['daily_url'],
                'reason': acquired['error'],
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'date': day_key, 'status': 'download_error', 'reason': acquired['error']},
                             ensure_ascii=False), flush=True)
            continue
        try:
            grid = nearest_grid(acquired['hourly_path'], points, np, cKDTree)
            rows = extract(acquired['hourly_path'], acquired['daily_path'], day, points, grid,
                           np, Dataset, num2date)
            fields = list(rows[0]) if rows else []
            with sample_path.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as packed:
                import io
                with io.TextIOWrapper(packed, encoding='utf-8', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            manifest['files'][day_key] = {
                'status': 'ok',
                'hourly_url': acquired['hourly_url'],
                'daily_url': acquired['daily_url'],
                'hourly_source_sha256': acquired['hourly_sha'],
                'daily_source_sha256': acquired['daily_sha'],
                'output_sha256': sha256(sample_path),
                'bytes': sample_path.stat().st_size,
                'route_point_rows': len(rows),
                'valid_route_points': sum(row['T2'] is not None and row['HR2'] is not None
                                          and row['magViento10'] is not None and row['PP'] is not None
                                          for row in rows),
                'max_grid_distance_km': max((row['grid_distance_km'] for row in rows), default=None),
            }
            complete.append(day_key)
            print(json.dumps({'date': day_key, 'status': 'ok', 'route_point_rows': len(rows),
                              'output_sha256': manifest['files'][day_key]['output_sha256']}, indent=2), flush=True)
        finally:
            for key in ('hourly_path', 'daily_path'):
                path = acquired.get(key)
                if path and Path(path).exists():
                    Path(path).unlink()
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    manifest['requested_period'] = {'start_inclusive': args.start.isoformat(),
                                    'end_exclusive': args.end_exclusive.isoformat()}
    manifest['successful_days_this_run'] = complete
    manifest['synthetic_observations'] = 0
    manifest['fire_labels_included'] = False
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': manifest_path.relative_to(ROOT).as_posix(),
                      'successful_days_this_run': complete,
                      'deployment_approved': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
