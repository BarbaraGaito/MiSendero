#!/usr/bin/env python3
"""Map one NOAA VIIRS E-FIRE mask granule to reviewed Argentine trail lines."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from environmental_sources import ROOT

GEOMETRY = ROOT / 'training/data/environmental/private/fire-route-geometries.json'
PILOT_DIR = ROOT / 'training/data/environmental/private/viirs-efire-pilot'
DEFAULT_EFIRE = next(PILOT_DIR.glob('EFIRE*2000405*.nc'))
DEFAULT_GEO = next(PILOT_DIR.glob('GITCO*2000405*.h5'))
OUTPUT = ROOT / 'docs/environmental-models-2026-10-22/fire-viirs-efire-route-mask-pilot-2025-01-05.json'
MASK_LABELS = {
    0: 'not_processed', 1: 'bowtie_deletion', 2: 'sun_glint', 3: 'water',
    4: 'cloud', 5: 'clear_land', 6: 'unclassified_fire', 7: 'low_confidence_fire',
    8: 'nominal_confidence_fire', 9: 'high_confidence_fire',
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    phi1 = math.radians(lat1)
    phi2 = np.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = np.radians(lon2 - lon1)
    a = np.sin(delta_phi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(delta_lon / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def route_vertices(route: dict, maximum_vertices: int = 100) -> list[tuple[float, float]]:
    coordinates = route['route_coordinates']
    step = max(1, len(coordinates) // maximum_vertices)
    points = coordinates[::step]
    if coordinates[-1] not in points:
        points.append(coordinates[-1])
    return [(float(lat), float(lon)) for lat, lon in points]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--efire', type=Path, default=DEFAULT_EFIRE)
    parser.add_argument('--geolocation', type=Path, default=DEFAULT_GEO)
    parser.add_argument('--geometry', type=Path, default=GEOMETRY)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    routes = json.loads(args.geometry.read_text(encoding='utf-8'))['fire_route_geometries']

    with Dataset(args.efire) as efire, Dataset(args.geolocation) as geolocation:
        sample_lat = np.asarray(efire['Sampled_Latitude'][:], dtype=np.float64)
        sample_lon = np.asarray(efire['Sampled_Longitude'][:], dtype=np.float64)
        sample_valid = (
            np.isfinite(sample_lat) & np.isfinite(sample_lon)
            & (sample_lat >= -90) & (sample_lat <= 90)
            & (sample_lon >= -180) & (sample_lon <= 180)
        )
        sample_lat = sample_lat[sample_valid]
        sample_lon = sample_lon[sample_valid]
        sample_indices = np.argwhere(sample_valid)
        geo_group = geolocation.groups['All_Data'].groups['VIIRS-IMG-GEO-TC_All']
        latitude = np.asarray(geo_group['Latitude'][:], dtype=np.float64)
        longitude = np.asarray(geo_group['Longitude'][:], dtype=np.float64)
        fire_mask = np.asarray(efire['fire_mask'][:], dtype=np.uint8)
        dqf = np.asarray(efire['DQF'][:], dtype=np.uint8)
        if latitude.shape != fire_mask.shape or longitude.shape != fire_mask.shape:
            raise ValueError('VIIRS geolocation arrays do not match the E-FIRE fire-mask grid')
        sampled_lat = np.asarray(efire['Sampled_Latitude'][:], dtype=np.float64)
        sampled_lon = np.asarray(efire['Sampled_Longitude'][:], dtype=np.float64)
        aligned_lat = latitude[8::64, 8::64]
        aligned_lon = longitude[8::64, 8::64]
        if aligned_lat.shape != sampled_lat.shape or aligned_lon.shape != sampled_lon.shape:
            raise ValueError('The expected 64-pixel E-FIRE geolocation decimation has a different shape')
        alignment_valid = (
            np.isfinite(sampled_lat) & np.isfinite(sampled_lon)
            & (sampled_lat >= -90) & (sampled_lat <= 90)
            & (sampled_lon >= -180) & (sampled_lon <= 180)
        )
        if alignment_valid.any():
            lat_error = np.max(np.abs(aligned_lat[alignment_valid] - sampled_lat[alignment_valid]))
            lon_error = np.max(np.abs(aligned_lon[alignment_valid] - sampled_lon[alignment_valid]))
            if max(float(lat_error), float(lon_error)) > 1e-4:
                raise ValueError('The coarse E-FIRE geolocation does not align with the assumed 64-pixel grid')

        per_route = []
        for route in routes:
            counts: Counter[str] = Counter()
            pixel_distances = []
            coarse_distances = []
            vertices = route_vertices(route)
            for lat, lon in vertices:
                coarse_distance = haversine_km(lat, lon, sample_lat, sample_lon)
                coarse_i = int(np.argmin(coarse_distance))
                coarse_row, coarse_col = sample_indices[coarse_i]
                coarse_km = float(coarse_distance[coarse_i])
                coarse_distances.append(coarse_km)
                # Sampled_Latitude/Longitude are an exact 64-pixel decimation
                # starting at row/column 8 in this NOAA E-FIRE format.
                center_row = 8 + int(coarse_row) * 64
                center_col = 8 + int(coarse_col) * 64
                if coarse_km > 50:
                    counts['outside_or_unresolved_swath'] += 1
                    continue
                row_slice = slice(max(0, center_row - 96), min(latitude.shape[0], center_row + 97))
                col_slice = slice(max(0, center_col - 96), min(latitude.shape[1], center_col + 97))
                local_lat = latitude[row_slice, col_slice]
                local_lon = longitude[row_slice, col_slice]
                valid = (
                    np.isfinite(local_lat) & np.isfinite(local_lon)
                    & (local_lat >= -90) & (local_lat <= 90)
                    & (local_lon >= -180) & (local_lon <= 180)
                )
                if not valid.any():
                    counts['outside_or_unresolved_swath'] += 1
                    continue
                local_distances = haversine_km(lat, lon, local_lat, local_lon)
                local_distances[~valid] = np.inf
                nearest = np.unravel_index(int(np.argmin(local_distances)), local_distances.shape)
                distance = float(local_distances[nearest])
                mask_code = int(fire_mask[row_slice, col_slice][nearest])
                dqf_code = int(dqf[row_slice, col_slice][nearest])
                counts[str(mask_code)] += 1
                counts[f'dqf_{dqf_code}'] += 1
                pixel_distances.append(distance)
            per_route.append({
                'route': route['name'],
                'sampled_vertices': len(vertices),
                'vertices_resolved_to_swath_pixels': len(pixel_distances),
                'nearest_pixel_mask_and_dqf_counts': dict(sorted(counts.items())),
                'median_nearest_pixel_distance_km': float(np.median(pixel_distances)) if pixel_distances else None,
                'maximum_nearest_pixel_distance_km': float(np.max(pixel_distances)) if pixel_distances else None,
                'median_nearest_coarse_sample_km': float(np.median(coarse_distances)) if coarse_distances else None,
            })

        source = {
            'dataset': 'NOAA VIIRS I-band Enterprise Fire EDR v1r3',
            'efire_filename': args.efire.name,
            'efire_sha256': sha256(args.efire),
            'geolocation_filename': args.geolocation.name,
            'geolocation_sha256': sha256(args.geolocation),
            'time_coverage_start': str(efire.time_coverage_start),
            'time_coverage_end': str(efire.time_coverage_end),
            'geospatial_bounds': str(efire.geospatial_bounds),
            'platform': str(efire.platform),
            'mask_labels': {str(key): value for key, value in MASK_LABELS.items()},
            'mask_grid_shape': list(fire_mask.shape),
        }
        result = {
            'experiment_id': (
                'noaa-viirs-efire-trail-mask-coverage-'
                f"{source['time_coverage_start'][:10]}-"
                f"{source['time_coverage_start'][11:19].replace(':', '')}utc"
            ),
            'purpose': 'Single-swath geolocation and clear-land/fire-mask feasibility check; not model evaluation.',
            'source': source,
            'geometry': {
                'path': str(args.geometry),
                'sha256': sha256(args.geometry),
                'route_count': len(routes),
                'sampling': 'About 100 trail vertices per route; nearest valid geolocated fire-mask pixel searched within 96 pixels of coarse 64-pixel geolocation sample.',
            },
            'per_route': per_route,
            'limitations': [
                'One satellite swath cannot establish seasonal opportunity or route-level prediction reliability.',
                'Clear land (mask 5) and detected-fire classes are product labels, not field-confirmed ground truth.',
                'The pilot assumes the E-FIRE 24x100 sampled geolocation is a 64-pixel decimation beginning at row/column 8; it was verified against the supplied full geolocation file for this granule.',
                'Routes not crossed by the swath are unknown, not fire-free.',
            ],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'time_coverage_start': source['time_coverage_start'],
                      'per_route': per_route}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
