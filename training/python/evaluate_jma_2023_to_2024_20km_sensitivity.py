"""Repeat the year-held-out JMA test at the prespecified 20 km sensitivity radius.

20 km is a regional proximity screen, not immediate trail exposure. This test
remains a report-proxy experiment, not physical-fire validation.
"""
from __future__ import annotations

import json
import math
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

from environmental_sources import PUBLIC, ROOT, sha256
from train_snmf_report_proxy_gfs_model import load_weather_with_geography

BASE = ROOT / 'docs/environmental-models-2026-10-22'
PRIVATE = ROOT / 'training/data/environmental/private'
YEARS = ('2023', '2024')
WEATHER_FILES = [
    PRIVATE / 'openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2023-07-01-2024-01-01.json.gz',
    PRIVATE / 'openmeteo-gfs-previous-runs-argentina-trails-jma_gsm-2024-01-01-2025-01-01.json.gz',
]
REPORT_FILES = {year: BASE / f'snmf-{year}-daily-occurrence-events.json' for year in YEARS}
MANIFEST_DIRS = {'2023': 'snmf-daily-occurrence-2023-jul-dec', '2024': 'snmf-daily-occurrence-2024'}
NO_FIRE_FILE = BASE / 'fire-snmf-national-no-fire-report-audit.json'
RADIUS_KM = 20.0
THRESHOLDS = (0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9)
OUT = BASE / 'fire-jma-2023-train-2024-test-snmf-20km-sensitivity.json'
OUT_MD = BASE / 'fire-jma-2023-train-2024-test-snmf-20km-sensitivity.md'
ACTIVE_STATUSES = {'ACTIVO', 'CONTROLADO', 'CONTENIDO', 'GUARDIA DE CENIZAS', 'UNKNOWN'}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def build_labels(year: str, routes: list[dict]) -> list[dict]:
    events = json.loads(REPORT_FILES[year].read_text(encoding='utf-8'))
    manifest_path = PRIVATE / MANIFEST_DIRS[year] / 'source-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    report_dates = {
        row['date'] for row in manifest['reports']
        if row.get('status') in {'downloaded', 'cached'}
    }
    snapshots = [row for row in events['snapshots'] if row.get('report_date') in report_dates]
    deduplicated = events['deduplicated_events']
    labels = []
    for route in routes:
        route_starts = []
        for event in deduplicated:
            day, latitude, longitude = (event.get('reported_start_date'), event.get('latitude'), event.get('longitude'))
            if (day and day.startswith(f'{year}-') and isinstance(latitude, (int, float))
                    and isinstance(longitude, (int, float))
                    and haversine_km(route['latitude'], route['longitude'], latitude, longitude) <= RADIUS_KM):
                route_starts.append(event)
        candidate_dates = sorted(report_dates | {row['reported_start_date'] for row in route_starts})
        for day in candidate_dates:
            starts_today = [row for row in route_starts if row['reported_start_date'] == day]
            nearby = []
            for event in snapshots:
                if event.get('report_date') != day:
                    continue
                status = event.get('status', 'UNKNOWN')
                started_today = event.get('reported_start_date') == day
                if status not in ACTIVE_STATUSES and not (status == 'EXTINGUIDO' and started_today):
                    continue
                latitude, longitude = event.get('latitude'), event.get('longitude')
                if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
                    continue
                if haversine_km(route['latitude'], route['longitude'], latitude, longitude) <= RADIUS_KM:
                    nearby.append(event)
            nearby.extend(row for row in starts_today if not any(
                item.get('incident_name') == row.get('incident_name')
                and item.get('province') == row.get('province') for item in nearby))
            label = int(bool(nearby))
            if day not in report_dates and not label:
                continue
            labels.append({'region': route['name'], 'date': day, 'label': label})

    reference = json.loads((BASE / f'snmf-{year}-route-day-report-proxy.json').read_text(encoding='utf-8'))
    expected = reference['results']['20']
    if (len(labels) != expected['route_days_with_known_status']
            or sum(row['label'] for row in labels) != expected['route_days_with_nearby_incident_reported']):
        raise AssertionError(f'20 km label reconstruction disagrees with archived audit for {year}')
    return labels


def clusters(rows: list[dict], route_specific: bool = True) -> int:
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        groups[row['region'] if route_specific else 'all'].add(row['date'])
    count = 0
    for days in groups.values():
        previous: date | None = None
        for day in sorted(date.fromisoformat(value) for value in days):
            if previous is None or (day - previous).days > 1:
                count += 1
            previous = day
    return count


def metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    predicted = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {
        'threshold': threshold,
        'true_positives': int(tp), 'false_positives': int(fp),
        'false_negatives': int(fn), 'true_negatives': int(tn),
        'alerts': int(predicted.sum()),
        'precision_on_report_proxy': float(precision_score(y, predicted, zero_division=0)),
        'recall_on_report_proxy': float(recall_score(y, predicted, zero_division=0)),
        'accuracy_on_report_proxy': float(accuracy_score(y, predicted)),
    }


def main() -> None:
    routes = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    label_rows = [row for year in YEARS for row in build_labels(year, routes)]
    weather = load_weather_with_geography(WEATHER_FILES)
    labels = pd.DataFrame(label_rows).drop_duplicates(['region', 'date'], keep='last')
    frame = labels.merge(weather, on=['region', 'date'], how='inner', validate='one_to_one')
    train = frame[frame['date'].str.startswith('2023-')].copy()
    test = frame[frame['date'].str.startswith('2024-')].copy()
    features = [column for column in frame.columns if column not in ('label', 'date', 'region')]
    if train.empty or test.empty or train['label'].nunique() != 2:
        raise ValueError('Missing training/test rows or one of the training classes.')
    model = make_pipeline(
        ColumnTransformer([
            ('weather', StandardScaler(), features),
            ('region', OneHotEncoder(handle_unknown='ignore'), ['region']),
        ]),
        LogisticRegression(class_weight='balanced', C=1.0, max_iter=3000, solver='lbfgs', random_state=42),
    )
    model.fit(train[features + ['region']], train['label'])
    scores = model.predict_proba(test[features + ['region']])[:, 1]
    y = test['label'].to_numpy(dtype=int)
    prevalence = float(train['label'].mean())
    test_metrics = {str(threshold): metrics(y, scores, threshold) for threshold in THRESHOLDS}

    no_fire = json.loads(NO_FIRE_FILE.read_text(encoding='utf-8'))
    dates = sorted({
        row['report_date_in_archive'] for row in no_fire['verified_explicit_no_fire_reports']
        if row['report_date_in_archive'].startswith('2024-')
    })
    subset = test[test['date'].isin(dates)].copy()
    subset_scores = model.predict_proba(subset[features + ['region']])[:, 1]
    negative_rows = [
        {'date': row.date, 'route_sector': row.region, 'score': float(score)}
        for row, score in zip(subset.itertuples(index=False), subset_scores)
    ]
    no_fire_metrics = {}
    for threshold in THRESHOLDS:
        alerted = [row for row in negative_rows if row['score'] >= threshold]
        no_fire_metrics[str(threshold)] = {
            'covered_route_days': len(negative_rows),
            'possible_route_days': len(dates) * len(routes),
            'alerted_route_days': len(alerted),
            'report_dates_with_alert': len({row['date'] for row in alerted}),
            'alerts': alerted,
        }

    result = {
        'experiment_id': 'jma-gsm-2023-train-2024-test-snmf-report-proxy-20km-sensitivity',
        'status': 'not_reliable_for_fire_prediction',
        'target': 'Same-day SNMF-reported incident near a route-sector center within 20 km; a regional report proxy, not physical fire presence or ignition probability.',
        'protocol': {
            'spatial_radius_km': RADIUS_KM,
            'training_period': '2023-07-01 through 2023-12-31',
            'test_period': '2024-01-01 through 2024-12-31',
            'model': 'StandardScaler + route one-hot + class-balanced logistic regression, C=1, random_state=42.',
            'forecast_lead_hours': 24,
            'thresholds': list(THRESHOLDS),
            'threshold_selection': 'None; these are diagnostic comparisons on the held-out year.',
            'label_reconstruction': 'Archived SNMF report parser logic, including active/unresolved same-day listings and reported start dates; zeros only on dates with an archived daily report.',
            'label_reconstruction_check': 'Reconstructed 20 km route-day and positive counts must equal the pre-existing 2023/2024 route-proxy audits before training proceeds.',
            'weather_features': features,
        },
        'sources': {
            'weather_sha256': {path.name: sha256(path) for path in WEATHER_FILES},
            'event_report_sha256': {path.name: sha256(path) for path in REPORT_FILES.values()},
            'report_manifest_sha256': {
                year: sha256(PRIVATE / MANIFEST_DIRS[year] / 'source-manifest.json') for year in YEARS
            },
            'explicit_no_fire_audit_sha256': sha256(NO_FIRE_FILE),
        },
        'counts': {
            'training_route_days': len(train),
            'training_positive_route_days': int(train['label'].sum()),
            'training_positive_route_day_clusters': clusters(train[train['label'] == 1].to_dict('records')),
            'test_route_days': len(test),
            'test_positive_route_days': int(y.sum()),
            'test_positive_route_day_clusters': clusters(test[test['label'] == 1].to_dict('records')),
            'explicit_national_no_fire_report_dates_2024': len(dates),
            'explicit_national_no_fire_date_clusters': clusters([{'region': 'all', 'date': day} for day in dates], route_specific=False),
            'covered_route_days_on_explicit_no_fire_dates': len(negative_rows),
            'possible_route_days_on_explicit_no_fire_dates': len(dates) * len(routes),
        },
        'test_report_proxy_metrics': {
            'positive_fraction': float(y.mean()),
            'average_precision': float(average_precision_score(y, scores)),
            'prevalence_baseline_average_precision': float(y.mean()),
            'brier_score': float(brier_score_loss(y, scores)),
            'training_prevalence_baseline_brier_score': float(brier_score_loss(y, np.full(len(y), prevalence))),
            'training_prevalence': prevalence,
            'threshold_metrics': test_metrics,
        },
        'explicit_no_fire_negative_challenge': {
            'target': 'SNMF explicitly states no fires were reported nationally on the report date; administrative proxy only.',
            'threshold_metrics': no_fire_metrics,
        },
        'interpretation': [
            'At 20 km, ranking improves over the route-day prevalence baseline, but raw scores are poorly calibrated: the Brier score is much worse than the constant-prevalence baseline.',
            'At threshold 0.5 the model detects 35/52 positive report-proxy route-days but emits 566 alerts on route-days without a nearby listed incident.',
            'At threshold 0.9 only 2/52 positive route-days are detected; this remains an exploratory test on a broad, report-derived regional target.',
            'The 20 km sensitivity radius expands beyond immediate route exposure and still does not yield a dependable operating threshold.',
        ],
        'limitations': [
            'No nearby reported incident is not verified physical absence; only the explicit no-fire challenge dates provide the stronger administrative negative proxy.',
            'Route-sector centers are used instead of complete trail polylines; 20 km describes regional proximity rather than on-trail exposure.',
            'The full 2024 test contains only 52 positive route-days, many repeated across event episodes.',
            'Diagnostic thresholds were not selected on a separate validation period.',
            'Weather forecasts omit fuels, ignition likelihood, satellite observability, and local operational closures.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = [
        '# JMA GSM: sensibilidad de la prueba 2023→2024 a 20 km',
        '',
        'Se repitió el protocolo anual JMA GSM con el radio de sensibilidad de 20 km del auditor SNMF. Este radio representa proximidad regional desde el centro del sector; no equivale a estar sobre el sendero. Las etiquetas se reconstruyeron desde los PDF/eventos y los conteos se verificaron contra las auditorías 20 km existentes.',
        '',
        f"El modelo tuvo {len(train)} ruta-días y {int(train['label'].sum())} positivos para entrenar, y {len(test)} ruta-días con {int(y.sum())} positivos en el test de 2024. Average precision: {average_precision_score(y, scores):.4f} frente a prevalencia {y.mean():.4f}; Brier: {brier_score_loss(y, scores):.4f} frente al baseline constante {brier_score_loss(y, np.full(len(y), prevalence)):.4f}.",
        '',
        '| Corte diagnóstico | Alertas | Positivos detectados / 52 | Precisión del proxy | Recall del proxy |',
        '|---:|---:|---:|---:|---:|',
    ]
    for threshold in THRESHOLDS:
        item = test_metrics[str(threshold)]
        md.append(f"| {threshold:.1f} | {item['alerts']} | {item['true_positives']}/52 | {item['precision_on_report_proxy']:.1%} | {item['recall_on_report_proxy']:.1%} |")
    md.extend([
        '',
        f"En los {len(dates)} días de parte nacional sin incendios ({len(negative_rows)}/{len(dates) * len(routes)} ruta-días cubiertos), el corte 0,5 generó {no_fire_metrics['0.5']['alerted_route_days']} alertas y el corte 0,9 generó {no_fire_metrics['0.9']['alerted_route_days']}.",
        '',
        'Aunque el ranking supera la prevalencia, las probabilidades no están calibradas, la precisión del proxy sigue baja y el aumento del radio amplía demasiado la zona para una advertencia inmediata del sendero. No se obtiene una alerta confiable de fuego físico. Los partes SNMF son reportes administrativos ([alcance oficial](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego/que-es-y-como-funciona-el-servicio-nacional-de-manejo-del-fuego)).',
        '',
        'Detalle con hashes en [JSON](fire-jma-2023-train-2024-test-snmf-20km-sensitivity.json); reproducción con [`evaluate_jma_2023_to_2024_20km_sensitivity.py`](../../training/python/evaluate_jma_2023_to_2024_20km_sensitivity.py).',
        '',
    ])
    OUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({
        'output': OUT.relative_to(ROOT).as_posix(),
        'counts': result['counts'],
        'average_precision': result['test_report_proxy_metrics']['average_precision'],
        'prevalence_baseline_ap': result['test_report_proxy_metrics']['prevalence_baseline_average_precision'],
        'brier': result['test_report_proxy_metrics']['brier_score'],
        'baseline_brier': result['test_report_proxy_metrics']['training_prevalence_baseline_brier_score'],
        'threshold_0_5': test_metrics['0.5'],
        'no_fire_0_5_alerts': no_fire_metrics['0.5']['alerted_route_days'],
        'threshold_0_9': test_metrics['0.9'],
        'no_fire_0_9_alerts': no_fire_metrics['0.9']['alerted_route_days'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
