"""Audit GOES active-fire detections against a specified GWIS GlobFire year.

This is an event coincidence audit, not a test of ignition prediction or a
validated estimate of route-level precision. GlobFire is a separate burned-area
product derived from MCD64A1; it is not ground truth independent of satellites.
"""
from datetime import date, timedelta
import argparse
import csv
import gzip
import json
import math
import sqlite3
import struct

from audit_fire_perimeters import geometry_distance_m
from environmental_sources import PUBLIC, ROOT, sha256
from fire_sources import PRIVATE

COHORTS = {
    'goes19': {'experiment': 'fire-goes19-2025q4-2026jan', 'layers': (2025,), 'year': 2025},
    'goes16': {'experiment': 'fire-goes16-2025-q1', 'layers': (2025,), 'year': 2025},
    'goes16-2024feb': {'experiment': 'fire-goes16-2024-feb-perimeter-test', 'layers': (2024,), 'year': 2024},
}
PIXEL_TOLERANCE_KM = (2.5, 5, 10)
DATE_MARGIN_DAYS = 3


def read_u32(data, offset, endian):
    return struct.unpack_from(endian + 'I', data, offset)[0], offset + 4


def read_coords(data, offset, endian, count):
    points = []
    for _ in range(count):
        x, y = struct.unpack_from(endian + 'dd', data, offset)
        offset += 16
        points.append([x, y])
    return points, offset


def read_wkb(data, offset=0):
    endian = '<' if data[offset] == 1 else '>'
    offset += 1
    geom_type, offset = read_u32(data, offset, endian)
    base_type = geom_type & 0xFF
    if base_type == 3:
        ring_count, offset = read_u32(data, offset, endian)
        rings = []
        for _ in range(ring_count):
            point_count, offset = read_u32(data, offset, endian)
            ring, offset = read_coords(data, offset, endian, point_count)
            rings.append(ring)
        return {'type': 'Polygon', 'coordinates': rings}, offset
    if base_type == 6:
        polygon_count, offset = read_u32(data, offset, endian)
        polygons = []
        for _ in range(polygon_count):
            geometry, offset = read_wkb(data, offset)
            if geometry['type'] != 'Polygon':
                raise ValueError('Unexpected non-Polygon member in MultiPolygon')
            polygons.append(geometry['coordinates'])
        return {'type': 'MultiPolygon', 'coordinates': polygons}, offset
    raise ValueError(f'Unsupported WKB type {geom_type}')


def gpkg_geometry(blob):
    if blob[:2] != b'GP':
        raise ValueError('Invalid GeoPackage geometry header')
    flags = blob[3]
    envelope_indicator = (flags >> 1) & 7
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    offset = 8 + envelope_sizes[envelope_indicator]
    geometry, end = read_wkb(blob, offset)
    if end != len(blob):
        raise ValueError('Unexpected trailing bytes in WKB')
    return geometry


def parse_date(value):
    return date.fromisoformat(str(value)[:10])


def load_positives(obs_path):
    rows = []
    with gzip.open(obs_path, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            if int(row['dqf']) == 0 and int(row['mask']) in (10, 11, 30, 31):
                rows.append({'region': row['region'], 'pixel_id': row['pixel_id'],
                    'date': parse_date(row['scan_start']), 'latitude': float(row['latitude']),
                    'longitude': float(row['longitude']), 'scan_start': row['scan_start']})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', choices=COHORTS, default='goes19')
    parser.add_argument('--route-radius-km', type=float, choices=(10, 20, 30), default=10,
        help='Exploratory radius from a sampled route-sector center; 10 km is the frozen default.')
    args = parser.parse_args()
    config = COHORTS[args.cohort]
    radius_km = args.route_radius_km
    experiment = config['experiment']
    gpkg = PRIVATE / f"globfire_{config['year']}.gpkg"
    obs_path = PRIVATE / f'{experiment}-observations.csv.gz'
    suffix = '' if radius_km == 10 else f'-r{int(radius_km)}km'
    out_path = ROOT / f'docs/environmental-models-2026-10-22/{args.cohort}-globfire-matches{suffix}.json'
    layers = config['layers']
    geography_path = PUBLIC / 'geography.json'
    regions = json.loads(geography_path.read_text(encoding='utf-8'))['fire_regions']
    positives = load_positives(obs_path)
    protocol = json.loads((PUBLIC / f'{experiment}-protocol.json').read_text(encoding='utf-8'))
    obs_start = date.fromisoformat(protocol['start'][:10])
    obs_end = date.fromisoformat(protocol['end_exclusive'][:10])
    conn = sqlite3.connect(f'file:{gpkg.as_posix()}?mode=ro', uri=True)
    events = {}
    for region in regions:
        # Conservative degree expansion around the fixed route-sector center.
        lat_pad = radius_km / 110.574
        lon_pad = radius_km / (111.320 * max(0.2, math.cos(math.radians(region['latitude']))))
        cur = conn.execute('''SELECT b.id,b.initialdate,b.finaldate,b.area_ha,b.geom
            FROM rtree_ba_geom r JOIN ba b ON b.fid=r.id
            WHERE r.minx<=? AND r.maxx>=? AND r.miny<=? AND r.maxy>=?''',
            (region['longitude'] + lon_pad, region['longitude'] - lon_pad,
             region['latitude'] + lat_pad, region['latitude'] - lat_pad))
        for fid, initial, final, area, blob in cur:
            key = (fid, initial, final, area)
            if key in events:
                continue
            geom = gpkg_geometry(blob)
            dist = geometry_distance_m(region['longitude'], region['latitude'], geom) / 1000
            if dist <= radius_km:
                events[key] = {'id': fid, 'initialdate': str(initial), 'finaldate': str(final),
                    'area_ha': area, 'nearest_region': region['name'],
                    'center_distance_km': round(dist, 3), 'geometry': geom}

    evaluated = []
    for event in events.values():
        start, end = parse_date(event['initialdate']), parse_date(event['finaldate'])
        if end + timedelta(days=DATE_MARGIN_DAYS) < obs_start or start - timedelta(days=DATE_MARGIN_DAYS) >= obs_end:
            continue
        event_start = start - timedelta(days=DATE_MARGIN_DAYS)
        event_end = end + timedelta(days=DATE_MARGIN_DAYS)
        candidates = []
        for obs in positives:
            if not event_start <= obs['date'] <= event_end:
                continue
            # Bounding-box precheck avoids expensive polygon-distance work.
            if geometry_distance_m(obs['longitude'], obs['latitude'], event['geometry']) <= max(PIXEL_TOLERANCE_KM) * 1000:
                dist = geometry_distance_m(obs['longitude'], obs['latitude'], event['geometry']) / 1000
                candidates.append({'region': obs['region'], 'pixel_id': obs['pixel_id'],
                    'scan_start': obs['scan_start'], 'distance_km': round(dist, 3),
                    'day_from_initial': (obs['date'] - start).days})
        event.pop('geometry')
        event['goes_coincidences'] = sorted(candidates, key=lambda x: (x['distance_km'], abs(x['day_from_initial'])))[:20]
        evaluated.append(event)

    conn.close()
    report = {'experiment_id': f'{experiment}-vs-gwis-globfire',
        'sources': {'globfire_urls': [f'https://gwis.jrc.ec.europa.eu/downloads/country.profile/globfire_{year}.gpkg.gz' for year in layers],
            'globfire_gpkg_sha256': sha256(gpkg), 'globfire_gpkg_bytes': gpkg.stat().st_size,
            'goes_observations_sha256': sha256(obs_path), 'goes_positive_rows': len(positives),
            'goes_observation_period': [obs_start.isoformat(), obs_end.isoformat()]},
        'protocol': {'site_center_radius_km': radius_km,
            'pixel_to_perimeter_thresholds_km': list(PIXEL_TOLERANCE_KM),
            'date_uncertainty_margin_days': DATE_MARGIN_DAYS,
            'globfire_algorithm': '2026 product from MCD64A1 C6.1 burned pixels; final event perimeters, initial/final dates; event merging by ST-DBSCAN; minimum four pixels (~86ha).',
            'purpose': 'Retrospective spatial-temporal coincidence audit of active-fire detections, not ignition prediction.'},
        'eligible_route_sector_events': len(evaluated), 'events': evaluated,
        'matched_events_by_distance_km': {str(t): sum(any(obs['distance_km'] <= t for obs in e['goes_coincidences']) for e in evaluated) for t in PIXEL_TOLERANCE_KM},
        'limitations': ['GlobFire is satellite-derived and is not independent ground truth.',
            f"Only the GlobFire {config['year']} layer was used in this cohort; no extrapolation to other years is supported.",
            'The route cohort is fixed sample centers, not complete trail geometries.',
            'A coincidence measures detection of active fire, not advance warning or ignition prediction.',
            'A handful of events cannot support a reliable precision estimate.']}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'report': out_path.relative_to(ROOT).as_posix(),
        'eligible_route_sector_events': len(evaluated),
        'matched_events_by_distance_km': report['matched_events_by_distance_km'],
        'events': [{k: v for k, v in e.items() if k != 'goes_coincidences'} | {'coincidences': e['goes_coincidences'][:1]} for e in evaluated]},
        ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
