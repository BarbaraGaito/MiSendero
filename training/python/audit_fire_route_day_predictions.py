"""Aggregate frozen fire-model pixel predictions to route-sector UTC days."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from environmental_sources import sha256
from fire_sources import PRIVATE, REPORT_DIR

OUT = REPORT_DIR / 'fire-route-day-prediction-audit.json'
THRESHOLD = 0.5


def summarize(grouped, score_column):
    y = grouped['observed'].to_numpy(dtype=np.uint8)
    probability = grouped[score_column].to_numpy(dtype=float)
    alert = probability >= THRESHOLD
    tp = int(np.count_nonzero(alert & (y == 1)))
    fp = int(np.count_nonzero(alert & (y == 0)))
    fn = int(np.count_nonzero(~alert & (y == 1)))
    return {'route_days': int(len(y)), 'positive_route_days': int(y.sum()),
        'alerts': int(alert.sum()), 'matched_positive_route_days': tp,
        'unmatched_alert_route_days': fp, 'missed_positive_route_days': fn,
        'proxy_precision': float(tp / (tp + fp)) if tp + fp else None,
        'proxy_recall': float(tp / (tp + fn)) if tp + fn else None,
        'route_day_average_precision': float(average_precision_score(y, probability)) if y.sum() else None,
        'threshold': THRESHOLD}


def main():
    partitions = {}
    for split in ('temporal_test', 'geographic_test'):
        path = PRIVATE / f'fire-{split}-predictions.csv.gz'
        if not path.is_file():
            raise FileNotFoundError(path)
        frame = pd.read_csv(path)
        grouped = frame.groupby(['region', 'target_at'], observed=True, sort=True).agg(
            observed=('observed', 'max'), xgboost=('xgboost', 'max'),
            persistence=('persistence', 'max'))
        partitions[split] = {'input_sha256': sha256(path),
            'pixel_days': int(len(frame)),
            'unit': 'one route-sector × UTC target day; positive if any sampled pixel is positive; score is maximum sampled-pixel score',
            'xgboost': summarize(grouped, 'xgboost'),
            'persistence': summarize(grouped, 'persistence')}
    result = {'experiment_id': 'frozen-fire-model-route-day-audit',
        'meaning': 'Proxy agreement with MOD14A1 nominal/high-confidence pixel detections; not precision for physical fires.',
        'protocol_sha256': sha256(Path('training/data/environmental/fire-protocol.json')),
        'threshold': THRESHOLD, 'partitions': partitions,
        'limitations': [
            'Prediction rows were grouped to the route-sector/day unit before computing alert counts.',
            'A route-day without a MODIS detection is not proven fire-free; therefore proxy precision can underestimate physical-fire precision.',
            'MODIS positive detections are still only a sparse subset and these results do not validate ignition prediction.',
            'The fixed threshold is from the frozen existing model protocol; no test threshold was tuned here.',
            'The geographic test has very few positive route-days, so it cannot support a reliable geographic performance estimate.'
        ], 'synthetic_observations': 0, 'deployment_approved': False}
    output = REPORT_DIR / OUT.name
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': output.as_posix(), 'partitions': partitions}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
