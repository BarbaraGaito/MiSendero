#!/usr/bin/env python3
"""Cross-check frozen January GOES alert episodes against NASA FIRMS VIIRS.

The cohort is selected from model alerts and FIRMS is a positive-only hotspot
source. This audit measures descriptive sensor coincidence, never fire
precision or fire-free periods.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from environmental_sources import ROOT, sha256


BASE = ROOT / 'docs/environmental-models-2026-10-22'
GOES_REPORT = BASE / 'fire-goes19-short-lead-route-sector-evaluation.json'
FIRMS_DATA_FILES = (
    ROOT / 'training/data/environmental/private/firms-goes19-alert-crosscheck-2026-jan/firms-viirs-route-detections-2026-01-04-2026-01-15.json',
    ROOT / 'training/data/environmental/private/firms-goes19-alert-crosscheck-noaa20-21-2026-jan/firms-viirs-route-detections-2026-01-04-2026-01-15.json',
)
SNMF_EVENTS = ROOT / 'docs/environmental-models-2026-10-22/snmf-2026-jan-daily-occurrence-events.json'
SNMF_MATCHES = ROOT / 'docs/environmental-models-2026-10-22/fire-goes19-short-lead-snmf-incident-crosscheck.json'
OUT = BASE / 'fire-goes19-alert-firms-crosscheck-2026-jan.json'
OUT_MD = OUT.with_suffix('.md')
ROUTE_RADII_KM = (10.0, 20.0)
CONFIDENCE_LABELS = {'h': 'high', 'n': 'nominal', 'l': 'low'}


def observation_time(row: dict) -> datetime:
    value = f"{row['acq_date']}{str(row['acq_time']).zfill(4)}"
    return datetime.strptime(value, '%Y-%m-%d%H%M').replace(tzinfo=timezone.utc)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    earth_radius_km = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def main() -> None:
    evaluation = json.loads(GOES_REPORT.read_text(encoding='utf-8'))
    firms_datasets = [json.loads(path.read_text(encoding='utf-8')) for path in FIRMS_DATA_FILES]
    firms = firms_datasets[0]
    if any(row['period'] != firms['period'] for row in firms_datasets):
        raise ValueError('FIRMS acquisition periods differ; cannot combine.')
    route_rows = [row for dataset in firms_datasets for row in dataset['route_detections']]
    request_rows = [row for dataset in firms_datasets for row in dataset['requests']]
    sensor_breakdown = {}
    for sensor in sorted({row['sensor_source'] for row in route_rows}):
        sensor_rows = [row for row in route_rows if row['sensor_source'] == sensor]
        sensor_breakdown[sensor] = {
            'detection_rows': len(sensor_rows),
            'confidence_counts': {
                label: sum(row.get('confidence') == code for row in sensor_rows)
                for code, label in CONFIDENCE_LABELS.items()
            },
            'distinct_route_dates': len({(row['route_sector'], row['acq_date']) for row in sensor_rows}),
            'nearest_to_trail_km': round(min(float(row['distance_to_route_km']) for row in sensor_rows), 3),
        }
    snmf_events = json.loads(SNMF_EVENTS.read_text(encoding='utf-8'))['snapshots']
    snmf_matches = json.loads(SNMF_MATCHES.read_text(encoding='utf-8'))['alert_episode_matches']
    episodes = evaluation['results_by_horizon']['1']['test_at_fixed_0_5_diagnostic'][
        'alert_episodes']['episode_details'
    ]
    detections_by_route: dict[str, list[tuple[datetime, dict]]] = {}
    for row in route_rows:
        detections_by_route.setdefault(row['route_sector'], []).append((observation_time(row), row))

    # Locate the official incident points that the preceding SNMF cross-check
    # already matched to these route alert episodes; compare FIRMS independently.
    matched_event_keys = {
        (incident['province'], incident['reported_start_date'], incident['incident_name'])
        for episode in snmf_matches
        if episode['route_sector'] == 'Bosque Tallado desde la plataforma del Piltriquitron'
        for incident in episode['nearby_active_snmf_incidents_within_20km']
    }
    official_incidents = []
    for key in sorted(matched_event_keys):
        snapshots = [
            row for row in snmf_events
            if (row.get('province'), row.get('reported_start_date'), row.get('incident_name')) == key
            and isinstance(row.get('latitude'), (int, float))
            and isinstance(row.get('longitude'), (int, float))
        ]
        if not snapshots:
            continue
        first_day = min(datetime.fromisoformat(row['report_date']).date() for row in snapshots)
        last_day = max(datetime.fromisoformat(row['report_date']).date() for row in snapshots)
        query_first = datetime.fromisoformat(firms['period'][0]).date()
        query_last = datetime.fromisoformat(firms['period'][1]).date()
        comparison_first = max(first_day - timedelta(days=1), query_first)
        comparison_last = min(last_day + timedelta(days=1), query_last)
        lat = float(snapshots[0]['latitude'])
        lon = float(snapshots[0]['longitude'])
        nearby = []
        for row in route_rows:
            day = datetime.fromisoformat(row['acq_date']).date()
            if comparison_first <= day <= comparison_last:
                distance = distance_km(lat, lon, float(row['latitude']), float(row['longitude']))
                nearby.append((distance, row))
        official_incidents.append({
            'incident_name': key[2],
            'province': key[0],
            'reported_start_date': key[1],
            'snmf_snapshot_period': [first_day.isoformat(), last_day.isoformat()],
            'firms_query_overlap_period': [comparison_first.isoformat(), comparison_last.isoformat()],
            'firms_detections_in_snmf_window': len(nearby),
            'nearest_firms_distance_to_reported_incident_km': round(min(
                (distance for distance, _ in nearby), default=float('inf')
            ), 3) if nearby else None,
            'firms_rows_within_10km_of_reported_incident': sum(distance <= 10 for distance, _ in nearby),
            'high_confidence_rows_within_10km_of_reported_incident': sum(
                distance <= 10 and row.get('confidence') == 'h' for distance, row in nearby
            ),
        })

    episode_matches = []
    for index, episode in enumerate(episodes, start=1):
        start = datetime.fromisoformat(episode['start_hour_utc'] + ':00+00:00')
        end = datetime.fromisoformat(episode['end_hour_utc'] + ':59:59+00:00')
        candidates = [
            (when, row) for when, row in detections_by_route.get(episode['route_sector'], [])
            if start - timedelta(hours=24) <= when <= end + timedelta(hours=24)
        ]
        within = {}
        for radius in ROUTE_RADII_KM:
            selected = [
                (when, row) for when, row in candidates
                if float(row['distance_to_route_km']) <= radius
            ]
            distances = [float(row['distance_to_route_km']) for _, row in selected]
            high = [row for _, row in selected if row.get('confidence') == 'h']
            exact_day = [
                row for when, row in selected
                if start.date() <= when.date() <= end.date()
            ]
            within[str(int(radius))] = {
                'detection_rows_within_24h': len(selected),
                'high_confidence_rows_within_24h': len(high),
                'same_alert_calendar_day_rows': len(exact_day),
                'nearest_detection_km': round(min(distances), 3) if distances else None,
                'nearest_high_confidence_km': round(min(
                    (float(row['distance_to_route_km']) for row in high), default=float('inf')
                ), 3) if high else None,
            }
        episode_matches.append({
            'episode_index': index,
            'route_sector': episode['route_sector'],
            'alert_start_hour_utc': episode['start_hour_utc'],
            'alert_end_hour_utc': episode['end_hour_utc'],
            'goes_positive_target_hours': episode['positive_goes_detection_hours'],
            'firms_match_by_route_radius_km': within,
        })

    radius_stats = {}
    for radius in ROUTE_RADII_KM:
        selected = [row for row in route_rows if float(row['distance_to_route_km']) <= radius]
        matched_eps = sum(
            row['firms_match_by_route_radius_km'][str(int(radius))]['detection_rows_within_24h'] > 0
            for row in episode_matches
        )
        radius_stats[str(int(radius))] = {
            'detection_rows_in_acquired_route_buffer': len(selected),
            'episodes_with_at_least_one_detection_within_24h': matched_eps,
        }

    result = {
        'experiment_id': 'goes19-january-2026-alert-episodes-firms-viirs-crosscheck',
        'status': 'descriptive_independent_sensor_crosscheck_precision_not_estimable',
        'cohort': 'All one-hour GOES test alert episodes at diagnostic threshold 0.5; selected by frozen model outputs before FIRMS query.',
        'firms_product': 'NASA FIRMS VIIRS S-NPP, NOAA-20, and NOAA-21 Standard Processing.',
        'firms_sensors': sorted({row['sensor'] for row in request_rows}),
        'firms_acquisition_period': firms['period'],
        'firms_by_sensor': sensor_breakdown,
        'matching_rule': 'Same route sector and FIRMS acquisition time within 24 hours before/after each GOES alert episode; route distance measured to full trail polyline in the acquisition script. Radii 10 km and 20 km are both reported; 10 km is the prespecified SNMF event protocol radius.',
        'model_alert_episodes': len(episode_matches),
        'raw_firms_route_detection_rows': len(route_rows),
        'raw_firms_confidence_counts': {
            label: sum(row.get('confidence') == code for row in route_rows)
            for code, label in CONFIDENCE_LABELS.items()
        },
        'raw_firms_distinct_route_dates': len({(row['route_sector'], row['acq_date']) for row in route_rows}),
        'raw_firms_nearest_route_distance_km': round(min(
            float(row['distance_to_route_km']) for row in route_rows
        ), 3) if route_rows else None,
        'route_radius_summary': radius_stats,
        'snmf_incident_point_crosscheck': official_incidents,
        'alert_episode_matches': episode_matches,
        'sources': {
            'goes_evaluation_sha256': sha256(GOES_REPORT),
            'firms_acquisition_sha256': {path.relative_to(ROOT).as_posix(): sha256(path) for path in FIRMS_DATA_FILES},
            'snmf_daily_events_sha256': sha256(SNMF_EVENTS),
            'goes_episode_snmf_crosscheck_sha256': sha256(SNMF_MATCHES),
            'firms_response_hashes': sorted({row['response_sha256'] for row in request_rows}),
            'route_geometry_sha256': firms['geometry_sha256'],
        },
        'precision_estimable': False,
        'forecast_lead_verifiable': False,
        'synthetic_observations': 0,
        'deployment_approved': False,
        'limitations': [
            'The alert cohort was selected from GOES model output and is not a representative sample of all route-time periods.',
            'FIRMS hotspot rows are not unique fire incidents; repeated pixels and adjacent detections can belong to one continuing fire.',
            'No FIRMS detection is not a verified no-fire label because overpass, cloud, smoke, canopy, and sensor quality limit coverage.',
            'The 24-hour matching window is descriptive and cannot establish that an alert preceded ignition.',
            'The 10 km route rule finds no acquired detections; the broader 20 km matches are regional coincidences, not evidence of fire on a trail.',
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

    within10 = radius_stats['10']['episodes_with_at_least_one_detection_within_24h']
    within20 = radius_stats['20']['episodes_with_at_least_one_detection_within_24h']
    counts = result['raw_firms_confidence_counts']
    sensor_notes = '; '.join(
        f"{sensor}: {row['detection_rows']} filas ({row['confidence_counts']['high']} alta, {row['confidence_counts']['nominal']} nominal, {row['confidence_counts']['low']} baja)"
        for sensor, row in sensor_breakdown.items()
    )
    incident_notes = []
    for incident in official_incidents:
        dist = incident['nearest_firms_distance_to_reported_incident_km']
        incident_notes.append(
            f"{incident['incident_name']} ({incident['firms_query_overlap_period'][0]} a {incident['firms_query_overlap_period'][1]}): {incident['firms_rows_within_10km_of_reported_incident']} filas a ≤10 km del punto SNMF; foco FIRMS más cercano a {dist} km"
        )
    lines = [
        '# Cruce independiente de alertas GOES con focos FIRMS VIIRS (enero de 2026)', '',
        f"Se consultó VIIRS S-NPP, NOAA-20 y NOAA-21 Standard Processing solo para las rutas y fechas de los {len(episodes)} episodios de alerta GOES de 1 h, con ventanas de ±24 h. La descarga obtuvo {len(route_rows)} filas de focos en {result['raw_firms_distinct_route_dates']} días-ruta; son detecciones repetidas, no incendios independientes. Hubo {counts['high']} focos de confianza alta, {counts['nominal']} nominales y {counts['low']} de confianza baja.", '',
        f"Desglose por sensor: {sensor_notes}.", '',
        f"Con la regla espacial de 10 km fijada en el protocolo de eventos, {within10}/{len(episodes)} episodios tuvieron una detección FIRMS dentro de ±24 h. A 20 km, el cruce fue {within20}/{len(episodes)}. La detección más cercana quedó a {result['raw_firms_nearest_route_distance_km']} km de una polilínea. Las coincidencias a 20 km son evidencia regional; no muestran fuego sobre el sendero.", '',
        'Al cotejar los focos con los dos incidentes SNMF ya asociados a los episodios de Bosque Tallado: ' + '; '.join(incident_notes) + '. Esto indica que la señal FIRMS se concentra junto a Primera Cantera Puerto Patriada, reportado a 18,2 km del recorrido, y no corrobora un foco FIRMS cercano al sendero en el radio de 10 km.', '',
        'El corte GOES fue diagnóstico y no superó el criterio de validación; FIRMS tampoco cubre todos los momentos y lugares. Por ello, las coincidencias no miden precisión y la ausencia de un foco FIRMS no cuenta como negativo. La ventana ±24 h tampoco demuestra adelanto respecto de la ignición. Esta prueba aporta corroboración satelital parcial, no valida el modelo para recomendaciones de seguridad.', '',
        f"Detalle por episodio, radios, sensores, hashes y límites: [JSON reproducible]({OUT.name}). Datos privados originales y plan de consulta: `training/data/environmental/private/firms-goes19-alert-crosscheck-2026-jan/` y `training/data/environmental/private/firms-goes19-alert-crosscheck-noaa20-21-2026-jan/`. Reproducción: [`audit_goes19_alert_firms_crosscheck.py`](../../training/python/audit_goes19_alert_firms_crosscheck.py). Fuentes: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/), [evaluación GOES congelada](fire-goes19-short-lead-route-sector-evaluation.md).", '',
    ]
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({
        'model_alert_episodes': len(episode_matches),
        'raw_firms_route_detection_rows': len(route_rows),
        'raw_firms_confidence_counts': result['raw_firms_confidence_counts'],
        'raw_firms_nearest_route_distance_km': result['raw_firms_nearest_route_distance_km'],
        'route_radius_summary': radius_stats,
        'snmf_incident_point_crosscheck': official_incidents,
        'precision_estimable': False,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
