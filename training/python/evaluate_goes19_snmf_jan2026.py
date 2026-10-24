"""Cross-check the frozen one-hour GOES-19 model against Jan-2026 SNMF events."""
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
import json
import math
from pathlib import Path
import sys

import joblib
import numpy as np
from sklearn.neighbors import BallTree

from environmental_sources import ROOT, sha256
from fire_sources import PRIVATE, REPORT_DIR
import train_fire_hourly as hourly

EXPERIMENT = 'fire-goes19-2025q4-2026jan'
EVENTS = ROOT / 'docs/environmental-models-2026-10-22/snmf-2026-jan-daily-occurrence-events.json'
TRAINING_REPORT = REPORT_DIR / f'{EXPERIMENT}-training-report.json'
MODEL = PRIVATE / f'{EXPERIMENT}-models/logistic-1h.joblib'
OUT = ROOT / 'docs/environmental-models-2026-10-22/goes19-snmf-2026-jan-event-audit.json'
THRESHOLD = 0.5
RADIUS_KM = 10.0
ACTIVE_STATES = {'ACTIVO', 'CONTENIDO', 'CONTROLADO'}


def wilson(successes, total, z=1.959963984540054):
    if total == 0:
        return None
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [max(0.0, center - margin), min(1.0, center + margin)]


def main():
    hourly.EXPERIMENT = EXPERIMENT
    hourly.OBS = PRIVATE / f'{EXPERIMENT}-observations.csv.gz'
    hourly.AVAILABILITY = PRIVATE / f'{EXPERIMENT}-availability-by-scan.csv'
    times, created, matrix, coordinates, regions = hourly.load_arrays()
    model = joblib.load(MODEL)
    event_report = json.loads(EVENTS.read_text(encoding='utf-8'))
    test_start, test_end = date(2026, 1, 1), date(2026, 2, 1)

    # Collapse repeat scans to the maximum model score per pixel-day. This
    # answers whether the route area had any alert that day; scans are not
    # treated as independent observations.
    score_by_day = {}
    persistence_by_day = {}
    predictions_by_day = defaultdict(int)
    for issue, issued_at in enumerate(created[:-1]):
        target_time = issued_at + timedelta(hours=1)
        right = bisect_left(created, target_time, lo=issue + 1)
        candidates = [j for j in (right - 1, right) if issue < j < len(created)]
        target = min(candidates, key=lambda j: abs((created[j] - target_time).total_seconds()), default=None)
        if target is None or abs((created[target] - target_time).total_seconds()) > 15 * 60:
            continue
        target_day = created[target].date()
        if not test_start <= target_day < test_end:
            continue
        features, usable = hourly.issue_features(issue, created, matrix, coordinates)
        usable &= matrix[target] >= 0
        if not usable.any():
            continue
        score = model.predict_proba(features[usable])[:, 1].astype(np.float32)
        day_scores = score_by_day.setdefault(target_day.isoformat(), np.full(len(coordinates), np.nan, dtype=np.float32))
        day_persistence = persistence_by_day.setdefault(target_day.isoformat(), np.zeros(len(coordinates), dtype=np.uint8))
        indices = np.flatnonzero(usable)
        prior = day_scores[indices]
        day_scores[indices] = np.where(np.isnan(prior), score, np.maximum(prior, score))
        day_persistence[indices] = np.maximum(day_persistence[indices], (features[usable, 6] >= 0.5).astype(np.uint8))
        predictions_by_day[target_day.isoformat()] += int(usable.sum())

    grouped_events = {}
    for event in event_report['deduplicated_events']:
        if event['latitude'] is None or event['longitude'] is None:
            continue
        key = (event['province'], event['reported_start_date'], round(event['latitude'], 3),
            round(event['longitude'], 3))
        current = grouped_events.get(key)
        if current is None:
            grouped_events[key] = event | {'name_aliases': [event['incident_name']]}
        else:
            current['name_aliases'].append(event['incident_name'])
            if event['report_date'] < current['report_date']:
                grouped_events[key] = event | {'name_aliases': current['name_aliases']}
    event_points = list(grouped_events.values())
    tree = BallTree(np.radians(coordinates.astype(np.float64)), metric='haversine')
    evaluated, uncovered = [], []
    for event in event_points:
        report_day = event['report_date']
        if not (test_start.isoformat() <= report_day < test_end.isoformat()):
            continue
        nearby = tree.query_radius(np.radians([[event['latitude'], event['longitude']]]),
            r=RADIUS_KM / 6371.0088)[0]
        day_scores = score_by_day.get(report_day)
        day_persistence = persistence_by_day.get(report_day)
        valid = nearby if day_scores is not None else np.array([], dtype=int)
        if day_scores is not None:
            valid = nearby[np.isfinite(day_scores[nearby])]
        row = {'incident_name': event['incident_name'], 'province': event['province'],
            'name_aliases_in_archive': event['name_aliases'],
            'reported_start_date': event['reported_start_date'], 'first_archived_snapshot_date': report_day,
            'reported_status': event['status'], 'latitude': event['latitude'], 'longitude': event['longitude'],
            'valid_model_pixels_within_radius': int(len(valid)),
            'maximum_one_hour_score_within_radius': (float(np.nanmax(day_scores[valid])) if len(valid) else None),
            'model_alert': bool(np.any(day_scores[valid] >= THRESHOLD)) if len(valid) else False,
            'persistence_alert': bool(np.any(day_persistence[valid] == 1)) if len(valid) else False}
        (evaluated if len(valid) else uncovered).append(row)

    active = [event for event in evaluated if event['reported_status'] in ACTIVE_STATES]
    detected = [event for event in active if event['model_alert']]
    persistence_detected = [event for event in active if event['persistence_alert']]
    label_metrics = json.loads(TRAINING_REPORT.read_text(encoding='utf-8'))['rows_by_horizon']['1']['test']
    report = {
        'experiment_id': 'frozen-goes19-1h-vs-independent-snmf-reports-2026-01',
        'interpretation': 'Retrospective event coincidence on the frozen test period; not an estimate of precision or a validated warning lead time.',
        'protocol': {'threshold': THRESHOLD, 'radius_km': RADIUS_KM,
            'day_aggregation': 'maximum 1h forecast score among all test scans for each pixel-day',
            'active_statuses': sorted(ACTIVE_STATES),
            'official_date_rule': 'first archived snapshot date per extracted incident; report date and start date are not exact ignition times'},
        'sources': {'snmf_events_sha256': sha256(EVENTS), 'training_report_sha256': sha256(TRAINING_REPORT),
            'goes_observations_sha256': sha256(hourly.OBS), 'goes_availability_sha256': sha256(hourly.AVAILABILITY),
            'model_sha256': sha256(MODEL)},
        'covered_test_pixel_days': int(sum(predictions_by_day.values())),
        'test_days_with_predictions': len(score_by_day),
        'snmf_incidents_with_test_day_pixel_coverage': len(evaluated),
        'snmf_incidents_without_test_day_pixel_coverage': len(uncovered),
        'active_or_controlled_incidents_with_coverage': len(active),
        'active_or_controlled_incidents_with_model_alert': len(detected),
        'active_or_controlled_incidents_with_persistence_alert': len(persistence_detected),
        'event_coincidence_sensitivity_on_covered_subset': len(detected) / len(active) if active else None,
        'event_coincidence_sensitivity_wilson_95pct': wilson(len(detected), len(active)),
        'persistence_event_coincidence_sensitivity_on_covered_subset': len(persistence_detected) / len(active) if active else None,
        'persistence_event_coincidence_sensitivity_wilson_95pct': wilson(len(persistence_detected), len(active)),
        'satellite_label_test_metrics': label_metrics,
        'incidents_with_model_alert': detected,
        'incidents_with_persistence_alert': persistence_detected,
        'incidents_with_coverage_without_alert': [event for event in active if not event['model_alert']],
        'limitations': [
            'The SNMF daily archive is jurisdiction-reported and not an exhaustive fire/no-fire registry; unmatched alerts cannot be counted as false positives, so event precision is not calculable.',
            'This comparison uses same-day report snapshots and cannot establish how many minutes before ignition the model warned.',
            'A 10 km circle around one reported coordinate is an exploratory association rule, not a validated trail-safety distance.',
            'Daily scores are maxima over correlated satellite scans and nearby pixels; event-level counts are the unit for this comparison.',
            'At 0.5 the frozen model was trained on 28 positive pixel-scan labels and evaluated on 136 positive test labels across 23 region-days; the small number of independent fire episodes limits precision claims.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('covered_test_pixel_days', 'test_days_with_predictions',
        'snmf_incidents_with_test_day_pixel_coverage', 'snmf_incidents_without_test_day_pixel_coverage',
        'active_or_controlled_incidents_with_coverage', 'active_or_controlled_incidents_with_model_alert',
        'active_or_controlled_incidents_with_persistence_alert', 'event_coincidence_sensitivity_on_covered_subset',
        'event_coincidence_sensitivity_wilson_95pct', 'persistence_event_coincidence_sensitivity_on_covered_subset',
        'persistence_event_coincidence_sensitivity_wilson_95pct',
        'incidents_with_model_alert')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
