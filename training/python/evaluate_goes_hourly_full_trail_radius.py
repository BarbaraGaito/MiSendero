#!/usr/bin/env python3
"""Re-evaluate frozen hourly GOES models only within a full-trail radius.

Research-only spatial sensitivity analysis. It does not retrain a model and
keeps GOES labels as satellite-detection proxies, not physical-fire labels.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np

import train_fire_hourly as hourly
from audit_inpe_reference_detections_route_polylines import (
    distance_to_polyline_km, prepare_routes,
)
from environmental_sources import ROOT, sha256
from evaluate_goes_hourly_route_sector_horizons import (
    HORIZONS, MIN_ALERTS_VALIDATION, PRECISION_FLOOR, choose_threshold,
    collapse_hourly, metrics,
)


EXPERIMENT = 'fire-goes19-2025q4-2026jan'
OBS = ROOT / 'training/data/environmental/private' / f'{EXPERIMENT}-observations.csv.gz'
AVAILABILITY = ROOT / 'training/data/environmental/private' / f'{EXPERIMENT}-availability-by-scan.csv'
MODELS = ROOT / 'training/data/environmental/private' / f'{EXPERIMENT}-models'
GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
TRAINING_REPORT = ROOT / 'docs/environmental-models-2026-10-22/fire-goes19-2025q4-2026jan-training-report.json'
SNMF_EVENT_AUDIT = ROOT / 'docs/environmental-models-2026-10-22/goes19-snmf-2026-jan-event-audit.json'
SNMF_CROSSCHECK = ROOT / 'docs/environmental-models-2026-10-22/fire-goes19-short-lead-snmf-incident-crosscheck.json'
OUT = ROOT / 'docs/environmental-models-2026-10-22/fire-goes19-full-trail-10km-evaluation.json'
OUT_MD = OUT.with_suffix('.md')
RADIUS_KM = 10.0
MIN_CORE_PIXELS = 5
VALIDATION_START = datetime.fromisoformat('2025-12-01T00:00:00+00:00')
TEST_START = datetime.fromisoformat('2026-01-01T00:00:00+00:00')
TEST_END = datetime.fromisoformat('2026-02-01T00:00:00+00:00')


def main() -> None:
    hourly.EXPERIMENT = EXPERIMENT
    hourly.OBS = OBS
    hourly.AVAILABILITY = AVAILABILITY
    times, created, matrix, coordinates, regions = hourly.load_arrays()
    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    routes = {row['name']: row for row in prepare_routes(geometry['fire_route_geometries'])}
    region_columns = {
        region: np.asarray([idx for idx, value in enumerate(regions) if value == region], dtype=np.int64)
        for region in sorted(set(regions))
    }
    core_columns = {}
    core_counts = {}
    for region, cols in region_columns.items():
        if region not in routes:
            raise ValueError(f'Missing complete route geometry for GOES region: {region}')
        distances = np.asarray([
            distance_to_polyline_km(float(coordinates[col, 0]), float(coordinates[col, 1]), routes[region]['projection'])
            for col in cols
        ])
        core = cols[distances <= RADIUS_KM]
        if len(core) < MIN_CORE_PIXELS:
            raise ValueError(f'Only {len(core)} sampled pixels within {RADIUS_KM} km for {region}')
        core_columns[region] = core
        core_counts[region] = int(len(core))

    models = {h: joblib.load(MODELS / f'logistic-{h}h.joblib') for h in HORIZONS}
    rows_by_horizon: dict[int, list[dict]] = {h: [] for h in HORIZONS}
    pair_counts = {h: 0 for h in HORIZONS}
    for issue, issue_time in enumerate(created):
        targets = {}
        for horizon in HORIZONS:
            wanted = issue_time + timedelta(hours=horizon)
            target = min(
                range(issue + 1, len(created)),
                key=lambda idx: abs((created[idx] - wanted).total_seconds()),
                default=None,
            )
            if target is None or abs((created[target] - wanted).total_seconds()) > 15 * 60:
                continue
            target_time = created[target]
            if target_time < TEST_END:
                targets[horizon] = (target, target_time)
                pair_counts[horizon] += 1
        if not targets:
            continue
        features, usable = hourly.issue_features(issue, created, matrix, coordinates)
        for horizon, (target, target_time) in targets.items():
            labels = matrix[target]
            if target_time < VALIDATION_START:
                part = 'training'
            elif target_time < TEST_START:
                part = 'validation'
            else:
                part = 'test'
            model = models[horizon]
            for region, cols in core_columns.items():
                target_core = cols[labels[cols] >= 0]
                min_valid = max(MIN_CORE_PIXELS, int(np.ceil(0.50 * len(cols))))
                if len(target_core) < min_valid:
                    continue
                usable_core = cols[usable[cols] & (labels[cols] >= 0)]
                min_history = max(3, int(np.ceil(0.25 * len(cols))))
                if len(usable_core) < min_history:
                    continue
                scores = model.predict_proba(features[usable_core])[:, 1]
                rows_by_horizon[horizon].append({
                    'partition': part,
                    'region': region,
                    'target_time': target_time.isoformat(),
                    'label': int(np.any(labels[target_core] == 1)),
                    'score': float(np.max(scores)),
                    'persistence': int(np.any(features[usable_core, 6] == 1)),
                })

    training_report = json.loads(TRAINING_REPORT.read_text(encoding='utf-8'))
    event_audit = json.loads(SNMF_EVENT_AUDIT.read_text(encoding='utf-8'))
    snmf_crosscheck = json.loads(SNMF_CROSSCHECK.read_text(encoding='utf-8'))
    barda = next(
        row for row in event_audit['incidents_with_coverage_without_alert']
        if row['incident_name'] == 'Barda de La Loma'
    )
    barda_match = next(
        incident
        for episode in snmf_crosscheck['alert_episode_matches']
        for incident in episode['nearby_active_snmf_incidents_within_10km']
        if incident['incident_name'] == 'Barda de La Loma'
    )
    external_event = {
        'source': 'Independent January SNMF event audit against frozen GOES model outputs.',
        'incident_name': barda['incident_name'],
        'province': barda['province'],
        'reported_start_date': barda['reported_start_date'],
        'reported_status': barda['reported_status'],
        'distance_to_trail_km': barda_match['distance_km'],
        'valid_model_pixels_within_event_radius': barda['valid_model_pixels_within_radius'],
        'maximum_one_hour_model_score': barda['maximum_one_hour_score_within_radius'],
        'model_alert': barda['model_alert'],
        'interpretation': 'SNMF reports a controlled incident near the route during the held-out January test; the frozen GOES model had valid pixel coverage but did not alert. The daily incident report does not establish ignition hour or GOES observational completeness.',
    }
    output = {
        'experiment_id': 'goes19-frozen-model-full-trail-10km-sensitivity',
        'status': 'exploratory_unapproved',
        'target': 'Any nominal/high-quality GOES fire detection among sampled pixels within 10 km of the complete trail polyline during the target hour; not a physical-fire occurrence or ignition label.',
        'protocol': {
            'frozen_models_only': True,
            'models_refit': False,
            'radius_km': RADIUS_KM,
            'geometry': 'Complete local route polylines; each GOES sampled pixel retained only when its distance to the matching route polyline is at most 10 km.',
            'sampled_core_pixels_by_route': core_counts,
            'coverage_rule': 'At least max(5, ceil(50% of sampled core pixels)) with known target labels, and at least max(3, ceil(25% of core pixels)) with usable recent history. Unknown pixels remain excluded.',
            'temporal_split': {'validation': ['2025-12-01', '2025-12-31'], 'test': ['2026-01-01', '2026-01-31']},
            'threshold_gate': f'Validation GOES proxy precision >= {PRECISION_FLOOR:.0%} with at least {MIN_ALERTS_VALIDATION} route-hour alerts; maximize recall. If no threshold passes, 0.5 is diagnostic only.',
        },
        'inputs': {
            'goes_observations_sha256': sha256(OBS),
            'goes_availability_sha256': sha256(AVAILABILITY),
            'training_report_sha256': sha256(TRAINING_REPORT),
            'route_geometry_sha256': sha256(GEOMETRY),
        'independent_snmf_event_audit_sha256': sha256(SNMF_EVENT_AUDIT),
        'goes_episode_snmf_crosscheck_sha256': sha256(SNMF_CROSSCHECK),
        },
        'results_by_horizon': {},
        'independent_near_route_event_check': external_event,
        'limitations': [
            'This spatially restricted target remains GOES detection, not independently confirmed physical wildfire or ignition.',
            'The frozen classifier was trained on broader pixels; this is a spatial transfer/sensitivity evaluation, not a newly fitted 10 km model.',
            'Pixels within 10 km are sampled raster locations, not continuous coverage of the full corridor.',
            'Adjacent route-hours and pixels are dependent; episode-level uncertainty remains wider than naive row counts suggest.',
            'No operating threshold is approved for safety advice or app deployment.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    for horizon in HORIZONS:
        rows = rows_by_horizon[horizon]
        training_rows = collapse_hourly([row for row in rows if row['partition'] == 'training'])
        validation_rows = collapse_hourly([row for row in rows if row['partition'] == 'validation'])
        test_rows = collapse_hourly([row for row in rows if row['partition'] == 'test'])
        prevalence = float(np.mean([row['label'] for row in training_rows])) if training_rows else 0.0
        threshold = choose_threshold(validation_rows, prevalence)
        threshold_value = threshold.get('threshold') if threshold['selected'] else 0.5
        output['results_by_horizon'][str(horizon)] = {
            'matched_issue_target_scan_pairs': pair_counts[horizon],
            'training_route_hours': len(training_rows),
            'training_positive_route_hours': int(sum(row['label'] for row in training_rows)),
            'validation_route_hours': len(validation_rows),
            'test_route_hours': len(test_rows),
            'validation_threshold': threshold,
            'selected_or_diagnostic_threshold': threshold_value,
            'validation': metrics(validation_rows, threshold_value, prevalence),
            'test_at_fixed_0_5_diagnostic': metrics(test_rows, 0.5, prevalence),
            'test_at_selected_or_diagnostic_threshold': metrics(test_rows, threshold_value, prevalence),
            'frozen_model_sha256': sha256(MODELS / f'logistic-{horizon}h.joblib'),
        }

    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        '# GOES G19: sensibilidad espacial a 10 km de la polilínea completa', '',
        'Se reusaron los cinco clasificadores congelados y el corte temporal original (validación diciembre de 2025; test enero de 2026), contando solo píxeles muestreados a ≤10 km de las polilíneas completas. No se reentrenó ni calibró ningún modelo.', '',
        '| Horizonte | Píxeles núcleo | Horas ruta train | Positivos GOES train | Horas ruta val. | Positivos GOES val. | Umbral validado | Horas ruta test | Positivos GOES test | Avisos test (0,5 diag.) |',
        '|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|',
    ]
    for horizon, item in output['results_by_horizon'].items():
        diagnostic = item['test_at_fixed_0_5_diagnostic']
        gate = item['validation_threshold']
        if gate['selected']:
            selection = f"sí: {gate['threshold']:.6g}"
        else:
            best = gate['best_validation_precision_with_at_least_minimum_alerts']
            selection = f"no; mejor {best['true_positive_alerts']}/{best['alerts']} ({best['precision_proxy']:.1%})"
        lines.append(
            f"| {horizon} | {sum(core_counts.values())} | {item['training_route_hours']} | {item['training_positive_route_hours']} | {item['validation_route_hours']} | {item['validation']['positive_route_sector_hours']} | {selection} | {item['test_route_hours']} | {diagnostic['positive_route_sector_hours']} | {diagnostic['alerts']} |"
        )
    lines += [
        '',
        'El objetivo es una detección GOES en el corredor cercano al recorrido, no un incendio físico confirmado. Un umbral se selecciona solo si supera la puerta de validación; si ninguno la supera, los conteos a 0,5 son diagnósticos. Los píxeles desconocidos no se convierten en negativos.', '',
        f"Las ocho polilíneas tienen {sum(core_counts.values())} píxeles muestreados dentro de 10 km (por ruta: {json.dumps(core_counts, ensure_ascii=False)}).", '',
        f"La ausencia de etiquetas GOES cercanas no demuestra ausencia de incendio. Durante el test, el SNMF registró {external_event['incident_name']} ({external_event['reported_status']}), a {external_event['distance_to_trail_km']:.3f} km del recorrido. El auditor independiente encontró {external_event['valid_model_pixels_within_event_radius']} píxeles GOES válidos pero score máximo {external_event['maximum_one_hour_model_score']:.6g} y ningún aviso del modelo. Es un caso preocupante de posible omisión de un evento reportado; el parte diario no fija la hora de ignición. [Detalle del cruce SNMF](goes19-snmf-2026-jan-event-audit.json).", '',
        'La comparación evalúa transferencia espacial de modelos entrenados con sectores más amplios. Incluso si mejora frente al análisis sectorial, no mide probabilidad de incendio ni justifica una alerta de seguridad; para eso siguen faltando observaciones independientes completas, incluidas ventanas sin incendio verificadas y tiempo de publicación del dato.', '',
        f"Criterios, datos por horizonte y hashes: [JSON reproducible]({OUT.name}). Reproducción: [`evaluate_goes_hourly_full_trail_radius.py`](../../training/python/evaluate_goes_hourly_full_trail_radius.py). Evaluación sectorial previa: [informe](fire-goes19-short-lead-route-sector-evaluation.md).", '',
    ]
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({
        'json': OUT.relative_to(ROOT).as_posix(),
        'markdown': OUT_MD.relative_to(ROOT).as_posix(),
        'route_core_pixel_counts': core_counts,
        'thresholds_selected': {h: row['validation_threshold']['selected'] for h, row in output['results_by_horizon'].items()},
        'test_diagnostics': {h: row['test_at_fixed_0_5_diagnostic'] for h, row in output['results_by_horizon'].items()},
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
