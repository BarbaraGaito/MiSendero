#!/usr/bin/env python3
"""Consolidate full-geolocation NOAA E-FIRE masks for the Barda route pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
PRIVATE = ROOT / 'training/data/environmental/private/viirs-efire-barda-pilot-2026-01-05'
MANIFEST = PRIVATE / 'download-manifest.json'
ROUTE = 'Bosque Tallado desde la plataforma del Piltriquitron'
SENSORS = ('n21', 'npp')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_route(sensor: str) -> dict:
    path = BASE / f'fire-viirs-efire-route-mask-barda-2026-01-05-{sensor}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    route = next(row for row in data['per_route'] if row['route'] == ROUTE)
    return {'path': path, 'data': data, 'route': route}


def load_point(sensor: str) -> dict:
    path = BASE / f'fire-viirs-efire-barda-point-2026-01-05-{sensor}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    point = next(row for row in data['per_route'] if row['route'] == 'Barda de La Loma SNMF point')
    return {'path': path, 'data': data, 'point': point}


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8-sig'))
    manifest_by_name = {row['filename']: row for row in manifest['files']}
    for row in manifest['files']:
        path = PRIVATE / row['filename']
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            raise RuntimeError(f'Private NOAA source verification failed: {row["filename"]}')

    passes = []
    for sensor in SENSORS:
        route_result = load_route(sensor)
        point_result = load_point(sensor)
        route_source = route_result['data']['source']
        point_source = point_result['data']['source']
        if route_source['efire_sha256'] != point_source['efire_sha256']:
            raise RuntimeError(f'Route and point audits use different {sensor} E-FIRE masks.')
        if route_source['geolocation_sha256'] != point_source['geolocation_sha256']:
            raise RuntimeError(f'Route and point audits use different {sensor} geolocation files.')
        for field, file_hash in (
            ('efire_filename', route_source['efire_sha256']),
            ('geolocation_filename', route_source['geolocation_sha256']),
        ):
            manifest_row = manifest_by_name.get(route_source[field])
            if not manifest_row or manifest_row['sha256'] != file_hash:
                raise RuntimeError(f'Manifest does not verify {route_source[field]}.')

        route = route_result['route']
        point = point_result['point']
        counts = route['nearest_pixel_mask_and_dqf_counts']
        point_counts = point['nearest_pixel_mask_and_dqf_counts']
        passes.append({
            'platform': route_source['platform'],
            'acquisition_start_utc': route_source['time_coverage_start'],
            'acquisition_end_utc': route_source['time_coverage_end'],
            'efire_file': route_source['efire_filename'],
            'efire_sha256': route_source['efire_sha256'],
            'geolocation_file': route_source['geolocation_filename'],
            'geolocation_sha256': route_source['geolocation_sha256'],
            'route_observation': {
                'sampled_vertices': route['sampled_vertices'],
                'vertices_resolved_to_swath_pixels': route['vertices_resolved_to_swath_pixels'],
                'median_nearest_pixel_distance_km': route['median_nearest_pixel_distance_km'],
                'maximum_nearest_pixel_distance_km': route['maximum_nearest_pixel_distance_km'],
                'nearest_pixel_mask_and_dqf_counts': counts,
                'clear_land_dqf1_vertices': int(counts.get('5', 0)),
                'fire_class_7_to_9_vertices': sum(int(counts.get(str(code), 0)) for code in (7, 8, 9)),
                'bowtie_vertices': int(counts.get('1', 0)),
            },
            'snmf_point_observation': {
                'sampled_points': point['sampled_vertices'],
                'resolved_points': point['vertices_resolved_to_swath_pixels'],
                'nearest_pixel_distance_km': point['median_nearest_pixel_distance_km'],
                'nearest_pixel_mask_and_dqf_counts': point_counts,
                'clear_land_dqf1': int(point_counts.get('5', 0)) == 1 and int(point_counts.get('dqf_1', 0)) == 1,
                'fire_class_7_to_9': sum(int(point_counts.get(str(code), 0)) for code in (7, 8, 9)),
            },
            'route_audit_json_sha256': sha256(route_result['path']),
            'point_audit_json_sha256': sha256(point_result['path']),
        })

    result = {
        'experiment_id': 'noaa-viirs-efire-barda-route-mask-pilot-2026-01-05',
        'status': 'two_passes_have_quality_valid_clear_land_at_snmf_point; route_sample_is_mixed_clear_and_bowtie',
        'target_incident': {
            'name': 'Barda de La Loma',
            'reported_start_date': '2026-01-05',
            'reported_status': 'CONTROLADO',
            'latitude': -41.98623333333333,
            'longitude': -71.54853888888888,
            'distance_to_route_km': 5.939,
            'exact_ignition_time_available': False,
        },
        'source': {
            'dataset': 'NOAA VIIRS Enterprise Fire I-band EDR v1r3',
            'public_access': 'NOAA NODD S3; no Earthdata token required for these pilot objects.',
            'download_manifest': MANIFEST.relative_to(ROOT).as_posix(),
            'download_manifest_sha256': sha256(MANIFEST),
            'files_hash_verified': len(manifest['files']),
            'total_bytes': sum(row['bytes'] for row in manifest['files']),
            'mask_classes': {'1': 'bowtie deletion', '4': 'cloud', '5': 'clear land', '7': 'low-confidence fire', '8': 'nominal-confidence fire', '9': 'high-confidence fire'},
            'dqf_semantics': {'1': 'good-quality fire-free land', '2': 'opaque cloud', '3': 'invalid surface/glint/view/input', '4': 'bad input data', '5': 'algorithm failure'},
            'dqf_semantics_source': 'NOAA Enterprise Fire EDR v1.3 Algorithm Theoretical Basis Document, section 5.2.',
        },
        'spatial_method': {
            'route': ROUTE,
            'route_geometry_sha256': '943d5295ae26d836263ab97bc40237870f91f42b4a88f14af8b73ed6fe17b7aa',
            'route_sampling': 'About 100 reviewed polyline vertices; nearest valid geolocated pixel searched locally around the exact 64-pixel coarse geolocation sample.',
            'point_method': 'The reported SNMF coordinate was mapped to its nearest valid pixel in the same full geolocation grid.',
            'pixel_resolution': '375 m nominal at nadir; actual pixels enlarge away from nadir.',
        },
        'passes': passes,
        'interpretation': [
            'Both passes classified the nearest pixel to the reported SNMF incident coordinate as class 5 with DQF 1, meaning a quality-valid clear-land pixel without a fire detection at those exact overpass times.',
            'For the sampled trail line, NOAA-21 resolved every sampled vertex to clear land (103/103); S-NPP resolved 44/103 to clear land and 59/103 to bowtie-deleted pixels. The sampled vertices showed no class 7-9 fire detections.',
            'These are observed satellite non-detections at two overpasses, not evidence that the reported fire did not exist. The incident has no exact ignition time, and a satellite may miss small or obscured fire.',
            'This one incident and two overpasses cannot estimate forecast precision, recall, lead time, or calibration.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    out = BASE / 'fire-viirs-efire-barda-route-mask-2026-01-05.json'
    out_md = out.with_suffix('.md')
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = [
        '# NOAA VIIRS E-FIRE: píxeles observados cerca de Barda, 5/1/2026', '',
        'Se descargaron desde el bucket público NOAA NODD y se verificaron con SHA-256 dos máscaras E-FIRE I-band v1r3 y sus geolocalizaciones completas GITCO (193,5 MB en total). Los pasos ocurrieron a las 04:31:17 UTC (NOAA-21) y 05:01:10 UTC (S-NPP).', '',
        'En ambos pasos, el píxel más cercano a la coordenada del parte SNMF de Barda de La Loma quedó a menos de 200 m y fue clase 5, con DQF 1: tierra despejada procesada con calidad y sin fuego detectado en ese instante. Sobre 103 vértices muestreados de Bosque Tallado, NOAA-21 resolvió 103 como tierra despejada; S-NPP resolvió 44 como tierra despejada y 59 como bowtie eliminado. Ninguno de esos vértices muestreados tuvo clase de fuego 7–9.', '',
        'La evidencia es útil para construir etiquetas de observación: clase 5 + DQF 1 es una no-detección válida en ese píxel y momento. No demuestra que el incendio reportado no existiera; el parte da fecha y estado, pero no hora exacta de inicio, y los sensores pueden omitir focos pequeños u ocultos. Dos pasos de un evento no estiman la precisión de una predicción ni justifican avisos de seguridad.', '',
        'La semántica DQF se tomó de la [guía técnica oficial NOAA E-FIRE v1.3, sección 5.2](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EFIRE_v1.3.pdf); NOAA describe E-FIRE VIIRS como producto de 375 m por granula en su [página del producto](https://www.ospo.noaa.gov/products/land/efire.html). Resultados por vértice, geometría y hashes: [JSON reproducible](fire-viirs-efire-barda-route-mask-2026-01-05.json). Auditoría de las máscaras: [NOAA-21](fire-viirs-efire-route-mask-barda-2026-01-05-n21.json), [S-NPP](fire-viirs-efire-route-mask-barda-2026-01-05-npp.json), [punto SNMF NOAA-21](fire-viirs-efire-barda-point-2026-01-05-n21.json) y [punto SNMF S-NPP](fire-viirs-efire-barda-point-2026-01-05-npp.json).', '',
        'Reproducción: [`audit_viirs_efire_route_mask_pilot.py`](../../training/python/audit_viirs_efire_route_mask_pilot.py) seguido de [`audit_viirs_efire_barda_route_passes.py`](../../training/python/audit_viirs_efire_barda_route_passes.py). Los archivos binarios quedan privados y excluidos de Git.', '',
    ]
    out_md.write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({
        'output': out.relative_to(ROOT).as_posix(),
        'verified_source_files': len(manifest['files']),
        'total_bytes': result['source']['total_bytes'],
        'passes': [{
            'platform': row['platform'],
            'start_utc': row['acquisition_start_utc'],
            'route_clear_land': row['route_observation']['clear_land_dqf1_vertices'],
            'route_bowtie': row['route_observation']['bowtie_vertices'],
            'point_clear_land': row['snmf_point_observation']['clear_land_dqf1'],
        } for row in passes],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
