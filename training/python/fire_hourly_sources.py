"""Original public GOES observations for a separate short-horizon experiment."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from statistics import median
import csv
import gzip
import io
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import netCDF4
import numpy as np
import rasterio
from rasterio import Affine
from rasterio.features import geometry_mask
from rasterio.warp import transform, transform_geom
from scipy.ndimage import binary_erosion

from environmental_sources import PUBLIC, RAW, ROOT, sha256, utc
from fire_sources import PRIVATE, REPORT_DIR

SATELLITE = 'G16'
BASE = f'https://noaa-goes{SATELLITE[1:]}.s3.amazonaws.com/'
DIRECTORY = RAW / 'fire-goes16'
PROTOCOL = PUBLIC / 'fire-hourly-protocol.json'
OBSERVATIONS = PRIVATE / 'fire-hourly-observations.csv.gz'
MANIFEST = PRIVATE / 'fire-hourly-source-manifest.json'
NS = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}


def plan(protocol_path=PROTOCOL):
    return json.loads(Path(protocol_path).read_text(encoding='utf-8'))


def qualified_label(mask, dqf):
    if dqf == 0 and mask in (10, 11, 30, 31):
        return 1
    if dqf == 1 and mask == 100:
        return 0
    return None


def sample_plane(variable, grid):
    """Read only small native-grid windows around the fixed route samples."""
    values = np.empty(len(grid), dtype=variable.dtype)
    groups = {}
    for index, point in enumerate(grid):
        groups.setdefault(point['region'], []).append((index, point['row'], point['col']))
    for points in groups.values():
        row0 = min(point[1] for point in points)
        row1 = max(point[1] for point in points) + 1
        col0 = min(point[2] for point in points)
        col1 = max(point[2] for point in points) + 1
        window = np.asarray(variable[row0:row1, col0:col1])
        for index, row, col in points:
            values[index] = window[row - row0, col - col0]
    return values


def acquire(hour):
    prefix = hour.strftime('ABI-L2-FDCF/%Y/%j/%H/')
    listing = DIRECTORY / (hour.strftime('%Y%m%d%H') + '.listing.xml')
    if not listing.exists():
        url = BASE + '?' + urllib.parse.urlencode({'list-type': 2, 'prefix': prefix})
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        ET.fromstring(data)
        listing.write_bytes(data)
    root = ET.fromstring(listing.read_bytes())
    if root.findtext('s:IsTruncated', namespaces=NS) == 'true':
        raise ValueError('Unexpected truncated hourly listing')
    rows = sorted(root.findall('s:Contents', NS), key=lambda r: r.findtext('s:Key', namespaces=NS))
    matches = [r for r in rows if Path(r.findtext('s:Key', namespaces=NS)).name.startswith(f'OR_ABI-L2-FDCF-M6_{SATELLITE}_')]
    matches = [r for r in matches if hour <= datetime.strptime(
        Path(r.findtext('s:Key', namespaces=NS)).name.split('_s', 1)[1][:13], '%Y%j%H%M%S').replace(tzinfo=timezone.utc)
        < hour + timedelta(minutes=12)]
    if not matches:
        return {'hour': hour.isoformat(), 'status': 'missing_scan', 'listing_sha256': sha256(listing)}
    row = matches[0]
    key = row.findtext('s:Key', namespaces=NS)
    path = DIRECTORY / Path(key).name
    sidecar = path.with_suffix('.source.json')
    if path.exists() and sidecar.exists():
        source = json.loads(sidecar.read_text(encoding='utf-8'))
        if source['sha256'] != sha256(path) or source['url'] != BASE + key:
            raise ValueError('Original NOAA file changed')
    else:
        with urllib.request.urlopen(BASE + key, timeout=120) as response:
            data = response.read()
            modified = parsedate_to_datetime(response.headers['Last-Modified']).astimezone(timezone.utc)
        if data[:8] != b'\x89HDF\r\n\x1a\n' or len(data) != int(row.findtext('s:Size', namespaces=NS)):
            raise ValueError('Expected complete original NetCDF4')
        temporary = path.with_suffix('.part')
        temporary.write_bytes(data)
        temporary.replace(path)
        source = {'url': BASE + key, 'sha256': sha256(path), 'bytes': len(data),
            'relative_path': path.relative_to(ROOT).as_posix(), 'http_last_modified': modified.isoformat(),
            'retrieved_at': datetime.now(timezone.utc).isoformat()}
        sidecar.write_text(json.dumps(source, indent=2) + '\n', encoding='utf-8')
    return source | {'hour': hour.isoformat(), 'status': 'acquired',
        's3_last_modified': row.findtext('s:LastModified', namespaces=NS), 'listing_sha256': sha256(listing)}


def retry_acquire(hour):
    for attempt in range(3):
        try:
            return acquire(hour)
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def geometry(ds, regions, country, offsets):
    projection = ds['goes_imager_projection']
    height = float(projection.perspective_point_height)
    crs = (f'+proj=geos +h={height} +lon_0={projection.longitude_of_projection_origin} '
           f'+a={projection.semi_major_axis} +b={projection.semi_minor_axis} +sweep=x +units=m')
    if projection.sweep_angle_axis != 'x':
        raise ValueError('Unreviewed GOES projection')
    x, y = np.asarray(ds['x'][:]) * height, np.asarray(ds['y'][:]) * height
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    # GOES stores scan angles as float32; after projecting to metres, rounding
    # introduces sub-pixel jitter (about 1.5 m on a ~2 km grid).
    if not np.allclose(np.diff(x), dx, rtol=0, atol=2) or not np.allclose(np.diff(y), dy, rtol=0, atol=2):
        raise ValueError('Expected regular native raster coordinates')
    # Argentine provincial polygons include portions beyond the geostationary
    # satellite horizon; transform the visible portions for local country masks.
    with rasterio.Env(OGR_ENABLE_PARTIAL_REPROJECTION='TRUE'):
        polygons = [transform_geom('EPSG:4326', crs, f['geometry']) for f in country['features']]
    grid = []
    for region in regions:
        px, py = transform('EPSG:4326', crs, [region['longitude']], [region['latitude']])
        col, row = int(np.argmin(abs(x - px[0]))), int(np.argmin(abs(y - py[0])))
        margin = max(abs(v) for v in offsets) + 2
        r0, c0 = row - margin, col - margin
        size = 2 * margin + 1
        if r0 < 0 or c0 < 0 or r0 + size > len(y) or c0 + size > len(x):
            continue
        affine = Affine(dx, 0, x[c0] - dx / 2, 0, dy, y[r0] - dy / 2)
        inside = binary_erosion(geometry_mask(polygons, out_shape=(size, size), transform=affine, invert=True), iterations=1)
        points = [(row + dr, col + dc) for dr in offsets for dc in offsets if inside[margin + dr, margin + dc]]
        if not points:
            continue
        cols, rows = [p[1] for p in points], [p[0] for p in points]
        lon, lat = transform(crs, 'EPSG:4326', x[cols].tolist(), y[rows].tolist())
        for (rr, cc), latitude, longitude in zip(points, lat, lon):
            grid.append({'region': region['name'], 'pixel_id': f'{SATELLITE}:{rr}:{cc}', 'row': rr, 'col': cc,
                'latitude': latitude, 'longitude': longitude})
    return grid, {k: str(projection.getncattr(k)) for k in projection.ncattrs()}, x, y


def extract(manifest, config):
    geography = PUBLIC / 'geography.json'
    country_path = RAW / 'argentina-provinces.geojson'
    country = json.loads(country_path.read_text(encoding='utf-8'))
    if len(country['features']) != 24 or not all(f['properties'].get('fuente') == 'IGN' for f in country['features']):
        raise ValueError('Reviewed Argentine IGN boundary required')
    regions = json.loads(geography.read_text(encoding='utf-8'))['fire_regions']
    fields = ['region', 'pixel_id', 'latitude', 'longitude', 'scan_start', 'scan_end', 'available_at', 'mask', 'dqf', 'source_id']
    grid, projection_signature, reference_x, reference_y = None, None, None, None
    counts = {'positive_rows': 0, 'negative_rows': 0, 'excluded_rows': 0}
    delays, examples = [], {}
    temporary = OBSERVATIONS.with_suffix('.part')
    with temporary.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed, io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for index, source in enumerate(manifest):
            if source['status'] != 'acquired':
                continue
            path = ROOT / source['relative_path']
            if sha256(path) != source['sha256']:
                raise ValueError('Original file hash mismatch')
            with netCDF4.Dataset(path) as ds:
                if ds.platform_ID != SATELLITE or ds.scene_id != 'Full Disk':
                    raise ValueError(f'Only reviewed {SATELLITE} full disk may enter this experiment')
                start, end = utc(ds.time_coverage_start), utc(ds.time_coverage_end)
                if not utc(source['hour']) <= start < utc(source['hour']) + timedelta(minutes=12) or not start <= end <= start + timedelta(minutes=11):
                    raise ValueError(f'Scan cadence/window mismatch: {source["hour"]} {start.isoformat()} {end.isoformat()}')
                available = max(utc(ds.date_created), utc(source['s3_last_modified']), utc(source['http_last_modified']))
                if available < end:
                    raise ValueError('Publication cannot precede scan completion')
                source.update(scan_start=start.isoformat(), scan_end=end.isoformat(), available_at=available.isoformat())
                if grid is None:
                    grid, projection_signature, reference_x, reference_y = geometry(ds, regions, country, config['pixel_offsets'])
                    rows, cols = np.array([p['row'] for p in grid]), np.array([p['col'] for p in grid])
                else:
                    signature = {k: str(ds['goes_imager_projection'].getncattr(k)) for k in ds['goes_imager_projection'].ncattrs()}
                    height = float(ds['goes_imager_projection'].perspective_point_height)
                    if signature != projection_signature or not np.array_equal(np.asarray(ds['x'][:]) * height, reference_x) or not np.array_equal(np.asarray(ds['y'][:]) * height, reference_y):
                        raise ValueError('Native raster geometry changed')
                # Read only the fixed small windows around the eight route areas.
                ds.set_auto_maskandscale(False)
                masks = sample_plane(ds['Mask'], grid)
                qualities = sample_plane(ds['DQF'], grid)
                for point, mask, dqf in zip(grid, masks, qualities):
                    label = qualified_label(int(mask), int(dqf))
                    counts['excluded_rows' if label is None else 'positive_rows' if label else 'negative_rows'] += 1
                    writer.writerow({k: point[k] for k in ('region', 'pixel_id', 'latitude', 'longitude')} |
                        {'scan_start': start.isoformat(), 'scan_end': end.isoformat(), 'available_at': available.isoformat(),
                         'mask': int(mask), 'dqf': int(dqf), 'source_id': path.name})
                    if label == 1:
                        examples.setdefault(point['region'], set()).add(start.date().isoformat())
                delays.append((available - end).total_seconds() / 60)
            if (index + 1) % 50 == 0:
                print('Extracted', index + 1, 'original hourly scans', flush=True)
    temporary.replace(OBSERVATIONS)
    return counts | {'sampled_native_pixels': len(grid or []),
        'positive_region_days': {k: sorted(v) for k, v in examples.items()},
        'median_publication_lag_minutes': median(delays) if delays else None,
        'maximum_publication_lag_minutes': max(delays) if delays else None,
        'observations_sha256': sha256(OBSERVATIONS), 'geography_sha256': sha256(geography),
        'country_sha256': sha256(country_path)}


def main():
    protocol_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PROTOCOL
    config = plan(protocol_path)
    experiment_id = config.get('experiment_id', 'fire-hourly')
    global DIRECTORY, OBSERVATIONS, MANIFEST, SATELLITE, BASE
    SATELLITE = config.get('satellite_id', 'G16')
    if SATELLITE not in ('G16', 'G19'):
        raise ValueError('Only explicitly reviewed GOES-16 or GOES-19 experiments are supported')
    BASE = f'https://noaa-goes{SATELLITE[1:]}.s3.amazonaws.com/'
    DIRECTORY = RAW / experiment_id
    OBSERVATIONS = PRIVATE / f'{experiment_id}-observations.csv.gz'
    MANIFEST = PRIVATE / f'{experiment_id}-source-manifest.json'
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    hours, current = [], utc(config['start'])
    while current < utc(config['end_exclusive']):
        hours.append(current)
        current += timedelta(hours=1)
    sources = []
    print(f'Acquiring {len(hours)} hourly slots from {BASE}', flush=True)
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(retry_acquire, hour) for hour in hours]
        for future in as_completed(futures):
            sources.append(future.result())
            if len(sources) % 10 == 0:
                print('Acquired', len(sources), '/', len(hours), 'UTC hourly slots', flush=True)
    sources.sort(key=lambda r: r['hour'])
    summary = extract(sources, config)
    MANIFEST.write_text(json.dumps(sources, indent=2) + '\n', encoding='utf-8')
    report = {'status': 'acquired', 'source': BASE, 'protocol_sha256': sha256(protocol_path),
        'generated_at': datetime.now(timezone.utc).isoformat(), 'expected_hourly_slots': len(hours),
        'original_files': sum(s['status'] == 'acquired' for s in sources),
        'missing_scans': [s['hour'] for s in sources if s['status'] != 'acquired'],
        'original_bytes': sum(s.get('bytes', 0) for s in sources), 'manifest_sha256': sha256(MANIFEST),
        'summary': summary, 'synthetic_observations': 0, 'deployment_approved': False}
    (REPORT_DIR / f'{experiment_id}-source-audit.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
