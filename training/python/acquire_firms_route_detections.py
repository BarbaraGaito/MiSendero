#!/usr/bin/env python3
"""Acquire NASA FIRMS standard active-fire detections near Argentine trails.

Research data only. A free FIRMS MAP_KEY must be supplied through the
NASA_FIRMS_MAP_KEY environment variable. Hotspot detections are positive
evidence only: an empty result is never treated as a no-fire observation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
OUT_DIR = ROOT / 'training/data/environmental/private/firms-route-detections'
API = 'https://firms.modaps.eosdis.nasa.gov/api/area/csv'
AVAILABILITY_API = 'https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv'
STANDARD_SENSORS = ('VIIRS_SNPP_SP', 'VIIRS_NOAA20_SP', 'VIIRS_NOAA21_SP')
NRT_SENSORS = ('VIIRS_SNPP_NRT', 'VIIRS_NOAA20_NRT', 'VIIRS_NOAA21_NRT')
SENSORS = STANDARD_SENSORS + NRT_SENSORS
KM_PER_DEG_LAT = 110.574


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def date_chunks(start: date, end: date, width: int = 5):
    current = start
    while current <= end:
        last = min(end, current + timedelta(days=width - 1))
        yield current, last
        current = last + timedelta(days=1)


def route_coordinates(route: dict) -> list[tuple[float, float]]:
    """Return (latitude, longitude) coordinate pairs from supported schemas."""
    values = route.get('route_coordinates') or route.get('coordinates')
    if not values:
        raise ValueError(f"No route coordinates for {route.get('name', 'unnamed route')}")
    if isinstance(values[0], dict):
        return [(float(point['latitude']), float(point['longitude'])) for point in values]
    # The private route geometry used by MiSendero stores [latitude, longitude].
    return [(float(point[0]), float(point[1])) for point in values]


def padded_bounds(routes: list[dict], buffer_km: float) -> tuple[float, float, float, float]:
    points = [point for route in routes for point in route_coordinates(route)]
    lat_padding = buffer_km / KM_PER_DEG_LAT
    max_abs_lat = max(abs(lat) for lat, _ in points)
    lon_padding = buffer_km / (111.320 * max(math.cos(math.radians(max_abs_lat)), 0.1))
    west = max(-180.0, min(lon for _, lon in points) - lon_padding)
    south = max(-90.0, min(lat for lat, _ in points) - lat_padding)
    east = min(180.0, max(lon for _, lon in points) + lon_padding)
    north = min(90.0, max(lat for lat, _ in points) + lat_padding)
    return west, south, east, north


def distance_to_route_km(latitude: float, longitude: float,
                         coordinates: list[tuple[float, float]]) -> float:
    """Approximate local point-to-polyline distance in a route-centered plane."""
    lat0 = sum(lat for lat, _ in coordinates) / len(coordinates)
    lon0 = sum(lon for _, lon in coordinates) / len(coordinates)
    scale_x = 111.320 * math.cos(math.radians(lat0))
    px, py = (longitude - lon0) * scale_x, (latitude - lat0) * KM_PER_DEG_LAT
    xy = [((lon - lon0) * scale_x, (lat - lat0) * KM_PER_DEG_LAT)
          for lat, lon in coordinates]
    best = math.inf
    for (ax, ay), (bx, by) in zip(xy, xy[1:]):
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    if len(xy) == 1:
        best = math.hypot(px - xy[0][0], py - xy[0][1])
    return best


def request_csv(map_key: str, sensor: str, bounds: tuple[float, float, float, float],
                start: date, day_count: int) -> bytes:
    area = ','.join(f'{value:.5f}' for value in bounds)
    url = f'{API}/{map_key}/{sensor}/{area}/{day_count}/{start.isoformat()}'
    request = urllib.request.Request(url, headers={'User-Agent': 'MiSenderoResearch/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        # Do not leak the MAP_KEY embedded in the request URL to logs.
        raise RuntimeError(f'NASA FIRMS request failed: HTTP {error.code} for {sensor}, {start}') from None
    except urllib.error.URLError as error:
        raise RuntimeError(f'NASA FIRMS connection failed for {sensor}, {start}: {error.reason}') from None


def request_availability(map_key: str, sensors: tuple[str, ...]) -> tuple[dict, str, bytes]:
    url = f'{AVAILABILITY_API}/{map_key}/all'
    request = urllib.request.Request(url, headers={'User-Agent': 'MiSenderoResearch/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'NASA FIRMS availability request failed: HTTP {error.code}') from None
    except urllib.error.URLError as error:
        raise RuntimeError(f'NASA FIRMS availability connection failed: {error.reason}') from None
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not reader.fieldnames or not {'data_id', 'min_date', 'max_date'} <= set(reader.fieldnames):
        raise RuntimeError('NASA FIRMS returned an unexpected availability response; check the MAP_KEY.')
    ranges = {}
    for row in reader:
        if row.get('data_id') in sensors:
            ranges[row['data_id']] = (date.fromisoformat(row['min_date']), date.fromisoformat(row['max_date']))
    missing = set(sensors) - set(ranges)
    if missing:
        raise RuntimeError(f'NASA FIRMS availability response omitted requested sensors: {sorted(missing)}')
    return ranges, sha256_bytes(raw), raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, required=True,
                        help='First day, YYYY-MM-DD; standard-product archive availability varies by sensor.')
    parser.add_argument('--end', type=date.fromisoformat, required=True,
                        help='Last day, YYYY-MM-DD, inclusive.')
    parser.add_argument('--buffer-km', type=float, default=20.0,
                        help='Keep detections within this distance of a trail polyline (default: 20 km).')
    parser.add_argument('--sensor', action='append', choices=SENSORS,
                        help='Repeat to choose sensors; default is the three VIIRS standard products. NRT data are provisional and positive-only.')
    parser.add_argument('--output-dir', type=Path, default=OUT_DIR)
    parser.add_argument('--resume', action='store_true', help='Resume completed route/sensor/date queries from the output JSON.')
    parser.add_argument('--date-windows-json', type=Path, help='Optional JSON mapping route names to [start, end] date windows; use for targeted event corroboration.')
    parser.add_argument('--pause-seconds', type=float, default=0.1,
                        help='Delay between requests to limit load on the public service.')
    args = parser.parse_args()
    if args.end < args.start:
        parser.error('--end must be on or after --start')
    if args.buffer_km <= 0:
        parser.error('--buffer-km must be positive')
    map_key = os.environ.get('NASA_FIRMS_MAP_KEY')
    if not map_key:
        parser.error('Set NASA_FIRMS_MAP_KEY to the free key emailed by NASA FIRMS; do not pass it as a command-line argument.')

    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    routes = geometry['fire_route_geometries']
    sensors = tuple(args.sensor or STANDARD_SENSORS)
    query_started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    availability, availability_hash, availability_raw = request_availability(map_key, sensors)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sensor_slug = '-'.join(sensor.lower().replace('_', '-') for sensor in sensors)
    availability_path = args.output_dir / f'firms-data-availability-{sensor_slug}.csv'
    availability_path.write_bytes(availability_raw)
    raw_response_dir = args.output_dir / 'raw-responses'
    raw_response_dir.mkdir(parents=True, exist_ok=True)
    sensor_suffix = '' if sensors == STANDARD_SENSORS else '-' + '-'.join(sensor.lower().replace('_', '-') for sensor in sensors)
    path = args.output_dir / f'firms-viirs-route-detections-{args.start}-{args.end}{sensor_suffix}.json'
    detections = []
    requests = []
    if args.resume and path.exists():
        previous = json.loads(path.read_text(encoding='utf-8'))
        if previous.get('period') != [args.start.isoformat(), args.end.isoformat()] or previous.get('route_buffer_km') != args.buffer_km:
            raise ValueError('Cannot resume: period or route buffer differs from the checkpoint.')
        if previous.get('sensors') != list(sensors):
            raise ValueError('Cannot resume: selected sensors differ from the checkpoint.')
        detections = previous.get('route_detections', [])
        requests = previous.get('requests', [])
    completed = {
        (row.get('route_sector'), row.get('sensor'), row.get('requested_start_date'), row.get('requested_end_date'))
        for row in requests if row.get('status') in {'ok', 'outside_available_date_range'}
    }
    bounds_by_route = {route['name']: padded_bounds([route], args.buffer_km) for route in routes}
    date_windows = json.loads(args.date_windows_json.read_text(encoding='utf-8')) if args.date_windows_json else None
    if date_windows is not None and set(date_windows) != set(bounds_by_route):
        raise ValueError('Date-window JSON must include every route name, with an empty list where no dates apply.')
    lines_by_route = {route['name']: route_coordinates(route) for route in routes}

    def checkpoint() -> None:
        snapshot = {
            'schema_version': 1,
            'experiment_id': 'nasa-firms-viirs-route-detection-archive',
            'query_started_at_utc': query_started_at,
            'checkpointed_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            'period': [args.start.isoformat(), args.end.isoformat()],
            'sensors': list(sensors),
            'sensor_date_availability': {sensor: [first.isoformat(), last.isoformat()] for sensor, (first, last) in availability.items()},
            'availability_response_file': availability_path.resolve().relative_to(ROOT).as_posix(),
            'availability_response_sha256': availability_hash,
            'route_buffer_km': args.buffer_km,
            'query_plan': 'SNMF event date windows' if date_windows is not None else 'complete date range split into five-day blocks',
            'date_windows_sha256': sha256_bytes(args.date_windows_json.read_bytes()) if args.date_windows_json else None,
            'spatial_filter': 'Approximate local point-to-polyline distance over complete route geometries.',
            'query_bounds_wsen_by_route': {name: list(bounds) for name, bounds in bounds_by_route.items()},
            'geometry_sha256': sha256_bytes(GEOMETRY.read_bytes()),
            'requests': requests,
            'route_detections': detections,
            'interpretation': 'Positive active-fire detection candidates only. Empty responses, satellite noncoverage, cloud, and no hotspot record are unknown, never negative labels.',
            'map_key_stored': False,
            'synthetic_observations': 0,
            'deployment_approved': False,
        }
        temp_path = path.with_suffix('.json.tmp')
        temp_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        temp_path.replace(path)

    for route in routes:
        route_name = route['name']
        route_bounds = bounds_by_route[route_name]
        route_line = lines_by_route[route_name]
        route_query_count = 0
        for sensor in sensors:
            available_start, available_end = availability[sensor]
            sensor_start, sensor_end = max(args.start, available_start), min(args.end, available_end)
            if sensor_start > sensor_end:
                key = (route_name, sensor, args.start.isoformat(), args.end.isoformat())
                if key not in completed:
                    requests.append({
                        'route_sector': route_name, 'sensor': sensor,
                        'requested_start_date': args.start.isoformat(),
                        'requested_end_date': args.end.isoformat(),
                        'status': 'outside_available_date_range',
                        'available_start_date': available_start.isoformat(),
                        'available_end_date': available_end.isoformat(),
                    })
                    checkpoint()
                continue
            if date_windows is None:
                windows = list(date_chunks(sensor_start, sensor_end))
            else:
                windows = []
                for window_start_raw, window_end_raw in date_windows[route_name]:
                    window_start = max(date.fromisoformat(window_start_raw), sensor_start)
                    window_end = min(date.fromisoformat(window_end_raw), sensor_end)
                    if window_start <= window_end:
                        windows.append((window_start, window_end))
            for start, end in windows:
                key = (route_name, sensor, start.isoformat(), end.isoformat())
                if key in completed:
                    continue
                raw = request_csv(map_key, sensor, route_bounds, start, (end - start).days + 1)
                route_token = hashlib.sha256(route_name.encode('utf-8')).hexdigest()[:12]
                raw_path = raw_response_dir / f'{route_token}-{sensor}-{start}-{end}.csv'
                raw_path.write_bytes(raw)
                query = {
                    'route_sector': route_name,
                    'sensor': sensor,
                    'requested_start_date': start.isoformat(),
                    'requested_end_date': end.isoformat(),
                    'start_date': start.isoformat(),
                    'end_date': end.isoformat(),
                    'available_start_date': available_start.isoformat(),
                    'available_end_date': available_end.isoformat(),
                    'query_bounds_wsen': list(route_bounds),
                    'availability_response_sha256': availability_hash,
                    'response_sha256': sha256_bytes(raw),
                    'response_bytes': len(raw),
                    'raw_response_file': raw_path.resolve().relative_to(ROOT).as_posix(),
                    'response_rows': 0,
                    'route_matches': 0,
                    'status': 'ok',
                }
                reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
                if not reader.fieldnames or not {'latitude', 'longitude', 'acq_date'} <= set(reader.fieldnames):
                    raise RuntimeError(
                        f'NASA FIRMS returned an unexpected response for {sensor}, {start}; '
                        'check the MAP_KEY and product date availability.'
                    )
                for row in reader:
                    query['response_rows'] += 1
                    try:
                        lat, lon = float(row['latitude']), float(row['longitude'])
                    except (KeyError, TypeError, ValueError):
                        continue
                    distance = distance_to_route_km(lat, lon, route_line)
                    if distance <= args.buffer_km:
                        detection = {key: row.get(key) for key in (
                            'latitude', 'longitude', 'bright_ti4', 'bright_ti5', 'frp',
                            'confidence', 'acq_date', 'acq_time', 'satellite',
                            'instrument', 'daynight', 'version')}
                        detection.update({
                            'route_sector': route_name,
                            'distance_to_route_km': round(distance, 3),
                            'sensor_source': sensor,
                            'query_start_date': start.isoformat(),
                            'query_sha256': query['response_sha256'],
                        })
                        detections.append(detection)
                        query['route_matches'] += 1
                requests.append(query)
                completed.add(key)
                route_query_count += 1
                checkpoint()
                if args.pause_seconds:
                    time.sleep(args.pause_seconds)
        print(f'Completed {route_name}: {route_query_count} new query blocks; total detections={len(detections)}', flush=True)

    output = {
        'schema_version': 1,
        'experiment_id': 'nasa-firms-viirs-route-detection-archive',
        'query_started_at_utc': query_started_at,
        'completed_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'period': [args.start.isoformat(), args.end.isoformat()],
        'sensors': list(sensors),
        'sensor_date_availability': {
            sensor: [first.isoformat(), last.isoformat()]
            for sensor, (first, last) in availability.items()
        },
        'availability_response_file': availability_path.resolve().relative_to(ROOT).as_posix(),
        'availability_response_sha256': availability_hash,
        'route_buffer_km': args.buffer_km,
        'query_plan': 'SNMF event date windows' if date_windows is not None else 'complete date range split into five-day blocks',
        'date_windows_sha256': sha256_bytes(args.date_windows_json.read_bytes()) if args.date_windows_json else None,
        'spatial_filter': 'Approximate local point-to-polyline distance over complete route geometries.',
        'query_bounds_wsen_by_route': {name: list(bounds) for name, bounds in bounds_by_route.items()},
        'geometry_sha256': sha256_bytes(GEOMETRY.read_bytes()),
        'requests': requests,
        'route_detections': detections,
        'interpretation': 'Positive active-fire detection candidates only. Empty responses, satellite noncoverage, cloud, and no hotspot record are unknown, never negative labels.',
        'map_key_stored': False,
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': path.resolve().relative_to(ROOT.resolve()).as_posix(),
        'requests': len(requests),
        'candidate_route_detections': len(detections),
        'unique_route_incident_days': len({(row['route_sector'], row.get('acq_date')) for row in detections}),
        'map_key_stored': False,
        'negative_labels_created': 0,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
