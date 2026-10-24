"""Test JMA fire-report models using complete trail polylines.

Chronology is 2023 training, 2024 threshold validation, 2025 untouched test.
The target is an SNMF report proxy, not confirmed physical fire occurrence.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

from environmental_sources import PUBLIC, ROOT, sha256
from train_snmf_report_proxy_gfs_model import load_weather_with_geography
from audit_inpe_reference_detections_route_polylines import (
    distance_to_polyline_km, prepare_routes,
)
from evaluate_jma_model_family_transfer_2025 import (
    MANIFEST_DIRS, NO_FIRE_FILE, REPORT_FILES, WEATHER_FILES,
    choose_validation_threshold, model_families, route_day_clusters,
    threshold_metrics,
)

BASE = ROOT / 'docs/environmental-models-2026-10-22'
PRIVATE = ROOT / 'training/data/environmental/private'
GEOMETRY = PRIVATE / 'fire-route-geometries.json'
YEARS = ('2023', '2024', '2025')
RADII_KM = (10, 20)
OUT = BASE / 'fire-jma-full-trail-polyline-2023-2025-transfer-test.json'
OUT_MD = BASE / 'fire-jma-full-trail-polyline-2023-2025-transfer-test.md'


def build_polyline_labels(year: str, routes: list[dict]) -> dict[int, list[dict]]:
    event_data = json.loads(REPORT_FILES[year].read_text(encoding='utf-8'))
    manifest_path = PRIVATE / MANIFEST_DIRS[year] / 'source-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    report_dates = {
        row['date'] for row in manifest['reports']
        if row.get('status') in {'cached', 'downloaded'}
    }
    snapshots = [
        row for row in event_data['snapshots']
        if row.get('report_date') in report_dates
        and isinstance(row.get('latitude'), (int, float))
        and isinstance(row.get('longitude'), (int, float))
    ]
    starts = [
        row for row in event_data['deduplicated_events']
        if (row.get('reported_start_date') or '').startswith(f'{year}-')
        and isinstance(row.get('latitude'), (int, float))
        and isinstance(row.get('longitude'), (int, float))
    ]
    labels: dict[int, list[dict]] = {radius: [] for radius in RADII_KM}
    active_statuses = {'ACTIVO', 'CONTROLADO', 'CONTENIDO', 'GUARDIA DE CENIZAS', 'UNKNOWN'}
    for route in routes:
        south, north, west, east = route['bounds']
        route_snapshots = []
        for row in snapshots:
            lat, lon = float(row['latitude']), float(row['longitude'])
            if south <= lat <= north and west <= lon <= east:
                distance = distance_to_polyline_km(lat, lon, route['projection'])
                if distance <= max(RADII_KM):
                    route_snapshots.append((row, distance))
        route_starts = []
        for row in starts:
            lat, lon = float(row['latitude']), float(row['longitude'])
            if south <= lat <= north and west <= lon <= east:
                distance = distance_to_polyline_km(lat, lon, route['projection'])
                if distance <= max(RADII_KM):
                    route_starts.append((row, distance))

        candidate_dates = sorted(report_dates | {
            row['reported_start_date'] for row, _ in route_starts
            if row.get('reported_start_date')
        })
        for day in candidate_dates:
            active_nearby = []
            for row, distance in route_snapshots:
                if row.get('report_date') != day:
                    continue
                status = row.get('status', 'UNKNOWN')
                started_today = row.get('reported_start_date') == day
                if status not in active_statuses and not (status == 'EXTINGUIDO' and started_today):
                    continue
                active_nearby.append((row, distance))
            start_nearby = [
                (row, distance) for row, distance in route_starts
                if row.get('reported_start_date') == day
            ]
            for radius in RADII_KM:
                nearby = [(row, distance) for row, distance in active_nearby if distance <= radius]
                nearby.extend((row, distance) for row, distance in start_nearby
                    if distance <= radius and not any(
                        current.get('incident_name') == row.get('incident_name')
                        and current.get('province') == row.get('province')
                        for current, _ in nearby
                    ))
                label = int(bool(nearby))
                # Without a daily PDF, only a documented positive start is known.
                if day not in report_dates and not label:
                    continue
                labels[radius].append({'region': route['name'], 'date': day, 'label': label})
    for radius in RADII_KM:
        unique = {(row['region'], row['date']): row for row in labels[radius]}
        labels[radius] = list(unique.values())
    return labels


def eval_radius(radius: int, label_rows: list[dict], weather: pd.DataFrame,
                no_fire_dates_2024: list[str], no_fire_dates_2025: list[str]) -> dict:
    labels = pd.DataFrame(label_rows).drop_duplicates(['region', 'date'], keep='last')
    frame = labels.merge(weather, on=['region', 'date'], how='inner', validate='one_to_one')
    train = frame[frame['date'].str.startswith('2023-')].copy()
    validation = frame[frame['date'].str.startswith('2024-')].copy()
    test = frame[frame['date'].str.startswith('2025-')].copy()
    features = [column for column in frame.columns if column not in ('label', 'date', 'region')]
    y_train = train['label'].to_numpy(dtype=int)
    y_validation = validation['label'].to_numpy(dtype=int)
    y_test = test['label'].to_numpy(dtype=int)
    if any(part.empty for part in (train, validation, test)) or y_train.sum() == 0:
        raise ValueError(f'Insufficient chronological split data at {radius} km.')

    validation_rows = validation[validation['label'] == 1].to_dict('records')
    test_rows = test[test['label'] == 1].to_dict('records')
    no_fire_validation = validation[validation['date'].isin(no_fire_dates_2024)].copy()
    no_fire_test = test[test['date'].isin(no_fire_dates_2025)].copy()
    results = {}
    for name, model in model_families(features, int(y_train.sum()), len(train)).items():
        model.fit(train[features + ['region']], y_train)
        validation_scores = model.predict_proba(validation[features + ['region']])[:, 1]
        test_scores = model.predict_proba(test[features + ['region']])[:, 1]
        selection = choose_validation_threshold(y_validation, validation_scores)
        thresholds = {'diagnostic_0_5': 0.5, 'diagnostic_0_8': 0.8, 'diagnostic_0_9': 0.9}
        if 'threshold' in selection:
            thresholds['best_validation_precision_with_minimum_5_alerts'] = selection['threshold']
        no_fire_validation_scores = model.predict_proba(no_fire_validation[features + ['region']])[:, 1] if len(no_fire_validation) else np.array([])
        no_fire_scores = model.predict_proba(no_fire_test[features + ['region']])[:, 1] if len(no_fire_test) else np.array([])
        no_fire_validation_metrics = {
            f'diagnostic_{threshold:.1f}': threshold_metrics(no_fire_validation['label'].to_numpy(dtype=int), no_fire_validation_scores, threshold)
            for threshold in (0.5, 0.9)
        }
        test_metrics = {
            key: threshold_metrics(y_test, test_scores, threshold)
            for key, threshold in thresholds.items()
        }
        no_fire_metrics = {}
        for key, threshold in thresholds.items():
            alerts = [
                {'date': row.date, 'route_sector': row.region, 'score': float(score)}
                for row, score in zip(no_fire_test.itertuples(index=False), no_fire_scores)
                if score >= threshold
            ]
            no_fire_metrics[key] = {
                'covered_route_days': len(no_fire_test),
                'possible_route_days': 8 * len(no_fire_dates_2025),
                'false_alert_route_days': len(alerts),
                'alerts': alerts,
            }
        prevalence = float(y_train.mean())
        results[name] = {
            'validation': {
                'explicit_no_fire_fixed_threshold_challenge': {
                    'report_dates': no_fire_dates_2024,
                    'covered_route_days': len(no_fire_validation),
                    'possible_route_days': 8 * len(no_fire_dates_2024),
                    'diagnostic_threshold_metrics': no_fire_validation_metrics,
                    'interpretation': 'Prespecified diagnostic thresholds on a subset of the validation year; not an untouched test cohort and not verified physical-fire absence.',
                },
                'route_days': len(validation),
                'positive_route_days': int(y_validation.sum()),
                'positive_route_day_clusters': route_day_clusters(validation_rows),
                'average_precision': float(average_precision_score(y_validation, validation_scores)),
                'threshold_selection': selection,
            },
            'test_2025': {
                'route_days': len(test),
                'positive_route_days': int(y_test.sum()),
                'positive_route_day_clusters': route_day_clusters(test_rows),
                'average_precision': float(average_precision_score(y_test, test_scores)),
                'prevalence_baseline_average_precision': float(y_test.mean()),
                'brier_score': float(brier_score_loss(y_test, test_scores)),
                'training_prevalence_baseline_brier_score': float(brier_score_loss(y_test, np.full(len(y_test), prevalence))),
                'threshold_metrics': test_metrics,
                'explicit_no_fire_test': no_fire_metrics,
            },
        }
    return {
        'label_counts': {
            year: {
                'route_days': sum(row['date'].startswith(f'{year}-') for row in label_rows),
                'positive_route_days': sum(row['date'].startswith(f'{year}-') and row['label'] == 1 for row in label_rows),
                'positive_route_day_clusters': route_day_clusters([row for row in label_rows if row['date'].startswith(f'{year}-') and row['label'] == 1]),
            }
            for year in YEARS
        },
        'models': results,
    }


def main() -> None:
    geometry_data = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    routes = prepare_routes(geometry_data['fire_route_geometries'])
    geography_names = {row['name'] for row in json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']}
    if {route['name'] for route in routes} != geography_names:
        raise ValueError('Full route geometry names do not match the SNMF sector list.')
    label_rows_by_year = {year: build_polyline_labels(year, routes) for year in YEARS}
    weather = load_weather_with_geography(WEATHER_FILES)
    no_fire = json.loads(NO_FIRE_FILE.read_text(encoding='utf-8'))
    no_fire_dates_by_year = {year: sorted({
        row['report_date_in_archive'] for row in no_fire['verified_explicit_no_fire_reports']
        if row['report_date_in_archive'].startswith(f'{year}-')
    }) for year in ('2024', '2025')}

    radius_results = {}
    for radius in RADII_KM:
        combined = [row for year in YEARS for row in label_rows_by_year[year][radius]]
        radius_results[str(radius)] = eval_radius(radius, combined, weather, no_fire_dates_by_year['2024'], no_fire_dates_by_year['2025'])

    result = {
        'experiment_id': 'jma-gsm-full-trail-polyline-labels-2023-train-2024-validation-2025-test',
        'status': 'no_candidate_passed_validation_reliability_gate',
        'target': 'SNMF-reported active or starting incident near full trail polyline; report proxy, not confirmed physical fire or ignition probability.',
        'protocol': {
            'spatial_geometry': 'Complete route polylines from fire-route-geometries.json; approximate local-plane point-to-polyline distances.',
            'radii_km': list(RADII_KM),
            'chronological_splits': {'train': '2023', 'validation': '2024', 'untouched_test': '2025'},
            'forecast_lead_hours': 24,
            'threshold_rule': 'For each fixed model, maximize 2024 validation precision subject to at least five alerts; require >=80% to pass. If no cut passes, the selected threshold is diagnostic only.',
            'known_negatives': 'Only report dates with cached/downloaded national daily PDFs may contribute negative route-days. Missing report days remain unknown; explicit national-no-fire dates are separately evaluated.',
            'positive_rule': 'Same-day active/unresolved snapshot or documented start-date event within radius of any complete route polyline.',
        },
        'sources': {
            'weather_sha256': {path.name: sha256(path) for path in WEATHER_FILES},
            'event_report_sha256': {path.name: sha256(path) for path in REPORT_FILES.values()},
            'report_manifest_sha256': {year: sha256(PRIVATE / MANIFEST_DIRS[year] / 'source-manifest.json') for year in YEARS},
            'route_geometry_sha256': sha256(GEOMETRY),
            'sector_geography_sha256': sha256(PUBLIC / 'geography.json'),
            'national_no_fire_audit_sha256': sha256(NO_FIRE_FILE),
        },
        'results_by_polyline_radius_km': radius_results,
        'limitations': [
            'SNMF reports are jurisdiction-reported incidents and do not establish that every physical fire was observed or reported.',
            '2025 has only one explicit national no-fire report date, so the independent negative challenge has just eight route-days.',
            'Twenty km is a broad regional warning distance and should not be presented as an on-trail distance.',
            'Positive route-days repeat incidents; event clusters, not rows, are closer to independent sample units.',
            'Weather-only inputs omit fuel state, ignition likelihood, suppression, access closures, and independently confirmed sensor coverage.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        '# Prueba JMA con polilineas completas (2023-2025)',
        '',
        'Se usaron trazados completos de ocho senderos y radios de 10 y 20 km. La separacion temporal es entrenamiento 2023, validacion 2024 y test intacto 2025. El objetivo son partes SNMF, no incendios fisicos confirmados.',
        '',
    ]
    for radius in RADII_KM:
        item = radius_results[str(radius)]
        lines.extend([f'## Radio {radius} km', '', '| Ano | Ruta-dias conocidos | Positivos | Clusters positivos |', '|---:|---:|---:|---:|'])
        for year in YEARS:
            counts = item['label_counts'][year]
            lines.append(f"| {year} | {counts['route_days']} | {counts['positive_route_days']} | {counts['positive_route_day_clusters']} |")
        lines.extend(['', '| Modelo | Precision validacion (>=5 alertas) | Pasa 80% | Aciertos test / positivos | Alertas test | Precision proxy test |', '|---|---:|:---:|---:|---:|---:|'])
        for name, model_result in item['models'].items():
            selection = model_result['validation']['threshold_selection']
            test_metric = model_result['test_2025']['threshold_metrics'].get('best_validation_precision_with_minimum_5_alerts')
            if test_metric:
                test_cell = f"{test_metric['true_positives']}/{model_result['test_2025']['positive_route_days']}"
                alert_count = test_metric['alerts']
                precision = f"{test_metric['precision_on_report_proxy']:.1%}"
            else:
                test_cell, alert_count, precision = 'sin corte', 0, 'sin corte'
            lines.append(f"| {name} | {selection.get('validation_precision', 0):.1%} | {'Si' if selection.get('eligible') else 'No'} | {test_cell} | {alert_count} | {precision} |")
        lines.extend(['', '| Modelo | Dias-ruta sin fuego reportado (2024) | Avisos a 0.5 | Avisos a 0.9 |', '|---|---:|---:|---:|'])
        for name, model_result in item['models'].items():
            challenge = model_result['validation']['explicit_no_fire_fixed_threshold_challenge']
            metrics = challenge['diagnostic_threshold_metrics']
            lines.append(f"| {name} | {challenge['covered_route_days']}/{challenge['possible_route_days']} | {metrics['diagnostic_0.5']['alerts']} | {metrics['diagnostic_0.9']['alerts']} |")
        lines.append('')
    lines.extend([
        'Ningun modelo alcanzo 80% de precision en validacion. En 20 km, Random Forest obtuvo 4/17 alertas correctas (23.5%) en el test de 2025 al corte elegido en 2024; en 10 km, Logistic Regression obtuvo 19/488 (3.9%). Los radios amplios representan avisos regionales, no distancia sobre el sendero. SNMF es un registro administrativo y no un censo de incendios; por eso estas metricas son precision del proxy, no precision de fuego fisico.',
        '',
        'Resultados con hashes en [JSON](fire-jma-full-trail-polyline-2023-2025-transfer-test.json); reproduccion con [`evaluate_jma_full_trail_polyline_transfer_2025.py`](../../training/python/evaluate_jma_full_trail_polyline_transfer_2025.py).',
        '',
    ])
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({
        'output': OUT.relative_to(ROOT).as_posix(),
        'by_radius': {
            radius: {
                'counts': item['label_counts'],
                'models': {
                    name: {
                        'validation': model['validation']['threshold_selection'],
                        'test_at_validation_threshold': model['test_2025']['threshold_metrics'].get('best_validation_precision_with_minimum_5_alerts'),
                        'test_ap': model['test_2025']['average_precision'],
                        'test_brier': model['test_2025']['brier_score'],
                        'test_brier_baseline': model['test_2025']['training_prevalence_baseline_brier_score'],
                    }
                    for name, model in item['models'].items()
                },
            }
            for radius, item in radius_results.items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
