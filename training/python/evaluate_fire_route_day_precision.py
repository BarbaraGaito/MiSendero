"""Exploratory route-day threshold evaluation for the MODIS fire detector.

The operational unit is one route-sector per UTC day, not each sampled pixel.
Threshold and model weight are selected on the frozen validation split only.
Temporal and geographic test splits are reported once and never used to select.
This remains a satellite-detection proxy, not a physical-fire probability.
"""
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve
from xgboost import XGBClassifier

from environmental_sources import sha256
from fire_features import FEATURES, load_cells, partitions
from fire_sources import OBSERVATIONS, PRIVATE, PROTOCOL, REPORT_DIR, protocol
from train_fire import prepare_frame

OUT = REPORT_DIR / 'fire-route-day-threshold-evaluation.json'
PRECISION_TARGET = 0.90
MIN_VALIDATION_ALERTS = 5
WEIGHT_MULTIPLIERS = (0.02, 0.1, 0.5, 1.0)


def aggregate(frame, mask, probability):
    selected = frame.loc[mask, ['region', 'target_at', 'observed']].copy()
    selected['probability'] = np.asarray(probability, dtype=float)
    grouped = selected.groupby(['region', 'target_at'], observed=True, sort=True).agg(
        observed=('observed', 'max'), probability=('probability', 'max'))
    return grouped['observed'].to_numpy(dtype=np.uint8), grouped['probability'].to_numpy(dtype=float), grouped.index


def summarize(y, p, threshold):
    predicted = p >= threshold
    tp = int(np.count_nonzero(predicted & (y == 1)))
    fp = int(np.count_nonzero(predicted & (y == 0)))
    fn = int(np.count_nonzero(~predicted & (y == 1)))
    return {
        'route_days': int(y.size), 'positive_route_days': int(y.sum()),
        'alerts': int(predicted.sum()), 'true_positive_alerts': tp,
        'unmatched_alerts': fp, 'missed_positive_route_days': fn,
        'precision': float(tp / (tp + fp)) if tp + fp else None,
        'recall': float(tp / (tp + fn)) if tp + fn else None,
        'average_precision': float(average_precision_score(y, p)) if y.sum() else None,
        'threshold': float(threshold),
    }


def choose_threshold(y, p):
    precision, recall, thresholds = precision_recall_curve(y, p)
    candidates = []
    for i, threshold in enumerate(thresholds):
        alerts = int(np.count_nonzero(p >= threshold))
        if alerts >= MIN_VALIDATION_ALERTS and precision[i] >= PRECISION_TARGET:
            candidates.append((float(recall[i]), float(precision[i]), -alerts, float(threshold), alerts))
    if not candidates:
        return None
    recall, precision, _, threshold, alerts = max(candidates)
    return {'threshold': threshold, 'validation_precision': precision,
            'validation_recall': recall, 'validation_alerts': alerts}


def main():
    plan = protocol()
    source_audit = REPORT_DIR / 'fire-source-audit.json'
    audit = json.loads(source_audit.read_text(encoding='utf-8'))
    if (audit['protocol_sha256'] != sha256(PROTOCOL)
            or audit['summary']['observations_sha256'] != sha256(OBSERVATIONS)):
        raise ValueError('Fire source/protocol hash mismatch')
    cells, _quality = load_cells()
    frame, rejected, _metadata = prepare_frame(cells, plan)
    del cells
    masks = partitions(frame, plan)
    train_mask, valid_mask = masks['train'], masks['validation']
    y_train = frame.loc[train_mask, 'observed'].to_numpy(dtype=np.uint8)
    ratio = float(np.count_nonzero(y_train == 0) / max(1, np.count_nonzero(y_train == 1)))
    yv, pv, _ = aggregate(frame, valid_mask,
        frame.loc[valid_mask, 'latest_fire'].to_numpy(dtype=float))
    candidates = []

    for multiplier in WEIGHT_MULTIPLIERS:
        model = XGBClassifier(n_estimators=150, max_depth=3, learning_rate=0.05,
            objective='binary:logistic', tree_method='hist', scale_pos_weight=ratio * multiplier,
            subsample=1, colsample_bytree=1, random_state=42, n_jobs=2, eval_metric='logloss')
        model.fit(frame.loc[train_mask, FEATURES], y_train, verbose=False)
        val_probability = model.predict_proba(frame.loc[valid_mask, FEATURES])[:, 1]
        val_y, val_p, _ = aggregate(frame, valid_mask, val_probability)
        threshold = choose_threshold(val_y, val_p)
        candidates.append({'multiplier': multiplier, 'model': model,
            'validation_ap': float(average_precision_score(val_y, val_p)) if val_y.sum() else 0.0,
            'threshold': threshold, 'validation_y': val_y, 'validation_p': val_p})

    feasible = [item for item in candidates if item['threshold'] is not None]
    selected = max(feasible, key=lambda item: (item['threshold']['validation_recall'],
        item['threshold']['validation_precision'], item['validation_ap'])) if feasible else None
    baseline_validation = summarize(yv, pv, 0.5)
    tests = {}
    for split_name in ('temporal_test', 'geographic_test'):
        mask = masks[split_name]
        base_y, base_p, _ = aggregate(frame, mask,
            frame.loc[mask, 'latest_fire'].to_numpy(dtype=float))
        item = {'persistence_feature_at_0_5': summarize(base_y, base_p, 0.5)}
        saved_predictions = PRIVATE / f'fire-{split_name}-predictions.csv.gz'
        if saved_predictions.is_file():
            pred = pd.read_csv(saved_predictions)
            pred_grouped = pred.groupby(['region', 'target_at'], observed=True, sort=True).agg(
                observed=('observed', 'max'),
                xgboost=('xgboost', 'max'),
                persistence=('persistence', 'max'))
            saved_y = pred_grouped['observed'].to_numpy(dtype=np.uint8)
            item['previously_frozen_xgboost_diagnostic_at_0_5'] = summarize(
                saved_y, pred_grouped['xgboost'].to_numpy(dtype=float), 0.5)
            item['previously_frozen_persistence_diagnostic_at_0_5'] = summarize(
                saved_y, pred_grouped['persistence'].to_numpy(dtype=float), 0.5)
        if selected:
            probability = selected['model'].predict_proba(frame.loc[mask, FEATURES])[:, 1]
            model_y, model_p, _ = aggregate(frame, mask, probability)
            item['selected_model_at_0_5'] = summarize(model_y, model_p, 0.5)
            item['selected_model_at_validation_threshold'] = summarize(model_y, model_p,
                selected['threshold']['threshold'])
        tests[split_name] = item

    result = {
        'experiment_id': 'modis-fire-route-day-validation-threshold',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'validation_threshold_selected_model_unverified' if selected else 'no_validation_threshold_met',
        'meaning': 'Route-day agreement with MODIS nominal/high-confidence fire detections only; not physical-fire precision or probability.',
        'protocol_sha256': sha256(PROTOCOL),
        'source_audit_sha256': sha256(source_audit),
        'selection': {'unit': 'one route-sector × UTC target day; score=max sampled pixel score; label=any sampled pixel positive',
            'precision_target': PRECISION_TARGET, 'minimum_validation_alerts': MIN_VALIDATION_ALERTS,
            'weight_multipliers': list(WEIGHT_MULTIPLIERS),
            'selected_weight_multiplier': selected['multiplier'] if selected else None,
            'selected_threshold': selected['threshold'] if selected else None,
            'threshold_rule': 'max validation recall among thresholds with >=90% validation precision and >=5 validation route-day alerts',
            'baseline_validation_persistence_at_0_5': baseline_validation},
        'partitions': {name: {'pixel_days': int(mask.sum()),
            'positive_pixel_days': int(frame.loc[mask, 'observed'].sum()),
            'route_days': int(frame.loc[mask, ['region', 'target_at']].drop_duplicates().shape[0])}
            for name, mask in masks.items()},
        'candidate_validation': [{'weight_multiplier': item['multiplier'],
            'route_day_average_precision': item['validation_ap'],
            'threshold': item['threshold'],
            'at_diagnostic_threshold_0_5': summarize(item['validation_y'], item['validation_p'], 0.5)}
            for item in candidates],
        'tests': tests,
        'excluded_examples': rejected,
        'limitations': [
            'MOD14A1 labels detect satellite-observed fire in sampled native pixels; they do not establish ignition or exhaustive absence.',
            'Route-day aggregation reduces correlated pixel rows but route-sector-days remain temporally correlated.',
            'A high validation precision estimate is unstable with few positives and must be confirmed by prospective independent route-days.',
            'No selected model or threshold is written to the app or approved for operational decisions.'
        ],
        'synthetic_observations': 0, 'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': OUT.as_posix(), 'status': result['status'],
        'selected_weight_multiplier': result['selection']['selected_weight_multiplier'],
        'selected_threshold': result['selection']['selected_threshold'], 'tests': tests},
        ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
