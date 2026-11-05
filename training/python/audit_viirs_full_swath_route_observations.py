#!/usr/bin/env python3
"""Pair all VIIRS fire masks with exact-time geolocation for a route screen."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
MASK_PLAN = BASE / 'fire-viirs-full-swath-coverage-barda-2026-jan.json'
MASK_DIR = ROOT / 'training/data/environmental/private/viirs-full-swath-barda-2026-jan'
GEO_DIR = ROOT / 'training/data/environmental/private/viirs-geolocation-pilot-barda-2026-jan'
MASK_MANIFEST = MASK_DIR / 'download-manifest.json'
GEO_MANIFEST = GEO_DIR / 'download-manifest.json'
GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
OUTPUT = BASE / 'fire-viirs-full-swath-route-observations-barda-2026-jan.json'
OUTPUT_MD = OUTPUT.with_suffix('.md')
PRODUCT_PAIRS = {'VNP14IMG': 'VNP03IMG', 'VJ114IMG': 'VJ103IMG', 'VJ214IMG': 'VJ203IMG'}
ROUTE_NAME = 'Bosque Tallado desde la plataforma del Piltriquitron'
EARTH_RADIUS_KM = 6371.0088
ROUTE_RADIUS_KM = 10.0
POINT_RADIUS_KM = 10.0
DETAIL_RADIUS_KM = 20.0
QA_INPUT_BITS = 0b1111111
QA_EXCLUSION_BITS = (1 << 18) | (1 << 19) | (1 << 22)
LAND_CLASSES = {1, 4, 5, 6}
FIRE_CLASSES = {7, 8, 9}
SEARCH_LAT_MARGIN = 0.20
SEARCH_LON_MARGIN = 0.25


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def distance_to_polyline_km(lat: np.ndarray, lon: np.ndarray,
                            coordinates: list[list[float]]) -> np.ndarray:
    line = np.asarray(coordinates, dtype=np.float64)
    reference_lat = float(np.mean(line[:, 0]))
    scale_x = EARTH_RADIUS_KM * math.cos(math.radians(reference_lat)) * math.pi / 180
    scale_y = EARTH_RADIUS_KM * math.pi / 180
    line_x, line_y = line[:, 1] * scale_x, line[:, 0] * scale_y
    point_x, point_y = lon * scale_x, lat * scale_y
    start_x, start_y = line_x[:-1], line_y[:-1]
    delta_x, delta_y = np.diff(line_x), np.diff(line_y)
    length_sq = delta_x**2 + delta_y**2
    result = np.full(len(lat), np.inf, dtype=np.float64)
    # Chunk to bound memory even if the selected corridor contains many pixels.
    for offset in range(0, len(lat), 8000):
        end = min(offset + 8000, len(lat))
        px = point_x[offset:end, None]
        py = point_y[offset:end, None]
        numerator = ((px - start_x[None, :]) * delta_x[None, :]
                     + (py - start_y[None, :]) * delta_y[None, :])
        fraction = np.clip(numerator / np.maximum(length_sq[None, :], 1e-18), 0.0, 1.0)
        dx = px - (start_x[None, :] + fraction * delta_x[None, :])
        dy = py - (start_y[None, :] + fraction * delta_y[None, :])
        result[offset:end] = np.sqrt(np.min(dx**2 + dy**2, axis=1))
    return result


def distance_to_point_km(lat: np.ndarray, lon: np.ndarray,
                         point_lat: float, point_lon: float) -> np.ndarray:
    phi1 = np.radians(point_lat)
    phi2 = np.radians(lat)
    dphi = phi2 - phi1
    dlon = np.radians(lon - point_lon)
    a = np.sin(dphi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def summarize_classes(mask: np.ndarray, eligible: np.ndarray) -> dict[str, int]:
    return {str(code): int(np.count_nonzero(eligible & (mask == code))) for code in range(10)}


def main() -> None:
    plan = json.loads(MASK_PLAN.read_text(encoding='utf-8'))
    mask_manifest = json.loads(MASK_MANIFEST.read_text(encoding='utf-8'))
    geo_manifest = json.loads(GEO_MANIFEST.read_text(encoding='utf-8'))
    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    route = next(row for row in geometry['fire_route_geometries'] if row['name'] == ROUTE_NAME)
    target = plan['target_incident']
    target_lat = float(target['snmf_point_latitude'])
    target_lon = float(target['snmf_point_longitude'])

    mask_records = {row['granule_id']: row for row in mask_manifest['granules']
                    if row.get('status') in {'downloaded', 'already_downloaded'}}
    geo_records = {row['granule_id']: row for row in geo_manifest['granules']
                   if row.get('status') in {'downloaded', 'already_downloaded'}}
    expected_count = sum(len(detail['overpasses']) for detail in plan['granules_by_product'].values())
    if len(mask_records) != expected_count or len(geo_records) != expected_count:
        raise RuntimeError(f'Expected {expected_count} hash-verified mask and geolocation files; '
                           f'found {len(mask_records)} and {len(geo_records)}.')

    geo_by_product_time = {}
    for row in geo_manifest['granules']:
        if row.get('status') in {'downloaded', 'already_downloaded'}:
            key = (row['product'], row['acquisition_start_utc'])
            if key in geo_by_product_time:
                raise RuntimeError(f'Duplicate geolocation acquisition key: {key}.')
            geo_by_product_time[key] = row

    per_overpass = []
    totals_by_product = defaultdict(Counter)
    point_totals_by_product = defaultdict(Counter)
    pass_counts_by_product = defaultdict(Counter)
    source_hashes = {}
    for product, detail in plan['granules_by_product'].items():
        geo_product = PRODUCT_PAIRS[product]
        for planned in detail['overpasses']:
            acquisition = planned['acquisition_start_utc']
            mask_id = planned['producer_granule_id']
            mask_record = mask_records.get(mask_id)
            if mask_record is None:
                raise RuntimeError(f'Missing verified mask granule: {mask_id}.')
            geo_record = geo_by_product_time.get((geo_product, acquisition))
            if geo_record is None:
                raise RuntimeError(f'Missing exact-time {geo_product} companion for {acquisition}.')

            mask_path = MASK_DIR / f'{mask_id}.nc'
            geo_path = GEO_DIR / geo_record['granule_id']
            for path, record, label in ((mask_path, mask_record, 'mask'), (geo_path, geo_record, 'geolocation')):
                if (not path.exists() or path.stat().st_size != record['bytes']
                        or sha256(path) != record['sha256']):
                    raise RuntimeError(f'Local {label} granule failed hash verification: {path.name}.')

            with Dataset(mask_path) as mask_data, Dataset(geo_path) as geo_data:
                mask_time = (str(getattr(mask_data, 'RangeBeginningDate', '')) + 'T'
                             + str(getattr(mask_data, 'RangeBeginningTime', ''))[:8] + '.000Z')
                geo_time = (str(getattr(geo_data, 'RangeBeginningDate', '')) + 'T'
                            + str(getattr(geo_data, 'RangeBeginningTime', ''))[:8] + '.000Z')
                if mask_time != acquisition or geo_time != acquisition:
                    raise RuntimeError(f'File acquisition metadata mismatch for {mask_id}.')
                fire_mask = np.asarray(mask_data['fire mask'][:], dtype=np.uint8)
                algorithm_qa = np.asarray(mask_data['algorithm QA'][:], dtype=np.uint32)
                geolocation = geo_data.groups['geolocation_data']
                if (fire_mask.shape != algorithm_qa.shape
                        or fire_mask.shape != geolocation['latitude'].shape
                        or fire_mask.shape != geolocation['longitude'].shape
                        or fire_mask.shape != geolocation['quality_flag'].shape
                        or fire_mask.shape != geolocation['land_water_mask'].shape):
                    raise RuntimeError(f'Grid mismatch between {mask_id} and {geo_record["granule_id"]}.')
                lat = np.asarray(geolocation['latitude'][:], dtype=np.float64)
                lon = np.asarray(geolocation['longitude'][:], dtype=np.float64)
                geo_quality = np.asarray(geolocation['quality_flag'][:], dtype=np.uint8)
                land_water = np.asarray(geolocation['land_water_mask'][:], dtype=np.uint8)
                satellite = str(getattr(mask_data, 'Satellite', ''))
                short_name = str(getattr(mask_data, 'ShortName', product))

            lat_min = min(float(np.min(np.asarray(route['route_coordinates'])[:, 0])), target_lat) - SEARCH_LAT_MARGIN
            lat_max = max(float(np.max(np.asarray(route['route_coordinates'])[:, 0])), target_lat) + SEARCH_LAT_MARGIN
            lon_min = min(float(np.min(np.asarray(route['route_coordinates'])[:, 1])), target_lon) - SEARCH_LON_MARGIN
            lon_max = max(float(np.max(np.asarray(route['route_coordinates'])[:, 1])), target_lon) + SEARCH_LON_MARGIN
            coarse = (np.isfinite(lat) & np.isfinite(lon) & (lat >= lat_min) & (lat <= lat_max)
                      & (lon >= lon_min) & (lon <= lon_max) & (lat >= -90) & (lat <= 90)
                      & (lon >= -180) & (lon <= 180) & (geo_quality == 0))
            rows, cols = np.nonzero(coarse)
            candidate_lat, candidate_lon = lat[rows, cols], lon[rows, cols]
            route_distance = distance_to_polyline_km(candidate_lat, candidate_lon, route['route_coordinates'])
            point_distance = distance_to_point_km(candidate_lat, candidate_lon, target_lat, target_lon)
            mask_values = fire_mask[rows, cols]
            qa_values = algorithm_qa[rows, cols]
            land_values = land_water[rows, cols]
            qa_ok = ((qa_values & QA_INPUT_BITS) == 0) & ((qa_values & QA_EXCLUSION_BITS) == 0)
            land_ok = np.isin(land_values, tuple(LAND_CLASSES))
            valid = qa_ok & land_ok
            route_10 = (route_distance <= ROUTE_RADIUS_KM) & valid
            point_10 = (point_distance <= POINT_RADIUS_KM) & valid
            route_20_fire = ((route_distance <= DETAIL_RADIUS_KM) & valid
                             & np.isin(mask_values, tuple(FIRE_CLASSES)))

            route_classes = summarize_classes(mask_values, route_10)
            point_classes = summarize_classes(mask_values, point_10)
            for code in range(10):
                totals_by_product[product][code] += route_classes[str(code)]
                point_totals_by_product[product][code] += point_classes[str(code)]
            pass_counts_by_product[product]['passes_with_class5_route'] += route_classes['5'] > 0
            pass_counts_by_product[product]['passes_with_fire_route'] += sum(route_classes[str(c)] for c in FIRE_CLASSES) > 0
            pass_counts_by_product[product]['passes_with_class5_point'] += point_classes['5'] > 0
            pass_counts_by_product[product]['passes_with_fire_point'] += sum(point_classes[str(c)] for c in FIRE_CLASSES) > 0

            route_fire_20 = []
            for index in np.flatnonzero(route_20_fire):
                route_fire_20.append({
                    'latitude': round(float(candidate_lat[index]), 6),
                    'longitude': round(float(candidate_lon[index]), 6),
                    'mask_class': int(mask_values[index]),
                    'distance_to_route_km': round(float(route_distance[index]), 3),
                    'distance_to_snmf_point_km': round(float(point_distance[index]), 3),
                    'algorithm_qa': int(qa_values[index]),
                    'land_water_mask': int(land_values[index]),
                })
            per_overpass.append({
                'acquisition_start_utc': acquisition,
                'mask_product': short_name,
                'geolocation_product': geo_product,
                'sensor': satellite,
                'mask_granule_id': mask_id,
                'geolocation_granule_id': geo_record['granule_id'],
                'grid_shape': list(fire_mask.shape),
                'qa_valid_geolocated_pixels_within_10km_of_route': int(route_10.sum()),
                'mask_classes_within_10km_of_route': route_classes,
                'qa_valid_geolocated_pixels_within_10km_of_snmf_point': int(point_10.sum()),
                'mask_classes_within_10km_of_snmf_point': point_classes,
                'quality_screened_fire_detections_within_20km_of_route': route_fire_20,
                'mask_sha256': mask_record['sha256'],
                'geolocation_sha256': geo_record['sha256'],
            })
            source_hashes[mask_id] = {'mask': mask_record['sha256'], 'geolocation': geo_record['sha256']}
            if len(per_overpass) % 5 == 0:
                print(json.dumps({'processed_overpasses': len(per_overpass),
                                  'expected_overpasses': expected_count}, ensure_ascii=False), flush=True)

    all_route = Counter()
    all_point = Counter()
    by_utc_day: dict[str, Counter] = defaultdict(Counter)
    for row in per_overpass:
        day = row['acquisition_start_utc'][:10]
        counts = row['mask_classes_within_10km_of_route']
        by_utc_day[day]['passes'] += 1
        by_utc_day[day]['quality_valid_pixels'] += row['qa_valid_geolocated_pixels_within_10km_of_route']
        by_utc_day[day]['class5_clear_land_pixels'] += int(counts['5'])
        by_utc_day[day]['class4_cloud_pixels'] += int(counts['4'])
        by_utc_day[day]['class3_water_pixels'] += int(counts['3'])
        by_utc_day[day]['class7_9_fire_pixels'] += sum(int(counts[str(code)]) for code in FIRE_CLASSES)
        by_utc_day[day]['passes_with_class5'] += int(int(counts['5']) > 0)
        by_utc_day[day]['passes_with_valid_pixels'] += int(row['qa_valid_geolocated_pixels_within_10km_of_route'] > 0)
    for counter in totals_by_product.values():
        all_route.update(counter)
    for counter in point_totals_by_product.values():
        all_point.update(counter)
    result = {
        'experiment_id': 'viirs-full-swath-route-observations-barda-2026-jan',
        'status': '61_exact_time_pairs_verified; per_overpass_observation_screen_complete',
        'target_incident': target,
        'route': ROUTE_NAME,
        'period_utc': [min(row['acquisition_start_utc'] for row in per_overpass),
                       max(row['acquisition_start_utc'] for row in per_overpass)],
        'source': {
            'fire_mask_collection': 'NASA VIIRS Collection 2 375 m L2 active-fire mask',
            'paired_geolocation': 'VNP03IMG/VJ103IMG/VJ203IMG full per-pixel 375 m geolocation',
            'expected_exact_time_pairs': expected_count,
            'verified_exact_time_pairs': len(per_overpass),
            'verified_mask_granules': len(mask_records),
            'verified_geolocation_granules': len(geo_records),
            'geolocation_downloaded_bytes': sum(row['bytes'] for row in geo_records.values()),
            'geolocation_downloaded_size_gb_decimal': round(
                sum(row['bytes'] for row in geo_records.values()) / 1_000_000_000, 3),
            'mask_manifest_sha256': sha256(MASK_MANIFEST),
            'geolocation_manifest_sha256': sha256(GEO_MANIFEST),
            'route_geometry_sha256': sha256(GEOMETRY),
            'qa_rules': {
                'geolocation_quality_flag_must_equal_zero': True,
                'land_water_mask_land_codes': sorted(LAND_CLASSES),
                'fire_mask_class_5': 'clear land; observed non-detection for this overpass',
                'fire_mask_classes_7_8_9': 'low/nominal/high confidence active-fire detections',
                'algorithm_QA_bits_0_to_6_must_be_zero': True,
                'algorithm_QA_exclusion_bits': [18, 19, 22],
            'label_interpretation': 'Class 5 is an observed clear-land non-detection; classes 7–9 are fire detections; all other classes remain unlabeled/unknown.',
            },
        },
        'spatial_rule': {
            'route_buffer_radius_km': ROUTE_RADIUS_KM,
            'incident_point_radius_km': POINT_RADIUS_KM,
            'distance_method': 'Local equirectangular point-to-polyline distance, consistent with the seven-day detection screen; incident point uses haversine distance.',
            'qa_valid_geolocated_pixel': 'valid geolocation + land-water class in {1,4,5,6} + algorithm QA screen; mask classes still determine whether the pixel is clear, fire, cloud, water, or unknown',
        },
        'summary': {
            'route_mask_class_counts_across_passes': {str(k): int(all_route[k]) for k in range(10)},
            'point_mask_class_counts_across_passes': {str(k): int(all_point[k]) for k in range(10)},
            'by_mask_product': {
                product: {
                    'passes': len([row for row in per_overpass if row['mask_product'] == product]),
                    'route_mask_class_counts': {str(k): int(totals_by_product[product][k]) for k in range(10)},
                    'point_mask_class_counts': {str(k): int(point_totals_by_product[product][k]) for k in range(10)},
                    **{key: int(value) for key, value in pass_counts_by_product[product].items()},
                }
                for product in PRODUCT_PAIRS
            },
            'route_passes_with_at_least_one_clear_land_pixel': sum(
                row['mask_classes_within_10km_of_route']['5'] > 0 for row in per_overpass),
            'route_passes_with_at_least_one_fire_detection': sum(
                sum(row['mask_classes_within_10km_of_route'][str(c)] for c in FIRE_CLASSES) > 0 for row in per_overpass),
            'point_passes_with_at_least_one_clear_land_pixel': sum(
                row['mask_classes_within_10km_of_snmf_point']['5'] > 0 for row in per_overpass),
            'point_passes_with_at_least_one_fire_detection': sum(
                sum(row['mask_classes_within_10km_of_snmf_point'][str(c)] for c in FIRE_CLASSES) > 0 for row in per_overpass),
            'unique_overpass_times_utc': len({row['acquisition_start_utc'] for row in per_overpass}),
            'by_utc_day': {
                day: {key: int(value) for key, value in counts.items()}
                for day, counts in sorted(by_utc_day.items())
            },
        },
        'per_overpass': per_overpass,
        'limitations': [
            'Class 5 is an observed clear-land non-detection at one satellite pass, not proof that no fire existed between passes or below the sensor detection threshold.',
            'Repeated passes over one short period and one route are not independent incidents and cannot estimate precision or recall.',
            'The SNMF report provides a date, not an exact ignition time; pass order relative to ignition is unknown.',
            'This screen evaluates satellite observations against a fixed route buffer; it does not establish a forecast lead-time outcome.',
            'Cloud, unclassified, unprocessed, invalid-QA, and missing passes remain unknown, not negative.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        '# VIIRS: observaciones por pasada junto a Bosque Tallado', '',
        f"Se emparejaron y verificaron {len(per_overpass)} máscaras VIIRS con sus granulas de geolocalización completa para {result['summary']['unique_overpass_times_utc']} tiempos de sobrepaso entre el 4 y el 10 de enero de 2026.", '',
        f"En el buffer de 10 km del sendero hubo {all_route[5]} píxeles clase 5 (tierra despejada sin detección en esa pasada) y {sum(all_route[c] for c in FIRE_CLASSES)} detecciones clase 7–9 tras el filtro de QA. {result['summary']['route_passes_with_at_least_one_clear_land_pixel']} de {len(per_overpass)} pasadas tuvieron al menos un píxel clase 5; {result['summary']['route_passes_with_at_least_one_fire_detection']} tuvieron una detección clase 7–9.", '',
        'Estos son conteos de observación por pasada, no incendios ni episodios de alerta independientes. Una clase 5 solo respalda una no-detección durante esa observación; las nubes, clases no clasificadas, píxeles inválidos y ventanas sin cobertura permanecen desconocidos. No se estima precisión del modelo.', '',
        'El [JSON reproducible con resultados por pasada, reglas y hashes](fire-viirs-full-swath-route-observations-barda-2026-jan.json) se generó con [`audit_viirs_full_swath_route_observations.py`](../../training/python/audit_viirs_full_swath_route_observations.py). Los archivos VIIRS permanecen en un directorio privado ignorado por Git.', '',
    ]
    OUTPUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({
        'output': OUTPUT.relative_to(ROOT).as_posix(),
        'verified_exact_time_pairs': len(per_overpass),
        'unique_overpass_times': result['summary']['unique_overpass_times_utc'],
        'route_class5_pixels': all_route[5],
        'route_fire_pixels': sum(all_route[c] for c in FIRE_CLASSES),
        'route_passes_with_class5': result['summary']['route_passes_with_at_least_one_clear_land_pixel'],
        'route_passes_with_fire': result['summary']['route_passes_with_at_least_one_fire_detection'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
