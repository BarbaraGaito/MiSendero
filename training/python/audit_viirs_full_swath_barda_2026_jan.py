#!/usr/bin/env python3
"""Screen downloaded NASA VIIRS fire detections near Barda and Bosque Tallado.

This audit uses the full-swath fire-pixel geolocation vectors in VNP14IMG,
VJ114IMG, and VJ214IMG. It counts detections only; without the companion
geolocation arrays it does not treat missing detections as clear-land labels.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
PRIVATE = ROOT / 'training/data/environmental/private/viirs-full-swath-barda-2026-jan'
MANIFEST = PRIVATE / 'download-manifest.json'
PLAN = BASE / 'fire-viirs-full-swath-coverage-barda-2026-jan.json'
GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
OUTPUT = BASE / 'fire-viirs-full-swath-barda-2026-jan-positive-screen.json'
OUTPUT_MD = OUTPUT.with_suffix('.md')
ROUTE_NAME = 'Bosque Tallado desde la plataforma del Piltriquitron'
RADIUS_KM = 10.0
DETAIL_RADIUS_KM = 20.0
EARTH_RADIUS_KM = 6371.0088
QA_INPUT_BITS = 0b1111111
QA_EXCLUSION_BITS = (1 << 18) | (1 << 19) | (1 << 22)
FIRE_CLASSES = {7, 8, 9}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def distance_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    phi1 = math.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = phi2 - phi1
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def distance_to_polyline_km(lat: np.ndarray, lon: np.ndarray,
                            coordinates: list[list[float]]) -> np.ndarray:
    """Local equirectangular point-to-segment distance for this short trail."""
    line = np.asarray(coordinates, dtype=np.float64)
    reference_lat = float(np.mean(line[:, 0]))
    scale_x = EARTH_RADIUS_KM * math.cos(math.radians(reference_lat)) * math.pi / 180
    scale_y = EARTH_RADIUS_KM * math.pi / 180
    line_x, line_y = line[:, 1] * scale_x, line[:, 0] * scale_y
    point_x, point_y = lon * scale_x, lat * scale_y
    start_x, start_y = line_x[:-1], line_y[:-1]
    delta_x, delta_y = np.diff(line_x), np.diff(line_y)
    length_sq = delta_x**2 + delta_y**2
    numerator = ((point_x[:, None] - start_x[None, :]) * delta_x[None, :]
                 + (point_y[:, None] - start_y[None, :]) * delta_y[None, :])
    fraction = np.clip(numerator / np.maximum(length_sq[None, :], 1e-18), 0.0, 1.0)
    dx = point_x[:, None] - (start_x[None, :] + fraction * delta_x[None, :])
    dy = point_y[:, None] - (start_y[None, :] + fraction * delta_y[None, :])
    return np.sqrt(np.min(dx**2 + dy**2, axis=1))


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    route = next(row for row in geometry['fire_route_geometries'] if row['name'] == ROUTE_NAME)
    point = plan['target_incident']
    target_lat = float(point['snmf_point_latitude'])
    target_lon = float(point['snmf_point_longitude'])

    granules = [row for row in manifest['granules']
                if row.get('status') in {'downloaded', 'already_downloaded'}]
    expected_ids = {
        row['producer_granule_id']
        for product in plan['granules_by_product'].values()
        for row in product['overpasses']
    }
    downloaded_ids = {row['granule_id'] for row in granules}
    if downloaded_ids != expected_ids:
        raise RuntimeError(f'Expected {len(expected_ids)} planned granules; found {len(downloaded_ids)} verified downloads.')
    if manifest.get('synthetic_observations') != 0:
        raise RuntimeError('Private download manifest has an unexpected synthetic-observation count.')

    per_granule = []
    nearby_records = []
    total_by_class: Counter[int] = Counter()
    near_route_by_class: Counter[int] = Counter()
    near_point_by_class: Counter[int] = Counter()
    quality_near_route_by_class: Counter[int] = Counter()
    quality_near_point_by_class: Counter[int] = Counter()
    nearest_route_detection: dict | None = None
    nearest_point_detection: dict | None = None

    for row in sorted(granules, key=lambda item: item['granule_id']):
        granule_id = row['granule_id']
        path = PRIVATE / f'{granule_id}.nc'
        actual_hash = sha256(path)
        if actual_hash != row['sha256'] or path.stat().st_size != row['bytes']:
            raise RuntimeError(f'Local file verification failed for {granule_id}.')
        with Dataset(path) as data:
            mask = data['fire mask']
            qa = data['algorithm QA']
            if mask.shape != qa.shape or len(mask.shape) != 2:
                raise RuntimeError(f'Unexpected mask or QA grid for {granule_id}.')
            lat = np.asarray(data['FP_latitude'][:], dtype=np.float64)
            lon = np.asarray(data['FP_longitude'][:], dtype=np.float64)
            line = np.asarray(data['FP_line'][:], dtype=np.int64)
            sample = np.asarray(data['FP_sample'][:], dtype=np.int64)
            if not (lat.shape == lon.shape == line.shape == sample.shape):
                raise RuntimeError(f'Fire-pixel coordinate vectors do not align for {granule_id}.')
            if np.any(line < 0) or np.any(line >= mask.shape[0]) or np.any(sample < 0) or np.any(sample >= mask.shape[1]):
                raise RuntimeError(f'Fire-pixel indices exceed the swath grid for {granule_id}.')

            mask_codes = np.asarray([mask[int(r), int(c)] for r, c in zip(line, sample)], dtype=np.uint8)
            qa_codes = np.asarray([qa[int(r), int(c)] for r, c in zip(line, sample)], dtype=np.uint32)
            valid_coordinates = (np.isfinite(lat) & np.isfinite(lon) & (lat >= -90) & (lat <= 90)
                                 & (lon >= -180) & (lon <= 180))
            active = valid_coordinates & np.isin(mask_codes, tuple(FIRE_CLASSES))
            lat, lon = lat[active], lon[active]
            mask_codes, qa_codes = mask_codes[active], qa_codes[active]
            route_distance = distance_to_polyline_km(lat, lon, route['route_coordinates'])
            point_distance = distance_km(target_lat, target_lon, lat, lon)
            qa_reviewed = ((qa_codes & QA_INPUT_BITS) == 0) & ((qa_codes & QA_EXCLUSION_BITS) == 0)
            within_route = route_distance <= RADIUS_KM
            within_point = point_distance <= RADIUS_KM
            acquisition_start = str(getattr(data, 'RangeBeginningDate', '')) + 'T' + str(getattr(data, 'RangeBeginningTime', ''))
            product = str(getattr(data, 'ShortName', granule_id.split('.')[0]))
            sensor = str(getattr(data, 'Satellite', ''))
            for code, count in Counter(int(value) for value in mask_codes).items():
                total_by_class[code] += count
            for code, count in Counter(int(value) for value in mask_codes[within_route]).items():
                near_route_by_class[code] += count
            for code, count in Counter(int(value) for value in mask_codes[within_point]).items():
                near_point_by_class[code] += count
            for code, count in Counter(int(value) for value in mask_codes[within_route & qa_reviewed]).items():
                quality_near_route_by_class[code] += count
            for code, count in Counter(int(value) for value in mask_codes[within_point & qa_reviewed]).items():
                quality_near_point_by_class[code] += count

            for index in np.flatnonzero(((route_distance <= DETAIL_RADIUS_KM)
                                         | (point_distance <= DETAIL_RADIUS_KM)) & qa_reviewed):
                nearby_records.append({
                    'granule_id': granule_id,
                    'product': product,
                    'sensor': sensor,
                    'acquisition_start_utc': acquisition_start,
                    'latitude': round(float(lat[index]), 6),
                    'longitude': round(float(lon[index]), 6),
                    'mask_class': int(mask_codes[index]),
                    'distance_to_route_km': round(float(route_distance[index]), 3),
                    'distance_to_snmf_point_km': round(float(point_distance[index]), 3),
                    'algorithm_qa': int(qa_codes[index]),
                })

            for distances, target_name in ((route_distance, 'route'), (point_distance, 'snmf_point')):
                eligible = np.flatnonzero(qa_reviewed)
                if not len(eligible):
                    continue
                nearest_index = int(eligible[np.argmin(distances[eligible])])
                nearest = {
                    'granule_id': granule_id,
                    'product': product,
                    'sensor': sensor,
                    'acquisition_start_utc': acquisition_start,
                    'latitude': round(float(lat[nearest_index]), 6),
                    'longitude': round(float(lon[nearest_index]), 6),
                    'mask_class': int(mask_codes[nearest_index]),
                    'distance_km': round(float(distances[nearest_index]), 3),
                    'algorithm_qa': int(qa_codes[nearest_index]),
                }
                if target_name == 'route' and (nearest_route_detection is None
                                                or nearest['distance_km'] < nearest_route_detection['distance_km']):
                    nearest_route_detection = nearest
                if target_name == 'snmf_point' and (nearest_point_detection is None
                                                    or nearest['distance_km'] < nearest_point_detection['distance_km']):
                    nearest_point_detection = nearest

            per_granule.append({
                'granule_id': granule_id,
                'product': product,
                'sensor': sensor,
                'acquisition_start_utc': acquisition_start,
                'all_fire_class_records': int(len(mask_codes)),
                'fire_class_records_within_10km_of_route': int(within_route.sum()),
                'fire_class_records_within_10km_of_snmf_point': int(within_point.sum()),
                'qa_screened_fire_records_within_10km_of_route': int((within_route & qa_reviewed).sum()),
                'qa_screened_fire_records_within_10km_of_snmf_point': int((within_point & qa_reviewed).sum()),
                'sha256': actual_hash,
            })

    result = {
        'experiment_id': 'viirs-c2-full-swath-barda-positive-detection-screen-2026-jan',
        'status': 'positive_detection_screen_complete; clear_land_negatives_not_established',
        'target': 'Pixel geolocated VIIRS active-fire detections near the SNMF Barda de La Loma point and Bosque Tallado route during 2026-01-04 through 2026-01-10.',
        'source': {
            'collection': 'NASA VIIRS Collection 2 VNP14IMG/VJ114IMG/VJ214IMG, 375 m L2 active-fire mask',
            'cmr_plan': PLAN.relative_to(ROOT).as_posix(),
            'cmr_plan_sha256': sha256(PLAN),
            'download_manifest': MANIFEST.relative_to(ROOT).as_posix(),
            'download_manifest_sha256': sha256(MANIFEST),
            'planned_sensor_overpasses': len(expected_ids),
            'downloaded_and_hash_verified_overpasses': len(granules),
            'reported_download_size_mb': round(sum(row['bytes'] for row in granules) / 1_000_000, 2),
            'geometry_file': GEOMETRY.relative_to(ROOT).as_posix(),
            'geometry_sha256': sha256(GEOMETRY),
            'mask_classes': {'7': 'low-confidence fire', '8': 'nominal-confidence fire', '9': 'high-confidence fire'},
            'qa_screen': {
                'require_bits_0_to_6_zero': True,
                'exclude_bit_18_south_atlantic_anomaly': True,
                'exclude_bit_19_fire_over_water': True,
                'exclude_bit_22_residual_bowtie': True,
                'source': 'NASA VIIRS Collection 2 Active Fire 375 m User Guide, Algorithm QA table.',
            },
        },
        'target_incident': {
            'name': point['incident_name'],
            'reported_start_date': point['reported_start_date'],
            'reported_status': point['reported_status'],
            'latitude': target_lat,
            'longitude': target_lon,
            'distance_to_route_km': point['distance_to_route_km'],
        },
        'spatial_test': {
            'radius_km': RADIUS_KM,
            'route': ROUTE_NAME,
            'route_distance_method': 'Local equirectangular point-to-segment distance on the reviewed route polyline; appropriate for this short route and 10 km neighborhood.',
            'pixel_location_source': 'Sparse FP_latitude/FP_longitude arrays aligned with FP_line/FP_sample positions in the fire mask and algorithm QA grids.',
        },
        'summary': {
            'all_fire_class_records_in_downloaded_swaths': int(sum(total_by_class.values())),
            'all_fire_class_records_by_mask_class': {str(k): int(v) for k, v in sorted(total_by_class.items())},
            'records_within_10km_of_route_by_mask_class': {str(k): int(v) for k, v in sorted(near_route_by_class.items())},
            'qa_screened_records_within_10km_of_route_by_mask_class': {str(k): int(v) for k, v in sorted(quality_near_route_by_class.items())},
            'records_within_10km_of_snmf_point_by_mask_class': {str(k): int(v) for k, v in sorted(near_point_by_class.items())},
            'qa_screened_records_within_10km_of_snmf_point_by_mask_class': {str(k): int(v) for k, v in sorted(quality_near_point_by_class.items())},
            'nearest_qa_screened_fire_detection_to_route': nearest_route_detection,
            'nearest_qa_screened_fire_detection_to_snmf_point': nearest_point_detection,
            'overpasses_with_a_qa_screened_detection_within_10km_of_route': sum(
                row['qa_screened_fire_records_within_10km_of_route'] > 0 for row in per_granule),
            'overpasses_with_a_qa_screened_detection_within_10km_of_snmf_point': sum(
                row['qa_screened_fire_records_within_10km_of_snmf_point'] > 0 for row in per_granule),
        },
        'nearby_qa_screened_detections': nearby_records,
        'per_overpass': per_granule,
        'limitations': [
            'This is a positive-detection screen. Absence of FP points does not establish that the route pixel was observed, clear, valid, or fire-free.',
            'Full per-pixel geolocation is not included in the fire product. The sparse fire-pixel coordinates are sufficient to locate detections, but not clear-land pixels.',
            'The SNMF incident has a reported start date but no exact ignition time; a same-day overpass cannot establish whether it occurred before or after the fire began.',
            'A satellite detection is an algorithmic observation, not a field-confirmed ignition label; detections across sensors/passes may repeat one regional event.',
            'This seven-day case study cannot estimate operational precision, recall, lead time, or calibration.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = [
        '# VIIRS Collection 2: detecciones alrededor de Barda de La Loma', '',
        f"Se descargaron y verificaron {len(granules)} granulas ({result['source']['reported_download_size_mb']} MB) de S-NPP, NOAA-20 y NOAA-21 para siete días alrededor del parte SNMF de Barda de La Loma. La búsqueda encontró {result['summary']['all_fire_class_records_in_downloaded_swaths']} registros de fuego en las granulas completas; son detecciones repetidas por paso, no incendios independientes.", '',
        f"Dentro de 10 km de la polilínea Bosque Tallado hubo {sum(near_route_by_class.values())} registros clase 7–9 y {sum(quality_near_route_by_class.values())} tras el filtro de QA; dentro de 10 km de la coordenada SNMF hubo {sum(near_point_by_class.values())} y {sum(quality_near_point_by_class.values())}, respectivamente. Las detecciones QA válidas más cercanas quedaron a {nearest_route_detection['distance_km'] if nearest_route_detection else 'sin coordenadas válidas'} km del sendero y {nearest_point_detection['distance_km'] if nearest_point_detection else 'sin coordenadas válidas'} km del punto SNMF. El conteo detallado y hashes están en el [JSON reproducible](fire-viirs-full-swath-barda-2026-jan-positive-screen.json).", '',
        'Este cruce permite afirmar si el producto registró un foco cercano en un paso; no permite afirmar que no hubo fuego cuando no hay un FP, porque la geolocalización completa de todos los píxeles se distribuye en otro producto. Tampoco fija el orden entre la pasada y el inicio informado por SNMF. Por eso no mide la precisión de una predicción ni transforma ausencias en negativos.', '',
        'La máscara clasifica 7/8/9 como fuego de confianza baja/nominal/alta. El filtro QA exige bits de calidad de entrada 0–6 en cero y excluye los indicadores de anomalía del Atlántico Sur, fuego sobre agua y bowtie residual, según la [guía oficial NASA VIIRS Collection 2](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf). El producto y la geolocalización completa corresponden a fuentes distintas: [VNP14IMG en LAADS](https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14IMG).', '',
        'Reproducción: [`audit_viirs_full_swath_barda_2026_jan.py`](../../training/python/audit_viirs_full_swath_barda_2026_jan.py). Los 61 NetCDF descargados y el manifiesto permanecen en `training/data/environmental/private/viirs-full-swath-barda-2026-jan/`, excluidos de Git.', '',
    ]
    OUTPUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({
        'output': OUTPUT.relative_to(ROOT).as_posix(),
        'verified_overpasses': len(granules),
        'all_fire_class_records': result['summary']['all_fire_class_records_in_downloaded_swaths'],
        'qa_screened_near_route': result['summary']['qa_screened_records_within_10km_of_route_by_mask_class'],
        'qa_screened_near_snmf_point': result['summary']['qa_screened_records_within_10km_of_snmf_point_by_mask_class'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
