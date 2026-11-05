"""Match frozen MODIS/XGBoost test predictions to official SNMF event snapshots."""
from datetime import date
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

from environmental_sources import ROOT, sha256
from fire_sources import PRIVATE

EVENTS = ROOT / 'docs/environmental-models-2026-10-22/snmf-2023-daily-occurrence-events.json'
PREDICTIONS = PRIVATE / 'fire-temporal_test-predictions.csv.gz'
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
PROTOCOL = ROOT / 'docs/environmental-models-2026-10-22/fire-snmf-event-protocol.json'
OUT = ROOT / 'docs/environmental-models-2026-10-22/fire-model-snmf-snapshot-audit.json'
THRESHOLD = 0.5
RADIUS_KM = 10
ACTIVE_STATES = {'ACTIVO', 'CONTENIDO', 'CONTROLADO'}
WATCH_STATE = 'GUARDIA DE CENIZAS'


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(a)))


def load_coordinates():
    coordinates = {}
    with gzip.open(OBSERVATIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            pixel_id = f"{row['tile']}:{row['row']}:{row['col']}"
            coordinates.setdefault((row['region'], pixel_id),
                (float(row['latitude']), float(row['longitude'])))
    return coordinates


def load_prediction_dates(coordinates):
    dates = {}
    with gzip.open(PREDICTIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            coord = coordinates.get((row['region'], row['pixel_id']))
            if coord is None:
                continue
            target = date.fromisoformat(row['target_at'][:10])
            dates.setdefault(target, []).append({'latitude': coord[0], 'longitude': coord[1],
                'region': row['region'], 'pixel_id': row['pixel_id'],
                'observed': int(row['observed']), 'score': float(row['xgboost'])})
    return dates


def first_report_per_incident(event_report, allowed_states):
    unique = {}
    for row in event_report['deduplicated_events']:
        if row['status'] not in allowed_states or row['latitude'] is None or row['longitude'] is None:
            continue
        key = (row['province'], row['incident_name'], row['reported_start_date'],
               round(row['latitude'], 3), round(row['longitude'], 3))
        current = unique.get(key)
        if current is None or row['report_date'] < current['report_date']:
            unique[key] = row
    return list(unique.values())


def main():
    protocol = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    # This audit keeps the threshold and spatial tolerance already fixed in the
    # incident protocol; it does not tune them on these event snapshots.
    threshold = float(protocol['threshold'])
    radius = float(protocol['primary_spatial_rule']['radius_km'])
    coordinates = load_coordinates()
    by_date = load_prediction_dates(coordinates)
    event_report = json.loads(EVENTS.read_text(encoding='utf-8'))
    extraction = event_report['extraction']
    incidents = first_report_per_incident(event_report, ACTIVE_STATES)
    evaluated, not_covered = [], []
    active_report_snapshots = [row for row in event_report['snapshots']
        if row['status'] in ACTIVE_STATES | {WATCH_STATE} and row['latitude'] is not None and row['longitude'] is not None]

    for event in incidents:
        report_day = date.fromisoformat(event['report_date'])
        predictions = by_date.get(report_day, [])
        within = []
        for pred in predictions:
            distance = haversine_km(event['latitude'], event['longitude'], pred['latitude'], pred['longitude'])
            if distance <= radius:
                within.append((distance, pred))
        record = {'name': event['incident_name'], 'province': event['province'],
            'reported_start_date': event['reported_start_date'], 'first_archived_snapshot_date': event['report_date'],
            'status': event['status'], 'latitude': event['latitude'], 'longitude': event['longitude'],
            'valid_test_pixels_within_radius': len(within),
            'xgboost_alert_pixel_days_within_radius': sum(pred['score'] >= threshold for _, pred in within),
            'maximum_xgboost_score_within_radius': max((pred['score'] for _, pred in within), default=None),
            'nearest_sample_pixel_km': round(min((distance for distance, _ in within), default=math.inf), 3) if within else None}
        if within:
            record['detected_at_threshold'] = record['xgboost_alert_pixel_days_within_radius'] > 0
            evaluated.append(record)
        else:
            not_covered.append(record)

    snapshot_results = []
    for event in active_report_snapshots:
        day = date.fromisoformat(event['report_date'])
        pixels = []
        for pred in by_date.get(day, []):
            distance = haversine_km(event['latitude'], event['longitude'], pred['latitude'], pred['longitude'])
            if distance <= radius:
                pixels.append((distance, pred))
        if pixels:
            snapshot_results.append({'name': event['incident_name'], 'province': event['province'],
                'report_date': event['report_date'], 'reported_start_date': event['reported_start_date'],
                'status': event['status'], 'valid_test_pixels_within_radius': len(pixels),
                'alert_pixel_days': sum(pred['score'] >= threshold for _, pred in pixels),
                'max_score': max(pred['score'] for _, pred in pixels),
                'nearest_pixel_km': round(min(distance for distance, _ in pixels), 3)})

    report = {'experiment_id': 'mod14a1-xgboost-heldout-test-vs-official-snmf-snapshots-2023',
        'sources': {'event_extraction_sha256': sha256(EVENTS), 'prediction_sha256': sha256(PREDICTIONS),
            'observation_coordinate_sha256': sha256(OBSERVATIONS), 'protocol_sha256': sha256(PROTOCOL)},
        'protocol': {'official_snapshot_date_is_target_date': True, 'alert_threshold': threshold,
            'maximum_distance_km': radius, 'incident_statuses_counted_as_active': sorted(ACTIVE_STATES),
            'guardia_de_cenizas': 'reported separately; not counted as a confirmed active-fire positive',
            'unit': 'one incident at its first archived active/controlled snapshot; repeated daily snapshots are reported separately',
            'model_target': 'MOD14A1 nominal/high-confidence active-fire label in same pixel on next UTC day'},
        'official_report_snapshot_rows_with_active_or_watch_status_and_coordinates': len(active_report_snapshots),
        'unique_incidents_with_first_report_snapshot_in_test_and_valid_pixel_coverage': len(evaluated),
        'unique_incidents_without_valid_pixel_coverage': len(not_covered),
        'unique_incidents_with_any_xgboost_alert': sum(event['detected_at_threshold'] for event in evaluated),
        'unique_incident_event_sensitivity_on_covered_subset': (sum(event['detected_at_threshold'] for event in evaluated) / len(evaluated) if evaluated else None),
        'report_snapshot_matches_with_pixel_coverage': len(snapshot_results),
        'report_snapshot_matches_with_alert': sum(row['alert_pixel_days'] > 0 for row in snapshot_results),
        'incidents': evaluated, 'incidents_not_covered': not_covered,
        'snapshot_results': snapshot_results,
        'limitations': [f"{extraction['reports_used']} archived reports were found at the checked public paths for Jul-Dec 2023; {extraction['missing_coordinate_snapshot_rows']} report rows lack usable coordinates and are excluded from spatial matching.",
            'Dates without archived PDFs are unobserved, not negative.',
            'The official archive contains jurisdiction-reported incidents and is not asserted exhaustive.',
            'The result estimates coincidence/sensitivity only among covered, reported incidents; there are no verified negative alert events, so precision cannot be calculated.',
            'The threshold and 10 km radius were fixed in the existing protocol but prior analysis had already seen this model test; this is exploratory external corroboration, not a pristine prospective test.',
            'A 10 km circle around an official coordinate does not represent the full trail geometry.']}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('official_report_snapshot_rows_with_active_or_watch_status_and_coordinates',
        'unique_incidents_with_first_report_snapshot_in_test_and_valid_pixel_coverage',
        'unique_incidents_without_valid_pixel_coverage', 'unique_incidents_with_any_xgboost_alert',
        'unique_incident_event_sensitivity_on_covered_subset', 'report_snapshot_matches_with_pixel_coverage',
        'report_snapshot_matches_with_alert')}, indent=2))
    print('detected incidents:', json.dumps([event for event in evaluated if event['detected_at_threshold']],
        ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
