"""Year-held-out JMA GSM transfer test for SNMF-reported route-day fires.

Research-only experiment. It evaluates reported-incident proximity, not
physical fire absence, ignition probability, or trail safety.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
    brier_score_loss, confusion_matrix, precision_score, recall_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from environmental_sources import ROOT, sha256
from train_snmf_report_proxy_gfs_model import load_weather_with_geography

BASE = ROOT / 'docs/environmental-models-2026-10-22'
PRIVATE = ROOT / 'training/data/environmental/private'
WEATHER_FILES = [
    PRIVATE / 'openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2023-07-01-2024-01-01.json.gz',
    PRIVATE / 'openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2024-01-01-2025-01-01.json.gz',
]
PROXY_FILES = [BASE / 'snmf-2023-route-day-report-proxy.json', BASE / 'snmf-2024-route-day-report-proxy.json']
NO_FIRE_FILE = BASE / 'fire-snmf-national-no-fire-report-audit.json'
THRESHOLDS = (0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9)
OUT = BASE / 'fire-jma-2023-train-2024-test-snmf-report-proxy.json'
OUT_MD = BASE / 'fire-jma-2023-train-2024-test-snmf-report-proxy.md'


def route_day_clusters(rows: list[dict]) -> int:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        grouped[row['region']].add(row['date'])
    clusters = 0
    for values in grouped.values():
        previous: date | None = None
        for value in sorted(date.fromisoformat(day) for day in values):
            if previous is None or (value - previous).days > 1:
                clusters += 1
            previous = value
    return clusters


def date_clusters(days: list[str]) -> int:
    clusters = 0
    previous: date | None = None
    for value in sorted(date.fromisoformat(item) for item in set(days)):
        if previous is None or (value - previous).days > 1:
            clusters += 1
        previous = value
    return clusters


def binary_metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    predicted = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {
        'threshold': threshold,
        'true_positives': int(tp),
        'false_positives': int(fp),
        'false_negatives': int(fn),
        'true_negatives': int(tn),
        'alerts': int(predicted.sum()),
        'precision_on_report_proxy': float(precision_score(y, predicted, zero_division=0)),
        'recall_on_report_proxy': float(recall_score(y, predicted, zero_division=0)),
        'accuracy_on_report_proxy': float(accuracy_score(y, predicted)),
    }


def main() -> None:
    if not all(path.is_file() for path in WEATHER_FILES + PROXY_FILES + [NO_FIRE_FILE]):
        raise FileNotFoundError('Required archived JMA weather, SNMF proxy, or no-fire audit file is missing.')
    daily = load_weather_with_geography(WEATHER_FILES)
    label_rows = []
    for path in PROXY_FILES:
        proxy = json.loads(path.read_text(encoding='utf-8'))
        for row in proxy['route_days']:
            label_rows.append({
                'region': row['route_sector'],
                'date': row['report_date'],
                'label': int(row['label']),
            })
    labels = pd.DataFrame(label_rows).drop_duplicates(['region', 'date'], keep='last')
    frame = labels.merge(daily, on=['region', 'date'], how='inner', validate='one_to_one')
    feature_columns = [column for column in frame.columns if column not in ('label', 'date', 'region')]
    train = frame[frame['date'].str.startswith('2023-')].copy()
    test = frame[frame['date'].str.startswith('2024-')].copy()
    if train.empty or test.empty or train['label'].nunique() != 2:
        raise ValueError('Training/test split is empty or training lacks both proxy classes.')

    transform = ColumnTransformer([
        ('weather', StandardScaler(), feature_columns),
        ('region', OneHotEncoder(handle_unknown='ignore'), ['region']),
    ])
    model = make_pipeline(transform, LogisticRegression(
        class_weight='balanced', C=1.0, max_iter=3000, solver='lbfgs', random_state=42))
    model.fit(train[feature_columns + ['region']], train['label'])
    scores = model.predict_proba(test[feature_columns + ['region']])[:, 1]
    y = test['label'].to_numpy(dtype=int)
    prevalence = float(train['label'].mean())
    threshold_metrics = {str(threshold): binary_metrics(y, scores, threshold) for threshold in THRESHOLDS}

    no_fire_data = json.loads(NO_FIRE_FILE.read_text(encoding='utf-8'))
    explicit_dates = sorted({
        row['report_date_in_archive']
        for row in no_fire_data['verified_explicit_no_fire_reports']
        if row['report_date_in_archive'].startswith('2024-')
    })
    no_fire_test = test[test['date'].isin(explicit_dates)].copy()
    no_fire_scores = model.predict_proba(no_fire_test[feature_columns + ['region']])[:, 1]
    no_fire_days = [
        {'date': row.date, 'route_sector': row.region, 'score': float(score)}
        for row, score in zip(no_fire_test.itertuples(index=False), no_fire_scores)
    ]
    positive_rows = test[y == 1]
    positive_case_days = [
        {'date': row.date, 'route_sector': row.region, 'score': float(score)}
        for row, score in zip(test.itertuples(index=False), scores) if int(row.label) == 1
    ]
    no_fire_thresholds = {}
    for threshold in THRESHOLDS:
        alerts = [row for row in no_fire_days if row['score'] >= threshold]
        no_fire_thresholds[str(threshold)] = {
            'covered_route_days': len(no_fire_days),
            'possible_route_days': 8 * len(explicit_dates),
            'alerted_route_days': len(alerts),
            'report_dates_with_any_alert': len({row['date'] for row in alerts}),
            'alerts': alerts,
        }

    result = {
        'experiment_id': 'jma-gsm-2023-train-2024-heldout-snmf-reported-fire-route-day-transfer',
        'status': 'not_reliable_for_fire_prediction',
        'target': 'Same-day nearby SNMF-listed active incident proxy within the archived route-sector label definition; not physical fire absence or ignition probability.',
        'protocol': {
            'forecast_lead_hours': 24,
            'model': 'StandardScaler + route one-hot + class-balanced logistic regression (C=1, random_state=42).',
            'train_period': '2023-07-01 through 2023-12-31',
            'test_period': '2024-01-01 through 2024-12-31',
            'thresholds': list(THRESHOLDS),
            'threshold_selection': 'None; all are diagnostic and the 2024 test was not used to choose a threshold.',
            'weather_features': feature_columns,
            'weather_window': 'Complete 24 hourly JMA GSM Previous Runs forecasts for the target UTC date; incomplete route-days excluded.',
            'route_day_label': 'Positive if an SNMF report lists a nearby incident; zero otherwise. Zeros are report-record proxies, not verified physical no-fire observations.',
        },
        'sources': {
            'weather_sha256': {path.name: sha256(path) for path in WEATHER_FILES},
            'proxy_sha256': {path.name: sha256(path) for path in PROXY_FILES},
            'explicit_no_fire_audit_sha256': sha256(NO_FIRE_FILE),
        },
        'counts': {
            'aligned_route_days_2023_2024': len(frame),
            'training_route_days': len(train),
            'training_positive_route_days': int(train['label'].sum()),
            'training_positive_route_day_clusters': route_day_clusters(train[train['label'] == 1].to_dict('records')),
            'test_route_days': len(test),
            'test_positive_route_days': int(y.sum()),
            'test_positive_route_day_clusters': route_day_clusters(positive_rows.to_dict('records')),
            'explicit_national_no_fire_report_dates_2024': len(explicit_dates),
            'explicit_national_no_fire_dates': explicit_dates,
            'covered_route_days_on_explicit_no_fire_dates': len(no_fire_test),
            'possible_route_days_on_explicit_no_fire_dates': 8 * len(explicit_dates),
            'route_days_missing_weather_coverage_on_explicit_no_fire_dates': 8 * len(explicit_dates) - len(no_fire_test),
        },
        'test_report_proxy_metrics': {
            'positive_fraction': float(y.mean()),
            'average_precision': float(average_precision_score(y, scores)),
            'training_prevalence_baseline_average_precision': float(y.mean()),
            'brier_score': float(brier_score_loss(y, scores)),
            'training_prevalence_baseline_brier_score': float(brier_score_loss(y, np.full(len(y), prevalence))),
            'training_prevalence': prevalence,
            'threshold_metrics': threshold_metrics,
        },
        'explicit_no_fire_negative_challenge': {
            'target': 'Official SNMF report explicitly states no fires were reported nationally on that date; administrative negative proxy only.',
            'report_dates': len(explicit_dates),
            'adjacent_date_clusters': date_clusters(explicit_dates),
            'threshold_results': no_fire_thresholds,
        },
        'positive_test_cases': positive_case_days,
        'interpretation': [
            'At the fixed diagnostic threshold 0.5, the model alerted on 73 route-days and detected none of the nine 2024 positive report-proxy route-days.',
            'At 0.1, recall was still only 2/9 and the model emitted 219 alerts; the test metrics do not identify a useful reliable threshold.',
            'The 27 explicit national no-fire report days provide an additional selected negative challenge set; they do not prove absence of unreported physical fires.',
            'Only five positive route-days were available for training and nine for the full held-out year. The 2024 results are too sparse to claim precision for physical fire or trail safety.',
        ],
        'limitations': [
            'SNMF reports document incidents supplied by jurisdictions; they are not a complete sensor-confirmed fire census.',
            'No report entry near a route is not automatically physical absence. Only explicit national no-fire report dates are used as the stronger negative challenge set.',
            'Positive route-days repeat some incidents; day rows and route sectors overstate the number of independent fires.',
            'No confidence threshold was selected on an independent validation set; all listed thresholds are descriptive test diagnostics.',
            'Forecast weather is only one part of fire occurrence; fuel condition, ignition likelihood, and route-level observed coverage are absent.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = [
        '# Prueba temporal JMA GSM: entrenar en 2023 y probar en 2024',
        '',
        'Se entrenó una regresión logística balanceada con los pronósticos JMA GSM de julio-diciembre de 2023 y se congeló para todo 2024. La etiqueta es si un parte SNMF registra un incidente cerca del sector ese día; no equivale a una medición completa de incendios físicos. No se eligió ningún umbral usando el año de prueba.',
        '',
        f"El entrenamiento tuvo {len(train)} ruta-días y solo {int(train['label'].sum())} positivos. El test tuvo {len(test)} ruta-días y {int(y.sum())} positivos en {route_day_clusters(positive_rows.to_dict('records'))} secuencias ruta-temporales. La precisión promedio (average precision) fue {average_precision_score(y, scores):.4f}, frente a prevalencia {y.mean():.4f}; el Brier fue {brier_score_loss(y, scores):.4f}, frente al baseline constante de entrenamiento {brier_score_loss(y, np.full(len(y), prevalence)):.4f}.",
        '',
        '| Corte diagnóstico | Alertas | Positivos detectados / 9 | Precisión del proxy | Recall del proxy |',
        '|---:|---:|---:|---:|---:|',
    ]
    for threshold in THRESHOLDS:
        metric = threshold_metrics[str(threshold)]
        md.append(f"| {threshold:.1f} | {metric['alerts']} | {metric['true_positives']}/9 | {metric['precision_on_report_proxy']:.1%} | {metric['recall_on_report_proxy']:.1%} |")
    md.extend([
        '',
        f"En las {len(explicit_dates)} fechas 2024 con parte que declara explícitamente cero incendios nacionales, el modelo tuvo cobertura para {len(no_fire_days)}/{8 * len(explicit_dates)} ruta-días. A corte 0,5 alertó en {no_fire_thresholds['0.5']['alerted_route_days']} ruta-días negativos; a 0,9 no alertó en ninguno, pero tampoco obtuvo recall útil en el conjunto de prueba.",
        '',
        'La mejora de ranking sobre la prevalencia no basta: los positivos son muy escasos, el Brier se compara con el baseline y los cortes diagnósticos producen muchos falsos avisos o casi ningún acierto. No se puede afirmar precisión fiable ni probabilidad calibrada para detectar fuego físico en trekking. El SNMF describe el reporte diario como estado de situación de incendios registrados, no como censo exhaustivo ([fuente oficial](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego/que-es-y-como-funciona-el-servicio-nacional-de-manejo-del-fuego)).',
        '',
        'Resultados con hashes en [JSON](fire-jma-2023-train-2024-test-snmf-report-proxy.json); reproducción con [`evaluate_jma_2023_to_2024_snmf_fire_transfer.py`](../../training/python/evaluate_jma_2023_to_2024_snmf_fire_transfer.py).',
        '',
    ])
    OUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({
        'output': OUT.relative_to(ROOT).as_posix(),
        'train_route_days': len(train),
        'train_positives': int(train['label'].sum()),
        'test_route_days': len(test),
        'test_positives': int(y.sum()),
        'average_precision': result['test_report_proxy_metrics']['average_precision'],
        'baseline_ap': result['test_report_proxy_metrics']['training_prevalence_baseline_average_precision'],
        'brier': result['test_report_proxy_metrics']['brier_score'],
        'baseline_brier': result['test_report_proxy_metrics']['training_prevalence_baseline_brier_score'],
        'threshold_0_5': threshold_metrics['0.5'],
        'no_fire_days_threshold_0_5_alerts': no_fire_thresholds['0.5']['alerted_route_days'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
