"""Score frozen SMN-WRF model on independently reported SNMF 2025 route events."""
import csv
import gzip
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import beta

from environmental_sources import PUBLIC, ROOT, sha256
from fire_sources import REPORT_DIR

EVENTS = REPORT_DIR / 'fire-snmf-route-event-coverage-2025.json'
MODEL_REPORT = REPORT_DIR / 'fire-smn-wrf-modis-evaluation.json'
FORECAST_DIR = PUBLIC / 'private' / 'smnf-wrf-official-event-2025'
OUT = REPORT_DIR / 'fire-smn-wrf-snmf-2025-event-test.json'
THRESHOLD = 0.5  # Diagnostic only; validation selected no threshold.


def day_features(day: str) -> tuple[float, float]:
    parsed = datetime.strptime(day, '%Y-%m-%d')
    angle = 2 * math.pi * parsed.timetuple().tm_yday / 365.2425
    return math.sin(angle), math.cos(angle)


def score(model: dict, row: dict, day: str) -> float:
    sin_day, cos_day = day_features(day)
    names = model['features']
    values = {'latitude': float(row['pixel_latitude']),
        'longitude': float(row['pixel_longitude']), 'day_sin': sin_day, 'day_cos': cos_day,
        'Tmax': float(row['Tmax']), 'Tmin': float(row['Tmin']), 'T2': float(row['T2']),
        'HR2': float(row['HR2']), 'wind10_ms': float(row['magViento10']),
        'precip_27h_mm': float(row['PP'])}
    x = np.asarray([values[name] for name in names], dtype=float)
    mean = np.asarray(model['standardization_mean'], dtype=float)
    scale = np.asarray(model['standardization_scale'], dtype=float)
    coefficients = np.asarray(model['standardized_coefficients'], dtype=float)
    logit = float(model['intercept'] + ((x - mean) / scale) @ coefficients)
    return float(1 / (1 + math.exp(-max(-40, min(40, logit)))))


def main():
    event_data = json.loads(EVENTS.read_text(encoding='utf-8'))
    model_report = json.loads(MODEL_REPORT.read_text(encoding='utf-8'))
    manifest_path = FORECAST_DIR / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    model = model_report['frozen_research_model_parameters']
    rows_by_key = {}
    for path in sorted(FORECAST_DIR.glob('????-??-??.csv.gz')):
        with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
            for row in csv.DictReader(stream):
                rows_by_key[(row['target_date'], row['pixel_id'])] = row
    scored = []
    missing = []
    for event in event_data['results']['10']['route_sector_start_days']:
        key = (event['target_date'], event['route_sector'])
        row = rows_by_key.get(key)
        if row is None:
            missing.append({'route_sector': key[1], 'target_date': key[0]})
            continue
        risk = score(model, row, event['target_date'])
        scored.append({'route_sector': event['route_sector'], 'target_date': event['target_date'],
            'incident_names': event['source_incident_names'],
            'nearest_reported_incident_km': event['nearest_reported_incident_km'],
            'forecast_issue_time_utc': row['issue_time_utc'],
            'forecast_valid_time_utc': row['valid_time_utc'],
            'lead_hours': int(row['lead_hours']), 'model_score_diagnostic': risk,
            'alert_at_unselected_0_5': risk >= THRESHOLD})
    hit = sum(event['alert_at_unselected_0_5'] for event in scored)
    n = len(scored)
    interval = ([float(beta.ppf(0.025, hit, n - hit + 1)) if hit else 0.0,
                 float(beta.ppf(0.975, hit + 1, n - hit)) if hit < n else 1.0] if n else None)
    result = {'experiment_id': 'smn-wrf-frozen-model-independent-snmf-2025-event-test',
        'status': 'independent_positive_event_crosscheck_only',
        'meaning': 'Sensitivity/coincidence on reported start-date route events; not precision, calibration, or verified advance warning.',
        'sources': {'official_report_event_inventory': {'path': EVENTS.relative_to(ROOT).as_posix(), 'sha256': sha256(EVENTS)},
            'frozen_model_report': {'path': MODEL_REPORT.relative_to(ROOT).as_posix(), 'sha256': sha256(MODEL_REPORT)},
            'forecast_manifest_sha256': sha256(manifest_path),
            'transport': manifest.get('transport')},
        'protocol': {'model_train_period': 'MODIS target dates before 2023-01-01',
            'validation_period': '2023-01-01 through 2023-06-30',
            'independent_event_test_dates': 'SNMF-reported route-sector event starts in 2025',
            'event_radius_km': 10, 'forecast_issue': '12:00 UTC previous day',
            'forecast_valid': '15:00 UTC event date; 27-hour lead',
            'diagnostic_threshold': THRESHOLD,
            'threshold_selection': 'None; validation selected no threshold at >=90% proxy precision and >=5 alerts.'},
        'coverage': {'official_route_event_days': len(event_data['results']['10']['route_sector_start_days']),
            'scored_event_days': n, 'missing_forecast_route_event_days': missing,
            'all_four_event_days_forecast_available': not missing and n == 4},
        'result': {'alerts_on_scored_event_days': hit, 'misses_on_scored_event_days': n-hit,
            'descriptive_sensitivity': hit/n if n else None,
            'exact_binomial_95pct_interval_naive': interval,
            'per_event_scores': scored},
        'limitations': [
            'Only four official positive route-sector start days were available; the events are not independent samples for a stable estimate.',
            'There are no verified negative route-days in this event-only cohort; precision and specificity cannot be computed.',
            'SNMF gives start dates but not ignition times, so an event-date forecast cannot prove the alert preceded ignition.',
            'The 0.5 cutoff was not selected by validation and is diagnostic only; scores are not calibrated fire probabilities.',
            'Forecast bytes were retrieved over HTTP because TLS was reset in this session. S3 CRC64NVME was checked, but that checksum was not authenticated over HTTP; reacquire over HTTPS before a final thesis claim.',
            'The model predicts MODIS satellite detection labels and was not trained to predict ignition.'
        ], 'synthetic_observations': 0, 'deployment_approved': False}
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': OUT.as_posix(), 'coverage': result['coverage'],
        'result': result['result']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
