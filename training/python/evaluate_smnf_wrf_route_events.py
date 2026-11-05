"""Audit held-out SMN WRF fire scores against SNMF-reported route events.

The weather model was trained to rank MODIS detection labels. This independent
check asks whether its frozen next-day scores coincide with officially reported
fire starts near the sampled Argentine route sectors. It is event sensitivity,
not precision: SNMF daily reports are not exhaustive negatives.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

from environmental_sources import PUBLIC, ROOT, sha256

PRIVATE = PUBLIC / 'private'
PREDICTIONS = PRIVATE / 'smn-wrf-modis-test-predictions.csv.gz'
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
EVENTS = ROOT / 'docs/environmental-models-2026-10-22/snmf-2023-daily-occurrence-events.json'
OUT = ROOT / 'docs/environmental-models-2026-10-22/fire-smn-wrf-snmf-route-event-audit.json'
OUT_MD = ROOT / 'docs/environmental-models-2026-10-22/fire-smn-wrf-snmf-route-event-audit.md'
THRESHOLD = 0.5  # Fixed diagnostic score; no SNMF event was used to select it.
RADIUS_KM = 10.0
TEST_START = '2023-07-01'
TEST_END = '2024-01-01'


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def main() -> None:
    for path in (PREDICTIONS, OBSERVATIONS, EVENTS, PUBLIC / 'geography.json'):
        if not path.is_file():
            raise FileNotFoundError(f'Missing audit input: {path}')

    geography = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))
    regions = geography['fire_regions']

    pixel_coordinates = {}
    with gzip.open(OBSERVATIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            key = (row['region'], row['tile'], row['row'], row['col'])
            pixel_coordinates[key] = (float(row['latitude']), float(row['longitude']))

    predictions = defaultdict(list)
    with gzip.open(PREDICTIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            target_date = row['target_date']
            if not TEST_START <= target_date < TEST_END:
                continue
            parts = row['pixel_id'].split(':')
            coordinate = pixel_coordinates.get((row['region'], parts[0], parts[1], parts[2]))
            if coordinate is not None:
                predictions[(row['region'], target_date)].append(
                    (float(row['risk_score']), coordinate, row['pixel_id']))

    event_data = json.loads(EVENTS.read_text(encoding='utf-8'))
    # Collapse repeated or separately named incident records to the route-day
    # evaluation unit; preserve all supporting event identities in the output.
    route_days = {}
    for event in event_data['deduplicated_events']:
        day = event.get('reported_start_date')
        lat, lon = event.get('latitude'), event.get('longitude')
        if not day or not TEST_START <= day < TEST_END:
            continue
        if not isinstance(lat, (float, int)) or not isinstance(lon, (float, int)):
            continue
        for region in regions:
            center_distance = haversine_km(lat, lon, region['latitude'], region['longitude'])
            if center_distance > RADIUS_KM:
                continue
            key = (region['name'], day)
            route_days.setdefault(key, []).append({
                'incident_name': event.get('incident_name'),
                'province': event.get('province'),
                'status_in_latest_deduplicated_record': event.get('status'),
                'reported_start_date': day,
                'report_date_in_latest_deduplicated_record': event.get('report_date'),
                'distance_from_sector_center_km': round(center_distance, 3),
                'latitude': lat,
                'longitude': lon,
            })

    evaluated = []
    for (region_name, day), events in sorted(route_days.items()):
        local = []
        for event in events:
            for score, (lat, lon), pixel_id in predictions.get((region_name, day), []):
                distance = haversine_km(event['latitude'], event['longitude'], lat, lon)
                if distance <= RADIUS_KM:
                    local.append({'score': score, 'distance_km': distance, 'pixel_id': pixel_id})
        evaluated.append({
            'route_sector': region_name,
            'target_date': day,
            'supporting_snmf_records': [{k: v for k, v in event.items() if k not in ('latitude', 'longitude')}
                                        for event in events],
            'unique_incident_names': sorted({str(event['incident_name']) for event in events}),
            'predicted_pixels_in_event_radius': len(local),
            'maximum_local_score': round(max((item['score'] for item in local), default=0.0), 8),
            'threshold': THRESHOLD,
            'alerted': any(item['score'] >= THRESHOLD for item in local),
            'nearest_threshold_alert_km': round(min((item['distance_km'] for item in local
                                                     if item['score'] >= THRESHOLD), default=0.0), 3)
            if any(item['score'] >= THRESHOLD for item in local) else None,
            'has_model_coverage': bool(local),
        })

    covered = [row for row in evaluated if row['has_model_coverage']]
    positives = [row for row in covered if row['alerted']]
    summary = {
        'unique_route_sector_start_days_with_snmf_fire_within_10km': len(evaluated),
        'route_sector_start_days_with_model_pixel_coverage': len(covered),
        'route_sector_start_days_with_alert': len(positives),
        'event_coincidence_sensitivity_on_covered_route_days': len(positives) / len(covered) if covered else None,
        'incident_names_preserved_across_route_days': len({name for row in evaluated
                                                           for name in row['unique_incident_names']}),
    }
    report = {
        'experiment_id': 'smn-wrf-27h-vs-independent-snmf-route-events-2023h2',
        'status': 'exploratory_independent_event_sensitivity_only',
        'model': 'Frozen weather-only logistic model trained/validated on MOD14A1 labels; no retraining or threshold selection in this audit.',
        'target_model': 'MOD14A1 next-day nominal/high-confidence fire detection; scores are not calibrated probabilities of ignition.',
        'protocol': {
            'test_period': [TEST_START, TEST_END],
            'forecast_issue': '12 UTC previous calendar day',
            'lead_hours': 27,
            'target_valid_time': '15 UTC on target date',
            'official_event_target': 'SNMF-reported start date and coordinates within 10 km of a sampled route-sector center',
            'model_alert_rule': f'at least one forecast pixel score >= {THRESHOLD} within {RADIUS_KM:g} km of reported incident coordinates on reported start date',
            'evaluation_unit': 'unique route-sector start day; repeated incident records at a route/day are grouped',
            'threshold_source': 'Fixed diagnostic value; not tuned against these official events.',
        },
        'sources': {
            'official_event_records': event_data['source'],
            'official_report_manifest_sha256': event_data['source_manifest_sha256'],
            'wrf_model_prediction_sha256': sha256(PREDICTIONS),
            'observation_coordinate_file_sha256': sha256(OBSERVATIONS),
            'geography_sha256': sha256(PUBLIC / 'geography.json'),
        },
        'summary': summary,
        'route_days': evaluated,
        'limitations': [
            'The SNMF daily report archive is incomplete in time and is not an exhaustive fire/no-fire register; this positive-event sensitivity audit cannot estimate precision.',
            'The weather model predicts a satellite label, not ignition, propagation, or trail safety.',
            'The diagnostic 0.5 score is not a calibrated probability and was not selected on the SNMF cases.',
            'Only 6 sampled sectors have WRF/MODIS prediction coverage in this test; the other sectors are not represented.',
            'SNMF incident coordinates, start dates, duplicate naming and status fields are jurisdiction-reported and can be approximate.',
            'The event cases are temporally held out from model fitting, but the period and model family were inspected elsewhere in this research; this is not a pristine study-wide test.',
            'Pixel forecasts within an incident radius are spatially correlated; the route-sector start day, not each pixel, is counted.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    OUT_MD.write_text(
        '# Evaluación independiente WRF-SMN frente a eventos SNMF, segundo semestre de 2023\n\n'
        'El pronóstico meteorológico WRF-SMN de 27 h se cruzó con el inicio y las coordenadas de incendios reportados oficialmente por SNMF. Se mantuvieron congelados el modelo y el umbral diagnóstico 0,5; el modelo no se reajustó con estos episodios.\n\n'
        f"En el radio fijado de 10 km se encontraron **{summary['unique_route_sector_start_days_with_snmf_fire_within_10km']} días sector-ruta** con un inicio de incendio reportado. "
        f"Solo **{summary['route_sector_start_days_with_model_pixel_coverage']}** tenían cobertura válida del modelo; ese único caso recibió alerta. El segundo evento no se cuenta como acierto ni error porque no tuvo cobertura.\n\n"
        'Esto mide coincidencia/sensibilidad frente a los casos reportados, no precisión: el archivo diario del SNMF no es exhaustivo y sus días sin parte no son negativos. El score 0,5 no es una probabilidad. Los detalles por evento, hashes y límites están en el JSON asociado.\n',
        encoding='utf-8')
    print(json.dumps({'output': OUT.relative_to(ROOT).as_posix(), 'summary': summary,
                      'route_days': evaluated}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
