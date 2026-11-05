"""Cross-check the frozen WRF fire-mask model on official no-fire reports and events.

This is a small external challenge set, not a representative precision estimate:
negative report dates are from the 2023 held-out period and positive events are
from 2025. The source labels concern official reports, not confirmed physical
absence or ignition time.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from environmental_sources import ROOT, sha256

BASE = ROOT / 'docs/environmental-models-2026-10-22'
PREDICTIONS = ROOT / 'training/data/environmental/private/smn-wrf-modis-test-predictions.csv.gz'
NO_FIRE = BASE / 'fire-snmf-national-no-fire-report-audit.json'
POSITIVE = BASE / 'fire-smn-wrf-snmf-2025-event-test.json'
MODEL_REPORT = BASE / 'fire-smn-wrf-modis-evaluation.json'
OUT = BASE / 'fire-wrf-explicit-no-fire-and-snmf-event-crosscheck.json'
OUT_MD = BASE / 'fire-wrf-explicit-no-fire-and-snmf-event-crosscheck.md'
DIAGNOSTIC_THRESHOLD = 0.5
VALIDATION_BEST_THRESHOLD = 0.7245825147400184


def consecutive_date_clusters(days: list[str]) -> int:
    clusters = 0
    previous: date | None = None
    for value in sorted(date.fromisoformat(item) for item in set(days)):
        if previous is None or (value - previous).days > 1:
            clusters += 1
        previous = value
    return clusters


def main() -> None:
    no_fire_data = json.loads(NO_FIRE.read_text(encoding='utf-8'))
    no_fire_rows = [row for row in no_fire_data['verified_explicit_no_fire_reports']
                    if row['report_date_in_archive'].startswith('2023-')]
    no_fire_dates = sorted({row['report_date_in_archive'] for row in no_fire_rows})
    route_scores: dict[tuple[str, str], list[float]] = defaultdict(list)
    with gzip.open(PREDICTIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            if row['target_date'] in no_fire_dates:
                route_scores[(row['target_date'], row['region'])].append(float(row['risk_score']))
    negative_route_days = [
        {'date': day, 'route_sector': route, 'max_score': max(scores)}
        for (day, route), scores in sorted(route_scores.items())
    ]

    positive_data = json.loads(POSITIVE.read_text(encoding='utf-8'))
    positive_events = positive_data['result']['per_event_scores']
    thresholds = {
        'diagnostic_0_5': DIAGNOSTIC_THRESHOLD,
        'best_validation_precision_with_minimum_5_alerts': VALIDATION_BEST_THRESHOLD,
    }
    comparisons = {}
    for name, threshold in thresholds.items():
        negative_alerts = [row for row in negative_route_days if row['max_score'] >= threshold]
        positive_alerts = [row for row in positive_events if row['model_score_diagnostic'] >= threshold]
        comparisons[name] = {
            'threshold': threshold,
            'explicit_national_no_fire_reports_2023': {
                'report_dates': len(no_fire_dates),
                'temporal_clusters_of_adjacent_dates': consecutive_date_clusters(no_fire_dates),
                'covered_route_days': len(negative_route_days),
                'possible_route_days': 8 * len(no_fire_dates),
                'route_days_missing_model_coverage': 8 * len(no_fire_dates) - len(negative_route_days),
                'false_alert_route_days': len(negative_alerts),
                'report_dates_with_any_alert': len({row['date'] for row in negative_alerts}),
                'alerted_route_days': negative_alerts,
            },
            'independent_snmf_reported_route_events_2025': {
                'scored_event_days': len(positive_events),
                'alerted_event_days': len(positive_alerts),
                'missed_event_days': len(positive_events) - len(positive_alerts),
                'descriptive_sensitivity': len(positive_alerts) / len(positive_events) if positive_events else None,
                'events': [
                    {
                        'route_sector': row['route_sector'],
                        'target_date': row['target_date'],
                        'incident_names': row['incident_names'],
                        'score': row['model_score_diagnostic'],
                        'alert': row['model_score_diagnostic'] >= threshold,
                    }
                    for row in positive_events
                ],
            },
        }

    result = {
        'experiment_id': 'frozen-wrf-fire-mask-model-explicit-national-no-fire-and-snmf-event-crosscheck',
        'status': 'candidate_not_supported_as_reliable_fire_prediction',
        'target': 'Cross-source screening of a frozen weather-only model trained against MODIS active-fire labels; SNMF outcomes are official-report proxies, not confirmed physical presence or absence.',
        'model': {
            'training_report': MODEL_REPORT.relative_to(ROOT).as_posix(),
            'training_report_sha256': sha256(MODEL_REPORT),
            'training_target_before': '2023-01-01',
            'model_test_period': ['2023-07-01', '2024-01-01'],
            'forecast_lead_hours': 27,
            'threshold_origin': '0.5 is diagnostic. The second threshold maximized validation precision among thresholds with at least five validation alerts; no threshold passed the 90% validation precision gate.',
        },
        'sources': {
            'frozen_prediction_file': PREDICTIONS.relative_to(ROOT).as_posix(),
            'prediction_sha256': sha256(PREDICTIONS),
            'explicit_no_fire_audit': NO_FIRE.relative_to(ROOT).as_posix(),
            'explicit_no_fire_audit_sha256': sha256(NO_FIRE),
            'positive_event_test': POSITIVE.relative_to(ROOT).as_posix(),
            'positive_event_test_sha256': sha256(POSITIVE),
        },
        'test_design': {
            'negative_cases': 'Every model-covered route-sector day among the 2023 SNMF reports that explicitly state no fires were reported nationally; dates are selected by report wording and coverage.',
            'positive_cases': 'Four 2025 route-sector event days in the existing external SNMF event test, scored by the same frozen model.',
            'independence': 'Outcomes are from SNMF reports rather than the MODIS training labels, but both cohorts are small, selected, from different years, and do not provide a representative route-day sample.',
        },
        'threshold_comparisons': comparisons,
        'interpretation': [
            'At the diagnostic 0.5 threshold, the model alerted on some explicit national no-fire report dates and missed all four positive event days.',
            'At the best validation-precision threshold, it emitted no alerts on either cohort, so the apparent reduction in false alerts came with no detected positive events.',
            'These selected cohorts cannot estimate deployment precision or calibration, but they do not support an operational threshold for this candidate.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = [
        '# Cruce WRF con partes nacionales sin incendios y eventos SNMF',
        '',
        'Se cruzaron las predicciones congeladas del modelo meteorológico WRF contra los días 2023 cuyos partes SNMF dicen explícitamente que no hubo incendios reportados en el país y contra los cuatro días-sector positivos del test externo de 2025. El modelo fue entrenado antes de 2023; el umbral 0,5 es solo diagnóstico y el otro umbral es el de mayor precisión en validación con al menos cinco alertas. Ningún umbral pasó la puerta de validación de precisión del 90%.',
        '',
        '| Umbral | Alertas en negativos nacionales cubiertos | Eventos positivos detectados |',
        '|---|---:|---:|',
    ]
    for name, threshold in thresholds.items():
        record = comparisons[name]
        negative = record['explicit_national_no_fire_reports_2023']
        positive = record['independent_snmf_reported_route_events_2025']
        md.append(f"| {threshold:.3f} ({name}) | {negative['false_alert_route_days']}/{negative['covered_route_days']} ruta-días | {positive['alerted_event_days']}/{positive['scored_event_days']} |")
    md.extend([
        '',
        'Con el umbral 0,5 hubo alertas en días donde el parte oficial nacional no reportó incendios y el modelo no avisó ante ninguno de los cuatro eventos positivos evaluados. El umbral más alto evitó alertas en ambos grupos, incluidos todos los positivos; no constituye una mejora útil.',
        '',
        'Las cohortes son pequeñas y seleccionadas, con negativos de 2023 y positivos de 2025. Este cruce no estima precisión de producción ni prueba ausencia física de fuego. Aun así, junto con la puerta de validación fallida y los resultados externos, descarta este modelo WRF como candidato a una alerta fiable para trekking.',
        '',
        'Resultados con hashes en [JSON](fire-wrf-explicit-no-fire-and-snmf-event-crosscheck.json); reproducción con [`evaluate_wrf_model_explicit_no_fire_vs_snmf_2025.py`](../../training/python/evaluate_wrf_model_explicit_no_fire_vs_snmf_2025.py).',
        '',
    ])
    OUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({
        'output': OUT.relative_to(ROOT).as_posix(),
        'thresholds': {
            name: {
                'false_alerts_on_negative_route_days': row['explicit_national_no_fire_reports_2023']['false_alert_route_days'],
                'negative_route_days': row['explicit_national_no_fire_reports_2023']['covered_route_days'],
                'positive_events_alerted': row['independent_snmf_reported_route_events_2025']['alerted_event_days'],
                'positive_events': row['independent_snmf_reported_route_events_2025']['scored_event_days'],
            }
            for name, row in comparisons.items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
