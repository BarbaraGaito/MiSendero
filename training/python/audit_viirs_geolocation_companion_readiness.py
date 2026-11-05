#!/usr/bin/env python3
"""Estimate CMR availability and size for 61 VIIRS geolocation companions.

This metadata-only audit does not download granules or use Earthdata secrets.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

from environmental_sources import ROOT


BASE = ROOT / 'docs/environmental-models-2026-10-22'
PLAN = BASE / 'fire-viirs-full-swath-coverage-barda-2026-jan.json'
OUTPUT = BASE / 'fire-viirs-geolocation-companion-readiness-2026-jan.json'
OUTPUT_MD = OUTPUT.with_suffix('.md')
DOWNLOAD_MANIFEST = ROOT / 'training/data/environmental/private/viirs-geolocation-pilot-barda-2026-jan/download-manifest.json'
DOWNLOAD_DIR = DOWNLOAD_MANIFEST.parent
CMR = 'https://cmr.earthdata.nasa.gov/search/granules.json'
MASK_TO_GEO = {'VNP14IMG': 'VNP03IMG', 'VJ114IMG': 'VJ103IMG', 'VJ214IMG': 'VJ203IMG'}


def query(product: str, start: str, end: str, lon: float, lat: float) -> tuple[dict, bytes]:
    params = urllib.parse.urlencode({
        'short_name': product,
        'temporal[]': f'{start},{end}',
        'point': f'{lon:.6f},{lat:.6f}',
        'page_size': 2000,
    })
    request = urllib.request.Request(
        f'{CMR}?{params}',
        headers={'Accept': 'application/json', 'User-Agent': 'MiSenderoResearch/1.0'},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    data = json.loads(raw)
    if not isinstance(data.get('feed', {}).get('entry'), list):
        raise RuntimeError(f'Unexpected CMR response for {product}.')
    return data, raw


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    lon = float(plan['target_incident']['snmf_point_longitude'])
    lat = float(plan['target_incident']['snmf_point_latitude'])
    all_times = sorted(
        row['acquisition_start_utc']
        for detail in plan['granules_by_product'].values()
        for row in detail['overpasses']
    )
    expected_count = len(all_times)
    start, end = all_times[0], all_times[-1]
    products = {}
    all_matches = 0
    total_mb = 0.0
    for mask_product, geo_product in MASK_TO_GEO.items():
        expected = {
            row['acquisition_start_utc']
            for row in plan['granules_by_product'][mask_product]['overpasses']
        }
        data, raw = query(geo_product, start, end, lon, lat)
        by_time: dict[str, dict] = {}
        for row in data['feed']['entry']:
            stamp = row.get('time_start')
            if stamp not in by_time or row.get('updated', '') > by_time[stamp].get('updated', ''):
                by_time[stamp] = row
        matches = []
        for stamp in sorted(expected):
            row = by_time.get(stamp)
            if row is None:
                continue
            matches.append({
                'acquisition_start_utc': stamp,
                'producer_granule_id': row.get('producer_granule_id'),
                'reported_size_mb': float(row['granule_size']) if row.get('granule_size') else None,
                'latest_metadata_update': row.get('updated'),
            })
        subtotal = sum(row['reported_size_mb'] or 0.0 for row in matches)
        missing = sorted(expected - set(by_time))
        total_mb += subtotal
        all_matches += len(matches)
        products[geo_product] = {
            'paired_fire_mask_product': mask_product,
            'expected_fire_mask_passes': len(expected),
            'exact_time_matches': len(matches),
            'missing_acquisition_times_utc': missing,
            'reported_total_size_mb': round(subtotal, 2),
            'cmr_response_sha256': hashlib.sha256(raw).hexdigest(),
            'matched_granules': matches,
        }

    download_state = {'downloaded_granules': 0, 'actual_bytes': 0, 'actual_size_gb_decimal': 0.0}
    if DOWNLOAD_MANIFEST.exists():
        manifest = json.loads(DOWNLOAD_MANIFEST.read_text(encoding='utf-8'))
        records = [row for row in manifest.get('granules', [])
                   if row.get('status') in {'downloaded', 'already_downloaded'}
                   and (DOWNLOAD_DIR / row['granule_id']).exists()]
        download_state = {
            'downloaded_granules': len(records),
            'actual_bytes': sum(int(row['bytes']) for row in records),
            'actual_size_gb_decimal': round(sum(int(row['bytes']) for row in records) / 1_000_000_000, 3),
        }
    result = {
        'experiment_id': 'viirs-geolocation-companion-readiness-barda-2026-jan',
        'status': 'all_exact_time_companions_found' if all_matches == expected_count else 'some_companions_missing',
        'target_incident': plan['target_incident'],
        'cmr_query': {
            'endpoint': CMR,
            'temporal_query_utc': [start, end],
            'spatial_query': f'point {lon:.6f},{lat:.6f} at the reported SNMF incident coordinate',
            'matching_rule': 'Exact CMR time_start match to each fire-mask acquisition; newest metadata revision selected per acquisition.',
            'metadata_query_downloaded_data': False,
        },
        'products': products,
        'expected_overpasses': expected_count,
        'exact_time_matches': all_matches,
        'reported_total_size_mb': round(total_mb, 2),
        'reported_total_size_gb_decimal': round(total_mb / 1000, 2),
        'download_state': download_state,
        'limitations': [
            'CMR granule footprint and reported size are metadata; neither establishes per-pixel observation validity.',
            'This estimates the storage required to repeat the one-pass geolocation pairing across the Barda seven-day sample only.',
            'Even a complete seven-day sample is not a representative alert cohort and cannot establish model precision.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = [
        '# Tamaño de compañeras de geolocalización VIIRS para Barda', '',
        f"NASA CMR tiene {result['exact_time_matches']} compañeras de geolocalización con hora de adquisición exactamente coincidente para los {result['expected_overpasses']} pasos VNP14IMG/VJ114IMG/VJ214IMG. El tamaño publicado suma {result['reported_total_size_mb']:.2f} MB (≈ {result['reported_total_size_gb_decimal']:.2f} GB decimales). Estado local: {download_state['downloaded_granules']} archivos, {download_state['actual_size_gb_decimal']:.3f} GB decimales.", '',
        'El tamaño publicado es una estimación de metadatos CMR; el tamaño local sale del manifiesto de descarga. La cohorte permite contar observaciones por pasada, pero sigue siendo un único incidente y no estima precisión del modelo.', '',
        'El [JSON reproducible](fire-viirs-geolocation-companion-readiness-2026-jan.json) conserva los 61 IDs, horas, tamaños por producto y SHA-256 de cada respuesta CMR. Reproducción: [`audit_viirs_geolocation_companion_readiness.py`](../../training/python/audit_viirs_geolocation_companion_readiness.py).', '',
    ]
    OUTPUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({
        'output': OUTPUT.relative_to(ROOT).as_posix(),
        'expected_overpasses': result['expected_overpasses'],
        'exact_time_matches': result['exact_time_matches'],
        'reported_total_size_mb': result['reported_total_size_mb'],
        'reported_total_size_gb_decimal': result['reported_total_size_gb_decimal'],
        'downloaded_granules': download_state['downloaded_granules'],
        'actual_size_gb_decimal': download_state['actual_size_gb_decimal'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
