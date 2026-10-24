"""Audit open INPE reference-satellite fire detections near Argentine trails.

This is a positive-detection coverage audit, not a prediction evaluation. A
missing point is never treated as an observed fire-free route-day.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import zipfile
from datetime import date, timedelta
from collections import Counter, defaultdict
from pathlib import Path

from environmental_sources import PUBLIC, ROOT, sha256

ARCHIVE_DIR = PUBLIC / 'private/inpe-ams-satellite-reference'
GEOGRAPHY = PUBLIC / 'geography.json'
YEARS = tuple(range(2018, 2026))
RADII_KM = (5, 10, 20, 50)
SOURCE_URL = 'https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/anual/AMS_sat_ref/'
SNMF_DIR = ROOT / 'docs/environmental-models-2026-10-22'


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180
    dlat, dlon = (lat2 - lat1) * rad, (lon2 - lon1) * rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def read_year(year: int, regions: list[dict]) -> tuple[dict, list[dict]]:
    archive = ARCHIVE_DIR / f'focos_ams_ref_{year}.zip'
    if not archive.is_file():
        raise FileNotFoundError(f'Missing public INPE archive: {archive}')
    country_rows = Counter()
    detections_by_region = defaultdict(list)
    argentina_days: set[str] = set()
    with zipfile.ZipFile(archive) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith('.csv')]
        if len(csv_names) != 1:
            raise ValueError(f'Expected exactly one CSV in {archive.name}; found {csv_names}')
        with zf.open(csv_names[0]) as raw:
            rows = csv.DictReader(io.TextIOWrapper(raw, encoding='latin1', newline=''))
            required = {'id_bdq', 'foco_id', 'lat', 'lon', 'data_pas', 'pais'}
            if not required.issubset(rows.fieldnames or []):
                raise ValueError(f'Unexpected CSV schema in {archive.name}: {rows.fieldnames}')
            for row in rows:
                country = row['pais'].strip().casefold()
                country_rows[country] += 1
                if country != 'argentina':
                    continue
                day = row['data_pas'][:10]
                argentina_days.add(day)
                lat, lon = float(row['lat']), float(row['lon'])
                for region in regions:
                    distance = haversine_km(lat, lon, region['latitude'], region['longitude'])
                    if distance <= max(RADII_KM):
                        detections_by_region[region['name']].append({
                            'detection_id': row['foco_id'],
                            'date': day,
                            'timestamp': row['data_pas'].strip(),
                            'distance_km': distance,
                            'latitude': lat,
                            'longitude': lon,
                        })

    radius_results = {}
    for radius in RADII_KM:
        matching_rows = [
            (region, detection)
            for region, detections in detections_by_region.items()
            for detection in detections
            if detection['distance_km'] <= radius
        ]
        route_days = defaultdict(list)
        for region, detection in matching_rows:
            route_days[(region, detection['date'])].append(detection)
        radius_results[str(radius)] = {
            'detection_records': len(matching_rows),
            'unique_route_sector_days_with_detection': len(route_days),
            'route_sector_days_by_region': dict(Counter(region for region, _ in route_days)),
            'route_sector_days': [
                {
                    'route_sector': region,
                    'date': day,
                    'detection_records': len(group),
                    'nearest_detection_km': round(min(d['distance_km'] for d in group), 3),
                    'detection_ids': sorted({d['detection_id'] for d in group}),
                }
                for (region, day), group in sorted(route_days.items())
            ],
        }
    snmf_path = SNMF_DIR / f'snmf-{year}-daily-occurrence-events.json'
    snmf_comparison = None
    if snmf_path.is_file() and year >= 2023:
        report = json.loads(snmf_path.read_text(encoding='utf-8'))
        report_days = defaultdict(list)
        for event in report.get('deduplicated_events', []):
            day, lat, lon = event.get('reported_start_date'), event.get('latitude'), event.get('longitude')
            if not day or not day.startswith(f'{year}-') or lat is None or lon is None:
                continue
            for region in regions:
                distance = haversine_km(float(lat), float(lon), region['latitude'], region['longitude'])
                if distance <= 10:
                    report_days[(region['name'], day)].append(event.get('incident_name'))
        same_date, within_one_day = [], []
        for region, day in sorted(report_days):
            report_date = date.fromisoformat(day)
            detection_days = {
                detection['date']
                for detection in detections_by_region.get(region, [])
                if detection['distance_km'] <= 10
            }
            if day in detection_days:
                same_date.append({'route_sector': region, 'reported_start_date': day})
            if any((report_date + timedelta(days=offset)).isoformat() in detection_days for offset in (-1, 0, 1)):
                within_one_day.append({'route_sector': region, 'reported_start_date': day})
        snmf_comparison = {
            'event_source': snmf_path.name,
            'event_source_sha256': sha256(snmf_path),
            'reported_start_route_days_with_coordinates_within_10km': len(report_days),
            'coinciding_reference_detection_same_date_within_10km': len(same_date),
            'coinciding_reference_detection_within_plus_minus_1_day_within_10km': len(within_one_day),
            'same_date_route_days': same_date,
            'plus_minus_1_day_route_days': within_one_day,
            'interpretation': 'Descriptive cross-source coincidence only; neither unmatched report days nor unmatched satellite detections are classified as errors.',
        }
    summary = {
        'year': year,
        'archive': archive.name,
        'archive_bytes': archive.stat().st_size,
        'archive_sha256': sha256(archive),
        'csv_country_rows': dict(sorted(country_rows.items())),
        'argentina_detection_records': country_rows['argentina'],
        'argentina_days_with_at_least_one_detection': len(argentina_days),
        'route_buffers': radius_results,
        'snmf_start_date_comparison': snmf_comparison,
    }
    nearby = [
        {'route_sector': region, **detection}
        for region, detections in detections_by_region.items()
        for detection in detections
    ]
    return summary, nearby


def main(output: Path | None = None) -> None:
    geography_path = PUBLIC / 'geography.json'
    regions = json.loads(geography_path.read_text(encoding='utf-8'))['fire_regions']
    yearly, detections = [], []
    for year in YEARS:
        summary, nearby = read_year(year, regions)
        yearly.append(summary)
        detections.extend(nearby)
    result = {
        'experiment_id': 'inpe-reference-satellite-detections-near-argentina-trail-centers-2018-2025',
        'meaning': 'Coverage audit of observed active-fire satellite detections near route-sector centers; not a prediction or precision evaluation.',
        'sources': {
            'publisher': 'INPE Programa Queimadas',
            'archive_directory': SOURCE_URL,
            'data_description': 'Annual South America CSV archives for the reference satellite; the INPE FAQ identifies AQUA/MODIS as the reference series.',
            'geography_sha256': sha256(geography_path),
            'years': YEARS,
        },
        'spatial_protocol': {
            'route_sectors': [region['name'] for region in regions],
            'distance': 'Haversine from point detection to fixed route-sector center; this is not distance to full trail geometry.',
            'radii_km': RADII_KM,
            'unit': 'detection record and unique route-sector-date; multiple records on one day are grouped in the route-day count.',
        },
        'yearly': yearly,
        'nearby_detections': sorted(detections, key=lambda d: (d['date'], d['route_sector'], d['distance_km'])),
        'limitations': [
            'Positive detections only: a route-sector day without a point is unknown, not a verified no-fire day.',
            'Satellite detections can miss fires because of overpass timing, cloud, canopy, fire size, and location error.',
            'A reference-satellite detection identifies active fire at overpass time; it does not by itself establish wildfire versus controlled/agricultural burning.',
            'The route-sector centers are a coarse spatial screen and do not replace overlay against complete route polylines.',
            'The source is independent of SNMF administrative reports but is not independent of other satellite-derived labels using the same or related sensors.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    output = output or ROOT / 'docs/environmental-models-2026-10-22/fire-inpe-reference-detections-route-coverage-2018-2025.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': output.relative_to(ROOT).as_posix(),
        'years': [{
            'year': item['year'],
            'argentina_detection_records': item['argentina_detection_records'],
            'route_days_10km': item['route_buffers']['10']['unique_route_sector_days_with_detection'],
            'route_days_20km': item['route_buffers']['20']['unique_route_sector_days_with_detection'],
        } for item in yearly],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.output)
