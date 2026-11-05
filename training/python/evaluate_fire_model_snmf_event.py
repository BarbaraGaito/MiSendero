"""Audit held-out model predictions against curated SNMF event reports.

This retrospective pilot is not a precision estimate. Daily reports record
reported incidents but are not exhaustive ground truth for every possible fire.
"""
import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from environmental_sources import ROOT, sha256
from fire_sources import PRIVATE

PREDICTIONS = PRIVATE / 'fire-temporal_test-predictions.csv.gz'
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
OUT = ROOT / 'docs/environmental-models-2026-10-22/fire-model-snmf-event-audit.json'
PROTOCOL_PATH = ROOT / 'docs/environmental-models-2026-10-22/fire-snmf-event-protocol.json'
SNMF_EVENT_PROTOCOL = json.loads(PROTOCOL_PATH.read_text(encoding='utf-8'))

REGION = 'Sendero Che Roga - Mburucuyá'
TARGET_DAY = '2023-08-06'
THRESHOLD = float(SNMF_EVENT_PROTOCOL['threshold'])
PRIMARY_RADIUS_KM = float(SNMF_EVENT_PROTOCOL['primary_spatial_rule']['radius_km'])
EVENT = {
    'name': 'Límite Potrero 13',
    'province': 'Corrientes',
    'department': 'Mburucuyá',
    'event_date': '2023-08-06',
    'status': 'Extinguido (06/08/2023)',
    'latitude': -(28 + 5 / 60 + 34.5 / 3600),
    'longitude': -(58 + 6 / 60 + 30.5 / 3600),
    'reported_burned_area_ha': 393.0,
    'source_url': 'https://www.argentina.gob.ar/sites/default/files/2023/06/reportediario_07-08-2023.pdf',
    'source_description': 'SNMF daily fire report dated 07/08/2023; event start and extinguishment date 06/08/2023.',
}
ADDITIONAL_EVENT = {
    'name': 'Ea. San Bernardo',
    'province': 'Córdoba',
    'department': 'Punilla',
    'event_start_date': '2023-10-29',
    'report_date': '2023-10-31',
    'status_at_report': 'Guardia de cenizas',
    'latitude': -(31 + 31 / 60 + 46.5 / 3600),
    'longitude': -(64 + 39 / 60 + 37.3 / 3600),
    'source_url': 'https://www.argentina.gob.ar/sites/default/files/2023/06/reportediario_31-10-2023.pdf',
    'source_description': 'SNMF daily report dated 31/10/2023; listed as Guardia de cenizas, with start date 29/10/2023 and coordinates.',
    'model_region': 'Quebrada del Condorito - Balcon Norte',
    'evaluated_target_dates': ['2023-10-29', '2023-10-30', '2023-10-31'],
    'matching_radii_km': [10, 20, 30],
    'spatial_rule_status': 'Exploratory; radii were not preregistered and cannot establish event-level precision.',
}
NO_REPORTED_FIRE_DAY = {
    'date': '2023-12-20',
    'source_url': 'https://www.argentina.gob.ar/sites/default/files/2024/01/reporte_diario_20-12-2023.pdf',
    'source_description': 'The SNMF daily report states that no fires were reported in Argentina on this date.',
}
ZERO_FIRE_MONTH_PROVINCES = {
    'month': '2023-12',
    'source_url': 'https://www.argentina.gob.ar/sites/default/files/2024/01/informe_ocurrencia_diciembre2023.pdf',
    'zero_reported_fire_count_by_province': {'Corrientes': 0, 'Buenos Aires': 0},
    'region_provinces': {
        'Sendero Che Roga - Mburucuyá': 'Corrientes',
        'Cerro Ventana - Hueco de la Ventana': 'Buenos Aires',
    },
}


def haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def main():
    required = (PREDICTIONS, OBSERVATIONS)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError('Frozen evaluation inputs are missing: ' + ', '.join(missing))

    coordinates = {}
    with gzip.open(OBSERVATIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            key = (row['region'], row['tile'], row['row'], row['col'])
            coordinates[key] = (float(row['latitude']), float(row['longitude']))

    day_predictions = []
    no_report_alerts = {}
    no_report_label_counts = {'modis_negative': 0, 'modis_positive': 0}
    monthly_alerts_by_region = Counter()
    monthly_days_by_region = defaultdict(set)
    monthly_modis_labels_by_region = defaultdict(Counter)
    missing_coordinates = 0
    additional_event_missing_coordinates = 0
    additional_event_predictions = []
    with gzip.open(PREDICTIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            if row['target_at'][:7] == ZERO_FIRE_MONTH_PROVINCES['month'] and row['region'] in ZERO_FIRE_MONTH_PROVINCES['region_provinces']:
                if float(row['xgboost']) >= THRESHOLD:
                    monthly_alerts_by_region[row['region']] += 1
                    monthly_days_by_region[row['region']].add(row['target_at'][:10])
                    label = 'modis_positive' if int(row['observed']) == 1 else 'modis_negative'
                    monthly_modis_labels_by_region[row['region']][label] += 1
            if row['target_at'][:10] == NO_REPORTED_FIRE_DAY['date']:
                if float(row['xgboost']) >= THRESHOLD:
                    no_report_alerts[row['region']] = no_report_alerts.get(row['region'], 0) + 1
                    label_key = 'modis_positive' if int(row['observed']) == 1 else 'modis_negative'
                    no_report_label_counts[label_key] += 1
            if row['region'] == REGION and row['target_at'][:10] == TARGET_DAY:
                parts = row['pixel_id'].split(':')
                point = coordinates.get((row['region'], row['tile'], parts[-2], parts[-1]))
                if point is None:
                    missing_coordinates += 1
                else:
                    distance = haversine_km(EVENT['latitude'], EVENT['longitude'], *point)
                    day_predictions.append({
                        'pixel_id': row['pixel_id'],
                        'score': float(row['xgboost']),
                        'distance_from_reported_event_km': round(distance, 4),
                        'threshold_alert': float(row['xgboost']) >= THRESHOLD,
                    })

            if (row['region'] == ADDITIONAL_EVENT['model_region']
                    and row['target_at'][:10] in ADDITIONAL_EVENT['evaluated_target_dates']):
                parts = row['pixel_id'].split(':')
                point = coordinates.get((row['region'], row['tile'], parts[-2], parts[-1]))
                if point is None:
                    additional_event_missing_coordinates += 1
                else:
                    additional_event_predictions.append({
                        'target_date': row['target_at'][:10],
                        'score': float(row['xgboost']),
                        'observed_modis_label': int(row['observed']),
                        'distance_from_reported_event_km': haversine_km(
                            ADDITIONAL_EVENT['latitude'], ADDITIONAL_EVENT['longitude'], *point),
                    })

    alert_predictions = [row for row in day_predictions if row['threshold_alert']]
    nearest_alert = min(alert_predictions, key=lambda row: row['distance_from_reported_event_km'], default=None)
    radii = (1, 5, 10)
    within_radius = {
        f'{radius}_km': {
            'predicted_pixels': sum(row['distance_from_reported_event_km'] <= radius for row in day_predictions),
            'threshold_alerts': sum(row['distance_from_reported_event_km'] <= radius for row in alert_predictions),
            'maximum_score': round(max((row['score'] for row in day_predictions
                                        if row['distance_from_reported_event_km'] <= radius), default=0.0), 8),
        }
        for radius in radii
    }
    additional_event_comparison = {
        **ADDITIONAL_EVENT,
        'threshold': THRESHOLD,
        'model_pixels_evaluated': len(additional_event_predictions),
        'model_pixels_with_missing_coordinates': additional_event_missing_coordinates,
        'by_radius': {
            f'{radius}_km': {
                'pixels_evaluated': sum(row['distance_from_reported_event_km'] <= radius
                                        for row in additional_event_predictions),
                'threshold_alert_pixel_days': sum(
                    row['distance_from_reported_event_km'] <= radius and row['score'] >= THRESHOLD
                    for row in additional_event_predictions),
                'maximum_score': round(max((row['score'] for row in additional_event_predictions
                                            if row['distance_from_reported_event_km'] <= radius), default=0.0), 8),
                'modis_labels_for_threshold_alerts': dict(Counter(
                    row['observed_modis_label'] for row in additional_event_predictions
                    if row['distance_from_reported_event_km'] <= radius and row['score'] >= THRESHOLD)),
            }
            for radius in ADDITIONAL_EVENT['matching_radii_km']
        },
        'nearest_threshold_alert': min(
            ({'target_date': row['target_date'], 'score': round(row['score'], 8),
              'distance_km': round(row['distance_from_reported_event_km'], 4)}
             for row in additional_event_predictions if row['score'] >= THRESHOLD),
            key=lambda row: row['distance_km'], default=None),
        'interpretation': 'One more official reported event, evaluated descriptively. The report status is Guardia de cenizas; spatial radii are exploratory, so this is not a precision estimate.',
    }
    result = {
        'experiment_id': 'fire-xgboost-heldout-snmf-event-audits',
        'meaning': 'Retrospective pilot spatial audits of two official SNMF event reports under a frozen exploratory rule; not a precision estimate or exhaustive test set.',
        'evaluation_protocol': SNMF_EVENT_PROTOCOL,
        'evaluation_protocol_sha256': sha256(PROTOCOL_PATH),
        'model': 'validation-selected XGBoost from frozen MOD14A1 protocol',
        'test_partition': 'July-December 2023 temporal holdout',
        'region': REGION,
        'target_day': TARGET_DAY,
        'threshold': THRESHOLD,
        'matching_radii_km': list(radii),
        'spatial_rule_status': 'Exploratory sensitivity check; freeze a matching radius before evaluating a new independent cohort.',
        'official_event': EVENT,
        'additional_official_event_comparison': additional_event_comparison,
        'official_no_report_day': NO_REPORTED_FIRE_DAY,
        'counts': {
            'model_pixels_evaluated': len(day_predictions),
            'model_pixels_without_source_coordinates': missing_coordinates,
            'pixels_scoring_at_or_above_threshold': len(alert_predictions),
        },
        'spatial_comparison': within_radius,
        'primary_protocol_radius_km': PRIMARY_RADIUS_KM,
        'primary_protocol_event_alerts': {
            'Limite Potrero 13': within_radius[f'{int(PRIMARY_RADIUS_KM)}_km']['threshold_alerts'],
            'Ea. San Bernardo': additional_event_comparison['by_radius'][f'{int(PRIMARY_RADIUS_KM)}_km']['threshold_alert_pixel_days'],
        },
        'nearest_threshold_alert': nearest_alert,
        'no_report_day_comparison': {
            'reported_fire_occurrences': 0,
            'threshold_alert_pixel_days': sum(no_report_alerts.values()),
            'threshold_alert_region_days': len(no_report_alerts),
            'threshold_alerts_by_region': no_report_alerts,
            'modis_labels_for_alert_pixel_days': no_report_label_counts,
            'interpretation': 'False alerts relative to the official SNMF reporting benchmark for this date; not proof of zero physical fires.',
        },
        'zero_fire_monthly_province_comparison': {
            **ZERO_FIRE_MONTH_PROVINCES,
            'alert_pixel_days': sum(monthly_alerts_by_region.values()),
            'alert_sector_days': sum(len(days) for days in monthly_days_by_region.values()),
            'by_region': {
                region: {
                    'province': ZERO_FIRE_MONTH_PROVINCES['region_provinces'][region],
                    'official_reported_fires_in_province': ZERO_FIRE_MONTH_PROVINCES['zero_reported_fire_count_by_province'][ZERO_FIRE_MONTH_PROVINCES['region_provinces'][region]],
                    'alert_pixel_days': monthly_alerts_by_region[region],
                    'alert_sector_days': len(monthly_days_by_region[region]),
                    'modis_labels_for_alert_pixel_days': dict(monthly_modis_labels_by_region[region]),
                }
                for region in ZERO_FIRE_MONTH_PROVINCES['region_provinces']
            },
            'interpretation': 'Alerts in provinces with zero officially reported fire occurrences during the month; this is a benchmark against reported occurrences, not proof that no unreported physical fire existed.',
        },
        'prediction_unit': 'pixel-day; nearby model pixels are correlated and are not independent events',
        'limitations': [
            'This audit tests whether a model alert localized near one officially reported event; it does not estimate overall precision.',
            'The SNMF daily report supports the occurrence, date, status, reported area, and reference coordinates of this event; it does not prove absence of other fires.',
            'Thresholded alerts elsewhere cannot be labeled false positives from this single report.',
            'The event is one independent case, so it cannot support a reliable population-level accuracy claim.',
        ],
        'synthetic_observations': 0,
        'inputs': {
            'predictions': PREDICTIONS.relative_to(ROOT).as_posix(),
            'predictions_sha256': sha256(PREDICTIONS),
            'observations': OBSERVATIONS.relative_to(ROOT).as_posix(),
            'observations_sha256': sha256(OBSERVATIONS),
        },
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': OUT.relative_to(ROOT).as_posix(), **result['counts'],
                      'spatial_comparison': within_radius, 'nearest_threshold_alert': nearest_alert,
                      'additional_official_event_comparison': additional_event_comparison},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
