"""Reuse archived SMN WRF grids for route pixels already covered by the archive.

The public WRF archive can be unreachable from some networks. This script
spatially maps each MODIS route pixel to the nearest WRF grid point that is
already present in the independently acquired, hash-recorded route-study files.
It does not extrapolate weather beyond 5 km or fill missing dates.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from environmental_sources import PUBLIC, ROOT, sha256

PRIVATE = PUBLIC / 'private'
OBSERVATIONS = PRIVATE / 'argentina-trail-modis-labels' / 'observations.csv.gz'
SOURCE_DIR = PRIVATE / 'smn-wrf-modis-weather'
OUT_DIR = PRIVATE / 'smn-wrf-argentina-routes-weather'
MAX_GRID_DISTANCE_KM = 5.0


def unit_sphere(latitude, longitude):
    lat, lon = np.deg2rad(latitude), np.deg2rad(longitude)
    return np.column_stack((np.cos(lat) * np.cos(lon),
                            np.cos(lat) * np.sin(lon), np.sin(lat)))


def load_pixels(path):
    pixels, dates = {}, set()
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            dates.add(row['observed_date'])
            pixel_id = f"{row['tile']}:{row['row']}:{row['col']}"
            coordinate = (float(row['latitude']), float(row['longitude']))
            old = pixels.setdefault(pixel_id, coordinate)
            if old != coordinate:
                raise ValueError(f'Inconsistent coordinate for MODIS pixel {pixel_id}')
    return pixels, dates


def read_weather(path):
    values = {}
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            key = (float(row['wrf_latitude']), float(row['wrf_longitude']))
            values.setdefault(key, row)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path, default=OBSERVATIONS)
    parser.add_argument('--source-dir', type=Path, default=SOURCE_DIR)
    parser.add_argument('--output-dir', type=Path, default=OUT_DIR)
    args = parser.parse_args()
    source_dir, output_dir = args.source_dir.resolve(), args.output_dir.resolve()
    manifest_path = source_dir / 'manifest.json'
    source_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    pixels, observation_dates = load_pixels(args.observations)
    seed_date = next((day for day, record in sorted(source_manifest['files'].items())
                      if record.get('status') == 'ok' and (source_dir / f'{day}.csv.gz').is_file()), None)
    if seed_date is None:
        raise ValueError('No acquired SMN WRF day is available to map the archive grid')
    seed_values = read_weather(source_dir / f'{seed_date}.csv.gz')
    grid_points = list(seed_values)
    tree = cKDTree(unit_sphere([p[0] for p in grid_points], [p[1] for p in grid_points]))
    pixel_ids = list(pixels)
    coordinates = [pixels[key] for key in pixel_ids]
    chord, indices = tree.query(unit_sphere([p[0] for p in coordinates], [p[1] for p in coordinates]), k=1)
    distances = 6371.0088 * 2 * np.arcsin(np.minimum(1.0, chord / 2))
    mapping = {}
    for pixel_id, coordinate, index, distance in zip(pixel_ids, coordinates, indices, distances):
        if distance <= MAX_GRID_DISTANCE_KM:
            mapping[pixel_id] = {'coordinate': coordinate, 'grid': grid_points[int(index)],
                                 'distance_km': float(distance)}
    if not mapping:
        raise ValueError('No route pixels within the existing WRF 5 km grid tolerance')

    output_dir.mkdir(parents=True, exist_ok=True)
    output_files, days_with_data, rejected = [], 0, 0
    mapped_dates = set()
    expected_grid = set(grid_points)
    for day, record in sorted(source_manifest['files'].items()):
        source_path = source_dir / f'{day}.csv.gz'
        if record.get('status') != 'ok' or not source_path.is_file():
            rejected += 1
            continue
        if record.get('daily_source_sha256') is None:
            raise ValueError(f'Source day lacks complete WRF provenance: {day}')
        actual_hash = sha256(source_path)
        grid_values = read_weather(source_path)
        if set(grid_values) != expected_grid:
            raise ValueError(f'WRF grid changed on {day}; refusing spatial remapping')
        path = output_dir / f'{day}.csv.gz'
        with path.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed, \
                __import__('io').TextIOWrapper(compressed, encoding='utf-8', newline='') as text:
            fields = ['pixel_id', 'target_date', 'issue_time_utc', 'valid_time_utc', 'lead_hours',
                      'pixel_latitude', 'pixel_longitude', 'wrf_latitude', 'wrf_longitude',
                      'grid_distance_km', 'T2', 'HR2', 'magViento10', 'dirViento10', 'PP', 'Tmax', 'Tmin']
            writer = csv.DictWriter(text, fieldnames=fields)
            writer.writeheader()
            for pixel_id, item in mapping.items():
                row = grid_values[item['grid']]
                writer.writerow({'pixel_id': pixel_id, 'target_date': day,
                    'issue_time_utc': row['issue_time_utc'], 'valid_time_utc': row['valid_time_utc'],
                    'lead_hours': row['lead_hours'], 'pixel_latitude': item['coordinate'][0],
                    'pixel_longitude': item['coordinate'][1], 'wrf_latitude': item['grid'][0],
                    'wrf_longitude': item['grid'][1], 'grid_distance_km': item['distance_km'],
                    **{name: row.get(name) for name in fields[10:]}})
        output_files.append({'date': day, 'source_weather_sha256': actual_hash,
                             'output_sha256': sha256(path), 'pixel_rows': len(mapping)})
        mapped_dates.add(day)
        days_with_data += 1
        if days_with_data % 50 == 0 or days_with_data == 1:
            print(f'{days_with_data} WRF dates mapped; latest {day}', flush=True)

    result = {'experiment_id': 'smn-wrf-weather-remapped-to-argentina-route-cohort',
        'source_manifest': manifest_path.relative_to(ROOT).as_posix(),
        'source_manifest_sha256': sha256(manifest_path), 'observation_file': args.observations.relative_to(ROOT).as_posix(),
        'observation_sha256': sha256(args.observations), 'output_directory': output_dir.relative_to(ROOT).as_posix(),
        'mapping': {'method': 'nearest existing WRF grid coordinate on the unchanged grid',
                    'distance_metric': 'great-circle from unit-sphere chord',
                    'maximum_distance_km': MAX_GRID_DISTANCE_KM,
                    'route_pixels': len(pixels), 'mapped_pixels': len(mapping),
                    'unique_grid_points': len(expected_grid), 'seed_date_for_grid': seed_date},
        'counts': {'observation_dates': len(observation_dates), 'weather_days_mapped': days_with_data,
                   'observation_dates_without_weather': len(observation_dates - mapped_dates),
                   'observation_dates_not_in_source_manifest': len(observation_dates - set(source_manifest['files'])),
                   'observation_dates_with_failed_source_download': len(observation_dates & {
                       day for day, record in source_manifest['files'].items() if record.get('status') != 'ok'}),
                   'source_manifest_rows_rejected': rejected,
                   'mapped_pixel_days': days_with_data * len(mapping)},
        'files': output_files, 'synthetic_observations': 0, 'deployment_approved': False,
        'limitations': ['Weather values are copied from original SMN WRF forecast grid cells, not interpolated.',
            'Route pixel cells farther than 5 km from the sampled WRF grid points are excluded.',
            'Unavailable WRF dates remain missing; this is not a complete sample of all MODIS dates.',
            'The model target remains a MODIS fire detection, not independently confirmed ignition.']}
    report_path = output_dir / 'mapping-manifest.json'
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': report_path.relative_to(ROOT).as_posix(), **result['counts'],
                      **result['mapping']}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
