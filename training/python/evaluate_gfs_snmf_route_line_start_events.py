#!/usr/bin/env python3
"""Audit frozen GFS scores against SNMF start days associated to full trails.

The trained model predicts an active-report proxy, not new ignition. This
secondary audit therefore reports event-start sensitivity/coincidence only;
it does not count all other alerts as false ignitions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scipy.stats import beta

from environmental_sources import ROOT

BASE = ROOT / 'docs/environmental-models-2026-10-22'
MODEL = BASE / 'fire-gfs-snmf-report-proxy-temporal-evaluation-2026-jan.json'
EVENTS = BASE / 'fire-snmf-polyline-event-coverage-2026-jan.json'
OUT = BASE / 'fire-gfs-snmf-route-line-start-event-evaluation-2026-jan.json'
DIAGNOSTIC_THRESHOLDS = (0.5, 0.7, 0.8, 0.9, 0.95)


def exact_interval(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    alpha = 0.05
    return [float(beta.ppf(alpha / 2, successes, total - successes + 1)) if successes else 0.0,
            float(beta.ppf(1 - alpha / 2, successes + 1, total - successes)) if successes < total else 1.0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=MODEL)
    parser.add_argument('--events', type=Path, default=EVENTS)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    model = json.loads(args.model.read_text(encoding='utf-8'))
    audit = json.loads(args.events.read_text(encoding='utf-8'))
    scores = {(row['route_sector'], row['date']): row
              for row in model.get('test_route_day_predictions', [])}
    if not scores:
        raise ValueError('The temporal training output must include test_route_day_predictions')
    summaries = {}
    weather_model = model.get('weather_model', 'gfs')
    for radius in (10, 20):
        event_rows = [row for row in audit['events_within_50km']
                      if row['line_distance_km'] <= radius]
        route_days = {}
        for row in event_rows:
            route_days.setdefault((row['route_sector'], row['reported_start_date']), []).append(row)
        evaluated = []
        for (route, day), support in sorted(route_days.items()):
            prediction = scores.get((route, day))
            evaluated.append({
                'route_sector': route, 'reported_start_date': day,
                'minimum_line_distance_km': min(row['line_distance_km'] for row in support),
                'minimum_center_distance_km': min(row['center_distance_km'] for row in support),
                'supporting_incident_records': len(support),
                'incident_names': sorted({str(row.get('incident_name')) for row in support}),
                'has_model_coverage': prediction is not None,
                'model_alert_at_0_5': prediction['alert_at_diagnostic_threshold_0_5'] if prediction else None,
                'model_score_not_calibrated_probability': prediction['diagnostic_score'] if prediction else None,
            })
        covered = [row for row in evaluated if row['has_model_coverage']]
        alerted = [row for row in covered if row['model_alert_at_0_5']]
        threshold_sensitivity = []
        for threshold in DIAGNOSTIC_THRESHOLDS:
            event_hits = sum(
                row['model_score_not_calibrated_probability'] >= threshold
                for row in covered
            )
            test_alert_days = sum(
                row['diagnostic_score'] >= threshold
                for row in scores.values()
            )
            threshold_sensitivity.append({
                'diagnostic_threshold': threshold,
                'test_alert_route_days': test_alert_days,
                'all_test_route_days': len(scores),
                'covered_start_days_alerted': event_hits,
                'covered_start_days': len(covered),
                'descriptive_event_start_sensitivity': event_hits / len(covered) if covered else None,
                'exact_95pct_interval': exact_interval(event_hits, len(covered)),
            })
        summaries[str(radius)] = {
            'unique_route_sector_start_days_on_trail_buffer': len(route_days),
            'route_sector_start_days_with_model_coverage': len(covered),
            'start_days_with_score_at_least_0_5': len(alerted),
            'descriptive_event_start_sensitivity': len(alerted) / len(covered) if covered else None,
            'exact_95pct_interval': exact_interval(len(alerted), len(covered)),
            'test_alert_route_days_at_0_5': model['test_at_0_5_diagnostic']['alerts_at_0_5_diagnostic'],
            'all_test_route_days': model['test_at_0_5_diagnostic']['route_days'],
            'threshold_sensitivity_diagnostic_only': threshold_sensitivity,
            'positive_start_days': evaluated,
        }
    result = {
        'experiment_id': f'{weather_model}-24h-active-report-model-vs-snmf-route-line-starts-2026-jan',
        'weather_model': weather_model,
        'candidate_status': 'not_reliable_for_ignition_prediction',
        'model_target': model['target'],
        'independent_event_target': 'SNMF-reported incident start date within a buffer of the reviewed trail polyline; reported date, not exact ignition time.',
        'threshold': 0.5,
        'results': summaries,
        'source_files': {'model_evaluation': {'path': str(args.model),
                'sha256': hashlib.sha256(args.model.read_bytes()).hexdigest()},
            'route_polyline_event_audit': {'path': str(args.events),
                'sha256': hashlib.sha256(args.events.read_bytes()).hexdigest()}},
        'limitations': [
            'The model was trained to reproduce an active-incident report proxy, not the new-start target assessed here.',
            'The SNMF archive is not an exhaustive registry of physical fire starts or no-fire periods.',
            'The test covers one month and only a few independent route-sector start days.',
            'Other model alerts cannot be counted as false new ignitions without exhaustive observed negatives.',
            'The 0.5 score cutoff is diagnostic and was not selected or validated for this event-start target.',
            'The threshold sensitivity table is an exploratory description of the frozen test set; it must not be used to select or claim an operational threshold.',
            'Route lines and buffers approximate exposure; alerts should not be interpreted as operational safety decisions.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'status': result['candidate_status'],
        'results': {radius: {key: value for key, value in summary.items() if key != 'positive_start_days'}
                    for radius, summary in summaries.items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
