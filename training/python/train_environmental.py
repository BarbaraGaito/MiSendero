"""Train observed gage-height forecasts with chronological, availability-aware holdouts.

Satellite models are blocked until actual daily observations with quality and
availability metadata can be acquired. Never train on invented negatives.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import xgboost
from xgboost import XGBRegressor

from environmental_sources import EXCLUDED_STATIONS, FEATURES, PUBLIC, ROOT, STATIONS, examples, fetch_station, observations, satellite_status, sha256, utc

PRIVATE = PUBLIC / 'private'
REPORT = ROOT / 'docs/environmental-models-2026-10-22/river-results.json'
TRAIN_END = utc('2025-01-01T00:00:00Z')
VALID_END = utc('2025-07-01T00:00:00Z')
TEST_END = utc('2026-01-01T00:00:00Z')


def regression_metrics(observed, predicted):
    return {'mae_m': float(mean_absolute_error(observed, predicted)),
            'rmse_m': float(np.sqrt(mean_squared_error(observed, predicted))), 'observations': len(observed)}


def partitions(frame):
    issue, target = pd.to_datetime(frame.issued_at), pd.to_datetime(frame.target_at)
    available = pd.to_datetime(frame.target_available_at, format='ISO8601', utc=True)
    # Labels must also have been published before fitting/model selection.
    # A target measured before a cutoff can be revised or published afterwards.
    return {'train': (issue < TRAIN_END) & (target < TRAIN_END) & (available < TRAIN_END),
            'validation': (issue >= TRAIN_END) & (target < VALID_END) & (available < VALID_END),
            'test': (issue >= VALID_END) & (target < TEST_END)}


def train_one(station: int, horizon: int):
    raw, provenance = fetch_station(station)
    clean, measurement_exclusions = observations(raw)
    rows, window_exclusions = examples(clean, horizon)
    if not rows:
        return {'series_id': station, 'horizon_hours': horizon, 'status': 'no_data', 'reason': 'No exact observed targets with fresh publication-aware history'}
    frame = pd.DataFrame(rows)
    split = partitions(frame)
    counts = {key: int(mask.sum()) for key, mask in split.items()}
    basic = {'series_id': station, 'station': raw['estacion']['nombre'], 'station_coordinates': raw['estacion']['geom'],
             'horizon_hours': horizon, 'source': provenance, 'counts': counts,
             'measurement_exclusions': measurement_exclusions, 'window_exclusions': window_exclusions,
             'units': 'm', 'deployment_approved': False, 'route_association_approved': False}
    if counts['train'] < 200 or counts['validation'] < 50 or counts['test'] < 50:
        return basic | {'status': 'no_data', 'reason': 'Insufficient chronological partitions; do not change dates to improve scores'}
    target = frame.observed - frame.baseline
    # Model the observed change and add the last available level back. This is
    # an invertible target transformation, not a rule-generated safety label.
    candidates = {
        'persistence': None,
        'linear': make_pipeline(StandardScaler(), LinearRegression()),
        'random_forest': RandomForestRegressor(n_estimators=150, max_depth=8, min_samples_leaf=5, random_state=42, n_jobs=2),
        'xgboost': XGBRegressor(n_estimators=200, max_depth=3, learning_rate=.05, objective='reg:squarederror',
                               tree_method='hist', n_jobs=2, random_state=42, subsample=1, colsample_bytree=1)}
    fitted, validation = {}, {}
    for name, candidate in candidates.items():
        if candidate is not None:
            candidate.fit(frame.loc[split['train'], FEATURES], target[split['train']])
        fitted[name] = candidate
        prediction = frame.loc[split['validation'], 'baseline'].to_numpy().copy()
        if candidate is not None:
            prediction += candidate.predict(frame.loc[split['validation'], FEATURES])
        validation[name] = regression_metrics(frame.loc[split['validation'], 'observed'], prediction)
    # Freeze selection before calculating any test score. Ties prefer persistence.
    selected = min(candidates, key=lambda name: validation[name]['mae_m'])
    test, predictions = {}, frame.loc[split['test'], ['issued_at', 'target_at', 'latest_observed_at',
        'latest_available_at', 'target_available_at', 'source_row_ids', 'target_source_row_id', 'observed', 'baseline']].copy()
    for name, candidate in fitted.items():
        predicted = frame.loc[split['test'], 'baseline'].to_numpy().copy()
        if candidate is not None:
            predicted += candidate.predict(frame.loc[split['test'], FEATURES])
        test[name] = regression_metrics(predictions.observed, predicted)
        predictions[name] = predicted
    path = PRIVATE / f'river-{station}-{horizon}h-test.csv'
    predictions.to_csv(path, index=False)
    model_path = PRIVATE / f'river-{station}-{horizon}h.joblib'
    if fitted[selected] is not None:
        joblib.dump(fitted[selected], model_path)
    artifact = {'id': f'river-{station}-{horizon}h', 'model_type': 'river_level', 'version': 1,
                'algorithm': selected, 'features': FEATURES, 'target_transform': 'future_observed_level_minus_latest_available_level',
                'series_id': station, 'horizon_hours': horizon,
                'model_file': model_path.name if fitted[selected] is not None else None,
                'model_sha256': sha256(model_path) if fitted[selected] is not None else None,
                'validation': validation[selected], 'test': test[selected], 'source_sha256': provenance['sha256'],
                'trained_at': datetime.now(timezone.utc).isoformat(), 'deployment_approved': False}
    (PRIVATE / f'river-{station}-{horizon}h-artifact.json').write_text(json.dumps(artifact, indent=2) + '\n', encoding='utf-8')
    monthly = {}
    for month, subset in predictions.groupby(predictions.issued_at.str.slice(0, 7)):
        monthly[month] = {'selected': regression_metrics(subset.observed, subset[selected]),
                          'persistence': regression_metrics(subset.observed, subset.persistence)}
    return basic | {'status': 'experimental', 'selection': selected, 'selection_method': 'Minimum validation MAE, tie preference persistence; test not used for selection',
                    'validation': validation, 'test': test,
                    'beats_test_persistence': test[selected]['mae_m'] < test['persistence']['mae_m'],
                    'test_predictions_file': str(path.relative_to(ROOT)), 'test_predictions_sha256': sha256(path),
                    'test_by_calendar_month': monthly,
                    'partition_ranges': {key: {'first_issue': str(frame.loc[mask, 'issued_at'].min()),
                                              'last_target': str(frame.loc[mask, 'target_at'].max()),
                                              'last_target_available_at': str(frame.loc[mask, 'target_available_at'].max())} for key, mask in split.items()},
                    'model_artifact': artifact}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('river_level', 'snow', 'fire_detection'), default='river_level')
    args = parser.parse_args()
    if args.model == 'fire_detection':
        from train_fire import main as train_fire
        return train_fire()
    if args.model != 'river_level':
        PUBLIC.mkdir(parents=True, exist_ok=True)
        status = satellite_status()[args.model]
        (PUBLIC / f'{args.model}-status.json').write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
        raise SystemExit(f"Training blocked: {status['reason']}. No scientific observations or labels generated.")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    results = []
    for station in STATIONS:
        for horizon in (3, 6):
            result = train_one(station, horizon)
            results.append(result)
            print(station, horizon, result['status'], result.get('selection'), result.get('counts'), flush=True)
    report = {'models': results, 'satellite_models': satellite_status(), 'synthetic_observations': 0,
              'scope_exclusions': EXCLUDED_STATIONS,
              'temporal_protocol': {'training_target_before': TRAIN_END.isoformat(), 'validation_target_before': VALID_END.isoformat(),
                                    'test_target_before': TEST_END.isoformat(), 'split': 'Chronological per station; purge targets crossing split boundaries; training/validation labels available before their cutoff'},
              'versions': {'numpy': np.__version__, 'pandas': pd.__version__, 'sklearn': sklearn.__version__, 'xgboost': xgboost.__version__},
              'limitations': ['Historical timeupdate is used as a conservative availability bound of the published final version, not assumed to be first publication.',
                              'Last four actually available observations, not interpolated hourly series. Missing exact targets are excluded.',
                              'Raw directly measured station values may lack consolidated quality control and may contain sensor errors.',
                              'Station-specific validation does not establish transfer between stations or applicability to any trail or river crossing.',
                              'No precipitation reanalysis, synthetic labels, imputation, SMOTE or generated observations.',
                              'Only validation selects the model. Test comparison does not automatically approve operational use.',
                              'Snow has no fitted artifact; fire is evaluated independently in fire-results.json.']}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
