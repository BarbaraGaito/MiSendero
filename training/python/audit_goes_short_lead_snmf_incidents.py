#!/usr/bin/env python3
"""Cross-check the frozen one-hour GOES route alerts against SNMF snapshots.

This is a sparse positive incident corroboration. It cannot estimate physical
fire precision or establish whether an alert preceded ignition.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from audit_inpe_reference_detections_route_polylines import (
    distance_to_polyline_km, prepare_routes,
)
from environmental_sources import ROOT, sha256


BASE = ROOT / 'docs/environmental-models-2026-10-22'
GOES_REPORT = BASE / 'fire-goes19-short-lead-route-sector-evaluation.json'
SNMF_EVENTS = BASE / 'snmf-2026-jan-daily-occurrence-events.json'
GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
OUT = BASE / 'fire-goes19-short-lead-snmf-incident-crosscheck.json'
OUT_MD = OUT.with_suffix('.md')
ACTIVE_STATUSES = {'ACTIVO', 'CONTROLADO', 'CONTENIDO', 'GUARDIA DE CENIZAS', 'UNKNOWN'}


def incident_key(row: dict) -> tuple:
    return (
        row.get('province'), row.get('reported_start_date'),
        round(float(row['latitude']), 3), round(float(row['longitude']), 3),
    )


def main() -> None:
    model = json.loads(GOES_REPORT.read_text(encoding='utf-8'))
    events = json.loads(SNMF_EVENTS.read_text(encoding='utf-8'))['snapshots']
    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    routes = {row['name']: row for row in prepare_routes(geometry['fire_route_geometries'])}
    episodes = model['results_by_horizon']['1']['test_at_fixed_0_5_diagnostic']['alert_episodes']['episode_details']
    per_episode = []
    for idx, episode in enumerate(episodes, start=1):
        route = routes[episode['route_sector']]
        first = date.fromisoformat(episode['start_hour_utc'][:10]) - timedelta(days=1)
        last = date.fromisoformat(episode['end_hour_utc'][:10]) + timedelta(days=1)
        nearby: dict[tuple, dict] = {}
        for row in events:
            report_day = date.fromisoformat(row['report_date'])
            if report_day < first or report_day > last:
                continue
            if str(row.get('status', 'UNKNOWN')).upper() not in ACTIVE_STATUSES:
                continue
            if not isinstance(row.get('latitude'), (int, float)) or not isinstance(row.get('longitude'), (int, float)):
                continue
            distance = distance_to_polyline_km(float(row['latitude']), float(row['longitude']), route['projection'])
            key = incident_key(row)
            current = nearby.get(key)
            if current is None or distance < current['distance_km']:
                nearby[key] = {
                    'incident_name': row.get('incident_name'),
                    'province': row.get('province'),
                    'reported_start_date': row.get('reported_start_date'),
                    'nearest_report_date': row.get('report_date'),
                    'reported_status': row.get('status'),
                    'distance_km': round(distance, 3),
                }
        near10 = sorted((row for row in nearby.values() if row['distance_km'] <= 10), key=lambda row: row['distance_km'])
        near20 = sorted((row for row in nearby.values() if row['distance_km'] <= 20), key=lambda row: row['distance_km'])
        per_episode.append({
            'episode_index': idx,
            'route_sector': episode['route_sector'],
            'alert_start_hour_utc': episode['start_hour_utc'],
            'alert_end_hour_utc': episode['end_hour_utc'],
            'hours': episode['hours'],
            'goes_positive_target_hours': episode['positive_goes_detection_hours'],
            'nearby_active_snmf_incidents_within_10km': near10,
            'nearby_active_snmf_incidents_within_20km': near20,
        })
    # Count unique SNMF events robustly from the output incident details.
    def unique(items_key: str) -> dict[tuple, dict]:
        unique_rows = {}
        for episode in per_episode:
            for row in episode[items_key]:
                key = (row['province'], row['reported_start_date'], row['incident_name'])
                unique_rows[key] = row
        return unique_rows

    # Keep the key names explicit for readers of the JSON.
    unique10 = unique('nearby_active_snmf_incidents_within_10km')
    unique20 = unique('nearby_active_snmf_incidents_within_20km')
    result = {
        'experiment_id': 'goes19-one-hour-alert-episode-snmf-snapshot-crosscheck',
        'status': 'descriptive_positive_event_crosscheck_precision_not_estimable',
        'selection': 'The one-hour GOES model and 0.5 diagnostic threshold were frozen before this report cross-check; the episode cohort is selected by model alerts, not a random route-time sample.',
        'matching_rule': 'For each route alert episode, match active/controlled/contained SNMF snapshots from one calendar day before through one calendar day after the alert interval, using full trail polyline distance. A match does not prove event identity or alert lead time.',
        'threshold': 0.5,
        'route_buffer_km': [10, 20],
        'model_alert_episodes': len(per_episode),
        'episodes_with_any_snmf_snapshot_within_10km': sum(bool(row['nearby_active_snmf_incidents_within_10km']) for row in per_episode),
        'episodes_with_any_snmf_snapshot_within_20km': sum(bool(row['nearby_active_snmf_incidents_within_20km']) for row in per_episode),
        'unique_matched_snmf_incidents_within_10km': len(unique10),
        'unique_matched_snmf_incidents_within_20km': len(unique20),
        'episodes_without_nearby_snmf_snapshot': [row['episode_index'] for row in per_episode if not row['nearby_active_snmf_incidents_within_20km']],
        'alert_episode_matches': per_episode,
        'sources': {
            'short_lead_model_evaluation_sha256': sha256(GOES_REPORT),
            'snmf_daily_occurrence_events_sha256': sha256(SNMF_EVENTS),
            'route_geometry_sha256': sha256(GEOMETRY),
        },
        'precision_estimable': False,
        'synthetic_observations': 0,
        'deployment_approved': False,
        'limitations': [
            'The 2026 January SNMF reports are daily administrative status snapshots, not timestamps of ignition.',
            'SNMF reporting is not an exhaustive list of every fire or every fire-free route-period.',
            'Repeated alert episodes can match the same continuing incident; these are not independent events.',
            'An episode without a nearby SNMF report is unmatched, not a confirmed false physical-fire alert.',
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        '# Cruce de alertas GOES de 1 hora con partes SNMF', '',
        f"Con el corte diagn?stico 0,5 aparecieron {result['model_alert_episodes']} episodios de alerta en enero de 2026. Al cruzar sus intervalos contra partes SNMF de fechas ?1 d?a, {result['episodes_with_any_snmf_snapshot_within_10km']} episodios encontraron incidentes reportados dentro de 10 km y {result['episodes_with_any_snmf_snapshot_within_20km']} dentro de 20 km. Esos episodios correspondieron a {result['unique_matched_snmf_incidents_within_10km']} incidentes ?nicos a 10 km y {result['unique_matched_snmf_incidents_within_20km']} a 20 km; por lo tanto, los episodios repetidos no son fuegos independientes.", '',
        f"Los episodios sin reporte cercano son {result['episodes_without_nearby_snmf_snapshot']}. Se describen como no emparejados; la falta de un parte pr?ximo no confirma ausencia f?sica de fuego. El informe diario no contiene la hora de ignici?n y no demuestra que la alerta haya precedido al inicio del incendio.", '',
        'Este cruce no estima precisi?n porque la cobertura SNMF es incompleta y la cohorte fue seleccionada por las alertas del modelo. El resultado GOES a nivel de ruta-hora tampoco equivale a detecci?n de incendio f?sico. Ver [JSON reproducible con distancias, incidentes e hashes](fire-goes19-short-lead-snmf-incident-crosscheck.json) y [evaluaci?n por horizonte](fire-goes19-short-lead-route-sector-evaluation.md).', '',
        'Reproducci?n: [`audit_goes_short_lead_snmf_incidents.py`](../../training/python/audit_goes_short_lead_snmf_incidents.py). Fuentes: [reportes diarios SNMF](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego) y geometr?as completas privadas del cat?logo local.', '',
    ]
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({key: result[key] for key in (
        'model_alert_episodes', 'episodes_with_any_snmf_snapshot_within_10km',
        'episodes_with_any_snmf_snapshot_within_20km', 'unique_matched_snmf_incidents_within_10km',
        'unique_matched_snmf_incidents_within_20km', 'episodes_without_nearby_snmf_snapshot')}, indent=2))


if __name__ == '__main__':
    main()
