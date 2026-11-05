"""Inventory SNMF-reported fire starts near the fixed Argentine trail sectors.

This source audit measures positive event/report coverage only. Missing daily
reports and parser-empty PDFs are never converted into fire-free labels.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from collections import Counter, defaultdict
from pathlib import Path

from environmental_sources import PUBLIC, ROOT, sha256

DEFAULT_YEAR = 2025
GEOGRAPHY = PUBLIC / 'geography.json'
RADII_KM = (10, 20)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def main(year=DEFAULT_YEAR, reports_path=None, manifest_path=None, out_path=None) -> None:
    reports_path = reports_path or ROOT / f'docs/environmental-models-2026-10-22/snmf-{year}-daily-occurrence-events.json'
    manifest_path = manifest_path or PUBLIC / f'private/snmf-daily-occurrence-{year}/source-manifest.json'
    out_path = out_path or ROOT / f'docs/environmental-models-2026-10-22/fire-snmf-route-event-coverage-{year}.json'
    out_md_path = out_path.with_suffix('.md')
    events = json.loads(reports_path.read_text(encoding='utf-8'))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    regions = json.loads(GEOGRAPHY.read_text(encoding='utf-8'))['fire_regions']
    observed_dates = sorted(record['date'] for record in manifest['reports']
                            if record.get('status') in ('downloaded', 'cached'))
    reports_by_month = Counter(day[:7] for day in observed_dates)
    parser_empty_reports = events['extraction'].get('reports_with_zero_parsed_events', 0)
    period_start, period_end = (date.fromisoformat(value) for value in manifest['period'])
    calendar_days = (period_end - period_start).days
    missing_report_days = calendar_days - len(observed_dates)

    starts = []
    for event in events['deduplicated_events']:
        day = event.get('reported_start_date')
        lat, lon = event.get('latitude'), event.get('longitude')
        if not day or not day.startswith(f'{year}-'):
            continue
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        for region in regions:
            distance = haversine_km(lat, lon, region['latitude'], region['longitude'])
            if distance <= max(RADII_KM):
                starts.append({
                    'incident_name': event.get('incident_name'),
                    'province': event.get('province'),
                    'reported_start_date': day,
                    'latest_report_date': event.get('report_date'),
                    'latest_status': event.get('status'),
                    'route_sector': region['name'],
                    'distance_from_sector_center_km': round(distance, 3),
                    'latitude': lat,
                    'longitude': lon,
                })

    per_radius = {}
    for radius in RADII_KM:
        eligible = [event for event in starts if event['distance_from_sector_center_km'] <= radius]
        route_days = defaultdict(list)
        for event in eligible:
            route_days[(event['route_sector'], event['reported_start_date'])].append(event)
        per_radius[str(radius)] = {
            'incident_records_within_radius': len(eligible),
            'unique_route_sector_start_days': len(route_days),
            'unique_route_sector_days_by_region': dict(Counter(key[0] for key in route_days)),
            'route_sector_start_days': [
                {
                    'route_sector': region,
                    'target_date': day,
                    'source_incident_names': sorted({str(event['incident_name']) for event in group}),
                    'nearest_reported_incident_km': min(event['distance_from_sector_center_km'] for event in group),
                }
                for (region, day), group in sorted(route_days.items())
            ],
        }

    result = {
        'experiment_id': f'snmf-reported-fire-starts-near-argentina-trail-centers-{year}',
        'meaning': 'Inventory of reported positive event starts only; not a model evaluation.',
        'sources': {
            'official_source': 'Sistema Nacional de Manejo del Fuego daily occurrence reports',
            'event_extraction_sha256': sha256(reports_path),
            'report_manifest_sha256': sha256(manifest_path),
            'geography_sha256': sha256(GEOGRAPHY),
        },
        'report_coverage': {
            'period': manifest['period'],
            'calendar_days': calendar_days,
            'downloaded_report_days': len(observed_dates),
            'dates_without_a_report_at_checked_paths': missing_report_days,
            'downloaded_days_by_month': dict(sorted(reports_by_month.items())),
            'reports_with_zero_extracted_event_rows': parser_empty_reports,
            'interpretation': 'No report is an unknown observation. A PDF with zero extracted rows may reflect report content or parser failure and was not called an official fire-free day.',
        },
        'spatial_protocol': {
            'regions': [region['name'] for region in regions],
            'distance_measure': 'Haversine between incident coordinates and fixed route-sector center',
            'radii_km': list(RADII_KM),
            'unit': 'route-sector start day; multiple incident records on the same route/date are grouped',
        },
        'results': per_radius,
        'limitations': [
            'Daily SNMF reports are jurisdiction-reported and not an exhaustive national event/no-event registry.',
            f'{missing_report_days} of {calendar_days} dates have no PDF at the checked paths; these are unknown, never negative.',
            f"The automated extraction has {events['extraction'].get('missing_coordinate_snapshot_rows', 0)} report snapshot rows without coordinates and {parser_empty_reports} reports with zero parsed event rows; original PDFs require review for those cases.",
            'Event starts may be approximate and duplicate naming may remain; route-day aggregation avoids treating duplicate records at the same route/date as separate positives.',
            'Route-sector centers do not represent the complete trail geometry.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        f'# Incendios SNMF reportados cerca de rutas, {year}',
        '',
        f"El archivo oficial contiene partes para {len(observed_dates)} de {calendar_days} días. En {parser_empty_reports} partes la extracción no encontró filas; no se asumió que fueran días sin incendios.",
        '',
    ]
    for radius in RADII_KM:
        summary = per_radius[str(radius)]
        lines.append(f"A {radius} km de los centros hay {summary['incident_records_within_radius']} registros de incidentes que corresponden a {summary['unique_route_sector_start_days']} días positivos sector-ruta.")
    lines += [
        '',
        'Este inventario aporta positivos para seleccionar una cohorte independiente. No permite estimar precisión: los días sin parte son desconocidos y no hay etiquetas negativas exhaustivas. El detalle, coordenadas, conteos mensuales y hashes está en el JSON asociado.',
    ]
    out_md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'output': out_path.relative_to(ROOT).as_posix(),
                      'report_coverage': result['report_coverage'],
                      'radius_results': {radius: {k: v for k, v in summary.items() if k != 'route_sector_start_days'}
                                         for radius, summary in per_radius.items()}},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=DEFAULT_YEAR)
    parser.add_argument('--reports', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.year, args.reports, args.manifest, args.output)
