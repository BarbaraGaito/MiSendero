"""Acquire actual MOD14A1 daily FireMask + QA from public Planetary Computer.

Full original COGs and unsigned provenance are cached locally. Temporary public
SAS URLs stay in memory and are never printed or written to the repository.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import csv
import gzip
import io
import json
import math
import re
from statistics import median
import threading
import time
import urllib.parse
import urllib.request

import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform, transform_geom
from rasterio.windows import Window
from scipy.ndimage import binary_erosion

from environmental_sources import PUBLIC, RAW, ROOT, cached_json, sha256, utc

STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1'
COLLECTION = 'modis-14A1-061'
DIRECTORY = RAW / 'fire-mod14a1'
PRIVATE = PUBLIC / 'private'
PROTOCOL = PUBLIC / 'fire-protocol.json'
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
REPORT_DIR = ROOT / 'docs/environmental-models-2026-10-22'
ID_PATTERN = re.compile(r'^MOD14A1\.A20\d{5}\.h\d{2}v\d{2}\.061\.\d{13}$')
local = threading.local()


def protocol():
    return json.loads(PROTOCOL.read_text(encoding='utf-8'))


def tile_at(latitude, longitude):
    radius, width = 6371007.181, 1111950.5196666667
    x = radius * math.radians(longitude) * math.cos(math.radians(latitude))
    y = radius * math.radians(latitude)
    h, v = math.floor((x + 20015109.354) / width), math.floor((10007554.677 - y) / width)
    return f'h{h:02d}v{v:02d}'


def valid_land_label(mask, qa):
    # Collection 6 QA bits 0-1: water=0, coast=1, land=2, missing=3.
    # Cloud, low confidence and missing cells never become negative labels.
    if (int(qa) & 3) != 2:
        return None
    if int(mask) == 5:
        return 0
    if int(mask) in (8, 9):
        return 1
    return None


def inventory(regions, plan):
    collection, collection_source = cached_json(f'{STAC}/collections/{COLLECTION}', 'pc-mod14a1-collection.json')
    grouped = defaultdict(list)
    for region in regions:
        grouped[tile_at(region['latitude'], region['longitude'])].append(region)
    items, sources = [], []
    until = utc(plan['observations_end_exclusive'] + 'T00:00:00Z') - timedelta(seconds=1)
    for tile in sorted(grouped):
        query = {'platform': {'eq': 'terra'}, 'modis:horizontal-tile': {'eq': int(tile[1:3])},
                 'modis:vertical-tile': {'eq': int(tile[4:6])}}
        params = urllib.parse.urlencode({'collections': COLLECTION, 'query': json.dumps(query),
            'datetime': f"{plan['observations_start']}T00:00:00Z/{until.strftime('%Y-%m-%dT%H:%M:%SZ')}", 'limit': 1000})
        interval = f"{plan['observations_start']}-{plan['observations_end_exclusive']}"
        data, source = cached_json(f'{STAC}/search?{params}', f'fire-items-{tile}-{interval}.json')
        if any(link.get('rel') == 'next' for link in data.get('links', [])):
            raise ValueError('STAC pagination required; refusing a silently truncated cohort')
        by_start = defaultdict(list)
        for item in data['features']:
            props = item['properties']
            if not ID_PATTERN.fullmatch(item['id']) or props['platform'] != 'terra':
                raise ValueError('Only reviewed Terra MOD14A1.061 originals are allowed')
            if f"h{props['modis:horizontal-tile']:02d}v{props['modis:vertical-tile']:02d}" != tile:
                raise ValueError('STAC tile filter did not match')
            by_start[props['start_datetime']].append(item)
        older = []
        for versions in by_start.values():
            # The suffix is the granule production YYYYDDDhhmmss. Retain the
            # final published revision, with its own conservative availability.
            versions.sort(key=lambda item: item['id'])
            items.append(versions[-1])
            older.extend(item['id'] for item in versions[:-1])
        sources.append(source | {'tile': tile, 'items': len(by_start), 'earlier_revisions_not_used': older})
        print(tile, len(by_start), 'daily-band files', flush=True)
    return sorted(items, key=lambda i: i['id']), grouped, {'collection': collection_source,
        'stac_license': collection.get('license'), 'searches': sources}


def signed_href(href):
    parsed = urllib.parse.urlparse(href)
    if parsed.scheme != 'https' or parsed.hostname != 'modiseuwest.blob.core.windows.net' or parsed.query:
        raise ValueError('Unexpected unsigned scientific asset URL')
    token = getattr(local, 'token', None)
    if token and token['expires'] > datetime.now(timezone.utc) + timedelta(minutes=5):
        return href + '?' + token['query']
    url = 'https://planetarycomputer.microsoft.com/api/sas/v1/sign?' + urllib.parse.urlencode({'href': href})
    with urllib.request.urlopen(url, timeout=60) as response:
        signed = json.load(response)['href']
    query = urllib.parse.urlparse(signed).query
    params = urllib.parse.parse_qs(query)
    if params.get('sr') == ['c'] and params.get('se'):
        local.token = {'query': query, 'expires': utc(params['se'][0])}
    return signed


def download_asset(item, band):
    path = DIRECTORY / f"{item['id']}_{band}.tif"
    sidecar = path.with_suffix('.source.json')
    href = item['assets'][band]['href']
    if path.exists() and sidecar.exists():
        source = json.loads(sidecar.read_text(encoding='utf-8'))
        if sha256(path) != source['sha256'] or source['url'] != href:
            raise ValueError('Original COG hash/provenance changed')
        return path, source
    for attempt in range(3):
        try:
            request = urllib.request.Request(signed_href(href), headers={'Accept': 'image/tiff'})
            with urllib.request.urlopen(request, timeout=90) as response:
                data, modified = response.read(), response.headers.get('Last-Modified')
            if data[:4] not in (b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+') or not modified:
                raise ValueError('Expected original TIFF with availability metadata')
            temporary = path.with_suffix('.part')
            temporary.write_bytes(data)
            temporary.replace(path)
            source = {'url': href, 'sha256': sha256(path), 'bytes': len(data),
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'last_modified': parsedate_to_datetime(modified).astimezone(timezone.utc).isoformat(),
                'relative_path': str(path.relative_to(ROOT))}
            sidecar.write_text(json.dumps(source, indent=2) + '\n', encoding='utf-8')
            return path, source
        except Exception as error:
            local.token = None
            if attempt == 2:
                # HTTP exception strings can contain a signed URL: never expose it.
                raise RuntimeError(f"Public asset download failed for {item['id']} {band}; {type(error).__name__}") from None
            time.sleep(attempt + 1)


def download_item(item):
    return item['id'], {band: download_asset(item, band)[1] for band in ('FireMask', 'QA')}


def extract(items, grouped, manifest, country, plan, output=OBSERVATIONS):
    country_by_tile, counts, exclusions = {}, Counter(), Counter()
    fields = ['region', 'tile', 'row', 'col', 'latitude', 'longitude', 'observed_date',
              'available_at', 'fire_mask', 'qa', 'item_id']
    region_counts, delays = defaultdict(Counter), []
    PRIVATE.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.part')
    with temporary.open('wb') as raw_stream, gzip.GzipFile(filename='', fileobj=raw_stream, mode='wb', mtime=0) as compressed, io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in items:
            identifier = item['id']
            h, v = item['properties']['modis:horizontal-tile'], item['properties']['modis:vertical-tile']
            tile = f'h{h:02d}v{v:02d}'
            with rasterio.open(DIRECTORY / f'{identifier}_FireMask.tif') as mask, rasterio.open(DIRECTORY / f'{identifier}_QA.tif') as qa:
                if mask.crs != qa.crs or mask.transform != qa.transform or mask.shape != qa.shape:
                    raise ValueError('Mask/QA geometry mismatch')
                tags = mask.tags()
                dates = tags['Dates'].split()
                if len(dates) != mask.count or qa.count != mask.count or qa.tags()['Dates'].split() != dates:
                    raise ValueError('Actual daily dates must match band count; never assume eight days')
                if tags['SHORTNAME'] != 'MOD14A1' or tags['VERSIONID'] != '61':
                    raise ValueError('Unexpected sensor/product version')
                stac_dates = [utc(item['properties'][k]) for k in ('created', 'updated') if item['properties'].get(k)]
                available = max(*stac_dates, utc(tags['PRODUCTIONDATETIME']),
                    *(utc(manifest[identifier][b]['last_modified']) for b in ('FireMask', 'QA')))
                if tile not in country_by_tile:
                    polygons = [transform_geom('EPSG:4326', mask.crs, f['geometry']) for f in country['features']]
                    inside = geometry_mask(polygons, out_shape=mask.shape, transform=mask.transform, invert=True)
                    country_by_tile[tile] = binary_erosion(inside, iterations=1)
                for region in grouped[tile]:
                    x, y = transform('EPSG:4326', mask.crs, [region['longitude']], [region['latitude']])
                    center_row, center_col = mask.index(x[0], y[0])
                    offsets = plan['pixel_offsets']
                    radius = max(abs(i) for i in offsets)
                    window = Window(center_col - radius, center_row - radius, 2 * radius + 1, 2 * radius + 1)
                    if window.col_off < 0 or window.row_off < 0 or window.col_off + window.width > mask.width or window.row_off + window.height > mask.height:
                        raise ValueError('A regional sample crosses tile boundaries; explicit neighboring tile acquisition required')
                    masks, quality = mask.read(window=window), qa.read(window=window)
                    for dr in offsets:
                        for dc in offsets:
                            rr, cc = center_row + dr, center_col + dc
                            if not country_by_tile[tile][rr, cc]:
                                exclusions['outside_argentina_or_border_buffer_pixel_days'] += len(dates)
                                continue
                            px, py = mask.xy(rr, cc)
                            lon, lat = transform(mask.crs, 'EPSG:4326', [px], [py])
                            for band, day in enumerate(dates):
                                if not plan['observations_start'] <= day < plan['observations_end_exclusive']:
                                    continue
                                value, quality_value = int(masks[band, dr + radius, dc + radius]), int(quality[band, dr + radius, dc + radius])
                                label = valid_land_label(value, quality_value)
                                counts[f'mask_{value}'] += 1
                                region_counts[region['name']]['sampled_pixel_days'] += 1
                                if label is not None:
                                    counts[f'label_{label}'] += 1
                                    region_counts[region['name']][f'label_{label}'] += 1
                                else:
                                    exclusions['invalid_cloud_water_low_confidence_or_missing_pixel_days'] += 1
                                writer.writerow({'region': region['name'], 'tile': tile, 'row': rr, 'col': cc,
                                    'latitude': lat[0], 'longitude': lon[0], 'observed_date': day,
                                    'available_at': available.isoformat(), 'fire_mask': value, 'qa': quality_value, 'item_id': identifier})
                delays.extend((available - utc(day + 'T23:59:59Z')).total_seconds() / 86400 for day in dates)
    temporary.replace(output)
    return {'counts': dict(counts), 'exclusions': dict(exclusions), 'regions': dict(region_counts),
        'availability_delay_days': {'median': median(delays), 'maximum': max(delays)},
        'observations_file': str(output.relative_to(ROOT)), 'observations_sha256': sha256(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=4)
    parser.add_argument('--recent', action='store_true', help='Separate recent inference inputs; never overwrite the research cohort')
    args = parser.parse_args()
    plan = protocol()
    if args.recent:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        plan = plan | {'observations_start': (today - timedelta(days=90)).strftime('%Y-%m-%d'),
            'observations_end_exclusive': (today + timedelta(days=1)).strftime('%Y-%m-%d')}
    regions = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))['fire_regions']
    country, country_source = cached_json('https://apis.datos.gob.ar/georef/api/v2.0/provincias.geojson', 'argentina-provinces.geojson')
    if len(country['features']) != 24 or not all(f['properties'].get('fuente') == 'IGN' for f in country['features']):
        raise ValueError('Requires the reviewed official IGN province dataset distributed by Georef')
    items, grouped, discovery = inventory(regions, plan)
    if not items:
        raise SystemExit('No original daily products returned for this period; no observations or negatives generated.')
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    manifest = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download_item, item) for item in items]
        for future in as_completed(futures):
            identifier, assets = future.result()
            manifest[identifier] = assets
            if len(manifest) % 25 == 0 or len(manifest) == len(items):
                print('Verified original mask/QA pairs', len(manifest), '/', len(items), flush=True)
    output = PRIVATE / 'fire-recent-observations.csv.gz' if args.recent else OBSERVATIONS
    summary = extract(items, grouped, manifest, country, plan, output)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = PRIVATE / ('fire-recent-source-manifest.json' if args.recent else 'fire-source-manifest.json')
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    report = {'status': 'acquired', 'source': 'NASA MOD14A1.061 / Microsoft Planetary Computer',
        'purpose': 'recent_inference_inputs' if args.recent else 'frozen_training_evaluation_cohort',
        'effective_observation_period': [plan['observations_start'], plan['observations_end_exclusive']],
        'source_documentation': 'https://landweb.modaps.eosdis.nasa.gov/data/userguide/MODIS_C6_Fire_User_Guide_C.pdf',
        'discovery': discovery, 'country': country_source, 'protocol_sha256': sha256(PROTOCOL),
        'original_mask_qa_pairs': len(items), 'original_bytes': sum(s['bytes'] for pair in manifest.values() for s in pair.values()),
        'manifest_sha256': sha256(manifest_path), 'summary': summary, 'synthetic_observations': 0,
        'limitations': ['Only nominal/high-confidence detected fire vs valid observed non-fire land; not proof of absence of physical fire.',
            'Daily layers package eight dates; full COG availability can lag by weeks.',
            'Last-Modified is a conservative proxy for final-version availability, not a logged first-publication time.',
            'Raster sampling does not establish wildfire cause, trail transitability, propagation or evacuation safety.',
            'Source STAC license is preserved as returned; original COGs are not redistributed in Git.']}
    report_name = 'fire-recent-source-audit.json' if args.recent else 'fire-source-audit.json'
    (REPORT_DIR / report_name).write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(summary['counts']), flush=True)


if __name__ == '__main__':
    main()
