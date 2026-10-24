#!/usr/bin/env python3
"""Audit event-selected FIRMS detections against SNMF positive route-days.

All date windows are selected from SNMF positives. Results are descriptive
corroboration only; they cannot estimate precision or create negatives.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from audit_inpe_reference_detections_route_polylines import prepare_routes
from environmental_sources import ROOT, sha256
from evaluate_jma_full_trail_polyline_transfer_2025 import build_polyline_labels

BASE = ROOT / 'docs/environmental-models-2026-10-22'
GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
PRIVATE = ROOT / 'training/data/environmental/private'
DATASETS = {
    '2023': PRIVATE / 'firms-route-detections-snmf-events-2023/firms-viirs-route-detections-2023-01-01-2023-12-31.json',
    '2024': PRIVATE / 'firms-route-detections-snmf-events-2024/firms-viirs-route-detections-2024-01-01-2024-12-31.json',
    '2025': PRIVATE / 'firms-route-detections-event-windows-2025/firms-viirs-route-detections-2025-01-01-2025-12-31.json',
}
PLANS = {
    year: PRIVATE / f'firms-route-detections/event-plan-{year}.json'
    for year in ('2023', '2024')
}
EVENTS = {
    year: BASE / f'snmf-{year}-daily-occurrence-events.json'
    for year in ('2023', '2024', '2025')
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--years', nargs='+', choices=sorted(DATASETS), default=['2023', '2024', '2025'])
    args = parser.parse_args()
    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    routes = prepare_routes(geometry['fire_route_geometries'])
    by_year = {}
    for year in args.years:
        archive_path = DATASETS[year]
        archive = json.loads(archive_path.read_text(encoding='utf-8'))
        labels = build_polyline_labels(year, routes)[20]
        positives = {(row['region'], row['date']) for row in labels if row['label'] == 1}
        detections = archive['route_detections']
        detection_days = {(row['route_sector'], row['acq_date']) for row in detections}
        exact = positives & detection_days
        adjacent = {
            (route, (date.fromisoformat(day) + timedelta(days=offset)).isoformat())
            for route, day in positives for offset in (-1, 0, 1)
        } & detection_days
        confidence = {}
        for level in ('h', 'n', 'l'):
            level_rows = [row for row in detections if str(row.get('confidence', '')).lower() == level]
            level_days = {(row['route_sector'], row['acq_date']) for row in level_rows}
            confidence[level] = {
                'detection_rows': len(level_rows),
                'unique_route_detection_days': len(level_days),
                'same_day_positive_route_days_with_detection': len(positives & level_days),
            }
        item = {
            'period': archive['period'],
            'sensor': 'VIIRS_SNPP_SP',
            'route_buffer_km': archive['route_buffer_km'],
            'snmf_positive_route_days_in_selected_cohort': len(positives),
            'snmf_positive_route_sectors': len({route for route, _ in positives}),
            'firms_query_blocks': len(archive['requests']),
            'firms_candidate_detection_rows': len(detections),
            'firms_unique_route_detection_days_in_selected_windows': len(detection_days),
            'same_day_snmf_positive_route_days_with_firms_detection': len(exact),
            'same_day_fraction_descriptive_only': len(exact) / len(positives) if positives else None,
            'positive_route_days_with_detection_within_plus_minus_one_day': len(adjacent),
            'confidence': confidence,
            'negative_examples_created': 0,
            'precision_estimable': False,
            'data_sha256': sha256(archive_path),
            'snmf_events_sha256': sha256(EVENTS[year]),
            'event_plan_sha256': sha256(PLANS[year]) if year in PLANS else None,
        }
        by_year[year] = item

    output = {
        'experiment_id': 'firms-snmf-selected-positive-route-day-corroboration-2023-2025',
        'status': 'positive_event_corroboration_only_precision_not_estimable',
        'cohort_selection': 'FIRMS query dates were selected from SNMF-positive route-sector dates; +/-1-day satellite detections are descriptive and do not prove event identity or forecast lead time.',
        'results_by_year': by_year,
        'limitations': [
            'The cohort is conditioned on SNMF-positive route-days and cannot estimate precision, false alarms, or general performance.',
            'SNMF reports have daily time precision; adjacent-day matches do not establish temporal ordering or a forecast lead.',
            'A FIRMS hotspot near a route may be a separate incident; no incident-level identity adjudication was performed.',
            'FIRMS active-fire detections do not contain complete observation coverage, so absence of a hotspot is unknown rather than a negative.',
            'SNMF extraction can omit archive dates or coordinates; see the source event files and manifests.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    out = BASE / 'fire-firms-snmf-positive-corroboration-2023-2025.json'
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        '# Corroboración de eventos SNMF con detecciones FIRMS (2023–2025)', '',
        'Se consultó VIIRS SNPP en ventanas de hasta cinco días seleccionadas alrededor de fechas positivas SNMF y se filtraron focos a 20 km de las polilíneas de los senderos. El resultado es una auditoría de coincidencias positivas; no mide precisión del modelo.', '',
        '| Año | Días-ruta SNMF seleccionados | Bloques FIRMS | Detecciones | Días-ruta con detección FIRMS | Coincidencia exacta | Coincidencia ±1 día |',
        '|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for year, item in by_year.items():
        lines.append(
            f"| {year} | {item['snmf_positive_route_days_in_selected_cohort']} | {item['firms_query_blocks']} | {item['firms_candidate_detection_rows']} | {item['firms_unique_route_detection_days_in_selected_windows']} | {item['same_day_snmf_positive_route_days_with_firms_detection']} ({item['same_day_fraction_descriptive_only']:.1%}) | {item['positive_route_days_with_detection_within_plus_minus_one_day']} |"
        )
    lines += [
        '',
        'Las coincidencias son descriptivas: la cohorte se eligió desde los positivos SNMF, la fecha diaria no ordena el hotspot respecto de la emisión del pronóstico y la proximidad no prueba que ambos registros sean el mismo incendio. La ausencia de una detección FIRMS no se convierte en negativo. Por estas razones, estos datos no estiman precisión ni permiten afirmar una predicción fiable.', '',
        'No se crearon etiquetas sintéticas ni negativas. Los CSV de respuesta y geometrías se guardan en directorios privados locales; el resumen registra sus hashes, bloques consultados y limitaciones en el [JSON](fire-firms-snmf-positive-corroboration-2023-2025.json).', '',
        'Fuentes: [informes diarios SNMF](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego), [API histórica FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/). Reproducción: [`plan_firms_snmf_event_windows.py`](../../training/python/plan_firms_snmf_event_windows.py) y [`audit_firms_snmf_positive_corroboration.py`](../../training/python/audit_firms_snmf_positive_corroboration.py).', '',
    ]
    md = BASE / 'fire-firms-snmf-positive-corroboration-2023-2025.md'
    md.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'json': out.relative_to(ROOT).as_posix(), 'markdown': md.relative_to(ROOT).as_posix(), 'results_by_year': by_year}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
