#!/usr/bin/env python3
"""Check NOAA GOES FDCF quality/mask coverage at reviewed Argentine trail lines."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from environmental_sources import ROOT

GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
SAMPLE_DIR = ROOT / 'training/data/environmental/private/goes-fdc-netcdf-pilot-2024-10-26'
OUTPUT = ROOT / 'docs/environmental-models-2026-10-22/fire-goes-fdc-route-quality-pilot-2024-10-26.json'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fixed_grid(lat: float, lon: float, *, height: float, semi_major: float,
               semi_minor: float, longitude_origin: float) -> tuple[float, float]:
    """Map lon/lat to GOES fixed-grid scan angles (radians; sweep-x)."""
    phi = math.radians(lat)
    delta_lon = math.radians(lon) - math.radians(longitude_origin)
    eccentricity_squared = (semi_major**2 - semi_minor**2) / semi_major**2
    geocentric_lat = math.atan((semi_minor**2 / semi_major**2) * math.tan(phi))
    radius = semi_minor / math.sqrt(
        1 - eccentricity_squared * math.cos(geocentric_lat) ** 2
    )
    sx = height - radius * math.cos(geocentric_lat) * math.cos(delta_lon)
    sy = -radius * math.cos(geocentric_lat) * math.sin(delta_lon)
    sz = radius * math.sin(geocentric_lat)
    return math.atan2(-sy, sx), math.atan2(sz, math.hypot(sx, sy))


def sample_route(route: dict, maximum_vertices: int = 100) -> list[tuple[float, float]]:
    coordinates = route['route_coordinates']
    step = max(1, len(coordinates) // maximum_vertices)
    points = coordinates[::step]
    if coordinates[-1] not in points:
        points.append(coordinates[-1])
    return [(float(lat), float(lon)) for lat, lon in points]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, help='NOAA FDCF NetCDF file; defaults to the private pilot file.')
    parser.add_argument('--geometry', type=Path, default=GEOMETRY)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    sample = args.sample or next(SAMPLE_DIR.glob('*.nc'))
    routes = json.loads(args.geometry.read_text(encoding='utf-8'))['fire_route_geometries']

    with Dataset(sample) as ds:
        projection = ds['goes_imager_projection']
        height = float(projection.perspective_point_height)
        semi_major = float(projection.semi_major_axis)
        semi_minor = float(projection.semi_minor_axis)
        longitude_origin = float(projection.longitude_of_projection_origin)
        x_values = np.asarray(ds['x'][:])
        y_values = np.asarray(ds['y'][:])
        dqf = ds['DQF']
        mask = ds['Mask']
        dqf_grid = np.asarray(dqf[:])
        mask_grid = np.asarray(mask[:])
        dqf_meanings = str(dqf.flag_meanings).split()
        mask_values = [int(value) for value in mask.flag_values]
        mask_meanings = str(mask.flag_meanings).split()
        mask_labels = dict(zip(mask_values, mask_meanings))
        scan = [float(value) for value in ds['time_bounds'][:]]

        per_route = []
        overall_dqf: Counter[str] = Counter()
        overall_mask: Counter[str] = Counter()
        for route in routes:
            route_dqf: Counter[str] = Counter()
            route_mask: Counter[str] = Counter()
            route_near_pixels: set[tuple[int, int]] = set()
            points = sample_route(route)
            for lat, lon in points:
                x, y = fixed_grid(
                    lat, lon, height=height, semi_major=semi_major,
                    semi_minor=semi_minor, longitude_origin=longitude_origin,
                )
                col = int(np.argmin(np.abs(x_values - x)))
                row = int(np.argmin(np.abs(y_values - y)))
                dqf_code = int(dqf[row, col])
                mask_code = int(mask[row, col])
                dqf_key = str(dqf_code)
                mask_key = str(mask_code)
                route_dqf[dqf_key] += 1
                route_mask[mask_key] += 1
                overall_dqf[dqf_key] += 1
                overall_mask[mask_key] += 1
                for near_row in range(max(0, row - 1), min(dqf_grid.shape[0], row + 2)):
                    for near_col in range(max(0, col - 1), min(dqf_grid.shape[1], col + 2)):
                        route_near_pixels.add((near_row, near_col))
            near_dqf = Counter(str(int(dqf_grid[row, col])) for row, col in route_near_pixels)
            near_mask = Counter(str(int(mask_grid[row, col])) for row, col in route_near_pixels)
            per_route.append({
                'route': route['name'],
                'sampled_line_vertices': len(points),
                'dqf_counts': dict(sorted(route_dqf.items(), key=lambda item: int(item[0]))),
                'mask_counts': {
                    key: {'count': count, 'meaning': mask_labels.get(int(key), 'unknown')}
                    for key, count in sorted(route_mask.items(), key=lambda item: int(item[0]))
                },
                'unique_pixels_in_approx_3x3_neighborhoods': len(route_near_pixels),
                'near_route_dqf_counts': dict(sorted(near_dqf.items(), key=lambda item: int(item[0]))),
                'near_route_mask_counts': {
                    key: {'count': count, 'meaning': mask_labels.get(int(key), 'unknown')}
                    for key, count in sorted(near_mask.items(), key=lambda item: int(item[0]))
                },
            })

    result = {
        'experiment_id': 'noaa-goes-fdc-sampled-trail-line-quality-2024-10-26',
        'purpose': 'Single-scan feasibility check of quality/mask coverage; not a fire-prediction evaluation.',
        'source': {
            'dataset': 'NOAA GOES ABI Level 2 Fire/Hot Spot Characterization (FDCF)',
            'filename': sample.name,
            'sha256': sha256(sample),
            'scan_time_bounds_seconds_since_2000_01_01_12_00_00': scan,
            'projection': 'GOES fixed grid, sweep-x; each route vertex assigned its nearest grid pixel.',
            'quality_flag_meanings': dict(enumerate(dqf_meanings)),
            'mask_flag_meanings': {str(key): value for key, value in mask_labels.items()},
        },
        'route_geometry': {
            'path': str(args.geometry),
            'sha256': sha256(args.geometry),
            'routes': len(routes),
            'sampling': 'Approximately 100 vertices per route, plus final vertex; nearest pixel per vertex.',
        },
        'overall_dqf_counts': dict(sorted(overall_dqf.items(), key=lambda item: int(item[0]))),
        'overall_mask_counts': {
            key: {'count': count, 'meaning': mask_labels.get(int(key), 'unknown')}
            for key, count in sorted(overall_mask.items(), key=lambda item: int(item[0]))
        },
        'per_route': per_route,
        'limitations': [
            'One scan cannot establish seasonal or route-level availability.',
            'GOES FDCF labels satellite classifications, not field-confirmed fire presence or absence.',
            'DQF values other than good-quality fire or good-quality fire-free land are unknown, not negatives.',
            'Nearest-pixel and sampled 3x3-neighborhood sampling is a feasibility check, not a complete route-buffer raster extraction.',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': str(args.output),
        'overall_dqf_counts': result['overall_dqf_counts'],
        'routes_with_good_quality_samples': sum(
            int(row['dqf_counts'].get('0', 0)) + int(row['dqf_counts'].get('1', 0)) > 0
            for row in per_route
        ),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
