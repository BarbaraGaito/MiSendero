"""External positive-event check: frozen GOES-16 one-hour model vs INPE 2025.

INPE reference-satellite detections are independent positive observations. This
does not estimate precision because the archive has no verified route-day
negatives or per-scan observability mask.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import io
import json
import math
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np

from environmental_sources import PUBLIC, ROOT, sha256, utc
from fire_sources import PRIVATE
import train_fire_hourly as hourly


EXPERIMENT = 'fire-goes16-2025-q1'
PROTOCOL = PUBLIC / f'{EXPERIMENT}-protocol.json'
INPE_ARCHIVE = PUBLIC / 'private/inpe-ams-satellite-reference/focos_ams_ref_2025.zip'
MODEL_DIR = PRIVATE / f'{EXPERIMENT}-models'
ARRAY_CACHE = PRIVATE / f'{EXPERIMENT}-independent-inpe-test-arrays.npz'
TRAINING_REPORT = ROOT / f'docs/environmental-models-2026-10-22/{EXPERIMENT}-training-report.json'
OUT = ROOT / 'docs/environmental-models-2026-10-22/fire-goes16-inpe-independent-route-event-test-2025q1.json'
HORIZONS = (1, 2, 3, 6, 12)
THRESHOLD = 0.5
ROUTE_RADIUS_KM = 10.0
POINT_RADIUS_KM = 5.0
MAX_SCAN_OFFSET_MINUTES = 30


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180
    dlat, dlon = (lat2 - lat1) * rad, (lon2 - lon1) * rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def read_inpe_route_days(regions: list[dict], start: date, end: date) -> list[dict]:
    grouped = defaultdict(list)
    with zipfile.ZipFile(INPE_ARCHIVE) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith('.csv')]
        if len(csv_names) != 1:
            raise ValueError(f'Expected one annual INPE CSV; found {csv_names}')
        with archive.open(csv_names[0]) as raw:
            rows = csv.DictReader(io.TextIOWrapper(raw, encoding='latin1', newline=''))
            required = {'foco_id', 'lat', 'lon', 'data_pas', 'pais'}
            if not required.issubset(rows.fieldnames or []):
                raise ValueError(f'Unexpected INPE schema: {rows.fieldnames}')
            for row in rows:
                if row.get('pais', '').strip().casefold() != 'argentina':
                    continue
                observed = datetime.strptime(row['data_pas'].strip(), '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                if not start <= observed.date() < end:
                    continue
                lat, lon = float(row['lat']), float(row['lon'])
                for region in regions:
                    distance = haversine_km(lat, lon, float(region['latitude']), float(region['longitude']))
                    if distance <= ROUTE_RADIUS_KM:
                        grouped[(region['name'], observed.date())].append({
                            'detection_id': row['foco_id'],
                            'observed_at_utc': observed,
                            'latitude': lat,
                            'longitude': lon,
                            'distance_to_route_center_km': distance,
                        })
    route_days = []
    for (region, observed_day), detections in sorted(grouped.items()):
        # Use a fixed, model-independent representative point: the detection
        # closest to the route center, breaking ties by timestamp and ID.
        selected = min(detections, key=lambda item: (item['distance_to_route_center_km'], item['observed_at_utc'], item['detection_id']))
        route_days.append({
            'route_sector': region,
            'target_day_utc': observed_day.isoformat(),
            'detection_records_in_10km': len(detections),
            'representative_detection': selected,
        })
    return route_days


def load_frozen_model_data():
    if ARRAY_CACHE.is_file():
        with np.load(ARRAY_CACHE, allow_pickle=False) as cached:
            times = [str(value) for value in cached['times']]
            created = [utc(str(value)) for value in cached['created']]
            matrix = cached['matrix']
            coordinates = cached['coordinates']
            regions = [str(value) for value in cached['regions']]
        return times, created, matrix, coordinates, regions
    hourly.EXPERIMENT = EXPERIMENT
    hourly.OBS = PRIVATE / f'{EXPERIMENT}-observations.csv.gz'
    hourly.AVAILABILITY = PRIVATE / f'{EXPERIMENT}-availability-by-scan.csv'
    times, created, matrix, coordinates, regions = hourly.load_arrays()
    np.savez_compressed(
        ARRAY_CACHE,
        times=np.asarray(times, dtype='U40'),
        created=np.asarray([value.isoformat() for value in created], dtype='U40'),
        matrix=matrix,
        coordinates=coordinates,
        regions=np.asarray(regions, dtype='U100'),
    )
    return times, created, matrix, coordinates, regions


def nearest_index(values, target, start=0, end=None):
    end = len(values) if end is None else end
    index = bisect.bisect_left(values, target, lo=start, hi=end)
    candidates = [candidate for candidate in (index - 1, index) if start <= candidate < end]
    return min(candidates, key=lambda candidate: abs((values[candidate] - target).total_seconds()), default=None)


def target_for_issue(issue: int, created: list[datetime], horizon_hours: int) -> int | None:
    wanted = created[issue] + timedelta(hours=horizon_hours)
    right = bisect.bisect_left(created, wanted, lo=issue + 1)
    candidates = [candidate for candidate in (right - 1, right) if issue < candidate < len(created)]
    target = min(candidates, key=lambda candidate: abs((created[candidate] - wanted).total_seconds()), default=None)
    if target is None or abs((created[target] - wanted).total_seconds()) > 15 * 60:
        return None
    return target


def score_route_day(event: dict, times, created, matrix, coordinates, regions, models: dict[int, object]) -> dict:
    observed = event['representative_detection']
    detected_at = observed['observed_at_utc']
    target_index = nearest_index(times, detected_at)
    if target_index is None:
        return {'status': 'no_nearby_goes_scan'}
    target_scan = times[target_index]
    scan_offset = abs((target_scan - detected_at).total_seconds()) / 60
    if scan_offset > MAX_SCAN_OFFSET_MINUTES:
        return {'status': 'no_scan_within_30_minutes', 'nearest_scan_start_utc': target_scan.isoformat(), 'scan_offset_minutes': round(scan_offset, 2)}

    route_name = event['route_sector']
    region_mask = np.asarray([region == route_name for region in regions], dtype=bool)
    center = next(route for route in json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions'] if route['name'] == route_name)
    route_distance = np.asarray([haversine_km(center['latitude'], center['longitude'], lat, lon) for lat, lon in coordinates])
    point_distance = np.asarray([haversine_km(observed['latitude'], observed['longitude'], lat, lon) for lat, lon in coordinates])
    route_area = region_mask & (route_distance <= ROUTE_RADIUS_KM)
    point_area = region_mask & (point_distance <= POINT_RADIUS_KM)
    target_labels = matrix[target_index]
    target_label_counts = {
        'route_center_10km': {
            'valid_positive_GOES_pixels': int(np.sum(target_labels[route_area] == 1)),
            'valid_negative_GOES_pixels': int(np.sum(target_labels[route_area] == 0)),
            'unknown_GOES_pixels': int(np.sum(target_labels[route_area] < 0)),
        },
        'INPE_point_5km': {
            'valid_positive_GOES_pixels': int(np.sum(target_labels[point_area] == 1)),
            'valid_negative_GOES_pixels': int(np.sum(target_labels[point_area] == 0)),
            'unknown_GOES_pixels': int(np.sum(target_labels[point_area] < 0)),
        },
    }
    horizon_results = {}
    for horizon in HORIZONS:
        issue_candidates = [i for i in range(max(0, target_index - horizon - 3), target_index)
                            if target_for_issue(i, created, horizon) == target_index]
        if not issue_candidates:
            horizon_results[str(horizon)] = {'status': f'no_valid_{horizon}h_issue_pair'}
            continue
        issue = min(issue_candidates, key=lambda i: abs((created[target_index] - created[i]).total_seconds() - horizon * 3600))
        features, usable = hourly.issue_features(issue, created, matrix, coordinates)
        route_pixels = np.flatnonzero(region_mask & (route_distance <= ROUTE_RADIUS_KM) & usable)
        point_pixels = np.flatnonzero(region_mask & (point_distance <= POINT_RADIUS_KM) & usable)
        if not len(route_pixels):
            horizon_results[str(horizon)] = {'status': 'no_usable_goes_pixels_in_route_buffer'}
            continue
        scores = np.full(len(coordinates), np.nan, dtype=np.float32)
        scores[usable] = models[horizon].predict_proba(features[usable])[:, 1].astype(np.float32)
        persistence = (features[:, 6] >= 0.5) & usable
        point_max = float(np.max(scores[point_pixels])) if len(point_pixels) else None
        route_max = float(np.max(scores[route_pixels]))
        horizon_results[str(horizon)] = {
            'status': 'scored',
            'issue_product_created_at_utc': created[issue].isoformat(),
            'target_product_created_at_utc': created[target_index].isoformat(),
            'route_pixels_with_usable_inputs_within_10km': int(len(route_pixels)),
            'pixels_with_usable_inputs_within_5km_of_detection': int(len(point_pixels)),
            'max_model_score_within_5km_of_detection': point_max,
            'model_alert_within_5km_of_detection_at_fixed_0_5': bool(point_max is not None and point_max >= THRESHOLD),
            'max_model_score_within_10km_of_route_center': route_max,
            'model_alert_within_10km_of_route_center_at_fixed_0_5': bool(route_max >= THRESHOLD),
            'persistence_alert_within_10km_of_route_center': bool(np.any(persistence[route_pixels])),
            'threshold_origin': 'Fixed diagnostic threshold 0.5 used in frozen GOES test reports; it is not calibrated as a probability.',
        }
    return {
        'status': 'scored',
        'target_scan_start_utc': target_scan.isoformat(),
        'independent_detection_at_utc': detected_at.isoformat(),
        'scan_offset_minutes': round(scan_offset, 2),
        'GOES_target_label_counts_at_nearest_scan': target_label_counts,
        'horizons': horizon_results,
    }


def main(output: Path | None = None) -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    start = date.fromisoformat(protocol['start'][:10])
    end = date.fromisoformat(protocol['end_exclusive'][:10])
    test_start = date(2025, 3, 1)
    model_report = json.loads(TRAINING_REPORT.read_text(encoding='utf-8'))
    test_end = date.fromisoformat(model_report.get('temporal_split', {}).get('test_end_exclusive', protocol['end_exclusive'])[:10])
    routes = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    events = read_inpe_route_days(routes, max(start, test_start), min(end, test_end))
    times, created, matrix, coordinates, region_names = load_frozen_model_data()
    scan_times = [utc(stamp) for stamp in times]
    model_paths = {horizon: MODEL_DIR / f'logistic-{horizon}h.joblib' for horizon in HORIZONS}
    models = {horizon: joblib.load(path) for horizon, path in model_paths.items()}
    evaluated = []
    for event in events:
        scored = score_route_day(event, scan_times, created, matrix, coordinates, region_names, models)
        observed = event['representative_detection']
        evaluated.append({
            'route_sector': event['route_sector'],
            'target_day_utc': event['target_day_utc'],
            'independent_detection_records_within_10km': event['detection_records_in_10km'],
            'representative_detection': {
                key: (value.isoformat().replace('+00:00', 'Z') if isinstance(value, datetime) else value)
                for key, value in observed.items()
            },
            'goes_model': scored,
        })
    scored_events = [event for event in evaluated if event['goes_model'].get('status') == 'scored']
    result = {
        'experiment_id': 'frozen-goes16-1-to-12h-models-vs-independent-inpe-reference-detections-2025-q1-test',
        'interpretation': 'External positive-event coincidence only. It does not estimate precision, calibrated probability, or ignition lead time.',
        'protocol': {
            'model': EXPERIMENT,
            'frozen_test_period': [test_start.isoformat(), test_end.isoformat()],
            'independent_target': 'INPE reference-satellite hotspot within 10 km of a fixed route-sector center, grouped to one route-day; representative point is nearest to route center before looking at scores.',
            'model_horizons_hours': HORIZONS,
            'scan_matching': 'Each horizon is paired to a GOES scan start nearest the INPE detection time, with a 30-minute maximum offset.',
            'alert_threshold': THRESHOLD,
            'spatial_scoring': {'route_center_radius_km': ROUTE_RADIUS_KM, 'independent_point_radius_km': POINT_RADIUS_KM},
            'event_unit': 'unique route-sector day; repeat satellite detections on that route/date are not counted as separate events.',
        },
        'sources': {
            'inpe_archive_sha256': sha256(INPE_ARCHIVE),
            'goes_observations_sha256': sha256(hourly.OBS),
            'goes_availability_sha256': sha256(hourly.AVAILABILITY),
            'model_sha256_by_horizon': {str(horizon): sha256(path) for horizon, path in model_paths.items()},
            'training_report_sha256': sha256(TRAINING_REPORT),
            'protocol_sha256': sha256(PROTOCOL),
        },
        'counts': {
            'independent_inpe_route_days_in_test_period': len(events),
            'events_with_goes_model_coverage': len(scored_events),
            'model_results_by_horizon': {
                str(horizon): {
                    'scored_events': sum(event['goes_model'].get('horizons', {}).get(str(horizon), {}).get('status') == 'scored' for event in scored_events),
                    'events_alerted_near_inpe_point_at_0_5': sum(event['goes_model'].get('horizons', {}).get(str(horizon), {}).get('model_alert_within_5km_of_detection_at_fixed_0_5', False) for event in scored_events),
                    'events_alerted_in_route_buffer_at_0_5': sum(event['goes_model'].get('horizons', {}).get(str(horizon), {}).get('model_alert_within_10km_of_route_center_at_fixed_0_5', False) for event in scored_events),
                    'events_with_persistence_in_route_buffer': sum(event['goes_model'].get('horizons', {}).get(str(horizon), {}).get('persistence_alert_within_10km_of_route_center', False) for event in scored_events),
                }
                for horizon in HORIZONS
            },
        },
        'events': evaluated,
        'limitations': [
            'Only positive satellite observations are available in the INPE annual archive; no verified negative route-days means no event precision can be calculated.',
            'The test subset may contain very few independent route-days; report counts rather than a generalizable performance estimate.',
            'INPE records an active-fire point, not necessarily a wildfire or a new ignition; detection time is not exact ignition time.',
            'INPE location, GOES pixel size, route-center radius, and scan-time mismatch introduce spatial and temporal uncertainty.',
            'The GOES model predicts a future GOES fire mask, not fire ignition, spread, or route safety; class-weighted score 0.5 is not 50% probability.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    output = output or OUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': output.relative_to(ROOT).as_posix(), 'counts': result['counts'], 'events': evaluated}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.output)
