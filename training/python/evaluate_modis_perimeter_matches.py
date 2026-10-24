"""Validate sampled MODIS active-fire pixels against official Córdoba perimeters."""
from datetime import date, timedelta
import csv
import gzip
import json
from pathlib import Path

from rasterio.warp import transform_geom

from audit_fire_perimeters import geometry_distance_m
from environmental_sources import PUBLIC, RAW, ROOT, sha256
from fire_sources import PRIVATE

OBS = PRIVATE / 'fire-observations.csv.gz'
LAYERS = (2022, 2023)
REPORT = ROOT / 'docs/environmental-models-2026-10-22/modis-official-perimeter-matches.json'
PIXEL_TOLERANCE_KM = 0.75
MAX_DETECTION_LAG_DAYS = 7
ROUTE_FOOTPRINT_KM = 40


def read_date(value):
    return date.fromisoformat(str(value)[:10])


def read_positive_pixels():
    positive = []
    with gzip.open(OBS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            if int(row['qa']) & 3 == 2 and int(row['fire_mask']) in (8, 9):
                positive.append({'region': row['region'], 'pixel_id': row['tile'] + ':' + row['row'] + ':' + row['col'],
                    'date': read_date(row['observed_date']), 'latitude': float(row['latitude']),
                    'longitude': float(row['longitude']), 'source_id': row['item_id']})
    return positive


def bbox(geometry):
    xs, ys = [], []
    def walk(value):
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                xs.append(value[0]); ys.append(value[1])
            else:
                for item in value:
                    walk(item)
    walk(geometry['coordinates'])
    return None if not xs else (min(xs), min(ys), max(xs), max(ys))


def main():
    positives = read_positive_pixels()
    regions = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    report = {'experiment_id': 'modis-2022-2023-official-perimeter-comparison',
        'protocol_sha256': sha256(PUBLIC / 'fire-protocol.json'), 'observation_sha256': sha256(OBS),
        'method': {'layer_years': list(LAYERS), 'official_date_window': 'same date through 7 days afterward',
            'maximum_pixel_to_perimeter_distance_km': PIXEL_TOLERANCE_KM,
            'route_footprint_filter_km': ROUTE_FOOTPRINT_KM,
            'meaning': 'Detection coincidence audit, not an ignition-time forecast test.'},
        'qualified_positive_pixel_rows': len(positives), 'source_layers': {}, 'eligible_events': 0,
        'matched_events': [], 'unmatched_events': []}
    for year in LAYERS:
        path = RAW / f'idecor-area-quemada-{year}.geojson'
        collection = json.loads(path.read_text(encoding='utf-8'))
        report['source_layers'][str(year)] = {'sha256': sha256(path), 'feature_count': len(collection['features'])}
        crs = collection['crs']['properties']['name']
        for feature in collection['features']:
            props = feature.get('properties', {})
            if not props.get('fecha_deteccion'):
                continue
            fire_date = read_date(props['fecha_deteccion'])
            if fire_date.year != year:
                continue
            geometry = transform_geom(crs, 'EPSG:4326', feature['geometry'])
            box = bbox(geometry)
            if box is None:
                continue
            nearest_center = min(geometry_distance_m(region['longitude'], region['latitude'], geometry)
                                 for region in regions) / 1000
            if nearest_center > ROUTE_FOOTPRINT_KM:
                continue
            event = {'layer_year': year, 'id': props.get('id_sicc') or props.get('fid'),
                'recorded_date': fire_date.isoformat(), 'site': props.get('sitio_referencia'),
                'locality': props.get('localidad_proxima'), 'area_ha': props.get('area_deteccion'),
                'nearest_route_center_distance_km': round(nearest_center, 3)}
            report['eligible_events'] += 1
            matches = []
            for pixel in positives:
                lag = (pixel['date'] - fire_date).days
                if not 0 <= lag <= MAX_DETECTION_LAG_DAYS:
                    continue
                if not (box[0] - .02 <= pixel['longitude'] <= box[2] + .02 and
                        box[1] - .02 <= pixel['latitude'] <= box[3] + .02):
                    continue
                distance = geometry_distance_m(pixel['longitude'], pixel['latitude'], geometry) / 1000
                if distance <= PIXEL_TOLERANCE_KM:
                    matches.append({'region': pixel['region'], 'pixel_id': pixel['pixel_id'],
                        'observed_date': pixel['date'].isoformat(), 'lag_days': lag,
                        'distance_to_perimeter_km': round(distance, 3), 'source_id': pixel['source_id']})
            if matches:
                matches.sort(key=lambda item: (item['lag_days'], item['distance_to_perimeter_km']))
                report['matched_events'].append(event | {'first_matched_detection': matches[0],
                    'coincidences': matches[:25]})
            else:
                report['unmatched_events'].append(event)
    report['matched_event_count'] = len(report['matched_events'])
    report['unmatched_event_count'] = len(report['unmatched_events'])
    report['limitations'] = [
        'Córdoba official perimeter layers are used only for years 2022 and 2023; other Argentine provinces are not represented.',
        'The satellite sample is fixed and sparse around eight sector centers, not a full-area observation.',
        'Several polygons or detections may be parts of the same physical incident; feature count is not an independent-event sample size.',
        'Official recorded date, mapped burned perimeter, and MODIS active-fire detection are different measurements.'
    ]
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'eligible_events': report['eligible_events'],
        'matched_events': report['matched_event_count'], 'unmatched_events': report['unmatched_event_count'],
        'matches': report['matched_events']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
