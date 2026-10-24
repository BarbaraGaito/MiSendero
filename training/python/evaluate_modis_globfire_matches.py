"""Cross-check held-out MOD14A1/XGBoost alerts against GlobFire 2022-2023."""
from datetime import date, timedelta
import csv
import gzip
import json
import math
import sqlite3
import struct

from audit_fire_perimeters import geometry_distance_m
from environmental_sources import PUBLIC, RAW, ROOT, sha256
from fire_sources import PRIVATE

PREDICTIONS = PRIVATE / 'fire-temporal_test-predictions.csv.gz'
YEARS = (2022, 2023)
ALERT_THRESHOLD = 0.5
EVENT_CENTER_RADIUS_KM = 40
ALERT_PERIMETER_RADIUS_KM = 10
DATE_MARGIN_DAYS = 3
OUT = ROOT / 'docs/environmental-models-2026-10-22/modis-globfire-matches.json'


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
    kind, offset = read_u32(data, offset, endian)
    if kind == 3:
        count, offset = read_u32(data, offset, endian)
        rings = []
        for _ in range(count):
            points, offset = read_u32(data, offset, endian)
            ring, offset = read_coords(data, offset, endian, points)
            rings.append(ring)
        return {'type': 'Polygon', 'coordinates': rings}, offset
    if kind == 6:
        count, offset = read_u32(data, offset, endian)
        polygons = []
        for _ in range(count):
            polygon, offset = read_wkb(data, offset)
            polygons.append(polygon['coordinates'])
        return {'type': 'MultiPolygon', 'coordinates': polygons}, offset
    raise ValueError(f'Unsupported WKB type {kind}')


def gpkg_geometry(blob):
    if blob[:2] != b'GP':
        raise ValueError('Invalid GeoPackage geometry header')
    envelope_size = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 7]
    return read_wkb(blob, 8 + envelope_size)[0]


def day(value):
    return date.fromisoformat(str(value)[:10])


def load_alerts(coordinates):
    rows = []
    with gzip.open(PREDICTIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            score = float(row['xgboost'])
            if score >= ALERT_THRESHOLD:
                region, pixel_id = row['region'], row['pixel_id']
                coordinate = coordinates.get((region, pixel_id))
                if coordinate is not None:
                    rows.append({'region': region, 'pixel_id': pixel_id,
                        'longitude': coordinate[0], 'latitude': coordinate[1],
                        'target_date': day(row['target_at']), 'score': score})
    return rows


def main():
    geography_path = PUBLIC / 'geography.json'
    regions = json.loads(geography_path.read_text(encoding='utf-8'))['fire_regions']
    observations = PRIVATE / 'fire-observations.csv.gz'
    coordinate_map = {}
    with gzip.open(observations, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            pixel_id = f"{row['tile']}:{row['row']}:{row['col']}"
            coordinate_map.setdefault((row['region'], pixel_id),
                (float(row['longitude']), float(row['latitude'])))
    alerts = load_alerts(coordinate_map)
    conn = sqlite3.connect(f'file:{PRIVATE.as_posix()}/globfire_2022.gpkg?mode=ro', uri=True)
    # Attach the next annual file so each perimeter is read from its original layer.
    conn.execute("ATTACH DATABASE ? AS y2023", (str((PRIVATE / 'globfire_2023.gpkg').resolve()),))
    events = {}
    for alias, year in (('main', 2022), ('y2023', 2023)):
        for region in regions:
            lat_pad = EVENT_CENTER_RADIUS_KM / 110.574
            lon_pad = EVENT_CENTER_RADIUS_KM / (111.320 * max(.2, math.cos(math.radians(region['latitude']))))
            query = f'''SELECT b.id,b.initialdate,b.finaldate,b.area_ha,b.geom FROM {alias}.rtree_ba_geom r
                JOIN {alias}.ba b ON b.fid=r.id WHERE r.minx<=? AND r.maxx>=? AND r.miny<=? AND r.maxy>=?'''
            cursor = conn.execute(query, (region['longitude'] + lon_pad, region['longitude'] - lon_pad,
                region['latitude'] + lat_pad, region['latitude'] - lat_pad))
            for fid, initial, final, area, blob in cursor:
                key = (year, fid)
                if key in events:
                    continue
                geom = gpkg_geometry(blob)
                distance = geometry_distance_m(region['longitude'], region['latitude'], geom) / 1000
                if distance <= EVENT_CENTER_RADIUS_KM:
                    events[key] = {'year': year, 'id': fid, 'initialdate': str(initial),
                        'finaldate': str(final), 'area_ha': area, 'nearest_route_sector': region['name'],
                        'center_distance_km': round(distance, 3), 'geometry': geom}
    conn.close()

    test_start, test_end = date(2023, 7, 1), date(2024, 1, 1)
    eligible = []
    for event in events.values():
        start, end = day(event['initialdate']), day(event['finaldate'])
        if end + timedelta(days=DATE_MARGIN_DAYS) < test_start or start - timedelta(days=DATE_MARGIN_DAYS) >= test_end:
            continue
        event['geometry_private'] = event.pop('geometry')
        eligible.append(event)

    for event in eligible:
        event['matched_xgboost_alerts'] = []
        geom = event.pop('geometry_private')
        start, end = day(event['initialdate']), day(event['finaldate'])
        for alert in alerts:
            if not start - timedelta(days=DATE_MARGIN_DAYS) <= alert['target_date'] <= end + timedelta(days=DATE_MARGIN_DAYS):
                continue
            distance = geometry_distance_m(alert['longitude'], alert['latitude'], geom) / 1000
            if distance <= ALERT_PERIMETER_RADIUS_KM:
                event['matched_xgboost_alerts'].append({'pixel_id': alert['pixel_id'],
                    'target_date': alert['target_date'].isoformat(), 'distance_km': round(distance, 3),
                    'score': alert['score']})
        event['matched_xgboost_alerts'] = event['matched_xgboost_alerts'][:20]

    report = {'experiment_id': 'mod14a1-xgboost-temporal-test-vs-globfire-2022-2023',
        'sources': {'predictions_path': PREDICTIONS.relative_to(ROOT).as_posix(),
            'predictions_sha256': sha256(PREDICTIONS),
            'globfire': {str(year): {'url': f'https://gwis.jrc.ec.europa.eu/downloads/country.profile/globfire_{year}.gpkg.gz',
                'gpkg_sha256': sha256(PRIVATE / f'globfire_{year}.gpkg')} for year in YEARS},
            'observations_sha256': sha256(observations)},
        'protocol': {'test_window_utc': [test_start.isoformat(), test_end.isoformat()],
            'alert_threshold_xgboost': ALERT_THRESHOLD, 'event_center_radius_km': EVENT_CENTER_RADIUS_KM,
            'alert_to_perimeter_radius_km': ALERT_PERIMETER_RADIUS_KM,
            'event_date_uncertainty_margin_each_side_days': DATE_MARGIN_DAYS,
            'unit': 'one GlobFire event, not a pixel-day',
            'purpose': 'Independent-product retrospective coincidence audit; not a precision estimate.'},
        'test_alert_pixel_days_at_threshold': len(alerts), 'eligible_events_near_route_sector_centers': len(eligible),
        'events_with_any_alert_coincidence': sum(bool(event['matched_xgboost_alerts']) for event in eligible),
        'events': eligible, 'limitations': ['GlobFire is also satellite-derived and is not ground truth independent of all remote sensing.',
            'GlobFire event dates are estimated and are not exact ignition times.',
            'The 40 km sector-center eligibility radius is exploratory and does not represent a route buffer.',
            'Coincidence does not validate the alert as a calibrated probability or guarantee precision.',
            'Events and pixels are spatially and temporally correlated; no independent precision interval is reported.']}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'report': OUT.relative_to(ROOT).as_posix(),
        'test_alert_pixel_days_at_threshold': len(alerts),
        'eligible_events_near_route_sector_centers': len(eligible),
        'events_with_any_alert_coincidence': report['events_with_any_alert_coincidence'],
        'events': [{k: v for k, v in event.items() if k != 'matched_xgboost_alerts'} |
            {'alert_matches': event['matched_xgboost_alerts'][:1]} for event in eligible]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
