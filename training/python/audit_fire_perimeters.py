"""Acquire official IDECOR annual fire perimeters and audit proximity to route centers."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import urllib.parse
import urllib.request

from rasterio.warp import transform_geom

from environmental_sources import PUBLIC, RAW, ROOT, sha256

BASE = 'https://idecor-ws.mapascordoba.gob.ar/geoserver/idecor/wfs'
YEARS = range(2022, 2027)
OUT = ROOT / 'docs/environmental-models-2026-10-22/idecor-fire-perimeters-audit.json'
RADIUSES_KM = (5, 10, 25)


def ring_contains(point_lon, point_lat, ring):
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if (y1 > point_lat) != (y2 > point_lat):
            cross = (x2 - x1) * (point_lat - y1) / (y2 - y1) + x1
            if point_lon < cross:
                inside = not inside
        previous = current
    return inside


def distance_to_ring_m(point_lon, point_lat, ring):
    scale_x = 111_320 * math.cos(math.radians(point_lat))
    scale_y = 110_574
    best = math.inf
    for index, first in enumerate(ring):
        second = ring[(index + 1) % len(ring)]
        ax, ay = (first[0] - point_lon) * scale_x, (first[1] - point_lat) * scale_y
        bx, by = (second[0] - point_lon) * scale_x, (second[1] - point_lat) * scale_y
        dx, dy = bx - ax, by - ay
        denominator = dx * dx + dy * dy
        t = 0 if denominator == 0 else max(0, min(1, -(ax * dx + ay * dy) / denominator))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def polygon_distance_m(point_lon, point_lat, rings):
    outer = rings[0]
    if ring_contains(point_lon, point_lat, outer) and not any(
            ring_contains(point_lon, point_lat, hole) for hole in rings[1:]):
        return 0.0
    return min(distance_to_ring_m(point_lon, point_lat, ring) for ring in rings)


def geometry_distance_m(point_lon, point_lat, geometry):
    if geometry['type'] == 'Polygon':
        polygons = [geometry['coordinates']]
    elif geometry['type'] == 'MultiPolygon':
        polygons = geometry['coordinates']
    else:
        raise ValueError(f'Unexpected official perimeter geometry: {geometry["type"]}')
    return min(polygon_distance_m(point_lon, point_lat, polygon) for polygon in polygons)


def acquire(year):
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f'idecor-area-quemada-{year}.geojson'
    sidecar = path.with_suffix('.geojson.source.json')
    params = urllib.parse.urlencode({'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature',
                                     'typeNames': f'idecor:area_quemada_{year}',
                                     'outputFormat': 'application/json'})
    url = f'{BASE}?{params}'
    if path.exists() and sidecar.exists():
        source = json.loads(sidecar.read_text(encoding='utf-8'))
        if source['url'] != url or source['sha256'] != sha256(path):
            raise ValueError(f'Cached original WFS response changed for {year}')
        data = path.read_bytes()
    else:
        request = urllib.request.Request(url, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read()
        collection = json.loads(data)
        if collection.get('type') != 'FeatureCollection' or not collection.get('features'):
            raise ValueError(f'WFS did not return a populated feature collection for {year}')
        path.write_bytes(data)
        source = {'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                  'sha256': sha256(path), 'bytes': len(data), 'feature_count': len(collection['features'])}
        sidecar.write_text(json.dumps(source, indent=2) + '\n', encoding='utf-8')
    collection = json.loads(data)
    if collection.get('type') != 'FeatureCollection' or not collection.get('features'):
        raise ValueError(f'Cached response is not a populated feature collection for {year}')
    return collection, path, source


def main():
    geography_path = PUBLIC / 'geography.json'
    geography = json.loads(geography_path.read_text(encoding='utf-8'))['fire_regions']
    result = {'experiment_id': 'idecor-cordoba-fire-perimeters-2022-2026',
              'protocol_sha256': sha256(PUBLIC / 'fire-perimeters-protocol.json'),
              'geography_sha256': sha256(geography_path), 'source_layers': {},
              'comparison': {}, 'synthetic_observations': 0, 'deployment_approved': False}
    all_features = []
    for year in YEARS:
        collection, path, source = acquire(year)
        dates = [str(feature.get('properties', {}).get('fecha_deteccion') or '') for feature in collection['features']]
        parsed_dates = []
        for value in dates:
            if value:
                parsed_dates.append(datetime.fromisoformat(value.removesuffix('Z')).date())
        result['source_layers'][str(year)] = {
            'url': source['url'], 'sha256': source['sha256'], 'bytes': source['bytes'],
            'features': len(collection['features']),
            'min_recorded_fire_date': min(parsed_dates).isoformat() if parsed_dates else None,
            'max_recorded_fire_date': max(parsed_dates).isoformat() if parsed_dates else None,
            'record_dates_outside_layer_year': sum(date.year != year for date in parsed_dates),
            'properties': sorted(collection['features'][0].get('properties', {})),
            'cache_path': path.relative_to(ROOT).as_posix(),
        }
        for feature in collection['features']:
            feature = dict(feature)
            feature['_layer_year'] = year
            feature['geometry'] = transform_geom(collection['crs']['properties']['name'],
                'EPSG:4326', feature['geometry'])
            all_features.append(feature)

    for region in geography:
        events = []
        for feature in all_features:
            props = feature.get('properties', {})
            geometry = feature.get('geometry')
            if not geometry:
                continue
            distance = geometry_distance_m(region['longitude'], region['latitude'], geometry)
            if distance <= max(RADIUSES_KM) * 1000:
                events.append({'layer_year': feature['_layer_year'], 'fire_date': props.get('fecha_deteccion'),
                    'id': props.get('id_sicc') or props.get('fid'), 'site': props.get('sitio_referencia'),
                    'locality': props.get('localidad_proxima'), 'department': props.get('departamento'),
                    'area_ha': props.get('area_deteccion'), 'distance_km': round(distance / 1000, 3)})
        events.sort(key=lambda event: event['distance_km'])
        result['comparison'][region['name']] = {
            'coordinate': {'latitude': region['latitude'], 'longitude': region['longitude']},
            'perimeters_within_km': {str(radius): sum(event['distance_km'] <= radius for event in events)
                                      for radius in RADIUSES_KM},
            'nearest_events': events[:10],
            'interpretation': 'Distance is from the catalog sector center, not the full trail geometry.'}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': OUT.relative_to(ROOT).as_posix(),
        'layers': {year: summary['features'] for year, summary in result['source_layers'].items()},
        'within_10km': {name: summary['perimeters_within_km']['10'] for name, summary in result['comparison'].items()},
        'report_sha256': sha256(OUT)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
