"""Compare GOES-19 high-quality active-fire detections with official perimeters."""
from datetime import date, timedelta
import csv
import gzip
import json
from pathlib import Path

from rasterio.warp import transform_geom

from audit_fire_perimeters import geometry_distance_m
from environmental_sources import PUBLIC, RAW, ROOT, sha256
from fire_sources import PRIVATE

EXPERIMENT = 'fire-goes19-2025q4-2026jan'
OBS = PRIVATE / f'{EXPERIMENT}-observations.csv.gz'
LAYERS = (2025, 2026)
REPORT = ROOT / 'docs/environmental-models-2026-10-22/goes19-official-perimeter-matches.json'
WINDOW_DAYS = 1
PIXEL_TOLERANCE_KM = (2.5, 5, 10)
ROUTE_FOOTPRINT_KM = 80


def as_date(value):
    return date.fromisoformat(str(value)[:10])


def bounds(geometry):
    xs, ys = [], []
    def walk(value):
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                xs.append(value[0]); ys.append(value[1])
            else:
                for item in value:
                    walk(item)
    walk(geometry['coordinates'])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def load_positive_observations():
    positives = []
    with gzip.open(OBS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            mask, dqf = int(row['mask']), int(row['dqf'])
            if dqf == 0 and mask in (10, 11, 30, 31):
                positives.append({'region': row['region'], 'pixel_id': row['pixel_id'],
                    'date': as_date(row['scan_start']), 'latitude': float(row['latitude']),
                    'longitude': float(row['longitude']), 'scan_start': row['scan_start']})
    return positives


def main():
    positives = load_positive_observations()
    regions = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    report = {'experiment_id': EXPERIMENT, 'observation_sha256': sha256(OBS),
        'method': {'official_date_window_days_each_side': WINDOW_DAYS,
            'pixel_to_perimeter_distance_thresholds_km': list(PIXEL_TOLERANCE_KM),
            'route_footprint_filter_km': ROUTE_FOOTPRINT_KM,
            'meaning': 'A spatial-temporal coincidence audit only; no detection does not prove absence of fire, and the recorded perimeter date is not exact ignition time.'},
        'goes_positive_rows': len(positives), 'official_perimeter_layers': {},
        'eligible_events_near_sampled_route_footprints': 0, 'matched_events': [],
        'unmatched_events': []}
    for year in LAYERS:
        path = RAW / f'idecor-area-quemada-{year}.geojson'
        collection = json.loads(path.read_text(encoding='utf-8'))
        report['official_perimeter_layers'][str(year)] = {'sha256': sha256(path), 'feature_count': len(collection['features'])}
        crs = collection['crs']['properties']['name']
        for feature in collection['features']:
            props = feature.get('properties', {})
            raw_date = props.get('fecha_deteccion')
            if not raw_date:
                continue
            fire_date = as_date(raw_date)
            if not date(2025, 10, 1) <= fire_date < date(2026, 2, 1):
                continue
            geometry = transform_geom(crs, 'EPSG:4326', feature['geometry'])
            box = bounds(geometry)
            if box is None:
                continue
            event = {'layer_year': year, 'id': props.get('id_sicc') or props.get('fid'),
                'fire_date': fire_date.isoformat(), 'site': props.get('sitio_referencia'),
                'locality': props.get('localidad_proxima'), 'area_ha': props.get('area_deteccion')}
            candidates = []
            for positive in positives:
                delta = (positive['date'] - fire_date).days
                if abs(delta) > WINDOW_DAYS:
                    continue
                if not (box[0] - .15 <= positive['longitude'] <= box[2] + .15 and
                        box[1] - .15 <= positive['latitude'] <= box[3] + .15):
                    continue
                distance = geometry_distance_m(positive['longitude'], positive['latitude'], geometry) / 1000
                if distance <= max(PIXEL_TOLERANCE_KM):
                    candidates.append({'region': positive['region'], 'pixel_id': positive['pixel_id'],
                        'scan_start': positive['scan_start'], 'day_offset_from_official_date': delta,
                        'distance_to_perimeter_km': round(distance, 3)})
            # Exclude events outside the fixed sampling footprint; they cannot be tested by this cohort.
            if not positives:
                continue
            nearest_route_center = min(geometry_distance_m(region['longitude'], region['latitude'], geometry)
                                       for region in regions) / 1000
            if nearest_route_center > ROUTE_FOOTPRINT_KM:
                continue
            report['eligible_events_near_sampled_route_footprints'] += 1
            if candidates:
                candidates.sort(key=lambda item: (abs(item['day_offset_from_official_date']), item['distance_to_perimeter_km']))
                report['matched_events'].append(event | {'coincidences': candidates[:20]})
            else:
                report['unmatched_events'].append(event | {'nearest_route_center_distance_km': round(nearest_route_center, 3)})
    report['matched_event_count'] = len(report['matched_events'])
    report['unmatched_event_count'] = len(report['unmatched_events'])
    report['event_matches_by_distance_threshold_km'] = {
        str(threshold): sum(any(item['distance_to_perimeter_km'] <= threshold for item in event['coincidences'])
                            for event in report['matched_events'])
        for threshold in PIXEL_TOLERANCE_KM}
    report['limitations'] = [
        'Only events mapped in Córdoba layers 2025 and 2026 and recorded from 2025-10-01 through 2026-01-31 are evaluated.',
        'The eight source samples are fixed pixels around route sectors, not complete route geometries or continuous wall-to-wall coverage.',
        'Multiple detections or pixels may belong to one fire; they do not count as independent successes.',
        'Burned-area perimeter and its recorded date are a different measurement from active-fire pixel detection.'
    ]
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'eligible': report['eligible_events_near_sampled_route_footprints'],
        'matched': report['matched_event_count'], 'unmatched': report['unmatched_event_count'],
        'matched': report['matched_events']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
