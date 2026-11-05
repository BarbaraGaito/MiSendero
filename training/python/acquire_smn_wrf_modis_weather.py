"""Extract causal SMN WRF forecasts at the MODIS fire-study pixels.

Research-only acquisition. Raw NetCDFs are streamed one at a time and deleted
after their selected grid values and SHA-256 have been recorded. Outputs remain
under the ignored private research cache; nothing is bundled into the app.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from environmental_sources import PUBLIC, ROOT


PRIVATE = PUBLIC / 'private'
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
OUT_DIR = PRIVATE / 'smn-wrf-modis-weather'
VARS = ('T2', 'HR2', 'magViento10', 'dirViento10', 'PP')
FORECAST_HOUR = 27
INIT_HOUR = 12


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def pixel_locations(path: Path):
    pixels = {}
    target_dates = set()
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            pixel_id = f"{row['tile']}:{row['row']}:{row['col']}"
            coordinate = (float(row['latitude']), float(row['longitude']))
            old = pixels.setdefault(pixel_id, coordinate)
            if old != coordinate:
                raise ValueError(f'Inconsistent coordinates for {pixel_id}')
            target_dates.add(date.fromisoformat(row['observed_date']))
    return pixels, sorted(target_dates)


def unit_sphere(latitude, longitude):
    import numpy as np
    lat = np.deg2rad(latitude)
    lon = np.deg2rad(longitude)
    return np.column_stack((np.cos(lat) * np.cos(lon),
                            np.cos(lat) * np.sin(lon), np.sin(lat)))


def open_dependencies():
    # Install research-only binary dependencies into the ignored cache.
    lib = PRIVATE / 'smn-wrf-sample' / 'python-libs'
    if lib.exists():
        sys.path.insert(0, str(lib))
    try:
        import numpy as np
        from netCDF4 import Dataset, num2date
        from scipy.spatial import cKDTree
    except ImportError as exc:
        raise SystemExit(
            'Missing research dependencies. Install numpy, netCDF4, and scipy '
            f'into {lib} (see fire-smn-wrf-24h-protocol.md).') from exc
    return np, Dataset, num2date, cKDTree


def s3_url(target_day: date) -> str:
    issue = target_day - timedelta(days=1)
    key = (f'DATA/WRF/DET/{issue:%Y/%m/%d}/{INIT_HOUR:02d}/'
           f'WRFDETAR_01H_{issue:%Y%m%d}_{INIT_HOUR:02d}_{FORECAST_HOUR:03d}.nc')
    return 'https://smn-ar-wrf.s3.us-west-2.amazonaws.com/' + key


def s3_daily_url(target_day: date) -> str:
    issue = target_day - timedelta(days=1)
    key = (f'DATA/WRF/DET/{issue:%Y/%m/%d}/{INIT_HOUR:02d}/'
           f'WRFDETAR_24H_{issue:%Y%m%d}_{INIT_HOUR:02d}_001.nc')
    return 'https://smn-ar-wrf.s3.us-west-2.amazonaws.com/' + key


def download(url: str, path: Path):
    last_error = None
    for attempt in range(4):
        request = Request(url, headers={'User-Agent': 'MiSendero-research/1.0'})
        try:
            with urlopen(request, timeout=180) as response, path.open('wb') as output:
                if response.status != 200:
                    raise ValueError(f'Unexpected HTTP status {response.status}')
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
            return digest(path), None
        except HTTPError as exc:
            if path.exists():
                path.unlink()
            if exc.code == 404:
                return None, f'HTTP 404: {url}'
            last_error = f'HTTP {exc.code}: {exc.reason}'
        except (URLError, TimeoutError, OSError) as exc:
            if path.exists():
                path.unlink()
            last_error = f'{type(exc).__name__}: {exc}'
        if attempt < 3:
            time.sleep(2 ** attempt)
    return None, f'Retries exhausted: {last_error}'


def acquire_day(target_day: date, cache_dir: Path):
    hourly_url, daily_url = s3_url(target_day), s3_daily_url(target_day)
    stem = target_day.isoformat()
    hourly_path = cache_dir / f'{stem}-hourly.nc.part'
    daily_path = cache_dir / f'{stem}-daily.nc.part'
    hourly_sha, error = download(hourly_url, hourly_path)
    daily_sha = None
    if not error:
        daily_sha, error = download(daily_url, daily_path)
    if error:
        for part in (hourly_path, daily_path):
            if part.exists():
                part.unlink()
        return {'day': target_day, 'hourly_url': hourly_url, 'daily_url': daily_url,
                'hourly_path': None, 'daily_path': None, 'hourly_sha': None,
                'daily_sha': None, 'error': error}
    return {'day': target_day, 'hourly_url': hourly_url, 'daily_url': daily_url,
            'hourly_path': hourly_path, 'daily_path': daily_path,
            'hourly_sha': hourly_sha, 'daily_sha': daily_sha, 'error': None}


def nearest_grid(ds, pixels, np, cKDTree):
    lat = np.asarray(ds.variables['lat'][:], dtype='float64').ravel()
    lon = np.asarray(ds.variables['lon'][:], dtype='float64').ravel()
    valid = np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
    flat_valid = np.flatnonzero(valid)
    tree = cKDTree(unit_sphere(lat[valid], lon[valid]))
    ids = list(pixels)
    coordinates = [pixels[key] for key in ids]
    query = unit_sphere([c[0] for c in coordinates], [c[1] for c in coordinates])
    chord, indices = tree.query(query, k=1)
    flat_indices = flat_valid[indices]
    nearest_lat, nearest_lon = lat[flat_indices], lon[flat_indices]
    # Great-circle distance from chord length on a unit sphere.
    distance_km = 6371.0088 * 2 * np.arcsin(np.minimum(1.0, chord / 2))
    return dict(zip(ids, zip(flat_indices.tolist(), nearest_lat.tolist(),
                             nearest_lon.tolist(), distance_km.tolist())))


def extract(hourly_path: Path, daily_path: Path, target_day: date, pixels, grid, np, Dataset, num2date):
    rows = []
    with Dataset(hourly_path, 'r') as ds, Dataset(daily_path, 'r') as daily:
        missing = [name for name in VARS if name not in ds.variables]
        if missing:
            raise ValueError(f'Missing expected WRF variables: {missing}')
        valid_time = num2date(ds.variables['time'][0], ds.variables['time'].units,
                              only_use_cftime_datetimes=False,
                              only_use_python_datetimes=True)
        valid_time = valid_time.replace(tzinfo=timezone.utc)
        expected = datetime.combine(target_day, datetime.min.time(), timezone.utc) + timedelta(hours=15)
        if valid_time != expected:
            raise ValueError(f'Forecast valid at {valid_time.isoformat()}, expected {expected.isoformat()}')
        if not {'Tmax', 'Tmin'} <= set(daily.variables):
            raise ValueError('Daily WRF file lacks Tmax/Tmin')
        daily_time_var = daily.variables['time']
        daily_valid_time = num2date(daily_time_var[0], daily_time_var.units,
                                    only_use_cftime_datetimes=False,
                                    only_use_python_datetimes=True).replace(tzinfo=timezone.utc)
        expected_daily = datetime.combine(target_day, datetime.min.time(), timezone.utc)
        if daily_valid_time != expected_daily:
            raise ValueError(f'Daily forecast valid at {daily_valid_time.isoformat()}, expected {expected_daily.isoformat()}')
        if daily.variables['Tmax'].shape != ds.variables['T2'].shape:
            raise ValueError('Daily and hourly WRF grids do not match')
        issue_time = datetime.combine(target_day - timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=12)
        ny, nx = len(ds.dimensions['y']), len(ds.dimensions['x'])
        selected = [(pixel_id, *point) for pixel_id, point in grid.items() if point[3] <= 5]
        flat_indices = np.asarray([item[1] for item in selected], dtype='int64')
        values_by_name = {}
        for name in VARS:
            field = np.ma.asarray(ds.variables[name][0]).reshape(-1)
            values_by_name[name] = field[flat_indices]
        for name in ('Tmax', 'Tmin'):
            field = np.ma.asarray(daily.variables[name][0]).reshape(-1)
            values_by_name[name] = field[flat_indices]
        for index, (pixel_id, flat, grid_lat, grid_lon, distance_km) in enumerate(selected):
            values = {}
            for name, field in values_by_name.items():
                value = field[index]
                values[name] = None if np.ma.is_masked(value) else float(value)
                if values[name] is not None and not math.isfinite(values[name]):
                    values[name] = None
            rows.append({
                'pixel_id': pixel_id,
                'target_date': target_day.isoformat(),
                'issue_time_utc': issue_time.isoformat().replace('+00:00', 'Z'),
                'valid_time_utc': valid_time.isoformat().replace('+00:00', 'Z'),
                'lead_hours': FORECAST_HOUR,
                'pixel_latitude': pixels[pixel_id][0],
                'pixel_longitude': pixels[pixel_id][1],
                'wrf_latitude': grid_lat,
                'wrf_longitude': grid_lon,
                'grid_distance_km': distance_km,
                **values,
            })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--observations', type=Path, default=OBSERVATIONS,
                        help='Research observation CSV.GZ whose pixel coordinates need WRF forecasts.')
    parser.add_argument('--output-dir', type=Path, default=OUT_DIR,
                        help='Output directory. Use a separate private directory for experimental cohorts.')
    parser.add_argument('--dates-manifest', type=Path,
                        help='Optional WRF manifest; restrict acquisition to dates previously verified as available.')
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--end-exclusive', type=date.fromisoformat)
    parser.add_argument('--limit-days', type=int, default=0,
                        help='Process only the first N target days (smoke test).')
    parser.add_argument('--workers', type=int, default=6,
                        help='Concurrent public S3 downloads; NetCDF extraction remains serial.')
    args = parser.parse_args()

    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    np, Dataset, num2date, cKDTree = open_dependencies()
    pixels, target_dates = pixel_locations(args.observations)
    if args.dates_manifest:
        previous = json.loads(args.dates_manifest.read_text(encoding='utf-8'))
        allowed = {date.fromisoformat(key) for key, value in previous.get('files', {}).items()
                   if value.get('status') == 'ok'}
        target_dates = [day for day in target_dates if day in allowed]
    if args.start:
        target_dates = [d for d in target_dates if d >= args.start]
    if args.end_exclusive:
        target_dates = [d for d in target_dates if d < args.end_exclusive]
    if args.limit_days:
        target_dates = target_dates[:args.limit_days]
    if not target_dates:
        raise SystemExit('No target dates selected')

    manifest_path = out_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
        'experiment_id': 'smn-wrf-forecast-weather-at-modis-fire-sample',
        'source': 'Public SMN-Argentina WRF DET bucket on AWS',
        'variables': list(VARS) + ['Tmax', 'Tmin'], 'init_hour_utc': INIT_HOUR, 'lead_hours': FORECAST_HOUR,
        'valid_hour_utc': 15, 'grid_tolerance_km': 5, 'synthetic_observations': 0,
        'files': {}, 'limitations': [
            'Forecast covariates are weather, not fire occurrence probability.',
            'MODIS daily fire mask is a satellite label, not a ground-truth ignition time.',
            'Weather is nearest-neighbor sampled from a 4 km WRF grid to MODIS pixel coordinates.'
        ]}

    grid = None
    target_dates = [d for d in target_dates
                    if not (d.isoformat() in manifest['files']
                            and (out_dir / f'{d.isoformat()}.csv.gz').exists()
                            and manifest['files'][d.isoformat()].get('daily_source_sha256'))]
    cache_dir = out_dir / 'downloads'
    cache_dir.mkdir(exist_ok=True)
    batch_size = max(1, min(args.workers, 12))
    processed = 0
    with ThreadPoolExecutor(max_workers=batch_size) as pool:
        for offset in range(0, len(target_dates), batch_size):
            batch = target_dates[offset:offset + batch_size]
            started = {d: time.time() for d in batch}
            acquired = list(pool.map(lambda d: acquire_day(d, cache_dir), batch))
            for item in acquired:
                processed += 1
                target_day = item['day']
                day_key = target_day.isoformat()
                output_path = out_dir / f'{day_key}.csv.gz'
                if item['error']:
                    status = 'missing' if 'HTTP 404' in item['error'] else 'download_error'
                    manifest['files'][day_key] = {'status': status, 'url': item['hourly_url'],
                        'daily_url': item['daily_url'], 'reason': item['error']}
                    print(f'[{processed}/{len(target_dates)}] {day_key}: {status} ({item["error"]})', flush=True)
                else:
                    if grid is None:
                        with Dataset(item['hourly_path'], 'r') as ds:
                            grid = nearest_grid(ds, pixels, np, cKDTree)
                        if not grid or max(v[3] for v in grid.values()) > 5:
                            raise ValueError('Some MODIS study points are outside the WRF 5 km sample tolerance')
                    rows = extract(item['hourly_path'], item['daily_path'], target_day,
                                   pixels, grid, np, Dataset, num2date)
                    with gzip.open(output_path, 'wt', encoding='utf-8', newline='') as stream:
                        fields = list(rows[0]) if rows else []
                        if fields:
                            writer = csv.DictWriter(stream, fieldnames=fields)
                            writer.writeheader()
                            writer.writerows(rows)
                    manifest['files'][day_key] = {
                        'status': 'ok', 'url': item['hourly_url'], 'sha256': item['hourly_sha'],
                        'bytes': item['hourly_path'].stat().st_size, 'daily_url': item['daily_url'],
                        'daily_source_sha256': item['daily_sha'], 'daily_bytes': item['daily_path'].stat().st_size,
                        'feature_rows': len(rows), 'duration_seconds': round(time.time() - started[target_day], 2),
                        'output': output_path.name,
                    }
                    print(f'[{processed}/{len(target_dates)}] {day_key}: {len(rows)} points '
                          f'({time.time()-started[target_day]:.1f}s including parallel download)', flush=True)
                for part in (item['hourly_path'], item['daily_path']):
                    if part and part.exists():
                        part.unlink()
                manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    manifest['target_dates_requested'] = len(target_dates)
    manifest['target_dates_ok'] = sum(row.get('status') == 'ok' for row in manifest['files'].values())
    manifest['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
