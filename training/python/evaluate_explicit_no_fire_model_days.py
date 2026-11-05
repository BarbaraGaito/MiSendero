"""Evaluate frozen held-out route fire scores on explicit SNMF no-fire dates.

The target is absence of a nationally reported SNMF incident, not proof that no
physical fire or satellite detection existed. Predictions remain raw model
scores; thresholds are diagnostic and are not selected by this evaluation.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

from environmental_sources import ROOT, sha256

DEFAULT_PREDICTIONS = ROOT / 'training/data/environmental/private/fire-temporal_test-predictions.csv.gz'
DEFAULT_NO_FIRE = ROOT / 'docs/environmental-models-2026-10-22/fire-snmf-national-no-fire-report-audit.json'
DEFAULT_OUTPUT = ROOT / 'docs/environmental-models-2026-10-22/fire-model-explicit-national-no-fire-test-2023.json'
MODELS = ('persistence', 'logistic', 'random_forest', 'xgboost')
THRESHOLDS = (0.1, 0.5, 0.8, 0.9)


def main(predictions: Path = DEFAULT_PREDICTIONS, no_fire_path: Path = DEFAULT_NO_FIRE,
         output: Path = DEFAULT_OUTPUT) -> None:
    no_fire_data = json.loads(no_fire_path.read_text(encoding='utf-8'))
    report_dates = sorted({
        row['report_date_in_archive']
        for row in no_fire_data['verified_explicit_no_fire_reports']
        if row['report_date_in_archive'].startswith('2023-')
    })
    date_set = set(report_dates)
    route_day: dict[tuple[str, str], dict] = {}
    with gzip.open(predictions, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            target_date = row['target_at'][:10]
            if target_date not in date_set:
                continue
            key = target_date, row['region']
            values = route_day.setdefault(key, {
                'scores': {model: [] for model in MODELS},
                'observed_labels': set(),
                'pixel_rows': 0,
            })
            values['pixel_rows'] += 1
            values['observed_labels'].add(int(row['observed']))
            for model in MODELS:
                values['scores'][model].append(float(row[model]))

    route_rows = []
    for (target_date, region), values in sorted(route_day.items()):
        route_rows.append({
            'report_date_utc': target_date,
            'route_region': region,
            'pixel_rows': values['pixel_rows'],
            'observed_MODIS_target_labels': sorted(values['observed_labels']),
            'max_route_score': {
                model: max(values['scores'][model]) for model in MODELS
            },
        })

    summary = {}
    for model in MODELS:
        summary[model] = {}
        for threshold in THRESHOLDS:
            alerted = [row for row in route_rows if row['max_route_score'][model] >= threshold]
            summary[model][str(threshold)] = {
                'alerted_route_days': len(alerted),
                'covered_route_days': len(route_rows),
                'days_with_any_route_alert': len({row['report_date_utc'] for row in alerted}),
                'report_days_with_any_route_alert': sorted({row['report_date_utc'] for row in alerted}),
                'interpretation': 'Diagnostic score threshold only; not a calibrated probability or precision estimate.',
            }

    result = {
        'experiment_id': 'frozen-modis-route-fire-model-vs-explicit-national-no-fire-reports-2023',
        'target': 'SNMF report explicitly stated no fires were reported nationally on the date; this is an administrative-report negative, not verified physical absence.',
        'protocol': {
            'prediction_file': predictions.relative_to(ROOT).as_posix(),
            'prediction_file_sha256': sha256(predictions),
            'negative_report_file': no_fire_path.relative_to(ROOT).as_posix(),
            'negative_report_file_sha256': sha256(no_fire_path),
            'test_dates': report_dates,
            'spatial_unit': 'route region-day, score aggregated as maximum over available evaluated pixels within that route region',
            'thresholds': list(THRESHOLDS),
            'threshold_selection': 'None; all thresholds are diagnostic and were not selected on these dates.',
        },
        'coverage': {
            'explicit_report_days': len(report_dates),
            'route_days_with_model_coverage': len(route_rows),
            'possible_route_days': 8 * len(report_dates),
            'route_regions_by_date': {
                day: sorted(row['route_region'] for row in route_rows if row['report_date_utc'] == day)
                for day in report_dates
            },
            'route_days_missing_model_coverage': 8 * len(report_dates) - len(route_rows),
            'route_days_with_any_MODIS_positive_label': sum(
                1 for row in route_rows if 1 in row['observed_MODIS_target_labels']
            ),
        },
        'diagnostic_alert_counts': summary,
        'route_day_results': route_rows,
        'limitations': [
            'Only four official no-fire report dates exist in the held-out temporal cohort; two pairs of dates are consecutive, so independent episode count is smaller.',
            'SNMF reports administrative incidents and do not prove physical absence of every fire.',
            'The maximum over sampled pixels is conservative for alert counting but is not a complete trail-line rasterization.',
            'Only six of eight route regions have prediction coverage on these dates.',
            'These negative cases alone cannot estimate precision, recall, calibration, or choose a safe operating threshold.',
            'Scores are frozen outputs from the MODIS one-day-ahead active-fire-mask test, not the separate GFS/GOES ignition or danger models.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': output.relative_to(ROOT).as_posix(),
        'report_days': len(report_dates),
        'covered_route_days': len(route_rows),
        'diagnostic_alerted_route_days_at_0_5': {
            model: summary[model]['0.5']['alerted_route_days'] for model in MODELS
        },
        'sha256': sha256(output),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--predictions', type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument('--no-fire-reports', type=Path, default=DEFAULT_NO_FIRE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    main(args.predictions, args.no_fire_reports, args.output)
