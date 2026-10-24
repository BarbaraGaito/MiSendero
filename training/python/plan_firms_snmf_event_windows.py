#!/usr/bin/env python3
"""Plan bounded NASA FIRMS queries around SNMF-positive route days.

This is an event-enriched corroboration cohort. It is not suitable for
estimating model precision and creates no negative labels.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from audit_inpe_reference_detections_route_polylines import prepare_routes
from evaluate_jma_full_trail_polyline_transfer_2025 import (
    BASE, PRIVATE, REPORT_FILES, MANIFEST_DIRS, build_polyline_labels,
)
from environmental_sources import ROOT, sha256

GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
OUTPUT_DIR = ROOT / 'training/data/environmental/private/firms-route-detections'


def plan_year(year: str, buffer_km: float = 20.0) -> dict:
    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    routes = prepare_routes(geometry['fire_route_geometries'])
    labels = build_polyline_labels(year, routes)[int(buffer_km)]
    positive_days: dict[str, set[date]] = {route['name']: set() for route in routes}
    for row in labels:
        if row['label']:
            positive_days[row['region']].add(date.fromisoformat(row['date']))

    windows: dict[str, list[list[str]]] = {}
    for route, days in positive_days.items():
        expanded = sorted({
            day + timedelta(days=offset)
            for day in days for offset in (-1, 0, 1)
        })
        spans: list[list[date]] = []
        for day in expanded:
            if spans and day <= spans[-1][1] + timedelta(days=1) and (day - spans[-1][0]).days < 5:
                spans[-1][1] = day
            else:
                spans.append([day, day])
        windows[route] = [[start.isoformat(), end.isoformat()] for start, end in spans]

    report_path = REPORT_FILES[year]
    manifest_path = ROOT / 'training/data/environmental/private' / MANIFEST_DIRS[year] / 'source-manifest.json'
    return {
        'schema_version': 1,
        'experiment_id': f'firms-snmf-positive-route-days-query-plan-{year}',
        'year': int(year),
        'buffer_km': buffer_km,
        'cohort': 'SNMF-positive full-polyline route-days at the stated radius; each query window includes one day before and after. Event-enriched corroboration only.',
        'route_positive_days': {route: sorted(day.isoformat() for day in days) for route, days in positive_days.items()},
        'date_windows': windows,
        'sources': {
            'snmf_events_sha256': sha256(report_path),
            'snmf_manifest_sha256': sha256(manifest_path),
            'route_geometry_sha256': sha256(GEOMETRY),
        },
        'negative_labels_created': 0,
        'precision_estimable': False,
        'synthetic_observations': 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--years', nargs='+', choices=sorted(REPORT_FILES), required=True)
    parser.add_argument('--buffer-km', type=float, default=20.0)
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for year in args.years:
        plan = plan_year(year, args.buffer_km)
        path = OUTPUT_DIR / f'event-windows-{year}.json'
        path.write_text(json.dumps(plan['date_windows'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        plan_path = OUTPUT_DIR / f'event-plan-{year}.json'
        plan['date_windows_sha256'] = sha256(path)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        block_count = sum(len(windows) for windows in plan['date_windows'].values())
        print(json.dumps({
            'year': year,
            'positive_route_days': sum(len(days) for days in plan['route_positive_days'].values()),
            'route_sectors_with_positive_days': sum(bool(days) for days in plan['route_positive_days'].values()),
            'date_window_blocks': block_count,
            'plan': plan_path.relative_to(ROOT).as_posix(),
            'date_windows': path.relative_to(ROOT).as_posix(),
        }, ensure_ascii=False))


if __name__ == '__main__':
    main()
