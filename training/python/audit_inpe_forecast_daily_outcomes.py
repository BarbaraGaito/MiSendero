"""Join archived INPE danger forecasts to later daily active-fire detections.

Only detections observed after the forecast raster's own creation timestamp are
counted. An incomplete/missing daily archive is pending, never a negative.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from environmental_sources import PUBLIC, ROOT, sha256
from audit_inpe_reference_detections_route_polylines import (
    GEOMETRY as ROUTE_GEOMETRY_PATH,
    distance_to_polyline_km,
    prepare_routes,
)

CAPTURE_DIR = PUBLIC / 'inpe_fire_forecasts'
DAILY_DIR = PUBLIC / 'private/inpe-ams-satellite-reference/daily'
DEFAULT_OUTPUT = ROOT / 'docs/environmental-models-2026-10-22/fire-inpe-prospective-outcomes.json'
COMPLETE_AFTER_UTC_HOUR = 6
RADIUS_KM = 10
MONTHS = {
    'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12,
}


def parse_creation_date(value: str) -> datetime:
    match = re.search(r'(\d{1,2})\s+([a-z]{3})\s+(\d{4})\s+(\d{2}:\d{2}:\d{2})\s+UTC$', value.strip(), re.I)
    if not match:
        raise ValueError(f'Unrecognized INPE raster creation date: {value!r}')
    day, month, year, clock = match.groups()
    month_number = MONTHS.get(month.casefold())
    if not month_number:
        raise ValueError(f'Unrecognized INPE month: {month!r}')
    return datetime.strptime(f'{year}-{month_number:02d}-{int(day):02d} {clock}', '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)


def completion_status(target_day: date) -> tuple[str, dict | None, Path | None]:
    stem = f'focos_diario_{target_day:%Y%m%d}'
    csv_path = DAILY_DIR / f'{stem}.csv'
    manifest_path = DAILY_DIR / f'{stem}.manifest.json'
    if not csv_path.is_file():
        return 'pending_daily_csv_missing', None, None
    if not manifest_path.is_file():
        return 'pending_no_server_timestamp', None, csv_path
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    last_modified = manifest.get('last_modified')
    if not last_modified:
        return 'pending_no_server_timestamp', manifest, csv_path
    modified = parsedate_to_datetime(last_modified).astimezone(timezone.utc)
    # A daily file cannot be considered complete before the following UTC day.
    minimum = datetime.combine(target_day + timedelta(days=1), time(COMPLETE_AFTER_UTC_HOUR), tzinfo=timezone.utc)
    if modified < minimum:
        return 'pending_daily_file_not_mature', manifest, csv_path
    return 'daily_file_matured_by_http_timestamp', manifest, csv_path


def read_detections(paths: list[Path], route_rows: list[dict], window_start: datetime,
                    window_end: datetime) -> dict[str, list[dict]]:
    by_route = defaultdict(list)
    expected = {'id', 'lat', 'lon', 'data_hora_gmt', 'satelite', 'pais'}
    for path in paths:
        with path.open('r', encoding='latin1', newline='') as stream:
            rows = csv.DictReader(stream)
            if not expected.issubset(rows.fieldnames or []):
                raise ValueError(f'Unexpected columns in {path.name}: {rows.fieldnames}')
            for row in rows:
                if row.get('pais', '').strip().casefold() != 'argentina':
                    continue
                observed_at = datetime.strptime(row['data_hora_gmt'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                if not (window_start <= observed_at < window_end):
                    continue
                lat, lon = float(row['lat']), float(row['lon'])
                for route in route_rows:
                    south, north, west, east = route['bounds']
                    if not (south <= lat <= north and west <= lon <= east):
                        continue
                    distance = distance_to_polyline_km(lat, lon, route['projection'])
                    if distance <= RADIUS_KM:
                        by_route[route['name']].append({
                            'detection_id': row['id'],
                            'observed_at_utc': observed_at.isoformat().replace('+00:00', 'Z'),
                            'sensor': row.get('satelite'),
                            'distance_km': round(distance, 3),
                        })
    return by_route


def main(output: Path | None = None) -> None:
    records, seen = [], set()
    route_geometry = json.loads(ROUTE_GEOMETRY_PATH.read_text(encoding='utf-8'))
    route_polylines = prepare_routes(route_geometry['fire_route_geometries'])
    for capture_path in sorted(CAPTURE_DIR.glob('capture_*.json')):
        capture = json.loads(capture_path.read_text(encoding='utf-8'))
        for forecast in capture.get('forecasts', []):
            valid_text = forecast.get('forecast_valid_utc')
            if not valid_text:
                continue
            valid_at = datetime.fromisoformat(valid_text.replace('Z', '+00:00')).astimezone(timezone.utc)
            window_start = valid_at
            window_end = valid_at + timedelta(hours=24)
            observed_dates = []
            current_day = window_start.date()
            while current_day < window_end.date() or (current_day == window_end.date() and window_end.time() != time.min):
                observed_dates.append(current_day)
                current_day += timedelta(days=1)
            identity = (forecast.get('horizon_file'), forecast.get('forecast_run_utc'), valid_text, forecast.get('sha256'))
            if identity in seen:
                continue
            seen.add(identity)
            issue = parse_creation_date(forecast['creation_date'])
            observations = []
            for observed_day in observed_dates:
                status, manifest, daily_path = completion_status(observed_day)
                observations.append({
                    'observation_date_utc': observed_day.isoformat(),
                    'status': status,
                    'file': daily_path.name if daily_path else None,
                    'manifest': manifest,
                })
            daily_paths = [
                DAILY_DIR / f"focos_diario_{observed_day:%Y%m%d}.csv"
                for observed_day in observed_dates
            ]
            status = (
                'daily_files_matured_by_http_timestamp'
                if observations and all(item['status'] == 'daily_file_matured_by_http_timestamp' for item in observations)
                else next((item['status'] for item in observations if item['status'] != 'daily_file_matured_by_http_timestamp'), 'pending_observation')
            )
            if issue >= valid_at:
                status = 'invalid_issue_time_after_valid_time'
            hits = read_detections(daily_paths, route_polylines, window_start, window_end) if status == 'daily_files_matured_by_http_timestamp' else {}
            routes = []
            for route in forecast['routes']:
                all_nearby = hits.get(route['name'], [])
                nearby = all_nearby
                routes.append({
                    'name': route['name'],
                    'risk_point': route.get('sample', {}).get('point', {}).get('value'),
                    'risk_radius_10km': route.get('sample', {}).get('radius_10km'),
                    'later_detection_count_within_10km': len(nearby),
                    'later_detection_sensors': sorted({hit['sensor'] for hit in nearby if hit['sensor']}),
                    'nearest_later_detection_km': min((hit['distance_km'] for hit in nearby), default=None),
                    'detections': nearby,
                    'detection_count_in_24h_after_validity': len(nearby),
                    'detection_sensors_in_24h_after_validity': sorted({hit['sensor'] for hit in nearby if hit['sensor']}),
                    'no_detection_interpretation': 'No INPE point listed during the 24-hour post-validity window; this is not a verified fire-free route-day.' if not nearby else None,
                })
            records.append({
                'source_capture': capture_path.name,
                'source_capture_sha256': sha256(capture_path),
                'horizon': forecast['horizon_file'],
                'forecast_run_utc': forecast.get('forecast_run_utc'),
                'forecast_sha256': forecast.get('sha256'),
                'issued_at_utc': issue.isoformat().replace('+00:00', 'Z'),
                'valid_at_utc': valid_text,
                'target_window_start_utc': window_start.isoformat().replace('+00:00', 'Z'),
                'target_window_end_utc_exclusive': window_end.isoformat().replace('+00:00', 'Z'),
                'observation_status': status,
                'observation_dates': observations,
                'routes': routes,
            })
    output = output or DEFAULT_OUTPUT
    result = {
        'experiment_id': 'prospective-inpe-risk-forecast-vs-subsequent-active-fire-detections',
        'meaning': 'Prospective index-to-detection audit. The index is danger, not ignition probability; outcome points are active-fire observations, not verified ignitions.',
        'protocol': {
            'source_observation': 'INPE daily South America active-fire CSV, all listed sensors, country Argentina',
            'issue_time': 'GeoTIFF creation_date embedded in the captured forecast',
            'target_window': '[forecast_valid_utc, forecast_valid_utc + 24 hours), UTC; detections before validity are excluded',
            'spatial_unit': f'complete trail polyline within {RADIUS_KM} km; local planar point-to-segment distance',
            'route_geometry_sha256': sha256(ROUTE_GEOMETRY_PATH),
            'incomplete_observations': 'Pending; never converted to negative',
            'matured_observation_heuristic': f'For every UTC date touched by the target window, HTTP Last-Modified >= following date {COMPLETE_AFTER_UTC_HOUR:02d}:00 UTC',
            'metrics': 'No precision/recall is computed. Absence of a listed point is not a verified no-fire outcome.',
        },
        'forecasts': records,
        'counts': dict(Counter(record['observation_status'] for record in records)),
        'limitations': [
            'A satellite point can represent an existing fire first detected after forecast validity, not a new ignition after validity.',
            'The daily CSV has no per-route observation mask; no listed point cannot prove absence of fire.',
            'Fire detections are evaluated against full trail lines, while the danger index values are still sampled at fixed route-sector centers.',
            'Many sensors and points may refer to one fire; detections are not independent fire episodes.',
            'Risk index values are not calibrated probabilities.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': output.relative_to(ROOT).as_posix(), 'forecast_records': len(records), 'counts': result['counts']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.output)
