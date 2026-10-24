#!/usr/bin/env python3
"""Check VIIRS E-FIRE pixels at SNMF event coordinates for one granule."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[2]
EVENTS = ROOT / 'docs/environmental-models-2026-10-22/snmf-2025-daily-occurrence-events.json'
ROUTE_EVENTS = ROOT / 'docs/environmental-models-2026-10-22/fire-snmf-polyline-event-coverage-2025.json'
OUT = ROOT / 'docs/environmental-models-2026-10-22/fire-viirs-snmf-event-point-pilot.json'
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


def distance_km(lat: float, lon: float, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
    phi1 = math.radians(lat)
    phi2 = np.radians(lat_grid)
    dphi = phi2 - phi1
    dlon = np.radians(lon_grid - lon)
    a = np.sin(dphi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--efire', type=Path, required=True)
    parser.add_argument('--geolocation', type=Path, required=True)
    parser.add_argument('--events', type=Path, default=EVENTS)
    parser.add_argument('--route-events', type=Path, default=ROUTE_EVENTS)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()

    with Dataset(args.efire) as efire, Dataset(args.geolocation) as geolocation:
        scan_start = str(efire.time_coverage_start)
        scan_date = scan_start[:10]
        sample_lat = np.asarray(efire['Sampled_Latitude'][:], dtype=np.float64)
        sample_lon = np.asarray(efire['Sampled_Longitude'][:], dtype=np.float64)
        valid_coarse = (np.isfinite(sample_lat) & np.isfinite(sample_lon)
                        & (sample_lat >= -90) & (sample_lat <= 90)
                        & (sample_lon >= -180) & (sample_lon <= 180))
        coarse_indices = np.argwhere(valid_coarse)
        flat_lat, flat_lon = sample_lat[valid_coarse], sample_lon[valid_coarse]
        geo = geolocation.groups['All_Data'].groups['VIIRS-IMG-GEO-TC_All']
        latitude = np.asarray(geo['Latitude'][:], dtype=np.float64)
        longitude = np.asarray(geo['Longitude'][:], dtype=np.float64)
        fire_mask = np.asarray(efire['fire_mask'][:], dtype=np.uint8)
        dqf = np.asarray(efire['DQF'][:], dtype=np.uint8)
        if latitude.shape != fire_mask.shape or longitude.shape != fire_mask.shape:
            raise ValueError('VIIRS geolocation and fire-mask grids do not match')

        route_events = json.loads(args.route_events.read_text(encoding='utf-8'))
        route_rows = [row for row in route_events['events_within_50km']
                      if row['reported_start_date'] == scan_date and row['line_distance_km'] <= 20]
        source_events = json.loads(args.events.read_text(encoding='utf-8'))['deduplicated_events']
        by_key = {(row['incident_name'], row['reported_start_date']): row for row in source_events}
        observations = []
        for route_row in route_rows:
            event = by_key.get((route_row['incident_name'], scan_date))
            if not event or event.get('latitude') is None or event.get('longitude') is None:
                observations.append({**route_row, 'mask_status': 'event_coordinate_missing'})
                continue
            lat, lon = float(event['latitude']), float(event['longitude'])
            coarse_distances = distance_km(lat, lon, flat_lat, flat_lon)
            coarse_idx = int(np.argmin(coarse_distances))
            coarse_km = float(coarse_distances[coarse_idx])
            coarse_row, coarse_col = coarse_indices[coarse_idx]
            if coarse_km > 50:
                observations.append({
                    **route_row, 'event_latitude': lat, 'event_longitude': lon,
                    'nearest_coarse_swath_sample_km': coarse_km,
                    'mask_status': 'outside_or_unresolved_swath',
                })
                continue
            center_row, center_col = 8 + int(coarse_row) * 64, 8 + int(coarse_col) * 64
            rows = slice(max(0, center_row - 96), min(latitude.shape[0], center_row + 97))
            cols = slice(max(0, center_col - 96), min(latitude.shape[1], center_col + 97))
            local_lat, local_lon = latitude[rows, cols], longitude[rows, cols]
            valid = (np.isfinite(local_lat) & np.isfinite(local_lon)
                     & (local_lat >= -90) & (local_lat <= 90)
                     & (local_lon >= -180) & (local_lon <= 180))
            if not valid.any():
                observations.append({
                    **route_row, 'event_latitude': lat, 'event_longitude': lon,
                    'nearest_coarse_swath_sample_km': coarse_km,
                    'mask_status': 'outside_or_unresolved_swath',
                })
                continue
            distances = distance_km(lat, lon, local_lat, local_lon)
            distances[~valid] = np.inf
            nearest = np.unravel_index(int(np.argmin(distances)), distances.shape)
            mask_code = int(fire_mask[rows, cols][nearest])
            dqf_code = int(dqf[rows, cols][nearest])
            observations.append({
                **route_row, 'event_latitude': lat, 'event_longitude': lon,
                'nearest_coarse_swath_sample_km': coarse_km,
                'nearest_pixel_distance_km': float(distances[nearest]),
                'mask_code': mask_code, 'mask_label': MASK_LABELS.get(mask_code, 'unknown'),
                'dqf_code': dqf_code,
                'mask_status': 'observed_fire_class' if mask_code in {7, 8, 9}
                else 'observed_clear_land' if mask_code == 5 and dqf_code == 1
                else 'unknown_quality_or_nonland',
            })

        source = {
            'dataset': 'NOAA VIIRS I-band Enterprise Fire EDR v1r3',
            'efire_filename': args.efire.name, 'efire_sha256': sha256(args.efire),
            'geolocation_filename': args.geolocation.name, 'geolocation_sha256': sha256(args.geolocation),
            'time_coverage_start_utc': scan_start,
            'time_coverage_end_utc': str(efire.time_coverage_end),
            'platform': str(efire.platform),
        }
    result = {
        'experiment_id': 'noaa-viirs-efire-snmf-event-coordinate-pass-audit',
        'purpose': 'Same-date sensor cross-check at SNMF incident coordinates; not an hourly event verification or prediction evaluation.',
        'source': source,
        'snmf_route_event_source_sha256': sha256(args.route_events),
        'snmf_event_coordinate_source_sha256': sha256(args.events),
        'observations': observations,
        'limitations': [
            'The SNMF reported start date does not establish exact ignition time; a satellite pass on that date may be before or after the event.',
            'A single nearest VIIRS pixel is not a complete fire perimeter or field-confirmed reference.',
            'Cloud, bowtie, water, invalid, and unresolved pixels remain unknown, not negative.',
            'Clear land means the sensor processed that pixel without detecting fire at the pass time; it does not prove no fire occurred.',
            'This cross-check does not measure a forecast model or its precision.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    counts = {}
    for row in observations:
        key = row['mask_status']
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({'output': str(args.output), 'time_coverage_start_utc': scan_start,
                      'observation_count': len(observations), 'mask_status_counts': counts}, indent=2))


if __name__ == '__main__':
    main()
