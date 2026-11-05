"""Inspect public NASA/INA metadata without account creation or private credentials."""
from __future__ import annotations

import json
import urllib.parse

from environmental_sources import PUBLIC, ROOT, cached_json, satellite_status


def main():
    geography = json.loads((PUBLIC / 'geography.json').read_text(encoding='utf-8'))
    url = 'https://cmr.earthdata.nasa.gov/search/collections.json?' + urllib.parse.urlencode({'short_name': 'MOD10A1', 'page_size': 20})
    collections, collection_source = cached_json(url, 'cmr-snow-collections.json')
    entries = [r for r in collections['feed']['entry'] if r.get('version_id') in ('61', '061', '6.1')]
    if len(entries) != 1:
        raise ValueError('Expected exactly one discovered MOD10A1 6.1 collection; do not guess a collection ID')
    collection = entries[0]
    granules = []
    for index, region in enumerate(geography['regions']):
        params = urllib.parse.urlencode({'collection_concept_id': collection['id'],
            'point': f"{region['longitude']},{region['latitude']}",
            'temporal': '2025-07-01T00:00:00Z,2025-07-03T23:59:59Z', 'page_size': 3})
        data, source = cached_json('https://cmr.earthdata.nasa.gov/search/granules.json?' + params, f'cmr-snow-region-{index}.json')
        granules.append({'region': region, 'source': source, 'metadata_granule_count': len(data['feed']['entry']),
                         'granules': [{'id': g['id'], 'title': g['title'], 'observed_from': g.get('time_start'),
                                       'observed_until': g.get('time_end'), 'links': g.get('links', [])} for g in data['feed']['entry']]})
    catalog, catalog_source = cached_json('https://modis.ornl.gov/rst/api/v1/products', 'modis-products.json')
    fire = [p for p in catalog['products'] if '14A' in p['product']]
    report = {'satellite_status': satellite_status(), 'snow_collection': {'id': collection['id'], 'version': collection['version_id'], 'source': collection_source},
              'snow_regional_metadata': granules, 'accessible_ornl_fire_products': fire, 'ornl_catalog_source': catalog_source,
              'data_downloaded': 'This audit covers CMR/ORNL metadata only. Actual MOD14A1 scientific pixels and QA are separately audited in fire-source-audit.json.',
              'ERA5_Land': 'Not used. Reanalysis blends numerical models and observations and is not a direct sensor ground truth; availability latency also needs explicit treatment.'}
    path = ROOT / 'docs/environmental-models-2026-10-22/access-audit.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Snow collection', collection['id'], 'regional metadata counts', [g['metadata_granule_count'] for g in granules])


if __name__ == '__main__':
    main()
