#!/usr/bin/env python3
"""Evaluate short-lead GOES fire models at the route-sector-hour unit.

Reuses frozen pixel classifiers and the original December-2025 validation /
January-2026 test split. Route scores are maxima over valid sampled pixels,
so all reported metrics remain satellite-detection proxies, not physical-fire
precision. No model is retrained and no production artifact is changed.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss

import train_fire_hourly as hourly
from environmental_sources import PUBLIC, ROOT, sha256, utc


EXPERIMENT = 'fire-goes19-2025q4-2026jan'
OBS = PUBLIC / 'private' / f'{EXPERIMENT}-observations.csv.gz'
AVAILABILITY = PUBLIC / 'private' / f'{EXPERIMENT}-availability-by-scan.csv'
MODELS = PUBLIC / 'private' / f'{EXPERIMENT}-models'
TRAINING_REPORT = ROOT / 'docs/environmental-models-2026-10-22/fire-goes19-2025q4-2026jan-training-report.json'
OUT = ROOT / 'docs/environmental-models-2026-10-22/fire-goes19-short-lead-route-sector-evaluation.json'
OUT_MD = OUT.with_suffix('.md')
HORIZONS = (1, 2, 3, 6, 12)
VALIDATION_START = datetime.fromisoformat('2025-12-01T00:00:00+00:00')
TEST_START = datetime.fromisoformat('2026-01-01T00:00:00+00:00')
TEST_END = datetime.fromisoformat('2026-02-01T00:00:00+00:00')
ROUTE_COVERAGE_FRACTION = 0.50
MIN_ROUTE_PIXELS = 10
MIN_ALERTS_VALIDATION = 5
PRECISION_FLOOR = 0.80


def interval(successes: int, trials: int) -> list[float] | None:
    if not trials:
        return None
    from scipy.stats import beta
    alpha = 0.05
    low = 0.0 if successes == 0 else float(beta.ppf(alpha / 2, successes, trials - successes + 1))
    high = 1.0 if successes == trials else float(beta.ppf(1 - alpha / 2, successes + 1, trials - successes))
    return [low, high]


def collapse_hourly(rows: list[dict]) -> list[dict]:
    by_key = {}
    for row in rows:
        hour = row['hour'] if 'hour' in row else row['target_time'][:13]
        key = (row['region'], hour)
        item = by_key.setdefault(key, {
            'region': row['region'], 'hour': key[1], 'label': 0,
            'score': float('-inf'), 'persistence': 0,
            'observed_scans': 0,
        })
        item['label'] = max(item['label'], row['label'])
        item['score'] = max(item['score'], row['score'])
        item['persistence'] = max(item['persistence'], row['persistence'])
        item['observed_scans'] += 1
    return [by_key[key] for key in sorted(by_key)]


def alert_episode_count(rows: list[dict], threshold: float, field: str = 'score') -> dict:
    """Collapse adjacent route-hour alerts; positive if any labeled target hour is positive."""
    hourly_rows = collapse_hourly(rows)
    by_route: dict[str, list[dict]] = defaultdict(list)
    for row in hourly_rows:
        by_route[row['region']].append(row)
    episodes = []
    for route, route_rows in by_route.items():
        current = []
        for row in route_rows:
            alerted = row[field] >= threshold
            hour = datetime.fromisoformat(row['hour'] + ':00+00:00')
            contiguous = current and hour - datetime.fromisoformat(current[-1]['hour'] + ':00+00:00') <= timedelta(hours=1)
            if alerted:
                if current and not contiguous:
                    episodes.append((route, current))
                    current = []
                current.append(row)
            elif current:
                episodes.append((route, current))
                current = []
        if current:
            episodes.append((route, current))
    positive_episodes = sum(any(row['label'] == 1 for row in episode) for _, episode in episodes)
    details = [
        {
            'route_sector': route,
            'start_hour_utc': episode[0]['hour'],
            'end_hour_utc': episode[-1]['hour'],
            'hours': len(episode),
            'positive_goes_detection_hours': sum(row['label'] == 1 for row in episode),
        }
        for route, episode in episodes
    ] if field == 'score' else None
    return {
        'alert_episodes': len(episodes),
        'positive_alert_episodes': positive_episodes,
        'precision_proxy': positive_episodes / len(episodes) if episodes else None,
        'precision_exact_95ci_descriptive': interval(positive_episodes, len(episodes)),
        'episode_details': details,
        'independence_warning': 'Consecutive alerts were grouped by route and hour; distinct routes may still share one physical fire and this remains a GOES-label proxy.',
    }


def metrics(rows: list[dict], threshold: float, prevalence: float) -> dict:
    y = np.asarray([row['label'] for row in rows], dtype=np.uint8)
    scores = np.asarray([row['score'] for row in rows], dtype=np.float64)
    persistence_scores = np.asarray([row['persistence'] for row in rows], dtype=np.uint8)
    alerts = scores >= threshold
    tp = int(np.sum(alerts & (y == 1)))
    n_alerts = int(alerts.sum())
    persistence_alerts = persistence_scores > 0
    persistence_tp = int(np.sum(persistence_alerts & (y == 1)))
    persistence_count = int(persistence_alerts.sum())
    return {
        'route_sector_hours': len(rows),
        'positive_route_sector_hours': int(y.sum()),
        'prevalence': float(y.mean()) if len(y) else None,
        'average_precision': float(average_precision_score(y, scores)) if y.sum() else None,
        'brier_score_class_weighted_scores_not_calibrated': float(brier_score_loss(y, scores)) if len(y) else None,
        'threshold': threshold,
        'alerts': n_alerts,
        'true_positive_alerts': tp,
        'precision_proxy': tp / n_alerts if n_alerts else None,
        'precision_exact_95ci_descriptive': interval(tp, n_alerts),
        'recall_proxy': tp / int(y.sum()) if y.sum() else None,
        'alert_episodes': alert_episode_count(rows, threshold),
        'persistence_baseline': {
            'alerts': persistence_count,
            'true_positive_alerts': persistence_tp,
            'precision_proxy': persistence_tp / persistence_count if persistence_count else None,
            'precision_exact_95ci_descriptive': interval(persistence_tp, persistence_count),
            'recall_proxy': persistence_tp / int(y.sum()) if y.sum() else None,
            'alert_episodes': alert_episode_count(rows, 1, field='persistence'),
        },
        'prevalence_baseline_brier': float(brier_score_loss(y, np.full(len(y), prevalence))) if len(y) else None,
    }


def choose_threshold(rows: list[dict], prevalence: float) -> dict:
    hourly_rows = collapse_hourly(rows)
    unique_scores = sorted({float(row['score']) for row in hourly_rows}, reverse=True)
    y = np.asarray([row['label'] for row in hourly_rows], dtype=np.uint8)
    scores = np.asarray([row['score'] for row in hourly_rows], dtype=np.float64)
    eligible = []
    best_fallback = None
    for threshold in unique_scores:
        alert = scores >= threshold
        alert_count = int(alert.sum())
        if alert_count < MIN_ALERTS_VALIDATION:
            continue
        tp = int(np.sum(alert & (y == 1)))
        precision = tp / alert_count
        recall = tp / int(y.sum()) if y.sum() else 0.0
        simple = {'threshold': threshold, 'alerts': alert_count, 'true_positive_alerts': tp,
                  'precision_proxy': precision, 'recall_proxy': recall}
        if best_fallback is None or precision > best_fallback['precision_proxy'] or (
            precision == best_fallback['precision_proxy'] and recall > best_fallback['recall_proxy']
        ):
            best_fallback = simple
        if precision >= PRECISION_FLOOR:
            eligible.append((recall, precision, threshold))
    if not eligible:
        return {
            'selected': False,
            'reason': f'No validation threshold achieved route-sector-hour proxy precision >= {PRECISION_FLOOR:.0%} with at least {MIN_ALERTS_VALIDATION} alerts.',
            'best_validation_precision_with_at_least_minimum_alerts': best_fallback,
        }
    _, _, threshold = max(eligible, key=lambda item: (item[0], item[1], item[2]))
    result = metrics(hourly_rows, threshold, prevalence)
    return {'selected': True, 'threshold': threshold, 'validation_result': result}


def main() -> None:
    hourly.EXPERIMENT = EXPERIMENT
    hourly.OBS = OBS
    hourly.AVAILABILITY = AVAILABILITY
    times, created, matrix, coordinates, regions = hourly.load_arrays()
    region_columns = {
        region: np.asarray([idx for idx, item in enumerate(regions) if item == region], dtype=np.int64)
        for region in sorted(set(regions))
    }
    models = {horizon: joblib.load(MODELS / f'logistic-{horizon}h.joblib') for horizon in HORIZONS}
    rows_by_horizon: dict[int, list[dict]] = {horizon: [] for horizon in HORIZONS}
    pair_counts = {horizon: 0 for horizon in HORIZONS}
    # Compute the costly satellite history features once per issue scan and reuse
    # them for every target lead.
    for issue, issue_time in enumerate(created):
        targets = {}
        for horizon in HORIZONS:
            wanted = issue_time + timedelta(hours=horizon)
            target = min(
                range(issue + 1, len(created)),
                key=lambda idx: abs((created[idx] - wanted).total_seconds()),
                default=None,
            )
            if target is not None and abs((created[target] - wanted).total_seconds()) <= 15 * 60:
                target_time = created[target]
                if VALIDATION_START <= target_time < TEST_END:
                    targets[horizon] = (target, target_time)
                    pair_counts[horizon] += 1
        if not targets:
            continue
        features, usable = hourly.issue_features(issue, created, matrix, coordinates)
        for horizon, (target, target_time) in targets.items():
            labels = matrix[target]
            part = 'validation' if target_time < TEST_START else 'test'
            model = models[horizon]
            scores = np.full(matrix.shape[1], np.nan, dtype=np.float32)
            valid_history = np.flatnonzero(usable & (labels >= 0))
            if len(valid_history):
                scores[valid_history] = model.predict_proba(features[valid_history])[:, 1]
            for region, cols in region_columns.items():
                valid_target = cols[labels[cols] >= 0]
                if len(valid_target) < max(MIN_ROUTE_PIXELS, int(ROUTE_COVERAGE_FRACTION * len(cols))):
                    continue
                usable_target = cols[usable[cols] & (labels[cols] >= 0)]
                if len(usable_target) < max(MIN_ROUTE_PIXELS, int(0.25 * len(cols))):
                    continue
                rows_by_horizon[horizon].append({
                    'partition': part,
                    'region': region,
                    'target_time': target_time.isoformat(),
                    'label': int(np.any(labels[valid_target] == 1)),
                    'score': float(np.nanmax(scores[usable_target])),
                    'persistence': int(np.any(features[usable_target, 6] == 1)),
                })
    training = json.loads(TRAINING_REPORT.read_text(encoding='utf-8'))
    output = {
        'experiment_id': 'goes19-short-lead-route-sector-hour-alert-evaluation',
        'status': 'exploratory_unapproved',
        'target': 'Any nominal/high-quality GOES FDCF fire detection in a sampled fixed route sector during an hourly target bin; not confirmed physical wildfire occurrence or ignition.',
        'protocol': {
            'frozen_model_source': TRAINING_REPORT.relative_to(ROOT).as_posix(),
            'forecast_horizons_hours': list(HORIZONS),
            'training_classifier': 'Existing class-weighted logistic classifiers trained at pixel-scan level; no refit in this audit.',
            'route_aggregation': 'For each valid target scan, max predicted score among valid-history pixels; group target scans into route-sector-hour bins using max score and any positive target pixel.',
            'coverage_rule': f'At least {MIN_ROUTE_PIXELS} target pixels and {ROUTE_COVERAGE_FRACTION:.0%} of the fixed sector pixels must have valid target labels; at least 25% of sector pixels must have usable history.',
            'validation_period': ['2025-12-01', '2025-12-31'],
            'test_period': ['2026-01-01', '2026-01-31'],
            'threshold_gate': f'Validation route-sector-hour proxy precision >= {PRECISION_FLOOR:.0%} and at least {MIN_ALERTS_VALIDATION} alerts; maximize recall among eligible thresholds.',
            'confidence_intervals': 'Exact binomial intervals are descriptive and overstate certainty if alerts within an event are dependent.',
        },
        'inputs': {
            'goes_observations_sha256': sha256(OBS),
            'goes_availability_sha256': sha256(AVAILABILITY),
            'training_report_sha256': sha256(TRAINING_REPORT),
        },
        'results_by_horizon': {},
        'limitations': [
            'This predicts another GOES product label, not independently confirmed physical wildfire or future ignition.',
            'A route sector covers a fixed sampled corridor; it does not use full trail polylines and cannot represent the entire route.',
            'Hourly bins and adjacent alert episodes are temporally dependent.',
            'The SNMF external event check has sparse corridor coverage and cannot estimate precision.',
            'No score is approved for display or safety decisions.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    for horizon in HORIZONS:
        model_path = MODELS / f'logistic-{horizon}h.joblib'
        all_rows = rows_by_horizon[horizon]
        validation_rows = [row for row in all_rows if row['partition'] == 'validation']
        test_rows = [row for row in all_rows if row['partition'] == 'test']
        train_count = training['rows_by_horizon'][str(horizon)]['training_positives']
        prevalence = train_count / training['rows_by_horizon'][str(horizon)]['training_rows']
        threshold = choose_threshold(validation_rows, prevalence)
        threshold_value = threshold.get('threshold') if threshold['selected'] else 0.5
        validation_hourly = collapse_hourly(validation_rows)
        test_hourly = collapse_hourly(test_rows)
        output['results_by_horizon'][str(horizon)] = {
            'frozen_model_sha256': sha256(model_path),
            'matched_issue_target_scan_pairs': pair_counts[horizon],
            'validation_route_sector_scan_rows': len(validation_rows),
            'test_route_sector_scan_rows': len(test_rows),
            'validation_route_sector_hours': len(validation_hourly),
            'test_route_sector_hours': len(test_hourly),
            'validation_threshold': threshold,
            'selected_or_diagnostic_threshold': threshold_value,
            'validation': metrics(validation_hourly, threshold_value, prevalence),
            'test': metrics(test_hourly, threshold_value, prevalence),
            'test_at_fixed_0_5_diagnostic': metrics(test_hourly, 0.5, prevalence),
            'model_file': model_path.relative_to(ROOT).as_posix(),
        }
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        '# GOES G19: evaluaci?n por horizonte a nivel de sendero', '',
        'Se evaluaron los clasificadores GOES G19 ya entrenados para 1, 2, 3, 6 y 12 horas, agregando sus scores desde p?xeles a la unidad ruta-sector-hora. La validaci?n sigue siendo diciembre de 2025 y enero de 2026 queda como test reservado. No se volvi? a entrenar ning?n modelo.', '',
        '| Horizonte | Horas ruta-sector validaci?n | Positivos validaci?n | Selecci?n en validaci?n | Avisos test (0,5 diagn?stico) | TP test | Precisi?n proxy test | Recall proxy test | Episodios de aviso test |',
        '|---:|---:|---:|---|---:|---:|---:|---:|---:|',
    ]
    for horizon, item in output['results_by_horizon'].items():
        diagnostic = item['test_at_fixed_0_5_diagnostic']
        precision = 'n/a' if diagnostic['precision_proxy'] is None else f"{diagnostic['precision_proxy']:.1%}"
        recall = 'n/a' if diagnostic['recall_proxy'] is None else f"{diagnostic['recall_proxy']:.1%}"
        gate = item['validation_threshold']
        if gate['selected']:
            selection = f"seleccionado {gate['threshold']:.6g}"
        else:
            best = gate['best_validation_precision_with_at_least_minimum_alerts']
            selection = f"ninguno; mejor {best['true_positive_alerts']}/{best['alerts']} = {best['precision_proxy']:.1%}"
        lines.append(
            f"| {horizon} | {item['validation_route_sector_hours']} | {item['validation']['positive_route_sector_hours']} | {selection} | {diagnostic['alerts']} | {diagnostic['true_positive_alerts']} | {precision} | {recall} | {diagnostic['alert_episodes']['alert_episodes']} ({diagnostic['alert_episodes']['positive_alert_episodes']} con detecci?n GOES) |"
        )
    lines += [
        '',
        'La puerta de selecci?n exige precisi?n proxy de 80% y al menos cinco avisos de ruta-hora en validaci?n. Los resultados de test con corte 0,5 son diagn?sticos y no representan un corte operativo seleccionado. En 1 h, el mejor corte elegible en validaci?n obtuvo 8/11 = 72,7%, por debajo del criterio; en los dem?s horizontes tampoco se seleccion? un corte.', '',
        'Estos resultados eval?an detecciones GOES nominales/altas, no incendios f?sicos confirmados ni la hora de ignici?n. Los intervalos por aviso pueden ser demasiado estrechos por la dependencia temporal; los conteos de episodios reducen, pero no eliminan, esa dependencia. El cruce SNMF independiente tampoco ofrece suficientes eventos cubiertos para estimar precisi?n f?sica. Por eso esta prueba puede comparar horizontes de detecci?n satelital, pero no autoriza alertas de seguridad.', '',
        f"Detalle por horizonte, criterios de cobertura, hashes y limitaciones: [JSON]({OUT.name}). Modelos congelados: [informe de entrenamiento](fire-goes19-2025q4-2026jan-training-report.json). Reproducci?n: [`evaluate_goes_hourly_route_sector_horizons.py`](../../training/python/evaluate_goes_hourly_route_sector_horizons.py).", '',
    ]
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'json': OUT.relative_to(ROOT).as_posix(), 'markdown': OUT_MD.relative_to(ROOT).as_posix(),
        'results_by_horizon': {h: {'threshold_selected': row['validation_threshold']['selected'],
            'threshold': row['selected_or_diagnostic_threshold'], 'test': row['test']}
            for h, row in output['results_by_horizon'].items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
