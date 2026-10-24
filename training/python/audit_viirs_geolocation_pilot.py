#!/usr/bin/env python3
"""Audit one paired VIIRS fire-mask/geolocation overpass near Barda.

The output is a single-overpass observation screen. It is not a model
performance estimate or a complete physical no-fire label.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
MASK_DIR = ROOT / 'training/data/environmental/private/viirs-full-swath-barda-2026-jan'
GEO_DIR = ROOT / 'training/data/environmental/private/viirs-geolocation-pilot-barda-2026-jan'
MASK_ID = 'VNP14IMG.A2026007.0424.002.2026013204154'
GEO_ID = 'VNP03IMG.A2026007.0424.002.2026013152419.nc'
GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
ROUTE_NAME = 'Bosque Tallado desde la plataforma del Piltriquitron'
OUTPUT = BASE / 'fire-viirs-geolocation-pilot-barda-2026-jan.json'
OUTPUT_MD = OUTPUT.with_suffix('.md')
RADIUS_KM = 10.0
DETAIL_RADIUS_KM = 20.0
EARTH_RADIUS_KM = 6371.0088
QA_INPUT_BITS = 0b1111111
QA_EXCLUSION_BITS = (1 << 18) | (1 << 19) | (1 << 22)
FIRE_CLASSES = {7, 8, 9}
LAND_CLASSES = {1, 4, 5, 6}


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
    numerator = ((point_x[:, None] - start_x[None, :]) * delta_x[None, :]
                 + (point_y[:, None] - start_y[None, :]) * delta_y[None, :])
    fraction = np.clip(numerator / np.maximum(length_sq[None, :], 1e-18), 0.0, 1.0)
    dx = point_x[:, None] - (start_x[None, :] + fraction * delta_x[None, :])
    dy = point_y[:, None] - (start_y[None, :] + fraction * delta_y[None, :])
    return np.sqrt(np.min(dx**2 + dy**2, axis=1))


def main() -> None:
    mask_path = MASK_DIR / f'{MASK_ID}.nc'
    geo_path = GEO_DIR / GEO_ID
    mask_manifest_path = MASK_DIR / 'download-manifest.json'
    geo_manifest_path = GEO_DIR / 'download-manifest.json'
    mask_manifest = json.loads(mask_manifest_path.read_text(encoding='utf-8'))
    geo_manifest = json.loads(geo_manifest_path.read_text(encoding='utf-8'))
    mask_record = next(row for row in mask_manifest['granules'] if row['granule_id'] == MASK_ID)
    geo_record = geo_manifest.get('geolocation_granule')
    if geo_record is None:
        geo_record = next(row for row in geo_manifest['granules'] if row['granule_id'] == GEO_ID)
    if sha256(mask_path) != mask_record['sha256'] or mask_path.stat().st_size != mask_record['bytes']:
        raise RuntimeError('Matching fire-mask granule failed manifest verification.')
    if sha256(geo_path) != geo_record['sha256'] or geo_path.stat().st_size != geo_record['bytes']:
        raise RuntimeError('Geolocation granule failed manifest verification.')

    geometry = json.loads(GEOMETRY.read_text(encoding='utf-8'))
    route = next(row for row in geometry['fire_route_geometries'] if row['name'] == ROUTE_NAME)
    line = np.asarray(route['route_coordinates'], dtype=np.float64)
    margin_lat = 0.20
    margin_lon = 0.25
    with Dataset(mask_path) as mask_data, Dataset(geo_path) as geo_data:
        if (str(getattr(mask_data, 'RangeBeginningDate', '')),
            str(getattr(mask_data, 'RangeBeginningTime', ''))[:8]) != ('2026-01-07', '04:24:00'):
            raise RuntimeError('Fire-mask acquisition time does not match the frozen pilot.')
        if (str(getattr(geo_data, 'RangeBeginningDate', '')),
            str(getattr(geo_data, 'RangeBeginningTime', ''))[:8]) != ('2026-01-07', '04:24:00'):
            raise RuntimeError('Geolocation acquisition time does not match the fire-mask granule.')

        fire_mask = np.asarray(mask_data['fire mask'][:], dtype=np.uint8)
        algorithm_qa = np.asarray(mask_data['algorithm QA'][:], dtype=np.uint32)
        geo = geo_data.groups['geolocation_data']
        if fire_mask.shape != algorithm_qa.shape or fire_mask.shape != geo['latitude'].shape:
            raise RuntimeError('VIIRS mask, QA, and geolocation grids do not align.')

        lat = np.asarray(geo['latitude'][:], dtype=np.float64)
        lon = np.asarray(geo['longitude'][:], dtype=np.float64)
        geo_quality = np.asarray(geo['quality_flag'][:], dtype=np.uint8)
        land_water = np.asarray(geo['land_water_mask'][:], dtype=np.uint8)

    lat_min, lat_max = float(line[:, 0].min() - margin_lat), float(line[:, 0].max() + margin_lat)
    lon_min, lon_max = float(line[:, 1].min() - margin_lon), float(line[:, 1].max() + margin_lon)
    coarse = (np.isfinite(lat) & np.isfinite(lon) & (lat >= lat_min) & (lat <= lat_max)
              & (lon >= lon_min) & (lon <= lon_max) & (lat >= -90) & (lat <= 90)
              & (lon >= -180) & (lon <= 180) & (geo_quality == 0))
    rows, cols = np.nonzero(coarse)
    candidate_lat, candidate_lon = lat[rows, cols], lon[rows, cols]
    route_distance = distance_to_polyline_km(candidate_lat, candidate_lon, route['route_coordinates'])
    in_radius = route_distance <= RADIUS_KM
    near_mask = fire_mask[rows, cols]
    near_qa = algorithm_qa[rows, cols]
    near_land = land_water[rows, cols]
    qa_ok = ((near_qa & QA_INPUT_BITS) == 0) & ((near_qa & QA_EXCLUSION_BITS) == 0)
    land_ok = np.isin(near_land, tuple(LAND_CLASSES))
    observation_valid = in_radius & qa_ok & land_ok
    clear_land = observation_valid & (near_mask == 5)
    fire = observation_valid & np.isin(near_mask, tuple(FIRE_CLASSES))

    nearby_fire = []
    for i in np.flatnonzero((route_distance <= DETAIL_RADIUS_KM) & qa_ok & land_ok
                            & np.isin(near_mask, tuple(FIRE_CLASSES))):
        nearby_fire.append({
            'latitude': round(float(candidate_lat[i]), 6),
            'longitude': round(float(candidate_lon[i]), 6),
            'mask_class': int(near_mask[i]),
            'algorithm_qa': int(near_qa[i]),
            'land_water_mask': int(near_land[i]),
            'distance_to_route_km': round(float(route_distance[i]), 3),
            'line': int(rows[i]),
            'sample': int(cols[i]),
        })

    result = {
        'experiment_id': 'viirs-geolocation-pilot-barda-2026-jan',
        'status': 'single_overpass_observation_screen_complete',
        'acquisition_utc': '2026-01-07T04:24:00Z',
        'route': ROUTE_NAME,
        'spatial_radius_km': RADIUS_KM,
        'source': {
            'fire_mask_product': 'VNP14IMG Collection 2, 375 m active-fire mask',
            'geolocation_product': 'VNP03IMG, 375 m per-pixel terrain-corrected geolocation',
            'fire_mask_granule': MASK_ID,
            'geolocation_granule': GEO_ID,
            'fire_mask_sha256': sha256(mask_path),
            'geolocation_sha256': sha256(geo_path),
            'geolocation_downloaded_bytes': int(geo_record['bytes']),
            'geolocation_downloaded_size_mb': round(int(geo_record['bytes']) / 1_000_000, 2),
            'fire_mask_manifest_sha256': sha256(mask_manifest_path),
            'geolocation_manifest_sha256': sha256(geo_manifest_path),
            'grid_shape': list(fire_mask.shape),
            'pixels_within_search_bbox_and_valid_geolocation': int(coarse.sum()),
            'geolocation_valid_rule': 'quality_flag == 0, finite geolocation within valid lat/lon bounds',
            'land_rule': 'land_water_mask in {1,4,5,6}; ocean, coastline, and fill excluded',
            'algorithm_qa_rule': 'bits 0–6 zero; exclude bits 18, 19, and 22',
        },
        'summary': {
            'geolocated_land_pixels_within_10km_of_route': int(observation_valid.sum()),
            'clear_land_class5_pixels_within_10km_of_route': int(clear_land.sum()),
            'fire_class7_8_9_pixels_within_10km_of_route': int(fire.sum()),
            'mask_class_counts_within_10km_of_route': {
                str(code): int((observation_valid & (near_mask == code)).sum())
                for code in range(10)
            },
            'qa_screened_fire_detections_within_20km_of_route': nearby_fire,
        },
        'limitations': [
            'A class-5 pixel is an observed clear-land non-detection at this satellite pass, not proof that no physical fire existed between passes or below the sensor detection threshold.',
            'One overpass around one incident cannot estimate alert precision, recall, lead time, or calibration.',
            'The route radius and mask QA filtering are descriptive evaluation rules; they do not change the trained model.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = [
        '# Piloto VIIRS con geolocalización completa: Barda de La Loma', '',
        f"Se emparejaron los productos NASA VNP14IMG y VNP03IMG de la pasada del 7 de enero de 2026 a las 04:24 UTC. Ambos gránulos tienen la misma grilla de {fire_mask.shape[0]} × {fire_mask.shape[1]} píxeles y se verificaron contra sus manifiestos SHA-256.", '',
        f"En el radio de 10 km alrededor de la polilínea Bosque Tallado se identificaron {result['summary']['geolocated_land_pixels_within_10km_of_route']} píxeles de tierra con geolocalización válida y QA aceptable, de los cuales {result['summary']['clear_land_class5_pixels_within_10km_of_route']} fueron clase 5 (tierra despejada sin fuego detectado en este paso) y {result['summary']['fire_class7_8_9_pixels_within_10km_of_route']} clase 7–9 (fuego detectado).", '',
        'Este paso demuestra que las granulas compañeras permiten distinguir una observación válida sin detección de una zona no observada. La clase 5 no prueba ausencia física de fuego entre pasadas ni sirve por sí sola para medir precisión; se necesita una cohorte de rutas, ventanas y pronósticos históricos congelados.', '',
        'Los dos NetCDF y sus manifiestos permanecen en `training/data/environmental/private/`, excluidos de Git. El [JSON reproducible](fire-viirs-geolocation-pilot-barda-2026-jan.json) contiene conteos, reglas y hashes. Reproducción: [`audit_viirs_geolocation_pilot.py`](../../training/python/audit_viirs_geolocation_pilot.py).', '',
    ]
    OUTPUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({
        'output': OUTPUT.relative_to(ROOT).as_posix(),
        'geolocated_land_pixels_within_10km': result['summary']['geolocated_land_pixels_within_10km_of_route'],
        'clear_land_class5_pixels_within_10km': result['summary']['clear_land_class5_pixels_within_10km_of_route'],
        'fire_pixels_within_10km': result['summary']['fire_class7_8_9_pixels_within_10km_of_route'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
