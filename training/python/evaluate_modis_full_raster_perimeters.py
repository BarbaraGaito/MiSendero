"""Compare all downloaded MOD14A1 pixels with official Córdoba fire perimeters."""
from collections import defaultdict
from datetime import date, timedelta
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import xy
from rasterio.warp import transform, transform_geom
from rasterio.windows import from_bounds

from audit_fire_perimeters import geometry_distance_m
from environmental_sources import PUBLIC, RAW, ROOT, sha256

LAYERS = (2022, 2023)
RASTERS = RAW / 'fire-mod14a1'
REPORT = ROOT / 'docs/environmental-models-2026-10-22/modis-full-raster-official-perimeter-matches.json'
PIXEL_TOLERANCE_KM = 0.75
MAX_DETECTION_LAG_DAYS = 7


def source_index():
    """Index the actual observation date for each daily band in every COG."""
    by_day = defaultdict(list)
    sources = []
    for fire_path in sorted(RASTERS.glob('*_FireMask.tif')):
        item_id = fire_path.name.removesuffix('_FireMask.tif')
        qa_path = RASTERS / f'{item_id}_QA.tif'
        if not qa_path.exists():
            continue
        with rasterio.open(fire_path) as dataset:
            tags = dataset.tags()
            if tags.get('SHORTNAME') != 'MOD14A1' or tags.get('VERSIONID') != '61':
                continue
            dates = tags.get('Dates', '').split()
            if len(dates) != dataset.count:
                continue
            dates = [value for value in dates if value.startswith(('2022-', '2023-'))]
            if not dates:
                continue
            source = {'item_id': item_id, 'fire_path': fire_path, 'qa_path': qa_path,
                      'dates': dates, 'crs': dataset.crs}
            sources.append(source)
            for band, value in enumerate(tags.get('Dates', '').split(), start=1):
                if value.startswith(('2022-', '2023-')):
                    by_day[value].append((source, band))
    return by_day, sources


def bbox(geometry):
    xs, ys = [], []

    def walk(value):
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                xs.append(value[0])
                ys.append(value[1])
            else:
                for item in value:
                    walk(item)

    walk(geometry['coordinates'])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def positive_centers(source, band, geometry_wgs84):
    """Return high-confidence active-fire pixel centers in/near one perimeter."""
    with rasterio.open(source['fire_path']) as mask_ds, rasterio.open(source['qa_path']) as qa_ds:
        geometry = transform_geom('EPSG:4326', mask_ds.crs, geometry_wgs84)
        bounds = bbox(geometry)
        if bounds is None:
            return [], 0
        # Transform an expanded geographic envelope to the raster CRS for a small window.
        wgs84_bounds = bbox(geometry_wgs84)
        west, south, east, north = wgs84_bounds
        lon_pad = 0.06
        lat_pad = 0.04
        xs, ys = transform('EPSG:4326', mask_ds.crs,
                           [west - lon_pad, east + lon_pad, west - lon_pad, east + lon_pad],
                           [south - lat_pad, south - lat_pad, north + lat_pad, north + lat_pad])
        left, right, top, bottom = min(xs), max(xs), max(ys), min(ys)
        window = from_bounds(left, bottom, right, top, transform=mask_ds.transform)
        window = window.round_offsets().round_lengths()
        window = window.intersection(rasterio.windows.Window(0, 0, mask_ds.width, mask_ds.height))
        if window.width <= 0 or window.height <= 0:
            return [], 0
        values = mask_ds.read(band, window=window)
        quality = qa_ds.read(band, window=window)
        valid_land = (quality & 3) == 2
        positive = valid_land & np.isin(values, (8, 9))
        rows, cols = np.where(positive)
        centers = []
        row_offset, col_offset = int(window.row_off), int(window.col_off)
        for row, col in zip(rows, cols):
            x, y = xy(mask_ds.transform, row + row_offset, col + col_offset, offset='center')
            lon, lat = transform(mask_ds.crs, 'EPSG:4326', [x], [y])
            distance = geometry_distance_m(lon[0], lat[0], geometry_wgs84) / 1000
            if distance <= PIXEL_TOLERANCE_KM:
                centers.append({'latitude': lat[0], 'longitude': lon[0],
                                 'distance_to_perimeter_km': round(distance, 3),
                                 'item_id': source['item_id']})
        return centers, int(np.count_nonzero(valid_land))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('route-40km', 'covered-tiles'), default='route-40km')
    args = parser.parse_args()
    by_day, sources = source_index()
    source_audit = ROOT / 'docs/environmental-models-2026-10-22/fire-source-audit.json'
    regions = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    tile_bounds = {}
    for source in sources:
        tile = source['item_id'].split('.')[2]
        if tile not in tile_bounds:
            with rasterio.open(source['fire_path']) as dataset:
                tile_bounds[tile] = (dataset.crs, dataset.bounds)
    scope = args.scope
    report_path = (REPORT if scope == 'route-40km' else
                   ROOT / 'docs/environmental-models-2026-10-22/modis-full-raster-cordoba-tile-coverage.json')
    report = {'experiment_id': f'modis-2022-2023-full-raster-official-perimeter-comparison-{scope}',
              'method': {'source_product': 'NASA Terra MOD14A1.061 original daily FireMask and QA COGs',
                         'spatial_sample': 'all MODIS pixels within a bounding window around each eligible official perimeter, read from original full-tile COGs; no fixed-point subsampling',
                         'official_date_window': f"same recorded date through {MAX_DETECTION_LAG_DAYS} days afterward",
                         'maximum_pixel_center_distance_km': PIXEL_TOLERANCE_KM,
                         'geographic_scope': 'perimeters within 40 km of catalog hiking-sector centers' if scope == 'route-40km' else 'all Córdoba perimeters intersecting any acquired MODIS tile',
                         'match_rule': 'QA land bits == 2, FireMask in {8,9}, and pixel center within tolerance of official burned perimeter',
                         'meaning': 'Spatial-temporal detection coincidence audit, not ignition-time forecast evaluation.'},
              'source_raster_count': len(sources),
              'source_audit_sha256': sha256(source_audit),
              'source_dates': [min(by_day), max(by_day)] if by_day else [],
              'source_layers': {}, 'eligible_events': 0,
              'synthetic_observations': 0, 'deployment_approved': False,
              'events_without_valid_raster_coverage': [], 'matched_events': [], 'unmatched_events': []}
    for year in LAYERS:
        layer = RAW / f'idecor-area-quemada-{year}.geojson'
        collection = json.loads(layer.read_text(encoding='utf-8'))
        report['source_layers'][str(year)] = {'sha256': sha256(layer), 'feature_count': len(collection['features'])}
        crs = collection['crs']['properties']['name']
        for feature in collection['features']:
            props = feature.get('properties', {})
            raw_date = props.get('fecha_deteccion')
            if not raw_date:
                continue
            fire_date = date.fromisoformat(str(raw_date)[:10])
            if fire_date.year != year:
                continue
            geometry = transform_geom(crs, 'EPSG:4326', feature['geometry'])
            nearest_route_center = None
            coverage_tiles = []
            if scope == 'route-40km':
                nearest_route_center = min(geometry_distance_m(region['longitude'], region['latitude'], geometry)
                                           for region in regions) / 1000
                if nearest_route_center > 40:
                    continue
            else:
                for tile, (tile_crs, bounds) in tile_bounds.items():
                    projected = transform_geom('EPSG:4326', tile_crs, geometry)
                    projected_box = bbox(projected)
                    if projected_box and not (projected_box[2] < bounds.left or projected_box[0] > bounds.right or
                                              projected_box[3] < bounds.bottom or projected_box[1] > bounds.top):
                        coverage_tiles.append(tile)
                if not coverage_tiles:
                    continue
            event = {'layer_year': year, 'id': props.get('id_sicc') or props.get('fid'),
                     'recorded_date': fire_date.isoformat(), 'site': props.get('sitio_referencia'),
                     'locality': props.get('localidad_proxima'), 'area_ha': props.get('area_deteccion')}
            if nearest_route_center is not None:
                event['nearest_route_center_distance_km'] = round(nearest_route_center, 3)
            else:
                event['acquired_tiles_intersecting_perimeter'] = sorted(coverage_tiles)
            detections, valid_pixels, observed_days = [], 0, 0
            for lag in range(MAX_DETECTION_LAG_DAYS + 1):
                observed_date = (fire_date + timedelta(days=lag)).isoformat()
                for source, band in by_day.get(observed_date, []):
                    if scope == 'covered-tiles' and source['item_id'].split('.')[2] not in coverage_tiles:
                        continue
                    # Only examine rasters whose native tile intersects the event's geometry.
                    with rasterio.open(source['fire_path']) as ds:
                        projected = transform_geom('EPSG:4326', ds.crs, geometry)
                        projected_bounds = bbox(projected)
                        if not projected_bounds:
                            continue
                        raster_bounds = ds.bounds
                        if (projected_bounds[2] < raster_bounds.left or projected_bounds[0] > raster_bounds.right or
                                projected_bounds[3] < raster_bounds.bottom or projected_bounds[1] > raster_bounds.top):
                            continue
                    centers, valid_count = positive_centers(source, band, geometry)
                    if valid_count:
                        valid_pixels += valid_count
                        observed_days += 1
                    for center in centers:
                        detections.append(center | {'observed_date': observed_date, 'lag_days': lag})
            if not observed_days:
                report['events_without_valid_raster_coverage'].append(event)
                continue
            report['eligible_events'] += 1
            event['valid_pixel_day_samples_in_window'] = valid_pixels
            event['days_with_valid_land_observations'] = observed_days
            if detections:
                detections.sort(key=lambda item: (item['lag_days'], item['distance_to_perimeter_km']))
                report['matched_events'].append(event | {'first_matched_detection': detections[0],
                                                         'coincidence_count': len(detections),
                                                         'coincidences': detections[:30]})
            else:
                report['unmatched_events'].append(event)
    report['matched_event_count'] = len(report['matched_events'])
    report['unmatched_event_count'] = len(report['unmatched_events'])
    report['events_without_valid_raster_coverage_count'] = len(report['events_without_valid_raster_coverage'])
    report['limitations'] = [
        'Córdoba perimeter layers are used only for years 2022 and 2023.',
        'The search examines a geographic window around each perimeter using downloaded full-tile COGs; it does not scan all Argentina, and events outside the acquired tile/date coverage are not evaluated.',
        'Daily product observations and perimeter-reported dates differ; the 0-7-day window is a sensitivity rule, not a claimed sensor latency.',
        'Only nominal/high-confidence active-fire classes are counted; a satellite non-detection does not prove absence of fire.',
        'Multiple perimeter features can belong to one physical fire; feature counts are not independent-event sample sizes.'
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'eligible_events': report['eligible_events'],
                      'matched_events': report['matched_event_count'],
                      'unmatched_events': report['unmatched_event_count'],
                      'events_without_valid_coverage': report['events_without_valid_raster_coverage_count'],
                      'matches': report['matched_events']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
