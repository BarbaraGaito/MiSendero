"""Audit INPE reference active-fire detections against full MiSendero routes.

This measures positive-detection coverage only. A route-day without a hotspot
is unknown and must never be used as a negative label or precision estimate.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from environmental_sources import PUBLIC, ROOT, sha256

ARCHIVE_DIR = PUBLIC / 'private/inpe-ams-satellite-reference'
GEOMETRY = PUBLIC / 'private/fire-route-geometries.json'
YEARS = tuple(range(2018, 2026))
RADII_KM = (2, 5, 10, 20)
KM_PER_DEG_LAT = 110.574


def project_route(coordinates: list[tuple[float, float]]) -> tuple[float, float, float, list[tuple[float, float]]]:
    lat0 = sum(lat for lat, _ in coordinates) / len(coordinates)
    lon0 = sum(lon for _, lon in coordinates) / len(coordinates)
    scale_x = 111.320 * math.cos(math.radians(lat0))
    xy = [((lon - lon0) * scale_x, (lat - lat0) * KM_PER_DEG_LAT)
          for lat, lon in coordinates]
    return lat0, lon0, scale_x, xy


def distance_to_polyline_km(latitude: float, longitude: float,
                            projection: tuple[float, float, float, list[tuple[float, float]]]) -> float:
    lat0, lon0, scale_x, xy = projection
    px = (longitude - lon0) * scale_x
    py = (latitude - lat0) * KM_PER_DEG_LAT
    best = math.inf
    for (ax, ay), (bx, by) in zip(xy, xy[1:]):
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
        best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    if len(xy) == 1:
        best = math.hypot(px - xy[0][0], py - xy[0][1])
    return best


def prepare_routes(geometries: list[dict]) -> list[dict]:
    result = []
    for item in geometries:
        coordinates = [(float(p[0]), float(p[1])) for p in item['route_coordinates']]
        lat_min, lat_max = min(p[0] for p in coordinates), max(p[0] for p in coordinates)
        lon_min, lon_max = min(p[1] for p in coordinates), max(p[1] for p in coordinates)
        lat_padding = max(RADII_KM) / KM_PER_DEG_LAT
        cos_lat = max(math.cos(math.radians((lat_min + lat_max) / 2)), 0.1)
        lon_padding = max(RADII_KM) / (111.320 * cos_lat)
        result.append({
            'name': item['name'],
            'coordinates': coordinates,
            'projection': project_route(coordinates),
            'bounds': (lat_min - lat_padding, lat_max + lat_padding,
                       lon_min - lon_padding, lon_max + lon_padding),
        })
    return result


def contiguous_sequences(days: set[str]) -> list[list[str]]:
    sequences: list[list[str]] = []
    for day in sorted(date.fromisoformat(item) for item in days):
        if not sequences or (day - date.fromisoformat(sequences[-1][-1])).days > 1:
            sequences.append([day.isoformat()])
        else:
            sequences[-1].append(day.isoformat())
    return sequences


def audit_year(year: int, routes: list[dict]) -> dict:
    archive = ARCHIVE_DIR / f'focos_ams_ref_{year}.zip'
    if not archive.is_file():
        raise FileNotFoundError(f'Missing INPE annual archive: {archive}')
    route_days: dict[str, dict[int, set[str]]] = {
        route['name']: {radius: set() for radius in RADII_KM} for route in routes
    }
    with zipfile.ZipFile(archive) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith('.csv')]
        if len(csv_names) != 1:
            raise ValueError(f'Expected one CSV in {archive.name}, found {len(csv_names)}')
        with zf.open(csv_names[0]) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding='latin1', newline=''))
            required = {'lat', 'lon', 'data_pas', 'pais'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f'Unexpected INPE schema: {reader.fieldnames}')
            for row in reader:
                if row['pais'].strip().casefold() != 'argentina':
                    continue
                latitude, longitude = float(row['lat']), float(row['lon'])
                day = row['data_pas'][:10]
                for route in routes:
                    south, north, west, east = route['bounds']
                    if not (south <= latitude <= north and west <= longitude <= east):
                        continue
                    distance = distance_to_polyline_km(latitude, longitude, route['projection'])
                    for radius in RADII_KM:
                        if distance <= radius:
                            route_days[route['name']][radius].add(day)

    by_radius = {}
    for radius in RADII_KM:
        sequences = []
        for route in routes:
            for sequence in contiguous_sequences(route_days[route['name']][radius]):
                sequences.append({
                    'route_sector': route['name'],
                    'first_detection_day': sequence[0],
                    'last_detection_day': sequence[-1],
                    'detection_days': len(sequence),
                })
        by_radius[str(radius)] = {
            'unique_route_days_with_detection': sum(len(route_days[route['name']][radius]) for route in routes),
            'route_days_by_sector': {
                route['name']: len(route_days[route['name']][radius])
                for route in routes if route_days[route['name']][radius]
            },
            'temporal_sequences_gap_at_most_one_day': len(sequences),
            'longest_sequence_days': max((item['detection_days'] for item in sequences), default=0),
            'sequences': sequences,
        }
    return {
        'year': year,
        'archive': archive.name,
        'archive_bytes': archive.stat().st_size,
        'archive_sha256': sha256(archive),
        'results_by_radius_km': by_radius,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/environmental-models-2026-10-22/fire-inpe-full-route-polyline-coverage-2018-2025.json')
    args = parser.parse_args()
    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    routes = prepare_routes(geometry['fire_route_geometries'])
    years = [audit_year(year, routes) for year in YEARS]
    result = {
        'experiment_id': 'inpe-ams-reference-active-fire-full-route-polyline-coverage-2018-2025',
        'purpose': 'Positive-detection spatial coverage and temporal clustering only; not model evaluation or precision.',
        'source': {
            'publisher': 'INPE Programa Queimadas',
            'archive_directory': 'https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/anual/AMS_sat_ref/',
            'geography_file': 'training/data/environmental/private/fire-route-geometries.json',
            'geography_sha256': sha256(GEOMETRY),
        },
        'method': {
            'distance': 'Approximate local planar point-to-full-polyline distance with longitude adjusted by route mean latitude.',
            'radii_km': list(RADII_KM),
            'temporal_clustering': 'Per route, detections on consecutive calendar dates (date difference at most one day) are grouped as one sequence. This diagnoses temporal dependence and does not establish one physical fire.',
            'label_policy': 'Positive detections only. No detections, missing observations, or dates without a hotspot are unknown, never negative labels.',
        },
        'years': years,
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': args.output.relative_to(ROOT).as_posix(),
        'route_days_by_year_at_5km': {
            str(item['year']): item['results_by_radius_km']['5']['unique_route_days_with_detection']
            for item in years
        },
        'temporal_sequences_at_5km': sum(item['results_by_radius_km']['5']['temporal_sequences_gap_at_most_one_day'] for item in years),
        'synthetic_observations': 0,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
