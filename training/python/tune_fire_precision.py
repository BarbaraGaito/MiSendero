"""Exploratory, validation-only tuning for fewer false fire-pixel alerts.

This experiment never updates the app artifact or the frozen fire-results.json.
It selects class weighting and a threshold using validation data only, then
measures the selected candidate once on the temporal and geographic holdouts.
"""
from datetime import datetime, timezone
import json

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_curve
from xgboost import XGBClassifier

from environmental_sources import sha256
from fire_features import FEATURES, load_cells, partitions
from fire_sources import PROTOCOL, OBSERVATIONS, PRIVATE, REPORT_DIR, protocol
from train_fire import prepare_frame

OUT = REPORT_DIR / 'fire-precision-tuning.json'
PRECISION_TARGET = 0.90
MIN_VALIDATION_ALERTS = 5
CLASS_WEIGHT_MULTIPLIERS = (0.02, 0.1, 0.5, 1.0)


def summarize(y, probability, threshold):
    y = np.asarray(y, dtype=np.uint8)
    p = np.asarray(probability, dtype=float)
    predicted = p >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel().tolist()
    return {
        'observations': int(y.size),
        'positives': int(y.sum()),
        'threshold': float(threshold),
        'predicted_positive_pixel_days': int(predicted.sum()),
        'true_positive_pixel_days': int(tp),
        'false_positive_pixel_days': int(fp),
        'false_negative_pixel_days': int(fn),
        'precision': float(tp / (tp + fp)) if tp + fp else None,
        'recall': float(tp / (tp + fn)) if tp + fn else None,
        'average_precision': float(average_precision_score(y, p)) if y.sum() else None,
        'confusion_matrix_tn_fp_fn_tp': [int(tn), int(fp), int(fn), int(tp)],
    }


def choose_threshold(y, probability):
    precision, recall, thresholds = precision_recall_curve(y, probability)
    feasible = []
    for index, threshold in enumerate(thresholds):
        predicted = int(np.count_nonzero(probability >= threshold))
        if predicted < MIN_VALIDATION_ALERTS or precision[index] < PRECISION_TARGET:
            continue
        feasible.append((float(recall[index]), float(precision[index]), -predicted, float(threshold), predicted))
    if not feasible:
        return None
    recall_value, precision_value, _, threshold_value, predicted = max(feasible)
    return {
        'threshold': threshold_value,
        'validation_precision': precision_value,
        'validation_recall': recall_value,
        'validation_alert_pixel_days': predicted,
    }


def main():
    plan = protocol()
    source_audit = REPORT_DIR / 'fire-source-audit.json'
    audit = json.loads(source_audit.read_text(encoding='utf-8'))
    if audit['protocol_sha256'] != sha256(PROTOCOL) or audit['summary']['observations_sha256'] != sha256(OBSERVATIONS):
        raise ValueError('Fire source/protocol hash mismatch')

    cells, quality = load_cells()
    frame, rejected, _metadata_path = prepare_frame(cells, plan)
    del cells
    split = partitions(frame, plan)
    train_mask, valid_mask = split['train'], split['validation']
    y_train = frame.loc[train_mask, 'observed'].to_numpy(dtype=np.uint8)
    y_valid = frame.loc[valid_mask, 'observed'].to_numpy(dtype=np.uint8)
    class_ratio = float(np.count_nonzero(y_train == 0) / np.count_nonzero(y_train == 1))

    candidates = []
    for multiplier in CLASS_WEIGHT_MULTIPLIERS:
        weight = class_ratio * multiplier
        model = XGBClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.05,
            objective='binary:logistic', tree_method='hist',
            scale_pos_weight=weight, subsample=1, colsample_bytree=1,
            random_state=42, n_jobs=2, eval_metric='logloss',
        )
        model.fit(frame.loc[train_mask, FEATURES], y_train, verbose=False)
        valid_p = model.predict_proba(frame.loc[valid_mask, FEATURES])[:, 1]
        ap = float(average_precision_score(y_valid, valid_p))
        threshold_choice = choose_threshold(y_valid, valid_p)
        candidates.append({
            'class_weight_multiplier': multiplier,
            'scale_pos_weight': weight,
            'validation_average_precision': ap,
            'validation_baseline_prevalence': float(y_valid.mean()),
            'threshold_choice': threshold_choice,
            '_model': model,
        })
        print(json.dumps({k: v for k, v in candidates[-1].items() if k != '_model'}, ensure_ascii=True), flush=True)

    eligible = [candidate for candidate in candidates if candidate['threshold_choice'] is not None]
    if eligible:
        selected = max(eligible, key=lambda item: (
            item['threshold_choice']['validation_recall'],
            item['threshold_choice']['validation_precision'],
            item['validation_average_precision'],
        ))
        status = 'selected_candidate'
    else:
        selected = max(candidates, key=lambda item: item['validation_average_precision'])
        status = 'no_validation_threshold_met_precision_target'

    test_metrics = {}
    if status == 'selected_candidate':
        model = selected['_model']
        threshold = selected['threshold_choice']['threshold']
        for split_name in ('temporal_test', 'geographic_test'):
            mask = split[split_name]
            if not mask.any():
                continue
            probability = model.predict_proba(frame.loc[mask, FEATURES])[:, 1]
            y = frame.loc[mask, 'observed'].to_numpy(dtype=np.uint8)
            test_metrics[split_name] = summarize(y, probability, threshold)

    cleaned_candidates = [{k: v for k, v in candidate.items() if k != '_model'} for candidate in candidates]
    result = {
        'experiment_id': 'fire-xgboost-validation-tuned-precision-candidate',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': status,
        'purpose': 'Exploratory reduction of false pixel-day alerts; no app artifact is written or approved.',
        'selection_protocol': {
            'class_weight_multipliers_of_frozen_training_class_ratio': list(CLASS_WEIGHT_MULTIPLIERS),
            'validation_precision_target': PRECISION_TARGET,
            'minimum_validation_alert_pixel_days': MIN_VALIDATION_ALERTS,
            'threshold_selection': 'Among candidates meeting the precision target and minimum alert count, maximize validation recall, then precision, then average precision.',
            'test_usage': 'The selected candidate is evaluated once on both frozen test splits; test metrics never select a model or threshold.',
        },
        'counts': {
            'train_rows': int(train_mask.sum()), 'train_positive_pixel_days': int(y_train.sum()),
            'validation_rows': int(valid_mask.sum()), 'validation_positive_pixel_days': int(y_valid.sum()),
            'class_ratio_before_weight_multiplier': class_ratio,
            'quality': quality, 'rejected_examples': rejected,
        },
        'candidate_validation_results': cleaned_candidates,
        'selected_candidate': {k: v for k, v in selected.items() if k != '_model'},
        'heldout_test_metrics': test_metrics,
        'limitations': [
            'Validation contains very few positive pixel-days; threshold selection can be unstable and requires a new independent dataset.',
            'Pixel-days are correlated in space and time, so row-level precision is not event-level fire precision.',
            'The labels are MODIS detections, not independently confirmed physical fires.',
            'This script does not modify the production artifact, app, or frozen baseline results.',
        ],
        'source_hashes': {
            'protocol_sha256': sha256(PROTOCOL),
            'source_audit_sha256': sha256(source_audit),
            'observations_sha256': sha256(OBSERVATIONS),
        },
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(OUT), 'status': status,
                      'selected': result['selected_candidate'], 'tests': test_metrics},
                     ensure_ascii=True, indent=2), flush=True)


if __name__ == '__main__':
    main()
