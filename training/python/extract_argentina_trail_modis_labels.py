"""Build a research-only MOD14A1 cohort from in-app Argentina trail routes.

This samples real MODIS FireMask/QA values in an 11x11-pixel neighborhood along
the in-app Argentina trail geometries. It does not create labels or touch the
frozen training/evaluation files.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import rasterio
import numpy as np
from rasterio.features import geometry_mask
from rasterio.warp import transform, transform_geom

from environmental_sources import PUBLIC, RAW, ROOT, sha256

PRIVATE = PUBLIC / 'private'
ROUTE_FILES = (ROOT / 'backend/src/data/additionalTrailRoutes.json',
               ROOT / 'backend/src/data/catalogExpansionRoutes20261017.json')
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
MASK_DIR = RAW / 'fire-mod14a1'
OUT_DIR = PRIVATE / 'argentina-trail-modis-labels'
START = date(2022, 1, 1)
MAX_END = date(2027, 1, 1)
ROUTE_STEP_METERS = 1000
PIXEL_OFFSETS = tuple(range(-5, 6))


def erode_one_pixel(mask):
    """Apply scipy's default 4-connected one-pixel erosion without SciPy."""
    eroded = np.zeros_like(mask)
    eroded[1:-1, 1:-1] = (mask[1:-1, 1:-1] & mask[:-2, 1:-1] & mask[2:, 1:-1]
                          & mask[1:-1, :-2] & mask[1:-1, 2:])
    return eroded


def route_samples(points):
    """Interpolate [lat, lon] route vertices no farther than 1 km apart."""
    samples = []
    for first, second in zip(points, points[1:]):
        lat1, lon1 = first
        lat2, lon2 = second
        mean_lat = math.radians((lat1 + lat2) / 2)
        length = math.hypot((lon2 - lon1) * 111_320 * math.cos(mean_lat),
                            (lat2 - lat1) * 110_574)
        steps = max(1, math.ceil(length / ROUTE_STEP_METERS))
        samples.extend((lat1 + (lat2 - lat1) * i / steps,
                        lon1 + (lon2 - lon1) * i / steps) for i in range(steps))
    samples.append(tuple(points[-1]))
    return samples


def modis_tile(latitude, longitude):
    radius, width = 6_371_007.181, 1_111_950.5196666667
    x = radius * math.radians(longitude) * math.cos(math.radians(latitude))
    y = radius * math.radians(latitude)
    h = math.floor((x + 20_015_109.354) / width)
    v = math.floor((10_007_554.677 - y) / width)
    return f'h{h:02d}v{v:02d}'


def load_routes():
    routes = {}
    for path in ROUTE_FILES:
        data = json.loads(path.read_text(encoding='utf-8'))
        for name, route in data.items():
            if len(route.get('points') or []) < 2 or not route.get('source_url'):
                raise ValueError(f'Route lacks verified geometry/source: {name}')
            routes[name] = {'points': route['points'], 'source_url': route['source_url'],
                            'source': route.get('source'), 'license': route.get('license')}
    available_tiles = {path.name.split('.')[2] for path in MASK_DIR.glob('*_FireMask.tif')}
    excluded_routes = {}
    for name, route in list(routes.items()):
        needed = {modis_tile(lat, lon) for lat, lon in route_samples(route['points'])}
        missing = sorted(needed - available_tiles)
        if missing:
            excluded_routes[name] = {'missing_MODIS_tiles': missing}
            del routes[name]
    if not routes:
        raise ValueError('No route has complete coverage in the cached MODIS tiles')
    return routes, excluded_routes


def pixel_locations(routes):
    pixels = defaultdict(set)
    tile_datasets = {}
    country_masks = {}
    country = json.loads((RAW / 'argentina-provinces.geojson').read_text(encoding='utf-8'))
    if len(country.get('features', [])) != 24:
        raise ValueError('Expected the reviewed 24-province Argentina boundary source')
    for name, route in routes.items():
        for latitude, longitude in route_samples(route['points']):
            # MODIS tiles are globally indexed in the same way as the frozen source pipeline.
            tile = modis_tile(latitude, longitude)
            if tile not in tile_datasets:
                candidates = sorted(MASK_DIR.glob(f'MOD14A1.*.{tile}.061.*_FireMask.tif'))
                if not candidates:
                    raise FileNotFoundError(f'No cached MOD14A1 raster for route tile {tile}')
                tile_datasets[tile] = rasterio.open(candidates[0])
            ds = tile_datasets[tile]
            if tile not in country_masks:
                polygons = [transform_geom('EPSG:4326', ds.crs, feature['geometry'])
                            for feature in country['features']]
                inside = geometry_mask(polygons, out_shape=ds.shape, transform=ds.transform, invert=True)
                country_masks[tile] = erode_one_pixel(inside)
            px, py = transform('EPSG:4326', ds.crs, [longitude], [latitude])
            row, col = ds.index(px[0], py[0])
            for dr in PIXEL_OFFSETS:
                for dc in PIXEL_OFFSETS:
                    rr, cc = row + dr, col + dc
                    if 0 <= rr < ds.height and 0 <= cc < ds.width and country_masks[tile][rr, cc]:
                        pixels[(tile, rr, cc)].add(name)
    for ds in tile_datasets.values():
        ds.close()
    return pixels


def item_availability():
    availability = {}
    with gzip.open(OBSERVATIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            availability.setdefault(row['item_id'], row['available_at'])
    # Later cached COGs were acquired for other documented studies and are not
    # present in the original pixel table. Their source sidecars carry the
    # upstream Last-Modified timestamp; never substitute our local download time.
    for mask_path in MASK_DIR.glob('*_FireMask.tif'):
        item_id = mask_path.name.removesuffix('_FireMask.tif')
        if item_id in availability:
            continue
        sidecar = mask_path.with_suffix('.source.json')
        if not sidecar.is_file():
            continue
        source = json.loads(sidecar.read_text(encoding='utf-8'))
        if source.get('last_modified'):
            availability[item_id] = source['last_modified']
    return availability


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=START)
    parser.add_argument('--end-exclusive', type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument('--output-tag', choices=('extended-2026-10', 'full-archive-2026-10', 'all-routes-full-archive-2026-10'),
                        help='Write a separate expanded cohort without replacing the frozen 2022-2023 artifact.')
    args = parser.parse_args()
    if not (START <= args.start < args.end_exclusive <= MAX_END):
        raise ValueError('Requested interval is outside the local MODIS archive bounds')

    routes, excluded_routes = load_routes()
    pixels = pixel_locations(routes)
    availability = item_availability()
    output_dir = (PRIVATE / f'argentina-trail-modis-labels-{args.output_tag}'
                  if args.output_tag else OUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / 'observations.csv.gz'
    manifest_path = output_dir / 'manifest.json'
    if output.exists() or manifest_path.exists():
        raise FileExistsError(f'Refusing to overwrite existing cohort: {output_dir}')
    fields = ['region', 'tile', 'row', 'col', 'latitude', 'longitude', 'observed_date',
              'available_at', 'fire_mask', 'qa', 'item_id', 'route_ids']
    counts = defaultdict(int)
    positive_dates, positive_pixels = set(), set()
    sources = []
    with output.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed, \
            __import__('io').TextIOWrapper(compressed, encoding='utf-8', newline='') as text:
        writer = csv.DictWriter(text, fieldnames=fields)
        writer.writeheader()
        for tile in sorted({key[0] for key in pixels}):
            rasters = sorted(MASK_DIR.glob(f'MOD14A1.*.{tile}.061.*_FireMask.tif'))
            for mask_path in rasters:
                item_id = mask_path.name.removesuffix('_FireMask.tif')
                qa_path = MASK_DIR / f'{item_id}_QA.tif'
                if not qa_path.is_file():
                    raise FileNotFoundError(qa_path)
                with rasterio.open(mask_path) as mask, rasterio.open(qa_path) as qa:
                    dates = mask.tags().get('Dates', '').split()
                    if not dates or len(dates) != mask.count or qa.count != mask.count:
                        raise ValueError(f'Invalid daily band/date alignment in {mask_path.name}')
                    if mask.crs != qa.crs or mask.transform != qa.transform:
                        raise ValueError(f'FireMask/QA raster geometry mismatch for {item_id}')
                    selected = [(key, names) for key, names in pixels.items() if key[0] == tile]
                    if not any(args.start.isoformat() <= d < args.end_exclusive.isoformat() for d in dates):
                        continue
                    if item_id not in availability:
                        raise ValueError(f'No source availability timestamp for {item_id}')
                    masks, qualities = mask.read(), qa.read()
                    rows = [(key, names, masks[:, key[1], key[2]], qualities[:, key[1], key[2]])
                            for key, names in selected]
                    for (t, row, col), names, masks, qualities in rows:
                        x, y = mask.xy(row, col)
                        lon, lat = transform(mask.crs, 'EPSG:4326', [x], [y])
                        for band, day in enumerate(dates):
                            if not args.start.isoformat() <= day < args.end_exclusive.isoformat():
                                continue
                            mask_value = int(masks[band])
                            qa_value = int(qualities[band])
                            if qa_value & 3 == 2 and mask_value in (8, 9):
                                counts['positive_pixel_days'] += 1
                                positive_dates.add(day)
                                positive_pixels.add((t, row, col))
                            elif qa_value & 3 == 2 and mask_value == 5:
                                counts['valid_observed_nonfire_pixel_days'] += 1
                            else:
                                counts['excluded_invalid_or_other_class_pixel_days'] += 1
                            writer.writerow({'region': 'Argentina - catálogo de rutas', 'tile': t,
                                'row': row, 'col': col, 'latitude': lat[0], 'longitude': lon[0],
                                'observed_date': day, 'available_at': availability[item_id],
                                'fire_mask': mask_value, 'qa': qa_value,
                                'item_id': item_id, 'route_ids': '|'.join(sorted(names))})
                            counts['rows'] += 1
                            counts[f'route_pixel_days_{len(names)}_routes'] += 1
                sources.append({'item_id': item_id, 'mask_sha256': sha256(mask_path),
                                'qa_sha256': sha256(qa_path), 'mask_bytes': mask_path.stat().st_size,
                                'dates': dates})
    routes_meta = {key: {'source': val['source'], 'source_url': val['source_url'],
                         'license': val['license'], 'route_vertices': len(val['points'])}
                   for key, val in routes.items()}
    manifest = {'experiment_id': 'argentina-in-app-trails-mod14a1-label-expansion',
        'period': {'start': args.start.isoformat(), 'end_exclusive': args.end_exclusive.isoformat()},
        'routes': routes_meta, 'excluded_routes': excluded_routes,
        'route_sampling': {'maximum_interpolation_spacing_m': ROUTE_STEP_METERS,
            'MODIS_pixel_offsets': [min(PIXEL_OFFSETS), max(PIXEL_OFFSETS)],
            'meaning': '11x11-pixel square windows centered on samples along route; broad route fire-risk context'},
        'counts': {'unique_MODIS_pixels': len(pixels), 'observations': counts['rows'],
                   'positive_pixel_days': counts['positive_pixel_days'],
                   'positive_dates': len(positive_dates), 'unique_positive_pixels': len(positive_pixels),
                   'valid_observed_nonfire_pixel_days': counts['valid_observed_nonfire_pixel_days'],
                   'excluded_invalid_or_other_class_pixel_days': counts['excluded_invalid_or_other_class_pixel_days'],
                   'source_rasters': len(sources)},
        'inputs': {'route_files': {str(path.relative_to(ROOT)): sha256(path) for path in ROUTE_FILES},
                   'argentina_provinces_path': (RAW / 'argentina-provinces.geojson').relative_to(ROOT).as_posix(),
                   'argentina_provinces_sha256': sha256(RAW / 'argentina-provinces.geojson'),
                   'availability_reference_path': OBSERVATIONS.relative_to(ROOT).as_posix(),
                   'availability_reference_sha256': sha256(OBSERVATIONS),
                   'source_rasters': sources},
        'observations_path': output.relative_to(ROOT).as_posix(), 'observations_sha256': sha256(output),
        'synthetic_observations': 0, 'deployment_approved': False,
        'limitations': ['Some route geometries were excluded because their MODIS tile rasters were not in the cached sources; see excluded_routes.',
            'Labels are Terra MOD14A1 FireMask/QA detections, not ground-truth ignition reports.',
            'The 11x11 pixel route windows overlap and include areas beyond each trail; a pixel-day is one observation.',
            'A wider corridor expands route coverage but does not make MODIS observations independent fire events.']}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': output.relative_to(ROOT).as_posix(), **manifest['counts'],
                      'sha256': manifest['observations_sha256']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
