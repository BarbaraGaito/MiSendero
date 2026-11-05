"""Sensitivity audit of frozen WRF scores around SNMF 2023 route events."""
import csv
import gzip
import json
import math
from collections import defaultdict
from datetime import date

from environmental_sources import PUBLIC, ROOT, sha256
from fire_sources import PRIVATE, REPORT_DIR

SNMF = REPORT_DIR / 'snmf-2023-daily-occurrence-events.json'
PREDICTIONS = PRIVATE / 'smn-wrf-modis-test-predictions.csv.gz'
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
GEOGRAPHY = PUBLIC / 'geography.json'
OUT = REPORT_DIR / 'fire-smn-wrf-snmf-2023-radius-sensitivity.json'
TEST_START, TEST_END = date(2023, 7, 1), date(2024, 1, 1)
EVENT_CENTER_RADIUS_KM = 10.0
ROUTE_RADII_KM = (10.0, 20.0)
DIAGNOSTIC_THRESHOLD = 0.5
OFFICIAL_NO_REPORT_DAY = '2023-12-20'
OFFICIAL_ZERO_MONTH = '2023-12'
OFFICIAL_ZERO_MONTH_ROUTES = (
    'Sendero Che Roga - Mburucuyá',
    'Cerro Ventana - Hueco de la Ventana',
)


def distance_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def main():
    events_doc = json.loads(SNMF.read_text(encoding='utf-8'))
    geography = json.loads(GEOGRAPHY.read_text(encoding='utf-8'))['fire_regions']
    centers = {row['name']: (float(row['latitude']), float(row['longitude'])) for row in geography}
    events = []
    for row in events_doc['deduplicated_events']:
        try:
            day = date.fromisoformat(row['reported_start_date'])
            lat, lon = float(row['latitude']), float(row['longitude'])
        except (KeyError, TypeError, ValueError):
            continue
        if TEST_START <= day < TEST_END:
            events.append({'date': day.isoformat(), 'name': row.get('incident_name'),
                'province': row.get('province'), 'latitude': lat, 'longitude': lon,
                'report_date': row.get('report_date'), 'status': row.get('status')})

    event_route_days = {radius: defaultdict(list) for radius in ROUTE_RADII_KM}
    for event in events:
        for route, (lat, lon) in centers.items():
            center_distance = distance_km(lat, lon, event['latitude'], event['longitude'])
            for radius in ROUTE_RADII_KM:
                if center_distance <= radius:
                    item = dict(event, route_center_distance_km=round(center_distance, 3))
                    event_route_days[radius][(route, event['date'])].append(item)

    coords = {}
    with gzip.open(OBSERVATIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            pixel_id = f"{row['tile']}:{row['row']}:{row['col']}"
            coords[(row['region'], pixel_id)] = (float(row['latitude']), float(row['longitude']))
    predictions = defaultdict(list)
    with gzip.open(PREDICTIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            key = (row['region'], row['target_date'])
            point = coords.get((row['region'], row['pixel_id']))
            if point is not None:
                predictions[key].append({'pixel_id': row['pixel_id'], 'lat': point[0], 'lon': point[1],
                    'score': float(row['risk_score']), 'label': int(row['label'])})

    radius_results = {}
    for radius in ROUTE_RADII_KM:
        route_days = []
        for (route, day), day_events in sorted(event_route_days[radius].items()):
            rows = predictions.get((route, day), [])
            local_rows = []
            for prediction in rows:
                local_distance = min(distance_km(prediction['lat'], prediction['lon'], event['latitude'], event['longitude'])
                    for event in day_events)
                if local_distance <= EVENT_CENTER_RADIUS_KM:
                    local_rows.append(dict(prediction, event_distance_km=round(local_distance, 3)))
            max_score = max((row['score'] for row in local_rows), default=None)
            route_days.append({'route_sector': route, 'target_date': day,
                'incidents': [{'name': e['name'], 'province': e['province'],
                    'route_center_distance_km': e['route_center_distance_km'], 'report_date': e['report_date']}
                    for e in day_events],
                'route_model_prediction_rows': len(rows),
                'event_local_prediction_rows_within_10km': len(local_rows),
                'maximum_event_local_score': max_score,
                'alert_at_unselected_0_5': max_score is not None and max_score >= DIAGNOSTIC_THRESHOLD})
        covered = [row for row in route_days if row['event_local_prediction_rows_within_10km']]
        alerts = sum(row['alert_at_unselected_0_5'] for row in route_days)
        covered_alerts = sum(row['alert_at_unselected_0_5'] for row in covered)
        radius_results[str(int(radius))] = {'unique_route_days_with_reported_event': len(route_days),
            'route_days_with_model_rows': sum(bool(row['route_model_prediction_rows']) for row in route_days),
            'route_days_with_event_local_model_coverage': len(covered),
            'alerted_route_days_at_diagnostic_threshold': alerts,
            'alerted_among_event_local_coverage': covered_alerts,
            'descriptive_event_coincidence_sensitivity_among_covered': covered_alerts / len(covered) if covered else None,
            'route_days': route_days}

    no_report_keys = [(route, day) for route, day in predictions if day == OFFICIAL_NO_REPORT_DAY]
    no_report_rows = [{'route_sector': route, 'target_date': day,
        'prediction_rows': len(predictions[(route, day)]),
        'maximum_score': max(row['score'] for row in predictions[(route, day)]),
        'modis_positive_pixels': sum(row['label'] for row in predictions[(route, day)]),
        'alert_at_unselected_0_5': max(row['score'] for row in predictions[(route, day)]) >= DIAGNOSTIC_THRESHOLD}
        for route, day in sorted(no_report_keys)]
    zero_month_rows = []
    for route in OFFICIAL_ZERO_MONTH_ROUTES:
        route_keys = [(name, day) for name, day in predictions if name == route and day.startswith(OFFICIAL_ZERO_MONTH)]
        for name, day in sorted(route_keys):
            values = predictions[(name, day)]
            zero_month_rows.append({'route_sector': name, 'target_date': day,
                'prediction_rows': len(values), 'maximum_score': max(row['score'] for row in values),
                'modis_positive_pixels': sum(row['label'] for row in values),
                'alert_at_unselected_0_5': max(row['score'] for row in values) >= DIAGNOSTIC_THRESHOLD})
    official_negative_proxies = {
        'single_national_no_report_day': {'date': OFFICIAL_NO_REPORT_DAY,
            'source_url': 'https://www.argentina.gob.ar/sites/default/files/2024/01/reporte_diario_20-12-2023.pdf',
            'route_days_with_model_coverage': len(no_report_rows),
            'route_days_alerted': sum(row['alert_at_unselected_0_5'] for row in no_report_rows),
            'positive_modis_route_days': sum(row['modis_positive_pixels'] > 0 for row in no_report_rows),
            'route_days': no_report_rows,
            'meaning': 'No fire was listed in the national report; not a verified physical-fire negative.'},
        'zero_reported_fire_provinces_for_month': {'month': OFFICIAL_ZERO_MONTH,
            'source_url': 'https://www.argentina.gob.ar/sites/default/files/2024/01/informe_ocurrencia_diciembre2023.pdf',
            'routes': list(OFFICIAL_ZERO_MONTH_ROUTES),
            'route_days_with_model_coverage': len(zero_month_rows),
            'route_days_alerted': sum(row['alert_at_unselected_0_5'] for row in zero_month_rows),
            'positive_modis_route_days': len({(row['route_sector'], row['target_date']) for row in zero_month_rows if row['modis_positive_pixels'] > 0}),
            'route_days': zero_month_rows,
            'meaning': 'The monthly report lists zero incidents in those provinces; not a verified physical-fire negative.'}}

    result = {'experiment_id': 'smn-wrf-snmf-2023-event-radius-sensitivity',
        'meaning': 'Secondary spatial sensitivity audit of reported positive event days only; not precision.',
        'inputs': {'snmf_events_sha256': sha256(SNMF), 'wrf_test_predictions_sha256': sha256(PREDICTIONS),
            'modis_coordinate_source_sha256': sha256(OBSERVATIONS), 'geography_sha256': sha256(GEOGRAPHY)},
        'protocol': {'test_period': [TEST_START.isoformat(), TEST_END.isoformat()],
            'route_center_radii_km': list(ROUTE_RADII_KM),
            'event_local_pixel_match_radius_km': EVENT_CENTER_RADIUS_KM,
            'threshold': DIAGNOSTIC_THRESHOLD,
            'threshold_status': 'Fixed diagnostic; validation selected no threshold meeting the precision gate.',
            'valid_time': '15 UTC on reported start date; 27 hours after WRF issue at 12 UTC the previous day.'},
        'results_by_route_radius': radius_results,
        'official_negative_proxy_checks': official_negative_proxies,
        'limitations': [
            'SNMF reports contain reported incidents but do not provide an exhaustive fire-free route-day cohort.',
            'The 20 km route-center result is secondary and exploratory; the primary predefined radius remains 10 km.',
            'A date-only start cannot verify that a +27 h forecast preceded ignition; it may be after the fire started.',
            'The 0.5 score is unselected and uncalibrated; detections near events are coincidence/sensitivity only.',
            'No true-negative universe is present, so precision and specificity cannot be calculated.'
        ], 'synthetic_observations': 0, 'deployment_approved': False}
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    summary = {r: {k: v for k, v in block.items() if k != 'route_days'}
        for r, block in radius_results.items()}
    print(json.dumps({'output': OUT.relative_to(ROOT).as_posix(), 'results': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
