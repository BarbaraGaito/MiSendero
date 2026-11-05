"""Export versioned station forecasts and registry; never infer a trail association.

Only own locally trained, hash-verified joblib artifacts are loaded. Route
snapshots additionally require an independently reviewed hydrological link.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import joblib
import pandas as pd

from environmental_sources import FEATURES, PUBLIC, ROOT, STATIONS, fetch_station, inputs, observations, sha256


def main():
    report_path = ROOT / 'docs/environmental-models-2026-10-22/river-results.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    registry_path = ROOT / 'backend/src/data/environmentalModels.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    registry['artifacts'] = {key: value for key, value in registry['artifacts'].items() if value['model_type'] != 'river_level'}
    forecasts = []
    # Hourly as-of origin matches the evaluated hourly issue schedule. A late
    # batch remains labelled with that origin, not falsely with its run time.
    issue = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for model in report['models']:
        if model['series_id'] not in STATIONS:
            continue  # Explicitly excluded sources cannot reappear from old reports.
        if model['status'] != 'experimental':
            continue
        artifact = model['model_artifact']
        station, horizon = model['series_id'], model['horizon_hours']
        if station not in STATIONS or horizon not in (3, 6):
            raise ValueError('Report refers to an unreviewed station or horizon')
        identifier = f'river-{station}-{horizon}h'
        if artifact['id'] != identifier:
            raise ValueError('Artifact identifier must match the reviewed station and horizon')
        allowed = model['beats_test_persistence'] and model['selection'] != 'persistence'
        registry['artifacts'][identifier] = {
            'model_type': 'river_level', 'version': str(artifact['version']), 'series_id': model['series_id'],
            'station_name': model['station'], 'horizon_hours': model['horizon_hours'],
            'algorithm': model['selection'], 'evidence_sha256': sha256(report_path),
            'historical_mae_m': model['test'][model['selection']]['mae_m'],
            'visualization_allowed': allowed, 'deployment_approved': False,
            'scope': 'Station-specific retrospective chronological test; trail applicability not approved.'}
        raw, input_source = fetch_station(model['series_id'])
        clean, _ = observations(raw)
        history = [r for r in clean if r['observed_at'] <= issue and r['available_at'] <= issue]
        x = inputs(history, issue)
        if not allowed or x is None:
            forecasts.append({'model_id': identifier, 'status': 'not_approved' if not allowed else 'no_data', 'prediction': None})
            continue
        artifact_path = PUBLIC / 'private' / f'{identifier}-artifact.json'
        saved = json.loads(artifact_path.read_text(encoding='utf-8'))
        path = PUBLIC / 'private' / f'{identifier}.joblib'
        if saved != artifact or saved['model_sha256'] != sha256(path):
            raise ValueError('Model artifact provenance/hash mismatch')
        predictor = joblib.load(path)
        value = x['latest_level_m'] + float(predictor.predict(pd.DataFrame([x], columns=FEATURES))[0])
        target = issue + timedelta(hours=model['horizon_hours'])
        forecasts.append({'model_id': identifier, 'model_version': str(artifact['version']), 'status': 'experimental',
            'series_id': model['series_id'], 'station_name': model['station'], 'station_coordinates': model['station_coordinates'],
            'level_m': value, 'latest_level_m': x['latest_level_m'], 'historical_mae_m': model['test'][model['selection']]['mae_m'],
            'observed_at': history[-1]['observed_at'].isoformat(),
            'inputs_available_at': max(r['available_at'] for r in history[-4:]).isoformat(),
            'issued_at': issue.isoformat(), 'target_at': target.isoformat(), 'valid_until': target.isoformat(),
            'horizon_hours': model['horizon_hours'], 'evidence_sha256': sha256(report_path),
            'source_sha256': input_source['sha256'], 'route_association_approved': False})
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    destination = PUBLIC / 'private/station-forecasts.json'
    destination.write_text(json.dumps({'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'forecasts': forecasts, 'route_snapshots': [],
        'note': 'No route forecasts: no independently reviewed river/station/trail associations configured.'},
        indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print('Registered', len(registry['artifacts']), 'evaluated station/horizon artifacts; numerical station forecasts',
          sum('level_m' in f for f in forecasts), '; route associations', len(registry['reviewed_route_associations']))


if __name__ == '__main__':
    main()
