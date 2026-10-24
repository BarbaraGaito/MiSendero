"""Temporal GFS experiment for SNMF-reported fire route-day proxy labels.

Research only. It does not modify the app or production model. The target is
reported-incident proximity, not verified physical fire or ignition.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
    brier_score_loss, confusion_matrix, precision_score, recall_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from environmental_sources import PUBLIC, ROOT, sha256

BASE = ROOT / 'docs/environmental-models-2026-10-22'
OUTS = {
    'gfs': BASE / 'fire-gfs-snmf-report-proxy-temporal-evaluation-2026-jan.json',
    'jma_gsm': BASE / 'fire-jma-snmf-report-proxy-temporal-evaluation-2026-jan.json',
}
WEATHER_FILES = {
    'gfs': [
    ROOT / 'training/data/environmental/private/openmeteo-gfs-previous-runs-argentina-trails-2024-01-01-2024-11-20.json.gz',
    ROOT / 'training/data/environmental/private/openmeteo-gfs-previous-runs-argentina-trails-2025-01-01-2026-02-01.json.gz',
    ],
    'jma_gsm': [
        ROOT / 'training/data/environmental/private/openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2023-07-01-2024-01-01.json.gz',
        ROOT / 'training/data/environmental/private/openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2024-01-01-2025-01-01.json.gz',
        ROOT / 'training/data/environmental/private/openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2025-01-01-2026-02-01.json.gz',
    ],
}
PROXY_FILES = [
    BASE / 'snmf-2024-route-day-report-proxy.json',
    BASE / 'snmf-2025-route-day-report-proxy.json',
    BASE / 'snmf-2026-jan-route-day-report-proxy.json',
]
EVENT_AUDIT = BASE / 'fire-snmf-route-event-coverage-2026-jan.json'
VARIABLES = {
    'temperature_2m_previous_day1': 'temperature_2m_previous_day1',
    'relative_humidity_2m_previous_day1': 'relative_humidity_2m_previous_day1',
    'wind_speed_10m_previous_day1': 'wind_speed_10m_previous_day1',
    'precipitation_previous_day1': 'precipitation_previous_day1',
}


def load_weather_with_geography(weather_files: list[Path]) -> pd.DataFrame:
    regions = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    region_names = [region['name'] for region in regions]
    all_frames = []
    for path in weather_files:
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            payload = json.load(stream)
        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(region_names):
            raise ValueError(f'Expected {len(region_names)} points in {path.name}, got {len(locations)}')
        for region, location in zip(region_names, locations):
            hourly = location['hourly']
            times = pd.to_datetime(hourly['time'], utc=True)
            frame = pd.DataFrame({'time': times, 'region': region})
            for output_name, source_name in VARIABLES.items():
                values = hourly[source_name]
                if len(values) != len(times):
                    raise ValueError(f'Misaligned {source_name} in {path.name}')
                frame[output_name] = values
            frame['date'] = frame['time'].dt.strftime('%Y-%m-%d')
            all_frames.append(frame)
    hourly = pd.concat(all_frames, ignore_index=True)
    variables = list(VARIABLES)
    # A full-day predictor uses the 24 valid-hour forecasts issued one day
    # earlier. Partial or missing days are excluded, never imputed.
    complete = hourly.groupby(['region', 'date'], sort=True).filter(
        lambda frame: len(frame) == 24 and frame[variables].notna().all().all())
    daily = complete.groupby(['region', 'date'], as_index=False).agg(
        temperature_mean=('temperature_2m_previous_day1', 'mean'),
        temperature_max=('temperature_2m_previous_day1', 'max'),
        humidity_mean=('relative_humidity_2m_previous_day1', 'mean'),
        humidity_min=('relative_humidity_2m_previous_day1', 'min'),
        wind_mean=('wind_speed_10m_previous_day1', 'mean'),
        wind_max=('wind_speed_10m_previous_day1', 'max'),
        precipitation_sum=('precipitation_previous_day1', 'sum'),
    )
    return daily


def load_labels() -> pd.DataFrame:
    rows = []
    for path in PROXY_FILES:
        proxy = json.loads(path.read_text(encoding='utf-8'))
        for row in proxy['route_days']:
            rows.append({'region': row['route_sector'], 'date': row['report_date'], 'label': row['label']})
    labels = pd.DataFrame(rows).drop_duplicates(['region', 'date'], keep='last')
    return labels


def summarize_split(part: pd.DataFrame, probability: np.ndarray, threshold=0.5) -> dict:
    y = part['label'].to_numpy(dtype=int)
    prediction = probability >= threshold
    return {
        'route_days': len(part), 'positive_route_days': int(y.sum()),
        'observed_positive_fraction': float(y.mean()) if len(y) else None,
        'average_precision': float(average_precision_score(y, probability)) if y.sum() else None,
        'brier_score': float(brier_score_loss(y, probability)) if len(y) else None,
        'accuracy_at_0_5_diagnostic': float(accuracy_score(y, prediction)) if len(y) else None,
        'precision_at_0_5_diagnostic': float(precision_score(y, prediction, zero_division=0)) if len(y) else None,
        'recall_at_0_5_diagnostic': float(recall_score(y, prediction, zero_division=0)) if len(y) else None,
        'confusion_matrix_labels_0_1': confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
        'alerts_at_0_5_diagnostic': int(prediction.sum()),
    }


def choose_validation_threshold(y: np.ndarray, probability: np.ndarray) -> dict:
    candidates = []
    for threshold in np.unique(probability):
        prediction = probability >= threshold
        alerts = int(prediction.sum())
        if alerts < 5:
            continue
        precision = float(precision_score(y, prediction, zero_division=0))
        recall = float(recall_score(y, prediction, zero_division=0))
        if precision >= 0.80:
            candidates.append((recall, precision, float(threshold), alerts))
    if not candidates:
        return {'selected': False, 'reason': 'No validation threshold achieved >=80% proxy precision with at least 5 alerts.'}
    recall, precision, threshold, alerts = max(candidates)
    return {'selected': True, 'threshold': threshold, 'validation_precision': precision,
        'validation_recall': recall, 'validation_alerts': alerts}


def main(weather_model='gfs'):
    if weather_model not in WEATHER_FILES:
        raise ValueError(f'Unsupported weather model: {weather_model}')
    weather_files = WEATHER_FILES[weather_model]
    output_path = OUTS[weather_model]
    if not all(path.is_file() for path in weather_files + PROXY_FILES + [EVENT_AUDIT]):
        raise FileNotFoundError(f'Expected local {weather_model} forecast and SNMF proxy files are missing.')
    daily = load_weather_with_geography(weather_files)
    labels = load_labels()
    frame = labels.merge(daily, on=['region', 'date'], how='inner', validate='one_to_one')
    feature_columns = [column for column in frame.columns if column not in ('label', 'date', 'region')]
    train = frame[(frame['date'] >= '2024-01-20') & (frame['date'] < '2025-12-01')].copy()
    validation = frame[(frame['date'] >= '2025-12-01') & (frame['date'] < '2026-01-01')].copy()
    test = frame[(frame['date'] >= '2026-01-01') & (frame['date'] < '2026-02-01')].copy()
    if train.empty or test.empty:
        raise ValueError('Temporal training or test split has no aligned route-days.')
    transformer = ColumnTransformer([
        ('weather', StandardScaler(), feature_columns),
        ('region', OneHotEncoder(handle_unknown='ignore'), ['region']),
    ])
    model = make_pipeline(transformer, LogisticRegression(
        class_weight='balanced', C=1.0, max_iter=3000, solver='lbfgs', random_state=42))
    model.fit(train[feature_columns + ['region']], train['label'])
    validation_probability = model.predict_proba(validation[feature_columns + ['region']])[:, 1]
    test_probability = model.predict_proba(test[feature_columns + ['region']])[:, 1]
    validation_threshold = choose_validation_threshold(validation['label'].to_numpy(dtype=int), validation_probability)
    event_audit = json.loads(EVENT_AUDIT.read_text(encoding='utf-8'))
    result = {
        'experiment_id': f'{weather_model}-24h-logistic-snmf-reported-fire-route-day-temporal-test-2026-jan',
        'candidate_status': 'not_reliable_for_fire_prediction',
        'target': 'SNMF-reported incident proxy within 10 km; not physical fire absence or ignition probability.',
        'weather_model': weather_model,
        'protocol': {'forecast_lead_hours': 24, 'daily_features': feature_columns,
            'feature_window_utc': 'all 24 hourly selected-model forecast values for the target date, at fixed 24-hour lead',
            'train_period': '2024-01-20 through 2025-11-30',
            'validation_period': '2025-12-01 through 2025-12-31',
            'test_period': '2026-01-01 through 2026-01-31',
            'algorithm': 'StandardScaler + region one-hot + class-balanced logistic regression (C=1)',
            'threshold_selection_rule': 'Validation only: maximize recall subject to proxy precision >=0.80 and >=5 alerts.',
            'test_diagnostic_threshold': 0.5},
        'sources': {
            'weather_sha256': {path.name: sha256(path) for path in weather_files},
            'proxy_sha256': {path.name: sha256(path) for path in PROXY_FILES},
            'event_audit_sha256': sha256(EVENT_AUDIT),
        },
        'data': {'aligned_route_days': len(frame), 'train_route_days': len(train),
            'train_positive_route_days': int(train['label'].sum()),
            'validation_route_days': len(validation),
            'validation_positive_route_days': int(validation['label'].sum()),
            'test_route_days': len(test), 'test_positive_route_days': int(test['label'].sum()),
            'test_positive_route_sector_start_days_from_official_event_audit': event_audit['results']['10']['unique_route_sector_start_days']},
        'validation_threshold': validation_threshold,
        'validation_at_0_5_diagnostic': summarize_split(validation, validation_probability),
        'test_at_0_5_diagnostic': summarize_split(test, test_probability),
        'test_route_day_predictions': [
            {'date': row.date, 'route_sector': row.region,
             'reported_active_fire_proxy_label': int(row.label),
             'diagnostic_score': float(probability),
             'alert_at_diagnostic_threshold_0_5': bool(probability >= 0.5)}
            for row, probability in zip(test.itertuples(index=False), test_probability)
        ],
        'test_training_prevalence_baseline': {
            'predicted_probability': float(train['label'].mean()),
            'average_precision': float(test['label'].mean()),
            'brier_score': float(brier_score_loss(test['label'], np.full(len(test), train['label'].mean()))),
        },
        'limitations': [
            'SNMF proxy negatives are absence of a nearby listed incident in an available report, not independently confirmed no-fire observations.',
            'The classifier uses only GFS weather and route identity; it lacks fuel state, vegetation, human ignition likelihood and confirmed sensor coverage.',
            'Route-day positives repeat episodes. The test has only a few independent route-sector incident starts, so day-level metrics exaggerate sample size.',
            'If validation cannot select a threshold, the 0.5 test result is diagnostic only and must not be used as an operational alert threshold.',
            'No model artifact is saved and no app or production file is modified.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items()
        if key not in ('sources', 'limitations', 'test_route_day_predictions')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weather-model', choices=sorted(WEATHER_FILES), default='gfs')
    main(parser.parse_args().weather_model)
