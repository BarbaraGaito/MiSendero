"""Cross-check the held-out GOES+GFS alert against the route-day SNMF proxy.

The 0.5 alert threshold was fixed by the preceding model evaluation; this
script does not tune it. Scores are compared with SNMF-listed incidents only.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from environmental_sources import ROOT, sha256

BASE = ROOT / 'docs/environmental-models-2026-10-22'
MODEL = BASE / 'fire-goes-gfs-24h-evaluation.json'
PROXY = BASE / 'snmf-2026-jan-route-day-report-proxy.json'
OUT = BASE / 'fire-goes-gfs-snmf-route-day-proxy-2026-jan.json'


def confusion(rows, alert_key):
    counts = {'tp': 0, 'alert_without_nearby_reported_fire': 0,
        'missed_nearby_reported_fire': 0, 'tn_no_nearby_reported_fire': 0}
    for row in rows:
        label, alert = row['snmf_proxy_label'], bool(row[alert_key])
        if label and alert:
            counts['tp'] += 1
        elif label:
            counts['missed_nearby_reported_fire'] += 1
        elif alert:
            counts['alert_without_nearby_reported_fire'] += 1
        else:
            counts['tn_no_nearby_reported_fire'] += 1
    alerts = counts['tp'] + counts['alert_without_nearby_reported_fire']
    positives = counts['tp'] + counts['missed_nearby_reported_fire']
    counts['precision_vs_SNMF_proxy'] = counts['tp'] / alerts if alerts else None
    counts['recall_vs_SNMF_proxy'] = counts['tp'] / positives if positives else None
    return counts


def alert_episodes(predictions, labels, alert_key):
    grouped = {}
    for prediction in predictions:
        grouped.setdefault(prediction['route_sector'], []).append(prediction)
    episodes = []
    for sector, sector_rows in grouped.items():
        sector_rows.sort(key=lambda row: row['target_date'])
        active = []
        previous_day = None
        for prediction in sector_rows + [{'target_date': None, alert_key: False}]:
            current_day = date.fromisoformat(prediction['target_date']) if prediction['target_date'] else None
            consecutive = (previous_day is not None and current_day is not None
                and current_day == previous_day + timedelta(days=1))
            if active and (not prediction[alert_key] or not consecutive):
                start, end = active[0]['target_date'], active[-1]['target_date']
                episode_labels = [labels[(sector, day.isoformat())]['label']
                    for day in (date.fromisoformat(start) + timedelta(days=offset)
                        for offset in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1))
                    if (sector, day.isoformat()) in labels]
                episodes.append({'route_sector': sector, 'start_date': start, 'end_date': end,
                    'alert_days': len(active), 'contains_report_proxy_positive': any(episode_labels),
                    'matched_positive_days': sum(episode_labels)})
                active = []
            if prediction['target_date'] and prediction[alert_key]:
                active.append(prediction)
            previous_day = current_day
    matched = sum(episode['contains_report_proxy_positive'] for episode in episodes)
    return {'alert_episodes': len(episodes),
        'episodes_with_nearby_reported_incident': matched,
        'descriptive_episode_coincidence_fraction': matched / len(episodes) if episodes else None,
        'alert_days_in_episodes': sum(episode['alert_days'] for episode in episodes),
        'episodes': episodes}


def main():
    evaluation = json.loads(MODEL.read_text(encoding='utf-8'))
    proxy = json.loads(PROXY.read_text(encoding='utf-8'))
    predictions = {(row['route_sector'], row['target_date']): row
        for row in evaluation['test']['route_sector_day_predictions']}
    labels = {(row['route_sector'], row['report_date']): row
        for row in proxy['route_days']}
    rows = []
    for key in sorted(predictions.keys() & labels.keys()):
        pred, label = predictions[key], labels[key]
        rows.append({'route_sector': key[0], 'date': key[1],
            'model_score': pred['score'], 'model_alert_at_0_5': pred['alert_at_0_5'],
            'persistence_alert': pred['persistence'], 'snmf_proxy_label': label['label'],
            'snmf_proxy_meaning': label['label_meaning'],
            'nearby_incidents': label['nearby_incidents']})
    results = {
        'experiment_id': 'goes-gfs-24h-vs-2026-jan-snmf-route-day-report-proxy',
        'interpretation': 'Descriptive agreement with available SNMF daily incident reports. A proxy-negative is not proof of physical absence of fire.',
        'protocol': {'threshold': 0.5, 'threshold_selection': 'fixed before this proxy comparison; not tuned here',
            'radius_km': 10, 'lead_hours': 24,
            'target': proxy['target'], 'missing_report_dates': 'unknown and excluded'},
        'sources': {'model_evaluation_sha256': sha256(MODEL), 'route_day_proxy_sha256': sha256(PROXY)},
        'matched_route_sector_days': len(rows),
        'matched_positive_route_sector_days': sum(row['snmf_proxy_label'] for row in rows),
        'model': confusion(rows, 'model_alert_at_0_5'),
        'persistence': confusion(rows, 'persistence_alert'),
        'model_alert_episode_coincidence': alert_episodes(
            [row for row in evaluation['test']['route_sector_day_predictions']
                if (row['route_sector'], row['target_date']) in labels], labels, 'alert_at_0_5'),
        'persistence_alert_episode_coincidence': alert_episodes(
            [row for row in evaluation['test']['route_sector_day_predictions']
                if (row['route_sector'], row['target_date']) in labels], labels, 'persistence'),
        'limitations': [
            'The SNMF proxy only establishes whether an incident was listed in the available official report; it cannot verify all physical fires or all clear periods.',
            'The January test observations repeat fire episodes across days and sectors, so route-day confidence intervals would overstate independent sample size.',
            'The diagnostic score threshold is not a calibrated probability and was not selected on this SNMF proxy.',
            'This comparison inherits the satellite model test period and cannot be used to claim ignition prediction accuracy or trail safety.',
        ],
        'deployment_approved': False,
        'route_sector_day_rows': rows,
    }
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in results.items()
        if key not in ('sources', 'limitations', 'route_sector_day_rows')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
