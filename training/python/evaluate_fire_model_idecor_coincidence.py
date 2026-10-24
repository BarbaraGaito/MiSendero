"""Audit whether held-out model alerts coincide with official Córdoba perimeters.

This is a corroboration audit only. IDECOR perimeters do not provide exhaustive
active-fire labels, so unmatched alerts must not be counted as false positives.
"""
from collections import defaultdict
from datetime import date, timedelta
import csv
import gzip
import json
from pathlib import Path

import rasterio
from rasterio.warp import transform_geom

from audit_fire_perimeters import geometry_distance_m
from environmental_sources import RAW, ROOT, sha256
from fire_sources import PRIVATE, tile_at

YEAR = 2023
PREDICTIONS = PRIVATE / 'fire-temporal_test-predictions.csv.gz'
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
PERIMETER = RAW / 'idecor-area-quemada-2023.geojson'
OUT = ROOT / 'docs/environmental-models-2026-10-22/fire-model-idecor-coincidence.json'
THRESHOLD = 0.5
MAX_DISTANCE_KM = 0.75
MAX_LAG_DAYS = 7


def walk_coordinates(value, lons, lats):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
            lons.append(value[0])
            lats.append(value[1])
        else:
            for item in value:
                walk_coordinates(item, lons, lats)


def load_events():
    collection = json.loads(PERIMETER.read_text(encoding='utf-8'))
    source_crs = collection['crs']['properties']['name']
    events = []
    for feature in collection['features']:
        raw_date = feature.get('properties', {}).get('fecha_deteccion')
        if not raw_date:
            continue
        geom = transform_geom(source_crs, 'EPSG:4326', feature['geometry'])
        lons, lats = [], []
        walk_coordinates(geom['coordinates'], lons, lats)
        if not lons:
            continue
        events.append({'id': feature.get('properties', {}).get('id_sicc')
                            or feature.get('properties', {}).get('fid')
                            or feature.get('properties', {}).get('id'),
                       'date': date.fromisoformat(str(raw_date)[:10]),
                       'site': feature.get('properties', {}).get('sitio_referencia'),
                       'locality': feature.get('properties', {}).get('localidad_proxima'),
                       'geometry': geom,
                       'bbox': (min(lons), min(lats), max(lons), max(lats))})
    return events


def main():
    required = (PREDICTIONS, OBSERVATIONS, PERIMETER)
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError('Required frozen evaluation inputs are missing: ' + ', '.join(missing))

    # Keep only coordinates for pixels whose held-out prediction crossed the
    # already-frozen threshold. Coordinates are from original sampled pixels.
    predicted = []
    wanted = set()
    with gzip.open(PREDICTIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            if float(row['xgboost']) >= THRESHOLD:
                row['target_day'] = date.fromisoformat(row['target_at'][:10])
                predicted.append(row)
                wanted.add((row['tile'], row['pixel_id'].split(':')[-2], row['pixel_id'].split(':')[-1]))

    coordinates = {}
    with gzip.open(OBSERVATIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            lat, lon = float(row['latitude']), float(row['longitude'])
            pixel_key = (tile_at(lat, lon), row['row'], row['col'])
            if pixel_key in wanted:
                coordinates[pixel_key] = (lon, lat)

    events = load_events()
    by_day = defaultdict(list)
    for event in events:
        by_day[event['date']].append(event)

    matches = []
    missing_coordinates = 0
    for row in predicted:
        _, pixel_row, pixel_col = row['pixel_id'].split(':')
        point = coordinates.get((row['tile'], pixel_row, pixel_col))
        if point is None:
            missing_coordinates += 1
            continue
        lon, lat = point
        target_day = row['target_day']
        candidate_dates = (target_day - timedelta(days=lag) for lag in range(MAX_LAG_DAYS + 1))
        candidates = []
        for event_day in candidate_dates:
            candidates.extend(by_day.get(event_day, ()))
        best = None
        for event in candidates:
            west, south, east, north = event['bbox']
            lat_pad, lon_pad = 0.015, 0.02
            if not (west - lon_pad <= lon <= east + lon_pad and south - lat_pad <= lat <= north + lat_pad):
                continue
            distance = geometry_distance_m(lon, lat, event['geometry']) / 1000
            if distance <= MAX_DISTANCE_KM and (best is None or distance < best['distance_km']):
                best = {'perimeter_id': event['id'], 'recorded_date': event['date'].isoformat(),
                        'site': event['site'], 'locality': event['locality'],
                        'lag_days': (target_day - event['date']).days,
                        'distance_km': round(distance, 4)}
        if best:
            matches.append({'tile': row['tile'], 'region': row['region'], 'pixel_id': row['pixel_id'],
                            'target_at': target_day.isoformat(), 'model_score': float(row['xgboost']),
                            'official_perimeter_match': best})

    matched_rows_by_perimeter = defaultdict(int)
    for match in matches:
        matched_rows_by_perimeter[str(match['official_perimeter_match']['perimeter_id'])] += 1
    result = {
        'experiment_id': 'fire-xgboost-heldout-2023-idecor-coincidence-audit',
        'meaning': 'Coincidence of fixed-threshold held-out model alerts with official burned-area perimeters; not precision, recall, or an exhaustive fire/no-fire evaluation.',
        'inputs': {'model_prediction_file': PREDICTIONS.relative_to(ROOT).as_posix(),
                   'model_prediction_sha256': sha256(PREDICTIONS),
                   'original_observations_sha256': sha256(OBSERVATIONS),
                   'official_perimeter_file': PERIMETER.relative_to(ROOT).as_posix(),
                   'official_perimeter_sha256': sha256(PERIMETER)},
        'protocol': {'model': 'validation-selected XGBoost from frozen MOD14A1 protocol',
                     'test_partition': 'July-December 2023 temporal holdout',
                     'threshold': THRESHOLD,
                     'same_pixel_center_distance_km': MAX_DISTANCE_KM,
                     'target_date_window': 'same day as IDECOR recorded date through +7 days',
                     'prediction_unit': 'thresholded pixel-day rows; correlated rows are retained and not treated as independent samples'},
        'counts': {'thresholded_prediction_rows': len(predicted),
                   'unique_predicted_cells': len({(r['tile'], r['pixel_id']) for r in predicted}),
                   'unique_region_days_with_at_least_one_alert': len({(r['region'], r['target_day']) for r in predicted}),
                   'regions_with_at_least_one_alert': len({r['region'] for r in predicted}),
                   'matched_prediction_rows': len(matches),
                   'unmatched_prediction_rows': len(predicted) - len(matches) - missing_coordinates,
                   'prediction_rows_without_original_coordinate': missing_coordinates,
                   'distinct_matched_official_perimeter_ids': len(matched_rows_by_perimeter),
                   'official_perimeter_features_with_dates': len(events)},
        'matches': matches,
        'limitations': [
            'An unmatched prediction is not counted as a false positive: IDECOR maps burned area, not every active fire, and is not an exhaustive fire-occurrence register.',
            'A matching perimeter supports an association with a mapped burned episode, not proof that the particular pixel was actively burning at that timestamp.',
            'Multiple perimeter features and adjacent pixel-days can represent one physical fire; row counts are correlated.',
            'The result covers only sampled route-sector pixels and the 2023 temporal test; it is not national or year-independent.',
            'A reliable precision claim requires independently verified positive and negative event labels and a sufficient number of independent predicted fire episodes.'
        ],
        'synthetic_observations': 0,
        'deployment_approved': False
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': OUT.relative_to(ROOT).as_posix(), **result['counts']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
