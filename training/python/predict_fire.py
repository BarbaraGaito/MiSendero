"""Versioned daily fire inference from separate recent observed pixel histories."""
from datetime import datetime, timedelta, timezone
import json
import math

import joblib
import pandas as pd

from environmental_sources import PUBLIC, ROOT, sha256
from fire_sources import PRIVATE, REPORT_DIR, protocol
from fire_features import FEATURES, inputs, load_cells


def visualization_gate(report):
    selected = report['selection']
    baselines = ('training_prevalence', 'seasonal_training_prevalence', 'persistence')
    if selected in baselines:
        return False
    for split in ('temporal_test', 'geographic_test'):
        scores = report['test'][split]
        chosen = scores[selected]
        if chosen['positive_observations'] < 5 or chosen['pr_auc_average_precision'] is None:
            return False
        if chosen['pr_auc_average_precision'] <= max(scores[b]['pr_auc_average_precision'] for b in baselines):
            return False
        if chosen['brier'] > scores['training_prevalence']['brier']:
            return False
    return True


def main():
    path = REPORT_DIR / 'fire-results.json'
    if not path.exists():
        return
    report = json.loads(path.read_text(encoding='utf-8'))
    registry_path = ROOT / 'backend/src/data/environmentalModels.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    registry['artifacts'] = {k: v for k, v in registry['artifacts'].items() if v['model_type'] != 'fire_detection'}
    if report['status'] != 'experimental':
        registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print('Fire model remains blocked by insufficient real classes')
        return
    audit = json.loads((REPORT_DIR / 'fire-results-audit.json').read_text(encoding='utf-8'))
    if audit['status'] != 'passed' or audit['report_sha256'] != sha256(path):
        raise ValueError('Fire model requires a matching passed real-source audit')
    artifact = report['artifact']
    allowed = visualization_gate(report)
    registry['models']['fire_detection']['fallback_status'] = 'no_data' if allowed else 'not_approved'
    registry['models']['fire_detection']['unavailable_message'] = ('No hay una estimación de actividad de fuego evaluada para este sector.' if allowed else
        'El modelo experimental de detección de fuego no alcanzó la fiabilidad necesaria para ofrecer estimaciones durante el trekking.')
    registry['artifacts'][artifact['id']] = {'model_type': 'fire_detection', 'version': artifact['version'],
        'algorithm': report['selection'], 'evidence_sha256': sha256(path), 'visualization_allowed': allowed,
        'deployment_approved': False, 'scope': 'One qualified Argentine land pixel; next 24h MODIS detection, not wildfire safety.'}
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    recent_path = PRIVATE / 'fire-recent-observations.csv.gz'
    recent_audit_path = REPORT_DIR / 'fire-recent-source-audit.json'
    if not recent_path.exists() or not recent_audit_path.exists():
        raise ValueError('Acquire separate recent fire inputs before inference')
    recent_source = json.loads(recent_audit_path.read_text(encoding='utf-8'))
    if recent_source['summary']['observations_sha256'] != sha256(recent_path):
        raise ValueError('Recent observed-pixel provenance mismatch')
    cells, _ = load_cells(recent_path)
    regions = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    issue = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    fitted = None
    if artifact['model_file']:
        if artifact['model_file'] != 'fire-mod14a1.joblib' or sha256(PRIVATE / 'fire-mod14a1.joblib') != artifact['model_sha256']:
            raise ValueError('Only own verified fire model artifact may be loaded')
        fitted = joblib.load(PRIVATE / 'fire-mod14a1.joblib')
    forecasts = []
    for region in regions:
        candidates = [c for c in cells.values() if c['region'] == region['name']]
        def distance(cell):
            dlat = cell['latitude'] - region['latitude']
            dlon = (cell['longitude'] - region['longitude']) * math.cos(math.radians(region['latitude']))
            return math.hypot(dlat, dlon) * 111195
        cell = min(candidates, key=distance) if candidates else None
        base = {'model_id': artifact['id'], 'model_version': artifact['version'], 'region': region['name'],
            'region_geometry_hash': region['geometry_sha256'], 'evidence_sha256': sha256(path)}
        if cell is None or distance(cell) > 1000:
            forecasts.append(base | {'status': 'no_data', 'prediction': None, 'reason': 'No qualified land cell at the catalog center'})
            continue
        history = [r for r in cell['records'] if r['available_at'] <= issue and r['day'] + timedelta(days=1) <= issue]
        x = inputs(history, issue, cell['latitude'], cell['longitude'], protocol()['maximum_latest_age_days'])
        if x is None:
            forecasts.append(base | {'status': 'no_data', 'prediction': None, 'reason': 'Recent qualified inputs missing or stale'})
            continue
        if fitted is not None:
            probability = float(fitted.predict_proba(pd.DataFrame([x], columns=FEATURES))[0, 1])
        elif report['selection'] == 'persistence':
            probability = x['latest_fire']
        elif report['selection'] == 'seasonal_training_prevalence':
            probability = artifact['seasonal_prevalence'].get(str(issue.month), artifact['prevalence'])
        else:
            probability = artifact['prevalence']
        scope = {'kind': 'pixel', 'pixel_id': cell['pixel_id'], 'latitude': cell['latitude'], 'longitude': cell['longitude'],
            'description': f"Celda MODIS de aproximadamente 1 km en {region['name']}. No representa todo el sendero ni identifica la causa del fuego."}
        candidate = base | {'status': 'experimental' if allowed else 'not_approved',
            'prediction': {'probability': probability, 'horizon_hours': 24} if allowed else None,
            'research_candidate_probability': probability, 'geographic_scope': scope,
            'observed_at': (history[-1]['day'] + timedelta(days=1)).isoformat(),
            'inputs_available_at': max(r['available_at'] for r in history[-4:]).isoformat(),
            'issued_at': issue.isoformat(), 'target_at': (issue + timedelta(days=1)).isoformat(),
            'valid_until': (issue + timedelta(days=1)).isoformat(), 'source_sha256': sha256(recent_path),
            'route_association_approved': False}
        forecasts.append(candidate)
    destination = PRIVATE / 'fire-forecasts.json'
    destination.write_text(json.dumps({'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'forecasts': forecasts, 'visualization_allowed': allowed, 'deployment_approved': False,
        'note': 'research_candidate_probability is a private diagnostic; a failed evaluation gate never becomes a numerical app snapshot.'},
        indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print('Fire inference:', len(forecasts), 'documented catalog sectors; experimental visualization gate:', allowed)


if __name__ == '__main__':
    main()
