#!/usr/bin/env python3
"""Screen one day of public NOAA VIIRS E-FIRE swaths against trail routes.

This downloads one small E-FIRE granule near the start of each UTC hour for
each selected satellite, reads the product's coarse sampled geolocation, and
discards the temporary NetCDF files. It locates candidate overpasses only; a
full GITCO geolocation file is still required to assign the 375 m mask exactly.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from environmental_sources import ROOT

GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
OUTPUT = ROOT / 'docs/environmental-models-2026-10-22/fire-viirs-efire-orbit-screen-2025-01-05.json'
BUCKETS = {'npp': 'noaa-nesdis-snpp-pds', 'n20': 'noaa-nesdis-n20-pds', 'n21': 'noaa-nesdis-n21-pds'}
PLATFORM_CODES = {value: key for key, value in BUCKETS.items()}
MAX_WORKERS = 6


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def url_for(bucket: str, day: date, minute_of_day: int) -> str:
    prefix = f'VIIRS_EFIRE_VIIRSI_EDR/{day:%Y/%m/%d}/'
    hour, minute = divmod(minute_of_day, 60)
    start_after = f'{prefix}EFIRE-VIIRSI_v1r3_{PLATFORM_CODES[bucket]}_s{day:%Y%m%d}{hour:02d}{minute:02d}000'
    params = urllib.parse.urlencode({
        'list-type': '2', 'prefix': prefix, 'start-after': start_after, 'max-keys': '1',
    })
    return f'https://{bucket}.s3.amazonaws.com/?{params}'


def list_one(bucket: str, day: date, minute_of_day: int,
             interval_minutes: int) -> tuple[str | None, str | None]:
    url = url_for(bucket, day, minute_of_day)
    try:
        with urllib.request.urlopen(url, timeout=40) as response:
            root = ET.fromstring(response.read())
    except Exception as exc:  # Network errors are kept explicit in the output.
        return None, f'{type(exc).__name__}: {exc}'
    key = next((node.text for node in root.iter() if node.tag.endswith('Key')), None)
    if not key:
        return None, 'no_object_after_hour_marker'
    filename = key.rsplit('/', 1)[-1]
    stamp_start = filename.find('_s') + 2
    stamp = filename[stamp_start:stamp_start + 14]
    try:
        actual_minute = int(stamp[8:10]) * 60 + int(stamp[10:12])
    except (ValueError, IndexError):
        return None, 'unrecognized_scan_start_time'
    if stamp[:8] != day.strftime('%Y%m%d') or not minute_of_day <= actual_minute < minute_of_day + interval_minutes:
        return None, 'no_granule_starting_in_requested_interval'
    return key, None


def sample_route(route: dict, maximum_vertices: int = 100) -> np.ndarray:
    coords = route['route_coordinates']
    step = max(1, len(coords) // maximum_vertices)
    points = coords[::step]
    if coords[-1] not in points:
        points.append(coords[-1])
    return np.asarray(points, dtype=np.float64)


def min_distances(sample_lat: np.ndarray, sample_lon: np.ndarray,
                  route_points: dict[str, np.ndarray]) -> dict[str, float | None]:
    valid = (
        np.isfinite(sample_lat) & np.isfinite(sample_lon)
        & (sample_lat >= -90) & (sample_lat <= 90)
        & (sample_lon >= -180) & (sample_lon <= 180)
    )
    lat2 = np.radians(sample_lat[valid])
    lon2 = np.radians(sample_lon[valid])
    results = {}
    for name, points in route_points.items():
        if not len(lat2):
            results[name] = None
            continue
        lat1 = np.radians(points[:, 0])[:, None]
        lon1 = np.radians(points[:, 1])[:, None]
        dlat = lat2[None, :] - lat1
        dlon = lon2[None, :] - lon1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2[None, :]) * np.sin(dlon / 2) ** 2
        results[name] = float(2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a, 0, 1))).min())
    return results


def download_one(bucket: str, day: date, minute_of_day: int, interval_minutes: int,
                 temp_dir: str) -> dict:
    key, error = list_one(bucket, day, minute_of_day, interval_minutes)
    base = {'platform_bucket': bucket, 'requested_minute_utc': minute_of_day}
    if error:
        return {**base, 'status': error}
    url = f'https://{bucket}.s3.amazonaws.com/{urllib.parse.quote(key, safe="/")}'
    try:
        with urllib.request.urlopen(url, timeout=90) as response:
            data = response.read()
        local_path = Path(temp_dir) / f'{bucket}-{minute_of_day:04d}.nc'
        local_path.write_bytes(data)
        return {
            **base, 'status': 'downloaded', 'key': key,
            'sha256': sha256_bytes(data), 'bytes': len(data),
            'local_path': str(local_path),
        }
    except Exception as exc:
        return {**base, 'key': key, 'status': f'{type(exc).__name__}: {exc}'}


def inspect_one(download: dict, route_points: dict[str, np.ndarray]) -> dict:
    if download['status'] != 'downloaded':
        return download
    local_path = Path(download['local_path'])
    try:
        with Dataset(local_path) as ds:
            lat = np.asarray(ds['Sampled_Latitude'][:], dtype=np.float64)
            lon = np.asarray(ds['Sampled_Longitude'][:], dtype=np.float64)
            distances = min_distances(lat, lon, route_points)
            start = str(ds.time_coverage_start)
            end = str(ds.time_coverage_end)
            bounds = str(getattr(ds, 'geospatial_bounds', ''))
        return {
            **{key: value for key, value in download.items() if key != 'local_path'},
            'status': 'ok',
            'time_coverage_start': start, 'time_coverage_end': end,
            'geospatial_bounds': bounds,
            'minimum_distance_to_coarse_swath_sample_km': distances,
            'candidate_routes_within_40km': sorted(name for name, value in distances.items()
                                                    if value is not None and value <= 40),
        }
    except Exception as exc:
        return {key: value for key, value in download.items() if key != 'local_path'} | {
            'status': f'{type(exc).__name__}: {exc}'
        }
    finally:
        local_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat, default=date(2025, 1, 5))
    parser.add_argument('--platforms', nargs='+', choices=sorted(BUCKETS), default=['npp', 'n20', 'n21'])
    parser.add_argument('--interval-minutes', type=int, default=60,
                        help='Minutes between representative granules (must divide 60).')
    parser.add_argument('--geometry', type=Path, default=GEOMETRY)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.interval_minutes <= 0 or 60 % args.interval_minutes:
        parser.error('--interval-minutes must be a positive divisor of 60')
    routes = json.loads(args.geometry.read_text(encoding='utf-8'))['fire_route_geometries']
    route_points = {route['name']: sample_route(route) for route in routes}
    tasks = [(BUCKETS[platform], minute) for platform in args.platforms
             for minute in range(0, 1440, args.interval_minutes)]

    with tempfile.TemporaryDirectory(prefix='viirs-efire-screen-') as temp_dir:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            downloaded = list(executor.map(
                lambda task: download_one(task[0], args.date, task[1], args.interval_minutes,
                                          temp_dir),
                tasks,
            ))
        # netCDF/HDF5 reads are deliberately sequential; some Windows HDF5
        # builds are not thread-safe even though the S3 downloads are.
        scans = [inspect_one(row, route_points) for row in downloaded]

    result = {
        'experiment_id': f'noaa-viirs-efire-coarse-route-overpass-screen-{args.date.isoformat()}',
        'purpose': f'One coarse swath screen per platform every {args.interval_minutes} minutes; identifies candidate granules only, not fire labels or prediction performance.',
        'period_utc': args.date.isoformat(),
        'source': {
            'dataset': 'NOAA VIIRS Enterprise Fire I-band EDR v1r3',
            'public_buckets': [BUCKETS[item] for item in args.platforms],
            's3_layout': 'VIIRS_EFIRE_VIIRSI_EDR/YYYY/MM/DD/',
            'route_geometry_sha256': sha256_bytes(args.geometry.read_bytes()),
            'candidate_radius_km': 40,
            'screen_interval_minutes': args.interval_minutes,
            'screening_method': 'Minimum haversine distance from sampled route vertices to NOAA E-FIRE Sampled_Latitude/Longitude (24x100).',
        },
        'scans': scans,
        'candidate_count_by_route': {
            route: sum(route in scan.get('candidate_routes_within_40km', []) for scan in scans)
            for route in route_points
        },
        'limitations': [
            'One granule per time interval can miss another granule in that interval; this is a coarse screen, not a complete coverage census.',
            'The E-FIRE sampled geolocation is too coarse to assign its 375 m fire mask accurately to a trail.',
            'A candidate within 40 km requires full granule GITCO geolocation and per-pixel quality screening before any label can be formed.',
            'Missing swaths and invalid or cloudy pixels remain unknown, not fire-free.',
        ],
        'synthetic_observations': 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'scans_ok': sum(row['status'] == 'ok' for row in scans),
                      'candidate_count_by_route': result['candidate_count_by_route']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
