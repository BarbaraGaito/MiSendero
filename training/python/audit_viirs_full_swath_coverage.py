#!/usr/bin/env python3
"""Audit NASA CMR availability of VIIRS full-swath fire-mask granules.

This metadata-only audit checks whether official full-swath products cover a
documented near-trail SNMF incident. It does not download swath data or label
fire/no-fire pixels.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
EVENT_REPORT = BASE / 'fire-goes19-short-lead-snmf-incident-crosscheck.json'
EVENT_AUDIT = BASE / 'goes19-snmf-2026-jan-event-audit.json'
OUT = BASE / 'fire-viirs-full-swath-coverage-barda-2026-jan.json'
OUT_MD = OUT.with_suffix('.md')
CMR = 'https://cmr.earthdata.nasa.gov/search/granules.json'
PRODUCTS = ('VNP14IMG', 'VJ114IMG', 'VJ214IMG')
START = '2026-01-04T00:00:00Z'
END = '2026-01-10T23:59:59Z'


def get_json(product: str, longitude: float, latitude: float) -> tuple[dict, bytes]:
    params = urllib.parse.urlencode({
        'short_name': product,
        'temporal[]': f'{START},{END}',
        'point': f'{longitude:.6f},{latitude:.6f}',
        'page_size': 2000,
    })
    request = urllib.request.Request(
        f'{CMR}?{params}',
        headers={'Accept': 'application/json', 'User-Agent': 'MiSenderoResearch/1.0'},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    data = json.loads(raw)
    if not isinstance(data.get('feed', {}).get('entry'), list):
        raise RuntimeError(f'Unexpected CMR response for {product}')
    return data, raw


def main() -> None:
    event_report = json.loads(EVENT_REPORT.read_text(encoding='utf-8'))
    event_audit = json.loads(EVENT_AUDIT.read_text(encoding='utf-8'))
    incident = next(
        item for item in event_audit['incidents_with_coverage_without_alert']
        if item['incident_name'] == 'Barda de La Loma'
    )
    matched = next(
        row
        for episode in event_report['alert_episode_matches']
        for row in episode['nearby_active_snmf_incidents_within_10km']
        if row['incident_name'] == 'Barda de La Loma'
    )
    point = (float(incident['longitude']), float(incident['latitude']))
    source_hashes = {}
    products = {}
    all_granules = []
    for product in PRODUCTS:
        data, raw = get_json(product, *point)
        source_hashes[product] = hashlib.sha256(raw).hexdigest()
        entries = data['feed']['entry']
        # CMR can list reprocessed variants for the same acquisition. Preserve
        # them all but count a pass once per sensor/acquisition time.
        by_time: dict[str, list[dict]] = defaultdict(list)
        for row in entries:
            by_time[row['time_start']].append(row)
        selected = []
        for acquisition_time, variants in sorted(by_time.items()):
            latest = max(variants, key=lambda row: row.get('updated', ''))
            download_url = next((
                link['href'] for link in latest.get('links', [])
                if link.get('rel', '').endswith('/data#')
            ), None)
            selected.append({
                'acquisition_start_utc': acquisition_time,
                'acquisition_end_utc': latest.get('time_end'),
                'producer_granule_id': latest.get('producer_granule_id'),
                'latest_metadata_update': latest.get('updated'),
                'reported_granule_size_mb': float(latest['granule_size']) if latest.get('granule_size') else None,
                'download_url': download_url,
                'granule_variants_for_this_acquisition': len(variants),
                'online_access_flag': latest.get('online_access_flag'),
                'download_link_is_protected': any(
                    'lp-prod-protected' in link.get('href', '') for link in latest.get('links', [])
                ),
            })
        by_day = Counter(row['acquisition_start_utc'][:10] for row in selected)
        products[product] = {
            'raw_cmr_entries_including_reprocessed_variants': len(entries),
            'unique_sensor_overpass_times': len(selected),
            'reprocessed_duplicate_entries': len(entries) - len(selected),
            'reported_total_size_mb': round(sum(row['reported_granule_size_mb'] or 0 for row in selected), 2),
            'overpasses_by_utc_day': dict(sorted(by_day.items())),
            'overpasses': selected,
        }
        all_granules.extend((product, row) for row in selected)

    result = {
        'experiment_id': 'viirs-full-swath-fire-mask-metadata-coverage-near-barda-2026-jan',
        'status': 'metadata_coverage_confirmed_data_not_downloaded',
        'target_incident': {
            'incident_name': incident['incident_name'],
            'province': incident['province'],
            'reported_start_date': incident['reported_start_date'],
            'reported_status': incident['reported_status'],
            'snmf_point_latitude': point[1],
            'snmf_point_longitude': point[0],
            'distance_to_route_km': matched['distance_km'],
            'goes_model_valid_pixels': incident['valid_model_pixels_within_radius'],
            'goes_model_maximum_score': incident['maximum_one_hour_score_within_radius'],
            'goes_model_alert': incident['model_alert'],
        },
        'cmr_query': {
            'endpoint': CMR,
            'spatial_query': 'point in product granule footprint at the reported SNMF incident coordinate; this is archive metadata, not pixel-level observation validity.',
            'temporal_query_utc': [START, END],
            'products': list(PRODUCTS),
            'collection': 'Collection 2 version 002 as identified by the returned granule names.',
        },
        'granules_by_product': products,
        'total_unique_sensor_overpass_times': len(all_granules),
        'reported_total_granule_size_mb': round(sum(row['reported_granule_size_mb'] or 0 for _, row in all_granules), 2),
        'unique_sensor_overpasses_by_utc_day': dict(sorted(Counter(
            row['acquisition_start_utc'][:10] for _, row in all_granules
        ).items())),
        'observation_mask_semantics': {
            'not_processed_or_poor_quality': 0,
            'sun_glint': 2,
            'water': 3,
            'cloud': 4,
            'clear_land_no_detected_fire': 5,
            'unclassified': 6,
            'fire_low_nominal_high_confidence': [7, 8, 9],
            'rule': 'Only class 5 may serve as an observed no-detection label; classes 0, 1, 2, 3, 4, and 6 are not negative samples. Apply Algorithm QA and land/route checks before use.',
        },
        'access': {
            'cmr_metadata_accessible_without_earthdata_login': True,
            'swath_files_downloaded': False,
            'local_earthdata_token_configured': False,
            'firms_map_key_is_sufficient_for_swath_download': False,
            'credential_required_for_download': 'NASA Earthdata Login / LAADS data access token.',
        },
        'source_response_sha256': source_hashes,
        'external_event_precision_estimable': False,
        'synthetic_observations': 0,
        'deployment_approved': False,
        'limitations': [
            'Granule-footprint coverage does not prove the specific route pixel was cloud-free, valid, or processed; the swath fire mask and QA layers must be downloaded and inspected.',
            'A class-5 clear-land observation without a detected fire is an observed non-detection at that overpass, not proof that no small or obscured physical fire existed between overpasses.',
            'The event report gives a day and administrative status, not an exact ignition timestamp.',
            'These few incident-day swaths are case-study coverage, not a representative precision cohort or verified negative-window panel.',
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        '# Cobertura de producto VIIRS completo para Barda de La Loma', '',
        f"La búsqueda pública de metadatos NASA CMR encontró {result['total_unique_sensor_overpass_times']} tiempos únicos de sobrepaso de tres productos VIIRS Collection 2 entre el 4 y el 10 de enero de 2026 sobre la coordenada SNMF de Barda de La Loma, a {matched['distance_km']} km del sendero: " + ', '.join(f"{name} {products[name]['unique_sensor_overpass_times']}" for name in PRODUCTS) + '. Se deduplicaron re-procesamientos del mismo sensor y hora. Esto confirma que existe archivo de granulas coincidentes con el evento; no confirma que cada píxel de ruta haya sido observado despejado.', '',
        'El producto de 375 m VNP14IMG/VJ114IMG/VJ214IMG contiene una máscara de fuego por píxel: clase 5 identifica tierra despejada sin fuego detectado; 7, 8 y 9 son fuego de confianza baja, nominal y alta. Clase 4 es nube, 0 es no procesado por mala calidad y 6 no clasificado; esas clases no son negativos. Se debe conservar además la QA algorítmica. Esto permite construir negativos observados por sobrepaso donde la calidad sea válida, con la limitación de que “sin detección durante el paso” no significa que no hubiera fuego entre pasos.', '',
        'El `.env` local tiene `NASA_FIRMS_MAP_KEY`, que permitió consultar el CSV de focos; no hay token NASA Earthdata/LAADS configurado. Las granulas completas están bajo acceso protegido y no se descargaron. Para completar la prueba de Barda y formar una cohorte representativa se necesita un token de descarga Earthdata, cobertura por píxel/QA de los tres satélites y muchas más fechas/rutas, además de pronósticos archivados antes de las observaciones.', '',
        f"Detalle de tiempos de paso, IDs, estados de acceso y hashes de las tres respuestas CMR: [JSON reproducible](fire-viirs-full-swath-coverage-barda-2026-jan.json). Reproducción de metadatos: [`audit_viirs_full_swath_coverage.py`](../../training/python/audit_viirs_full_swath_coverage.py). Especificación: [guía NASA del producto VIIRS de 375 m](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf), [campos VNP14IMG en LAADS](https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14IMG), [acceso a datos LAADS](https://ladsweb.modaps.eosdis.nasa.gov/learn/download-files-using-edl-tokens/).", '',
    ]
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({
        'output': OUT.relative_to(ROOT).as_posix(),
        'unique_sensor_overpasses_by_product': {name: products[name]['unique_sensor_overpass_times'] for name in PRODUCTS},
        'total_unique_sensor_overpass_times': result['total_unique_sensor_overpass_times'],
        'swath_files_downloaded': False,
        'earthdata_token_configured': False,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
