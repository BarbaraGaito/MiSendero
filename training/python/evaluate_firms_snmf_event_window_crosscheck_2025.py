"""Cross-check targeted 2025 SNMF fire-report dates against VIIRS FIRMS detections.

The date cohort is selected from SNMF positives, so this is corroboration only;
it cannot estimate precision or create negative examples.
"""
from __future__ import annotations

import json
from pathlib import Path

from environmental_sources import ROOT, sha256
from audit_inpe_reference_detections_route_polylines import prepare_routes
from evaluate_jma_full_trail_polyline_transfer_2025 import build_polyline_labels

BASE = ROOT / 'docs/environmental-models-2026-10-22'
PRIVATE_FIRMS = ROOT / 'training/data/environmental/private/' / 'firms-route-detections-event-windows-2025'
FIRMS = PRIVATE_FIRMS / 'firms-viirs-route-detections-2025-01-01-2025-12-31.json'
WINDOWS = ROOT / 'training/data/environmental/private/firms-route-detections/event-windows-2025.json'
GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
REPORT = ROOT / 'docs/environmental-models-2026-10-22/snmf-2025-daily-occurrence-events.json'
MANIFEST = ROOT / 'training/data/environmental/private/snmf-daily-occurrence-2025/source-manifest.json'
OUT = BASE / 'fire-firms-snmf-event-window-crosscheck-2025.json'
OUT_MD = BASE / 'fire-firms-snmf-event-window-crosscheck-2025.md'


def main() -> None:
    firms = json.loads(FIRMS.read_text(encoding='utf-8'))
    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    routes = prepare_routes(geometry['fire_route_geometries'])
    labels = build_polyline_labels('2025', routes)[20]
    positive_days = {(row['region'], row['date']) for row in labels if row['label'] == 1}
    detections = firms['route_detections']
    detection_days = {(row['route_sector'], row['acq_date']) for row in detections}
    same_day = positive_days & detection_days
    from datetime import date, timedelta
    plus_minus_one = {
        (route, (date.fromisoformat(day) + timedelta(days=offset)).isoformat())
        for route, day in positive_days for offset in (-1, 0, 1)
    }
    confidence_overlap = {}
    for confidence in ('h', 'n', 'l'):
        days = {(row['route_sector'], row['acq_date']) for row in detections if row.get('confidence') == confidence}
        confidence_overlap[confidence] = {
            'detection_rows': sum(row.get('confidence') == confidence for row in detections),
            'route_detection_days': len(days),
            'same_day_snmf_positive_route_days': len(days & positive_days),
        }
    result = {
        'experiment_id': 'firms-viirs-snmf-positive-event-window-crosscheck-2025',
        'status': 'corroboration_only_precision_not_estimable',
        'period': ['2025-01-01', '2025-12-31'],
        'sensor': 'VIIRS_SNPP_SP',
        'buffer_km': firms['route_buffer_km'],
        'cohort_selection': 'Only route-days labeled positive by same-day SNMF report proxy at 20 km were selected; queried date windows extend one day before and after and are merged into spans no longer than five days.',
        'results': {
            'snmf_positive_route_days_in_cohort': len(positive_days),
            'targeted_api_query_blocks': len(firms['requests']),
            'firm_detection_rows': len(detections),
            'unique_route_detection_days_in_queried_windows': len(detection_days),
            'same_day_snmf_positive_route_days_with_detection': len(same_day),
            'same_day_cohort_detection_fraction_descriptive_only': len(same_day) / len(positive_days) if positive_days else None,
            'snmf_positive_route_days_with_detection_within_plus_minus_one_day': len(plus_minus_one & detection_days),
            'confidence': confidence_overlap,
            'negative_examples_created': 0,
            'precision_estimable': False,
        },
        'limitations': [
            'Query windows were selected from SNMF-positive days, so the sample is event-enriched and cannot estimate alert precision.',
            'FIRMS detects satellite-observed thermal anomalies; a missing point does not prove no fire because of overpass timing, cloud, smoke, or sensor coverage.',
            'SNMF report dates have daily rather than ignition-time precision; the plus/minus one-day figure is descriptive only.',
            'A hotspot within the same route buffer and day is not necessarily the same incident as the SNMF report.',
        ],
        'sources': {
            'firms_event_window_archive_sha256': sha256(FIRMS),
            'snmf_event_report_sha256': sha256(REPORT),
            'snmf_source_manifest_sha256': sha256(MANIFEST),
            'route_geometry_sha256': sha256(GEOMETRY),
            'event_window_plan_sha256': sha256(WINDOWS),
        },
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    r = result['results']
    lines = [
        '# Cruce FIRMS VIIRS y partes SNMF, ventanas de eventos 2025', '',
        f"Se consultaron {r['targeted_api_query_blocks']} ventanas del sensor VIIRS SNPP alrededor de {r['snmf_positive_route_days_in_cohort']} ruta-dias positivos SNMF a 20 km. La consulta dirigida produjo {r['firm_detection_rows']} filas de focos en {r['unique_route_detection_days_in_queried_windows']} ruta-dias unicos.", '',
        f"Hubo coincidencia el mismo dia en {r['same_day_snmf_positive_route_days_with_detection']}/{r['snmf_positive_route_days_in_cohort']} ruta-dias positivos SNMF ({r['same_day_cohort_detection_fraction_descriptive_only']:.1%}, descriptivo). En {r['snmf_positive_route_days_with_detection_within_plus_minus_one_day']} hubo una deteccion en la ventana de mas o menos un dia.", '',
        '| Confianza FIRMS | Filas | Ruta-dias con deteccion | Coincidencias exactas con SNMF positivo |', '|---|---:|---:|---:|',
    ]
    for confidence, item in confidence_overlap.items():
        lines.append(f"| {confidence} | {item['detection_rows']} | {item['route_detection_days']} | {item['same_day_snmf_positive_route_days']} |")
    lines += ['', 'Esta cohorte se eligio a partir de eventos SNMF, por lo que no sirve para estimar precision, falsos positivos ni rendimiento general. Un hotspot cercano el mismo dia tampoco confirma que sea el mismo incidente. No se crearon negativos: las ausencias de FIRMS siguen siendo desconocidas.', '',
        'El archivo de detecciones se conserva en el directorio privado local y no se incluye en el repositorio. Sus hashes, el plan de ventanas y las fuentes SNMF quedan registrados en el [JSON](fire-firms-snmf-event-window-crosscheck-2025.json). Reproduccion del resumen: [`evaluate_firms_snmf_event_window_crosscheck_2025.py`](../../training/python/evaluate_firms_snmf_event_window_crosscheck_2025.py).', '']
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'json': OUT.relative_to(ROOT).as_posix(), 'results': r}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
