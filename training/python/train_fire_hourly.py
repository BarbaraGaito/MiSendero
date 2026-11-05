"""Exploratory short-lead GOES fire-pixel model; never writes an app artifact."""
from collections import defaultdict
from datetime import datetime, timedelta
import sys
import csv
import gzip
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_curve, precision_score, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from environmental_sources import PUBLIC, ROOT, sha256, utc
from fire_sources import PRIVATE, REPORT_DIR

EXPERIMENT = 'fire-goes16-2025-q1'
OBS = PRIVATE / f'{EXPERIMENT}-observations.csv.gz'
AVAILABILITY = PRIVATE / f'{EXPERIMENT}-availability-by-scan.csv'
MODEL_DIR = PRIVATE / f'{EXPERIMENT}-models'
REPORT = REPORT_DIR / f'{EXPERIMENT}-training-report.json'
HORIZONS = (1, 2, 3, 6, 12)
FEATURES = ['latitude', 'longitude', 'day_sin', 'day_cos', 'hour_sin', 'hour_cos',
    'latest_fire', 'latest_age_hours', 'history_count', 'history_fire_fraction',
    'history_1', 'history_2', 'history_3', 'history_4']


def load_arrays():
    availability = {}
    with AVAILABILITY.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            availability[row['source_id']] = utc(row['product_created_at'])
    times, keys, labels_by_time, coordinates = [], {}, [], {}
    with gzip.open(OBS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            timestamp = row['scan_start']
            if not times or times[-1] != timestamp:
                times.append(timestamp)
                labels_by_time.append({})
            key = (row['region'], row['pixel_id'])
            col = keys.setdefault(key, len(keys))
            coordinates[key] = (float(row['latitude']), float(row['longitude']))
            mask, dqf = int(row['mask']), int(row['dqf'])
            label = 1 if dqf == 0 and mask in (10, 11, 30, 31) else 0 if dqf == 1 and mask == 100 else -1
            labels_by_time[-1][col] = label
    matrix = np.full((len(times), len(keys)), -1, dtype=np.int8)
    for index, frame in enumerate(labels_by_time):
        for col, label in frame.items():
            matrix[index, col] = label
    created = []
    for timestamp in times:
        # Match this scan to the original product-creation timestamp using the
        # acquisition file represented by its first observation row.
        created.append(None)
    # Resolve once from original IDs without retaining the full observation table.
    source_by_scan = {}
    with gzip.open(OBS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            source_by_scan.setdefault(row['scan_start'], row['source_id'])
    created = [availability[source_by_scan[t]] for t in times]
    coord = np.zeros((len(keys), 2), dtype=np.float32)
    regions = [''] * len(keys)
    for key, col in keys.items():
        coord[col] = coordinates[key]
        regions[col] = key[0]
    return times, created, matrix, coord, regions


def issue_features(issue, created, matrix, coord):
    issue_time = created[issue]
    first = max(0, issue - 8)
    candidate = matrix[first:issue + 1][::-1]
    candidate_times = created[first:issue + 1][::-1]
    features = np.full((matrix.shape[1], len(FEATURES)), np.nan, dtype=np.float32)
    features[:, :2] = coord
    day = issue_time.timetuple().tm_yday
    angle = 2 * np.pi * day / 365.2425
    features[:, 2:4] = (np.sin(angle), np.cos(angle))
    hour_angle = 2 * np.pi * (issue_time.hour + issue_time.minute / 60) / 24
    features[:, 4:6] = (np.sin(hour_angle), np.cos(hour_angle))
    selected = np.full((4, matrix.shape[1]), -1, dtype=np.int8)
    ranks = np.zeros(matrix.shape[1], dtype=np.int8)
    latest_age = np.full(matrix.shape[1], np.nan, dtype=np.float32)
    for offset, (stamp, row) in enumerate(zip(candidate_times, candidate)):
        age = (issue_time - stamp).total_seconds() / 3600
        if age < 0 or age > 8:
            continue
        valid = (row >= 0) & (ranks < 4)
        if offset == 0:
            latest_age[valid] = age
        cols = np.flatnonzero(valid)
        selected[ranks[cols], cols] = row[cols]
        ranks[cols] += 1
    latest = selected[0]
    good = (ranks > 0) & (latest_age <= 3)
    features[good, 6] = latest[good]
    features[good, 7] = latest_age[good]
    features[good, 8] = ranks[good]
    observed = selected >= 0
    sums = np.where(observed, selected, 0).sum(axis=0)
    counts = observed.sum(axis=0)
    features[good, 9] = sums[good] / counts[good]
    features[good, 10:14] = selected[:, good].T
    return features, good


def main():
    global EXPERIMENT, OBS, AVAILABILITY, MODEL_DIR, REPORT
    protocol_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PUBLIC / f'{EXPERIMENT}-protocol.json'
    config = json.loads(protocol_path.read_text(encoding='utf-8'))
    EXPERIMENT = config.get('experiment_id', EXPERIMENT)
    OBS = PRIVATE / f'{EXPERIMENT}-observations.csv.gz'
    AVAILABILITY = PRIVATE / f'{EXPERIMENT}-availability-by-scan.csv'
    MODEL_DIR = PRIVATE / f'{EXPERIMENT}-models'
    REPORT = REPORT_DIR / f'{EXPERIMENT}-training-report.json'
    if not AVAILABILITY.exists():
        raise FileNotFoundError(f'Missing independent availability audit: {AVAILABILITY}')
    split = config.get('temporal_split', {})
    validation_start = utc(split.get('validation_start', '2025-02-01T00:00:00Z')).date()
    test_start = utc(split.get('test_start', '2025-03-01T00:00:00Z')).date()
    test_end = utc(split.get('test_end_exclusive', '2025-04-01T00:00:00Z')).date()
    if not validation_start < test_start < test_end:
        raise ValueError('Temporal split must be chronological and non-empty')
    times, created, matrix, coord, regions = load_arrays()
    results = {'experiment_id': EXPERIMENT, 'protocol_sha256': sha256(protocol_path),
        'temporal_split': {'validation_start': validation_start.isoformat(), 'test_start': test_start.isoformat(), 'test_end_exclusive': test_end.isoformat()},
        'source_sha256': sha256(OBS),
        'availability_sha256': sha256(AVAILABILITY), 'rows_by_horizon': {},
        'selection': 'Exploratory only; no horizon authorized for app use.', 'deployment_approved': False}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for horizon in HORIZONS:
        train_X, train_y, valid_X, valid_y, test_X, test_y = [], [], [], [], [], []
        partition_region_days = {'train': set(), 'validation': set(), 'test': set()}
        pairs = 0
        for issue, issued_at in enumerate(created):
            wanted = issued_at + timedelta(hours=horizon)
            target = min(range(issue + 1, len(created)), key=lambda j: abs((created[j] - wanted).total_seconds()), default=None)
            if target is None or abs((created[target] - wanted).total_seconds()) > 15 * 60:
                continue
            pairs += 1
            features, usable = issue_features(issue, created, matrix, coord)
            labels = matrix[target]
            usable &= labels >= 0
            if not usable.any():
                continue
            X, y = features[usable], labels[usable].astype(np.uint8)
            target_date = created[target].date()
            if target_date < validation_start:
                bucket, target_y = train_X, train_y
                partition = 'train'
            elif target_date < test_start:
                bucket, target_y = valid_X, valid_y
                partition = 'validation'
            elif target_date < test_end:
                bucket, target_y = test_X, test_y
                partition = 'test'
            else:
                continue
            bucket.append(X); target_y.append(y)
            partition_region_days[partition].update((regions[int(col)], target_date.isoformat())
                for col in np.flatnonzero(usable & (labels == 1)))
        if not train_X or not valid_X or not test_X:
            results['rows_by_horizon'][str(horizon)] = {'status': 'insufficient_temporal_partition', 'matched_pairs': pairs}
            continue
        X_train, y_train = np.concatenate(train_X), np.concatenate(train_y)
        X_valid, y_valid = np.concatenate(valid_X), np.concatenate(valid_y)
        X_test, y_test = np.concatenate(test_X), np.concatenate(test_y)
        sparse_partitions = [name for name, values in [('train', y_train), ('validation', y_valid), ('test', y_test)] if values.sum() < 20]
        model = make_pipeline(StandardScaler(), LogisticRegression(class_weight='balanced', max_iter=500, random_state=42))
        model.fit(X_train, y_train)
        model_path = MODEL_DIR / f'logistic-{horizon}h.joblib'
        joblib.dump(model, model_path, compress=3)
        row = results['rows_by_horizon'].setdefault(str(horizon), {})
        validation_probability = model.predict_proba(X_valid)[:, 1]
        precision_curve, recall_curve, thresholds = precision_recall_curve(y_valid, validation_probability)
        eligible = np.flatnonzero((precision_curve[:-1] >= 0.80) & (recall_curve[:-1] > 0))
        selected_threshold = float(thresholds[eligible[np.argmax(recall_curve[eligible])]]) if len(eligible) else None
        for name, X, y in [('validation', X_valid, y_valid), ('test', X_test, y_test)]:
            probabilities = model.predict_proba(X)[:, 1]
            prediction = probabilities >= 0.5
            row[name] = {'average_precision': float(average_precision_score(y, probabilities)),
                'brier': float(brier_score_loss(y, probabilities)),
                'precision_at_0_5': float(precision_score(y, prediction, zero_division=0)),
                'recall_at_0_5': float(recall_score(y, prediction, zero_division=0)),
                'rows': len(y), 'positives': int(y.sum())}
            persistence = (X[:, 6] == 1).astype(np.uint8)
            row[name]['persistence_baseline'] = {
                'average_precision': float(average_precision_score(y, persistence)),
                'brier': float(brier_score_loss(y, persistence)),
                'precision': float(precision_score(y, persistence, zero_division=0)),
                'recall': float(recall_score(y, persistence, zero_division=0)),
            }
            prevalence = float(y_train.mean())
            row[name]['training_prevalence_baseline'] = {
                'average_precision': prevalence, 'brier': float(brier_score_loss(y, np.full(len(y), prevalence)))
            }
            if selected_threshold is not None:
                selected = probabilities >= selected_threshold
                row[name]['validation_selected_threshold'] = selected_threshold
                row[name]['at_validation_precision_floor_0_80'] = {
                    'precision': float(precision_score(y, selected, zero_division=0)),
                    'recall': float(recall_score(y, selected, zero_division=0)),
                    'predicted_positive_rows': int(selected.sum()),
                }
        row.update(status='trained_exploratory_with_sparse_partitions' if sparse_partitions else 'trained_exploratory',
            sparse_positive_partitions=sparse_partitions,
            positive_region_days_by_partition={name: len(values) for name, values in partition_region_days.items()},
            region_day_caution='A region-day is not an independent physical wildfire event; multiple regions may observe the same fire and adjacent days are correlated.',
            model_sha256=sha256(model_path), model_path=model_path.relative_to(ROOT).as_posix(),
            training_rows=len(y_train), training_positives=int(y_train.sum()), matched_pairs=pairs,
            note='Class-weighted scores are not calibrated probabilities; repeated pixels and scenes are correlated.')
        print(f'{horizon}h', json.dumps(row), flush=True)
    REPORT.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    main()
