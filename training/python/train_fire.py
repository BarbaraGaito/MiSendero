"""Train and evaluate conditional next-24h satellite detection on real pixels."""
from datetime import datetime, timezone
from array import array
from collections import Counter
import csv
import gzip
import io
import json

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,
    confusion_matrix, f1_score, precision_score, recall_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import xgboost
from xgboost import XGBClassifier

from environmental_sources import sha256, utc
from fire_sources import OBSERVATIONS, PRIVATE, PROTOCOL, REPORT_DIR, protocol
from fire_features import FEATURES, iter_examples, load_cells, partitions

META_FIELDS = ['region', 'tile', 'pixel_id', 'issued_at', 'target_at', 'target_available_at', 'observed',
    'target_item_id', 'input_item_ids', 'input_dates', 'input_available_at']


def prepare_frame(cells, plan):
    """Stream metadata to disk and keep only a compact numerical matrix in RAM."""
    values, rejected, region_codes, tile_codes = array('d'), Counter(), {}, {}
    path = PRIVATE / 'fire-example-metadata.csv.gz'
    with path.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed, io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=META_FIELDS, extrasaction='ignore')
        writer.writeheader()
        for row in iter_examples(cells, plan, rejected):
            region_code = region_codes.setdefault(row['region'], len(region_codes))
            tile_code = tile_codes.setdefault(row['tile'], len(tile_codes))
            values.extend([row[k] for k in FEATURES] + [row['observed'],
                *(utc(row[k]).timestamp() for k in ('issued_at', 'target_at', 'target_available_at')), region_code, tile_code])
            writer.writerow(row)
    columns = FEATURES + ['observed', 'issued_at', 'target_at', 'target_available_at', 'region_code', 'tile_code']
    frame = pd.DataFrame(np.frombuffer(values, dtype=np.float64).reshape((-1, len(columns))), columns=columns)
    for name in ('issued_at', 'target_at', 'target_available_at'):
        frame[name] = pd.to_datetime(frame[name], unit='s', utc=True)
    frame['region'] = pd.Categorical.from_codes(frame.region_code.to_numpy(dtype=int), list(region_codes))
    frame['tile'] = pd.Categorical.from_codes(frame.tile_code.to_numpy(dtype=int), list(tile_codes))
    return frame, dict(rejected), path


def prediction_metadata(path, mask):
    pieces, offset = [], 0
    chosen = mask.to_numpy()
    for chunk in pd.read_csv(path, chunksize=20000):
        selected = chosen[offset:offset + len(chunk)]
        if selected.any():
            pieces.append(chunk.loc[selected])
        offset += len(chunk)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=META_FIELDS)


def scores(y, probability):
    predicted = np.asarray(probability) >= .5
    y = np.asarray(y)
    if not len(y):
        return {'observations': 0, 'positive_observations': 0, 'status': 'no_data'}
    bins = []
    for lower in np.arange(0, 1, .1):
        selected = (probability >= lower) & (probability < lower + .1 if lower < .9 else probability <= 1)
        if selected.any():
            bins.append({'lower': float(lower), 'count': int(selected.sum()),
                'mean_probability': float(np.mean(probability[selected])), 'observed_fraction': float(np.mean(y[selected]))})
    return {'observations': len(y), 'positive_observations': int(y.sum()),
        'accuracy': float(accuracy_score(y, predicted)), 'precision': float(precision_score(y, predicted, zero_division=0)),
        'recall': float(recall_score(y, predicted, zero_division=0)), 'f1': float(f1_score(y, predicted, zero_division=0)),
        'macro_f1': float(f1_score(y, predicted, average='macro', labels=[0, 1], zero_division=0)),
        'pr_auc_average_precision': float(average_precision_score(y, probability)) if y.sum() else None,
        'brier': float(brier_score_loss(y, probability)), 'confusion_labels': [0, 1],
        'confusion_matrix': confusion_matrix(y, predicted, labels=[0, 1]).tolist(), 'reliability_bins': bins}


def main():
    plan = protocol()
    source_path = REPORT_DIR / 'fire-source-audit.json'
    source = json.loads(source_path.read_text(encoding='utf-8'))
    if source['protocol_sha256'] != sha256(PROTOCOL) or source['summary']['observations_sha256'] != sha256(OBSERVATIONS):
        raise ValueError('Scientific source/protocol hash mismatch')
    cells, quality = load_cells()
    frame, excluded, meta_path = prepare_frame(cells, plan)
    del cells
    if frame.empty:
        raise ValueError('No causal examples from qualified observations')
    masks = partitions(frame, plan)
    counts = {name: {'observations': int(mask.sum()), 'positive_observations': int(frame.loc[mask, 'observed'].sum()),
        'tiles': sorted(frame.loc[mask, 'tile'].unique().tolist()), 'regions': sorted(frame.loc[mask, 'region'].unique().tolist())}
        for name, mask in masks.items()}
    print(json.dumps(counts, ensure_ascii=True), flush=True)
    report = {'model_type': 'fire_detection', 'status': 'experimental', 'deployment_approved': False,
        'protocol': plan, 'protocol_sha256': sha256(PROTOCOL), 'source_audit_sha256': sha256(source_path),
        'quality': quality, 'excluded_examples': excluded, 'partitions': counts, 'synthetic_observations': 0}
    blocked = [name for name, minimum in plan['minimum_positive_counts'].items()
        if counts[name]['positive_observations'] < minimum or counts[name]['observations'] - counts[name]['positive_observations'] < minimum]
    if blocked:
        report.update(status='no_data', reason='Insufficient real classes in fixed partitions: ' + ', '.join(blocked))
        (REPORT_DIR / 'fire-results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        raise SystemExit(report['reason'])
    train = masks['train']
    y = frame.observed
    prevalence = float(y[train].mean())
    months = frame.issued_at.dt.month
    seasonal = y[train].groupby(months[train]).mean().to_dict()
    class_ratio = float((y[train] == 0).sum() / (y[train] == 1).sum())
    models = {'training_prevalence': None, 'seasonal_training_prevalence': None, 'persistence': None,
        'logistic': make_pipeline(StandardScaler(), LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)),
        'random_forest': RandomForestClassifier(n_estimators=120, max_depth=8, min_samples_leaf=10,
            class_weight='balanced', random_state=42, n_jobs=2),
        'xgboost': XGBClassifier(n_estimators=150, max_depth=3, learning_rate=.05, objective='binary:logistic',
            tree_method='hist', scale_pos_weight=class_ratio, subsample=1, colsample_bytree=1, random_state=42, n_jobs=2)}
    def probabilities(name, mask):
        if name == 'training_prevalence':
            return np.full(int(mask.sum()), prevalence)
        if name == 'seasonal_training_prevalence':
            return months[mask].map(seasonal).fillna(prevalence).to_numpy()
        if name == 'persistence':
            return frame.loc[mask, 'latest_fire'].to_numpy(dtype=float)
        return models[name].predict_proba(frame.loc[mask, FEATURES])[:, 1]
    validation = {}
    for name, model in models.items():
        if model is not None:
            print('Fitting', name, int(train.sum()), 'original observations', flush=True)
            model.fit(frame.loc[train, FEATURES], y[train])
        validation[name] = scores(y[masks['validation']], probabilities(name, masks['validation']))
    selected = max(models, key=lambda n: validation[n]['pr_auc_average_precision'])
    tests, prediction_files = {}, {}
    for split in ('temporal_test', 'geographic_test'):
        mask = masks[split]
        predictions = prediction_metadata(meta_path, mask)
        tests[split] = {}
        for name in models:
            probability = probabilities(name, mask) if mask.any() else np.array([])
            predictions[name] = probability
            tests[split][name] = scores(y[mask], probability)
        path = PRIVATE / f'fire-{split}-predictions.csv.gz'
        predictions.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
        prediction_files[split] = {'path': str(path.relative_to(ROOT)), 'sha256': sha256(path)}
    model_path = PRIVATE / 'fire-mod14a1.joblib'
    if models[selected] is not None:
        joblib.dump(models[selected], model_path)
    monthly = {}
    test = masks['temporal_test']
    calendar_month = frame.issued_at.dt.year * 100 + frame.issued_at.dt.month
    for month in sorted(calendar_month[test].unique()):
        mask = test & (calendar_month == month)
        monthly[f'{month // 100:04d}-{month % 100:02d}'] = scores(y[mask], probabilities(selected, mask))
    report.update(selection=selected, validation=validation, test=tests, prediction_files=prediction_files,
        temporal_test_by_month=monthly, classification_threshold=.5, features=FEATURES,
        artifact={'id': 'fire-mod14a1-daily', 'version': '1', 'algorithm': selected,
            'model_file': model_path.name if models[selected] is not None else None,
            'model_sha256': sha256(model_path) if models[selected] is not None else None,
            'trained_at': datetime.now(timezone.utc).isoformat(), 'prevalence': prevalence,
            'seasonal_prevalence': seasonal, 'deployment_approved': False},
        versions={'numpy': np.__version__, 'pandas': pd.__version__, 'sklearn': sklearn.__version__, 'xgboost': xgboost.__version__},
        limitations=['Probabilities concern observed MODIS nominal/high-confidence detection in one pixel, not physical fire occurrence.',
            'No cloud, low-confidence, water or missing target is relabelled as non-fire.',
            'Historical features may be weeks old because full daily-band files are published after acquisition.',
            'Class weighting changes the fitted loss; no synthetic observations or minority oversampling used.',
            'Weighted classifiers are not assumed calibrated; Brier and reliability bins are reported on held-out data.',
            'Neighboring test pixels and days are correlated; row counts are not independent fire events.',
            'No recommendation to cross, evacuate or infer route safety; no operational approval.'])
    (REPORT_DIR / 'fire-results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print('Selected using validation only:', selected, '; temporal test', tests['temporal_test'][selected], flush=True)
    print('Geographic test', tests['geographic_test'][selected], flush=True)


if __name__ == '__main__':
    main()
