"""Frozen 2023→2024 validation→2025 test of JMA fire-report proxy models.

All outcomes are SNMF administrative report proxies at a 20 km sector-center
radius, not verified physical-fire labels. Model families are fixed in code;
2025 is not used for threshold selection.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
    brier_score_loss, confusion_matrix, precision_score, recall_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from environmental_sources import PUBLIC, ROOT, sha256
from train_snmf_report_proxy_gfs_model import load_weather_with_geography
import evaluate_jma_2023_to_2024_20km_sensitivity as labels_source

BASE = ROOT / 'docs/environmental-models-2026-10-22'
PRIVATE = ROOT / 'training/data/environmental/private'
YEARS = ('2023', '2024', '2025')
WEATHER_FILES = [
    PRIVATE / 'openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2023-07-01-2024-01-01.json.gz',
    PRIVATE / 'openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2024-01-01-2025-01-01.json.gz',
    PRIVATE / 'openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2025-01-01-2026-02-01.json.gz',
]
REPORT_FILES = {year: BASE / f'snmf-{year}-daily-occurrence-events.json' for year in YEARS}
ROUTE_PROXY_FILES = {year: BASE / f'snmf-{year}-route-day-report-proxy.json' for year in YEARS}
MANIFEST_DIRS = {
    '2023': 'snmf-daily-occurrence-2023-jul-dec',
    '2024': 'snmf-daily-occurrence-2024',
    '2025': 'snmf-daily-occurrence-2025',
}
NO_FIRE_FILE = BASE / 'fire-snmf-national-no-fire-report-audit.json'
RADII_KM = (20,)
MIN_VALIDATION_ALERTS = 5
PRECISION_GATE = 0.80
OUT = BASE / 'fire-jma-model-family-2023-2025-transfer-test.json'
OUT_MD = BASE / 'fire-jma-model-family-2023-2025-transfer-test.md'


def route_day_clusters(rows: list[dict]) -> int:
    from collections import defaultdict
    from datetime import date
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        grouped[row['region']].add(row['date'])
    count = 0
    for days in grouped.values():
        previous = None
        for value in sorted(date.fromisoformat(day) for day in days):
            if previous is None or (value - previous).days > 1:
                count += 1
            previous = value
    return count


def build_label_rows() -> pd.DataFrame:
    labels_source.REPORT_FILES.update(REPORT_FILES)
    labels_source.MANIFEST_DIRS.update(MANIFEST_DIRS)
    routes = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    rows = [row for year in YEARS for row in labels_source.build_labels(year, routes)]
    return pd.DataFrame(rows).drop_duplicates(['region', 'date'], keep='last')


def transform(features: list[str]) -> ColumnTransformer:
    return ColumnTransformer([
        ('weather', StandardScaler(), features),
        ('region', OneHotEncoder(handle_unknown='ignore'), ['region']),
    ])


def model_families(features: list[str], positives: int, rows: int) -> dict:
    return {
        'logistic_regression': make_pipeline(
            transform(features),
            LogisticRegression(class_weight='balanced', C=1.0, max_iter=3000,
                               solver='lbfgs', random_state=42),
        ),
        'random_forest': make_pipeline(
            transform(features),
            RandomForestClassifier(n_estimators=500, min_samples_leaf=5,
                max_features=0.8, class_weight='balanced_subsample',
                random_state=42, n_jobs=-1),
        ),
        'xgboost': make_pipeline(
            transform(features),
            XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
                scale_pos_weight=(rows - positives) / max(positives, 1),
                reg_lambda=2, eval_metric='logloss', n_jobs=-1,
                random_state=42),
        ),
    }


def choose_validation_threshold(y: np.ndarray, scores: np.ndarray) -> dict:
    candidates = []
    for threshold in np.unique(scores):
        predicted = scores >= threshold
        alerts = int(predicted.sum())
        if alerts < MIN_VALIDATION_ALERTS:
            continue
        candidates.append((
            float(precision_score(y, predicted, zero_division=0)),
            float(recall_score(y, predicted, zero_division=0)),
            float(threshold), alerts,
        ))
    if not candidates:
        return {'eligible': False, 'reason': 'Fewer than five validation alerts at every threshold.'}
    precision, recall, threshold, alerts = max(candidates)
    return {
        'threshold': threshold,
        'validation_precision': precision,
        'validation_recall': recall,
        'validation_alerts': alerts,
        'minimum_alert_requirement': MIN_VALIDATION_ALERTS,
        'precision_gate': PRECISION_GATE,
        'eligible': precision >= PRECISION_GATE,
    }


def threshold_metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    predicted = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {
        'threshold': float(threshold),
        'alerts': int(predicted.sum()),
        'true_positives': int(tp), 'false_positives': int(fp),
        'false_negatives': int(fn), 'true_negatives': int(tn),
        'precision_on_report_proxy': float(precision_score(y, predicted, zero_division=0)),
        'recall_on_report_proxy': float(recall_score(y, predicted, zero_division=0)),
        'accuracy_on_report_proxy': float(accuracy_score(y, predicted)),
    }


def main() -> None:
    labels = build_label_rows()
    weather = load_weather_with_geography(WEATHER_FILES)
    frame = labels.merge(weather, on=['region', 'date'], how='inner', validate='one_to_one')
    train = frame[frame['date'].str.startswith('2023-')].copy()
    validation = frame[frame['date'].str.startswith('2024-')].copy()
    test = frame[frame['date'].str.startswith('2025-')].copy()
    features = [column for column in frame.columns if column not in ('label', 'date', 'region')]
    y_train = train['label'].to_numpy(dtype=int)
    y_validation = validation['label'].to_numpy(dtype=int)
    y_test = test['label'].to_numpy(dtype=int)
    if any(part.empty for part in (train, validation, test)) or y_train.sum() == 0:
        raise ValueError('One of the chronological partitions is empty or training has no positives.')

    no_fire_data = json.loads(NO_FIRE_FILE.read_text(encoding='utf-8'))
    no_fire_dates_2025 = sorted({
        row['report_date_in_archive'] for row in no_fire_data['verified_explicit_no_fire_reports']
        if row['report_date_in_archive'].startswith('2025-')
    })
    no_fire_test = test[test['date'].isin(no_fire_dates_2025)].copy()
    results = {}
    for name, model in model_families(features, int(y_train.sum()), len(train)).items():
        model.fit(train[features + ['region']], y_train)
        validation_scores = model.predict_proba(validation[features + ['region']])[:, 1]
        test_scores = model.predict_proba(test[features + ['region']])[:, 1]
        selection = choose_validation_threshold(y_validation, validation_scores)
        thresholds = {
            'diagnostic_0_5': 0.5,
            'diagnostic_0_8': 0.8,
            'diagnostic_0_9': 0.9,
        }
        if 'threshold' in selection:
            thresholds['best_validation_precision_with_minimum_5_alerts'] = selection['threshold']
        no_fire_scores = model.predict_proba(no_fire_test[features + ['region']])[:, 1] if len(no_fire_test) else np.array([])
        metrics_by_threshold = {
            key: threshold_metrics(y_test, test_scores, threshold)
            for key, threshold in thresholds.items()
        }
        no_fire_by_threshold = {}
        for key, threshold in thresholds.items():
            alerted = [
                {'date': row.date, 'route_sector': row.region, 'score': float(score)}
                for row, score in zip(no_fire_test.itertuples(index=False), no_fire_scores)
                if score >= threshold
            ]
            no_fire_by_threshold[key] = {
                'explicit_no_fire_report_dates': no_fire_dates_2025,
                'covered_route_days': len(no_fire_test),
                'possible_route_days': len(no_fire_dates_2025) * 8,
                'false_alert_route_days': len(alerted),
                'alerted_dates': len({row['date'] for row in alerted}),
                'alerts': alerted,
            }
        validation_gate_rows = {
            'best_precision_threshold_with_minimum_5_alerts': selection,
        }
        validation_baseline = float(y_train.mean())
        results[name] = {
            'validation': {
                'route_days': len(validation),
                'positive_route_days': int(y_validation.sum()),
                'positive_route_day_clusters': route_day_clusters(validation[validation['label'] == 1].to_dict('records')),
                'average_precision': float(average_precision_score(y_validation, validation_scores)),
                'prevalence_baseline_average_precision': float(y_validation.mean()),
                'threshold_selection': validation_gate_rows,
            },
            'test_2025': {
                'route_days': len(test),
                'positive_route_days': int(y_test.sum()),
                'positive_route_day_clusters': route_day_clusters(test[test['label'] == 1].to_dict('records')),
                'average_precision': float(average_precision_score(y_test, test_scores)),
                'prevalence_baseline_average_precision': float(y_test.mean()),
                'brier_score': float(brier_score_loss(y_test, test_scores)),
                'training_prevalence_baseline_brier_score': float(brier_score_loss(y_test, np.full(len(y_test), validation_baseline))),
                'threshold_metrics': metrics_by_threshold,
                'explicit_national_no_fire_challenge': no_fire_by_threshold,
            },
        }

    result = {
        'experiment_id': 'jma-gsm-report-proxy-model-family-2023-train-2024-validation-2025-test',
        'status': 'no_model_passed_validation_gate_or_generalized_reliably',
        'target': 'Same-day SNMF-listed active/start-date fire event within 20 km of a fixed route-sector center; administrative report proxy only.',
        'protocol': {
            'spatial_radius_km': 20,
            'chronological_splits': {
                'train': '2023-07-01 through 2023-12-31',
                'validation': '2024-01-01 through 2024-12-31',
                'final_test': '2025-01-01 through 2025-12-31',
            },
            'forecast_lead_hours': 24,
            'features': features,
            'threshold_rule': f'Maximize validation precision among thresholds with at least {MIN_VALIDATION_ALERTS} alerts; require at least {PRECISION_GATE:.0%} validation precision to pass the candidate gate. If no threshold passes, validation-best threshold is diagnostic only.',
            'fixed_diagnostic_test_thresholds': [0.5, 0.8, 0.9],
            'model_families': {
                'logistic_regression': 'Class-balanced logistic regression, C=1, max_iter=3000, lbfgs, seed 42.',
                'random_forest': '500 trees, min leaf 5, max features 0.8, balanced_subsample, seed 42.',
                'xgboost': '200 trees, depth 3, learning rate 0.05, subsample/colsample 0.8, min child weight 3, class-ratio scale_pos_weight, L2=2, seed 42.',
            },
            'threshold_selection': 'Only 2024 validation labels. No model or threshold changes based on 2025 final-test outcomes.',
            'label_method': 'Reconstructs existing SNMF route-proxy labels; asserts exact match to audited known/positive route-day totals for each year before fitting.',
        },
        'sources': {
            'weather_sha256': {path.name: sha256(path) for path in WEATHER_FILES},
            'event_report_sha256': {path.name: sha256(path) for path in REPORT_FILES.values()},
            'route_proxy_audit_sha256': {path.name: sha256(path) for path in ROUTE_PROXY_FILES.values()},
            'report_manifest_sha256': {
                year: sha256(PRIVATE / MANIFEST_DIRS[year] / 'source-manifest.json') for year in YEARS
            },
            'geography_sha256': sha256(PUBLIC / 'geography.json'),
            'no_fire_report_audit_sha256': sha256(NO_FIRE_FILE),
        },
        'counts': {
            'train_route_days': len(train),
            'train_positive_route_days': int(y_train.sum()),
            'train_positive_route_day_clusters': route_day_clusters(train[train['label'] == 1].to_dict('records')),
            'validation_route_days': len(validation),
            'validation_positive_route_days': int(y_validation.sum()),
            'validation_positive_route_day_clusters': route_day_clusters(validation[validation['label'] == 1].to_dict('records')),
            'test_route_days': len(test),
            'test_positive_route_days': int(y_test.sum()),
            'test_positive_route_day_clusters': route_day_clusters(test[test['label'] == 1].to_dict('records')),
            'explicit_national_no_fire_report_dates_in_2025': no_fire_dates_2025,
            'test_route_days_covered_on_explicit_no_fire_dates': len(no_fire_test),
        },
        'models': results,
        'limitations': [
            'SNMF report-proxy negatives are not proof of physical absence; only explicitly no-fire national reports are a stronger administrative negative challenge.',
            'The 20 km center-radius target is regional and may not reflect exposure along the full trail geometry.',
            'Adjacent route-days from one incident are correlated; clusters are reported, but confidence bounds are not calculated from these labels.',
            'The 2025 national-no-fire negative challenge includes only one explicit report date and cannot establish a low false-alert rate.',
            'The feature set uses weather forecasts and sector identity only; it lacks validated fuel state, ignition likelihood, and consistent independent sensor coverage.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = [
        '# Comparación temporal JMA: entrenamiento 2023, validación 2024 y test 2025',
        '',
        'Se compararon tres modelos con cortes cronológicos estrictos. Los modelos se entrenaron solo con 2023; el corte se eligió solo en 2024; 2025 quedó como test final. La etiqueta es un incendio publicado por SNMF en un radio regional de 20 km desde el centro del sector, no una observación completa de fuego físico.',
        '',
        f"El entrenamiento tuvo {len(train)} ruta-días y {int(y_train.sum())} positivos. La validación tuvo {len(validation)} ruta-días, {int(y_validation.sum())} positivos en {route_day_clusters(validation[validation['label'] == 1].to_dict('records'))} secuencias. El test de 2025 tuvo {len(test)} ruta-días y {int(y_test.sum())} positivos en {route_day_clusters(test[test['label'] == 1].to_dict('records'))} secuencias.",
        '',
        '| Modelo | Precisión máxima validación (≥5 alertas) | Corte de validación | Pasó 80% | Precisión test 2025 en corte validado | Recall test | Alertas test |',
        '|---|---:|---:|:---:|---:|---:|---:|',
    ]
    for name, item in results.items():
        selection = item['validation']['threshold_selection']['best_precision_threshold_with_minimum_5_alerts']
        test_metric = item['test_2025']['threshold_metrics'].get('best_validation_precision_with_minimum_5_alerts')
        if test_metric is None:
            test_precision = test_recall = 'sin corte'
            alerts = 0
        else:
            test_precision = f"{test_metric['precision_on_report_proxy']:.1%}"
            test_recall = f"{test_metric['recall_on_report_proxy']:.1%}"
            alerts = test_metric['alerts']
        md.append(f"| {name} | {selection.get('validation_precision', 0):.1%} | {selection.get('threshold', float('nan')):.3f} | {'Sí' if selection.get('eligible') else 'No'} | {test_precision} | {test_recall} | {alerts} |")
    md.extend([
        '',
        'Ningún modelo alcanzó 80% de precisión en validación. En el test final, el mejor corte validado no generalizó: logística y XGBoost detectaron 0 eventos positivos; Random Forest detectó 1 de 60 con 3 alertas y precisión del proxy de 33,3%. Ningún candidato es aceptable como alerta fiable. El corte de 2025 no se ajustó.',
        '',
        'Solo hubo un parte nacional explícito sin incendios en 2025, por lo que esa comprobación negativa tampoco mide una tasa de falsas alarmas estable. Los partes SNMF reflejan eventos reportados por jurisdicciones ([fuente oficial](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego/que-es-y-como-funciona-el-servicio-nacional-de-manejo-del-fuego)). Hace falta ampliar observaciones independientes y sensor-cubiertas antes de estimar rendimiento para fuego físico.',
        '',
        'Los conteos de etiquetas se comprueban contra las auditorías archivadas antes de entrenar. Resultados y hashes en [JSON](fire-jma-model-family-2023-2025-transfer-test.json); reproducción con [`evaluate_jma_model_family_transfer_2025.py`](../../training/python/evaluate_jma_model_family_transfer_2025.py).',
        '',
    ])
    OUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({
        'output': OUT.relative_to(ROOT).as_posix(),
        'counts': result['counts'],
        'summary_by_model': {
            name: {
                'validation_best': item['validation']['threshold_selection']['best_precision_threshold_with_minimum_5_alerts'],
                'test_at_validation_threshold': item['test_2025']['threshold_metrics'].get('best_validation_precision_with_minimum_5_alerts'),
                'test_ap': item['test_2025']['average_precision'],
                'test_brier': item['test_2025']['brier_score'],
                'test_brier_baseline': item['test_2025']['training_prevalence_baseline_brier_score'],
            }
            for name, item in results.items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
