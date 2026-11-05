"""Paired temporal test comparison of the frozen MODIS and WRF fire models."""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from environmental_sources import sha256
from fire_sources import PRIVATE, PROTOCOL, REPORT_DIR, ROOT

BASE = PRIVATE / 'fire-temporal_test-predictions.csv.gz'
WEATHER = PRIVATE / 'smn-wrf-modis-test-predictions.csv.gz'
OUT = REPORT_DIR / 'fire-weather-vs-satellite-route-day-test.json'
THRESHOLD = 0.5


def metrics(grouped, column):
    y = grouped['observed'].to_numpy(dtype=np.uint8)
    score = grouped[column].to_numpy(dtype=float)
    predicted = score >= THRESHOLD
    tp = int(np.count_nonzero(predicted & (y == 1)))
    fp = int(np.count_nonzero(predicted & (y == 0)))
    fn = int(np.count_nonzero(~predicted & (y == 1)))
    return {'route_days': int(len(y)), 'positive_route_days': int(y.sum()),
        'alerts': int(predicted.sum()), 'matched_positive_route_days': tp,
        'unmatched_label_alerts': fp, 'missed_positive_route_days': fn,
        'proxy_precision': float(tp / (tp + fp)) if tp + fp else None,
        'proxy_recall': float(tp / (tp + fn)) if tp + fn else None,
        'average_precision': float(average_precision_score(y, score)) if y.sum() else None,
        'prevalence_baseline_ap': float(y.mean()) if len(y) else None,
        'threshold': THRESHOLD}


def main():
    base = pd.read_csv(BASE, usecols=['region', 'pixel_id', 'target_at', 'observed', 'xgboost'])
    # The protocol stores target_at as the exclusive end of the 24-hour valid
    # window. The observed MODIS label belongs to the preceding UTC calendar day.
    base['target_date'] = (pd.to_datetime(base['target_at'], utc=True)
        - pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    base = base.drop(columns='target_at')
    wrf = pd.read_csv(WEATHER, usecols=['region', 'pixel_id', 'target_date', 'label', 'risk_score'])
    joined = base.merge(wrf, on=['region', 'pixel_id', 'target_date'], how='inner', validate='one_to_one')
    paired_pixel_days = len(joined)
    label_disagreements = int((joined['observed'].astype(int) != joined['label'].astype(int)).sum())
    joined = joined[joined['observed'].astype(int) == joined['label'].astype(int)].copy()
    grouped = joined.groupby(['region', 'target_date'], observed=True, sort=True).agg(
        observed=('observed', 'max'), xgboost=('xgboost', 'max'), wrf=('risk_score', 'max'))
    result = {'experiment_id': 'paired-fire-weather-vs-satellite-route-day-test',
        'meaning': 'Paired comparison of frozen models on their common temporal test coverage against MODIS pixel detections; not physical-fire precision.',
        'inputs': {'temporal_test_predictions': {'path': BASE.relative_to(ROOT).as_posix(), 'sha256': sha256(BASE)},
                   'wrf_test_predictions': {'path': WEATHER.relative_to(ROOT).as_posix(), 'sha256': sha256(WEATHER)},
                   'protocol_sha256': sha256(PROTOCOL)},
        'protocol': {'unit': 'route-sector × UTC label date, max pixel score, positive if any matched pixel label is positive',
            'test_period': '2023-07-01 through 2023-12-31',
            'date_alignment': 'MODIS observed_date equals target_at minus one day because target_at is the exclusive end of the next-24h prediction window',
            'threshold': THRESHOLD, 'threshold_note': 'diagnostic frozen cutoff; no model or cutoff selection from the test'},
        'coverage': {'base_pixel_days': int(len(base)), 'wrf_pixel_days': int(len(wrf)),
            'paired_pixel_days': int(paired_pixel_days), 'paired_valid_label_pixel_days': int(len(joined)),
            'paired_positive_pixel_days': int(joined['observed'].sum()),
            'label_disagreements_excluded': label_disagreements,
            'common_route_days': int(len(grouped)), 'positive_common_route_days': int(grouped['observed'].sum())},
        'models': {'satellite_history_xgboost': metrics(grouped, 'xgboost'),
                   'weather_only_wrf': metrics(grouped, 'wrf')},
        'limitations': [
            'The target is MODIS satellite detection in sampled pixels, not an exhaustive inventory of physical fires or ignition time.',
            'Unmatched alert route-days mean no MODIS label in the sampled cells, not confirmed false fires.',
            'The shared test covers one six-month period and the model sampling footprint; it cannot support a stable national accuracy claim.',
            'The WRF cut was not selected on this test; 0.5 is diagnostic only, not a calibrated probability threshold.',
            'Weather coverage is limited to model-valid pixel-days within the WRF grid-distance rule.'
        ], 'synthetic_observations': 0, 'deployment_approved': False}
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': OUT.as_posix(), 'coverage': result['coverage'], 'models': result['models']},
        ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
