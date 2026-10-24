#!/usr/bin/env python3
"""Compare official SNMF fire starts to full reviewed trail polylines.

This is a positive-event coverage audit only. It does not turn unlisted fires
or dates without PDFs into negatives, and it does not estimate prediction
precision. Distances use a local equirectangular projection centered on each
incident; trail vertices are the catalog's reviewed mapped geometry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

from environmental_sources import ROOT
from fire_sources import PRIVATE

BASE = ROOT / 'docs/environmental-models-2026-10-22'
GEOGRAPHY = ROOT / 'training/data/environmental/geography.json'
DEFAULT_GEOMETRY = PRIVATE / 'fire-route-geometries.json'
DEFAULT_YEAR = 2022


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def point_to_polyline_km(latitude: float, longitude: float,
                         coordinates: list[list[float]]) -> float:
    """Return approximate point-to-segment distance in a local metric plane."""
    cos_lat = math.cos(math.radians(latitude))
    points = [((lon - longitude) * 111.32 * cos_lat,
               (lat - latitude) * 110.574) for lat, lon in coordinates]
    if len(points) == 1:
        return math.hypot(*points[0])
    best_sq = math.inf
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy
        if denom == 0:
            t = 0.0
        else:
            t = max(0.0, min(1.0, -(ax * dx + ay * dy) / denom))
        px, py = ax + t * dx, ay + t * dy
        best_sq = min(best_sq, px * px + py * py)
    return math.sqrt(best_sq)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, default=DEFAULT_YEAR)
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--end-exclusive', type=date.fromisoformat)
    parser.add_argument('--reports', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--geometry', type=Path, default=DEFAULT_GEOMETRY)
    parser.add_argument('--geography', type=Path, default=GEOGRAPHY)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    reports_path = args.reports or BASE / f'snmf-{args.year}-daily-occurrence-events.json'
    manifest_path = args.manifest or PRIVATE / f'snmf-daily-occurrence-{args.year}' / 'source-manifest.json'
    out_path = args.output or BASE / f'fire-snmf-polyline-event-coverage-{args.year}.json'
    for path in (reports_path, manifest_path, args.geometry, args.geography):
        if not path.is_file():
            raise FileNotFoundError(path)
    reports = json.loads(reports_path.read_text(encoding='utf-8'))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    geography = json.loads(args.geography.read_text(encoding='utf-8'))
    geometry_doc = json.loads(args.geometry.read_text(encoding='utf-8'))
    geometries = {item['name']: item for item in geometry_doc['fire_route_geometries']}
    centers = {item['name']: item for item in geography['fire_regions']}
    selected = {name: item for name, item in geometries.items() if name in centers}
    start = args.start or date.fromisoformat(manifest['period'][0])
    end = args.end_exclusive or date.fromisoformat(manifest['period'][1])
    if start >= end:
        raise ValueError('Invalid period')

    supported_days = {item['date'] for item in manifest.get('reports', [])
                      if item.get('status') in ('downloaded', 'cached')}
    events_by_region_day: dict[tuple[str, str], list[dict]] = defaultdict(list)
    matched_events = []
    for event in reports.get('deduplicated_events', []):
        day_text = event.get('reported_start_date')
        lat, lon = event.get('latitude'), event.get('longitude')
        if not day_text or not start.isoformat() <= day_text < end.isoformat():
            continue
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        for name, geometry in selected.items():
            line_distance = point_to_polyline_km(lat, lon, geometry['route_coordinates'])
            center_distance = point_to_polyline_km(lat, lon,
                [[centers[name]['latitude'], centers[name]['longitude']]])
            if line_distance > 50:
                continue
            record = {
                'route_sector': name, 'reported_start_date': day_text,
                'incident_name': event.get('incident_name'), 'province': event.get('province'),
                'line_distance_km': round(line_distance, 3),
                'center_distance_km': round(center_distance, 3),
                'reported_start_date_pdf_available': day_text in supported_days,
                'geometry_sha256': geometry['geometry_sha256'],
            }
            matched_events.append(record)
            events_by_region_day[(name, day_text)].append(record)

    radius_results = {}
    for radius in (10, 20):
        matches = [item for item in matched_events if item['line_distance_km'] <= radius]
        route_days = sorted({(item['route_sector'], item['reported_start_date']) for item in matches})
        region_counts = defaultdict(int)
        for name, _ in route_days:
            region_counts[name] += 1
        center_miss_days = sorted({(item['route_sector'], item['reported_start_date'])
            for item in matches if item['center_distance_km'] > radius})
        radius_results[str(radius)] = {
            'incident_records_within_radius': len(matches),
            'unique_route_sector_start_days': len(route_days),
            'route_sector_days_by_region': dict(sorted(region_counts.items())),
            'days_found_by_polyline_but_missed_by_center': [
                {'route_sector': name, 'reported_start_date': day}
                for name, day in center_miss_days],
        }

    available_names = sorted(selected)
    missing_names = sorted(set(centers) - set(selected))
    source_hashes = {'reports': sha256(reports_path), 'manifest': sha256(manifest_path),
        'geometry': sha256(args.geometry), 'geography': sha256(args.geography)}
    result = {
        'experiment_id': f'snmf-reported-fire-starts-full-trail-polyline-{args.year}',
        'meaning': 'Positive event coverage using complete reviewed trail polylines; not an evaluation of prediction precision.',
        'period': [start.isoformat(), end.isoformat()],
        'spatial_protocol': {
            'distance': 'Local equirectangular point-to-polyline segment distance, centered on each event',
            'radii_km': [10, 20],
            'minimum_polyline_vertices_by_route': {name: len(item['route_coordinates']) for name, item in selected.items()},
            'route_geometry_source_hashes': {name: item['geometry_sha256'] for name, item in selected.items()},
            'routes_without_reviewed_polyline': missing_names,
            'center_distance_is_computed_against_existing_sector_coordinate': True,
        },
        'report_coverage': {'available_report_dates': len(supported_days),
            'period_days': (end - start).days,
            'dates_without_pdf_are_unknown': (end - start).days - len(supported_days)},
        'source_hashes': source_hashes,
        'results': radius_results,
        'events_within_50km': sorted(matched_events, key=lambda item: (
            item['route_sector'], item['reported_start_date'], item['line_distance_km'])),
        'limitations': [
            'SNMF reports are jurisdiction-reported, not an exhaustive incident/no-incident registry.',
            'A missing report or no listed nearby incident is not a verified physical no-fire window.',
            'Dates are reported calendar dates; exact ignition time and lead time are unavailable.',
            'Routes without a reviewed polyline are excluded; sector centers are not substituted into line-distance counts.',
            'A mapped trail line does not imply that all adjacent land is equally exposed or that the trail was open.',
            'Local equirectangular distance is an approximation; the 10/20 km results should be checked geodesically before threshold-sensitive use.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out_path), 'available_routes': available_names,
        'routes_without_reviewed_polyline': missing_names,
        'results': {radius: {key: value for key, value in summary.items()
                             if key != 'days_found_by_polyline_but_missed_by_center'}
                    for radius, summary in radius_results.items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
