"""Auditable acquisition and causal features for observed environmental records.

No synthetic observations, interpolation, assumed publication time or conversion
of missing satellite detections into negative examples.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right, insort
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'training/data/raw/environmental'
PUBLIC = ROOT / 'training/data/environmental'
INA = 'https://alerta.ina.gob.ar/a5/obs/puntual/series'
STATIONS = (36964, 37019)
EXCLUDED_STATIONS = {32926: 'Excluded from the active project and thesis at user request on 2026-10-22; located in Entre Rios, Argentina.'}
FEATURES = ['latest_level_m', 'previous_1_m', 'previous_2_m', 'previous_3_m',
            'change_1_m', 'change_2_m', 'change_3_m', 'age_hours', 'history_hours',
            'day_sin', 'day_cos', 'hour_sin', 'hour_cos']


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError('Timestamp must be an explicit timezone-aware string')
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Timezone is required; do not assume a local timezone')
    return date.astimezone(timezone.utc)


def cached_json(url: str, name: str, refresh=False) -> tuple[dict, dict]:
    if not name.replace('-', '').replace('_', '').replace('.', '').isalnum():
        raise ValueError('Cache filename must be a simple basename')
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    sidecar = path.with_suffix(path.suffix + '.source.json')
    if not path.exists() or refresh:
        if path.exists():
            # Explicit refresh must not destroy the original research bytes.
            archive = RAW / 'archive' / f'{sha256(path)}.json'
            archive.parent.mkdir(parents=True, exist_ok=True)
            if not archive.exists():
                archive.write_bytes(path.read_bytes())
                old_source = json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else {
                    'url': url, 'retrieved_at': None, 'note': 'Cache predates acquisition sidecar; acquisition instant unknown.'}
                archive.with_suffix('.source.json').write_text(json.dumps(old_source | {'sha256': sha256(path), 'original_basename': name}, indent=2) + '\n', encoding='utf-8')
        request = urllib.request.Request(url, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read()
        json.loads(data)  # Never cache an HTML error page as scientific input.
        path.write_bytes(data)
        sidecar.write_text(json.dumps({'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                                       'sha256': sha256(path), 'bytes': len(data)}, indent=2) + '\n', encoding='utf-8')
    source = json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else {
        'url': url, 'retrieved_at': None, 'note': 'Existing research cache predates acquisition sidecar; acquisition instant unknown.'}
    if source.get('sha256') and source['sha256'] != sha256(path):
        raise ValueError('Source cache hash changed; explicit refresh required')
    return json.loads(path.read_bytes()), source | {'sha256': sha256(path), 'bytes': path.stat().st_size}


def fetch_station(station: int, refresh=False) -> tuple[dict, dict]:
    if station not in STATIONS:
        raise ValueError('Station must first be reviewed in the official inventory')
    params = urllib.parse.urlencode({'timestart': '2023-01-01T00:00:00Z', 'timeend': '2026-10-22T23:59:59Z'})
    payload, source = cached_json(f'{INA}/{station}?{params}', f'ina-{station}-2023-2026.json', refresh)
    if payload['id'] != station or payload['var']['id'] != 2 or payload['procedimiento']['id'] != 1 or payload['unidades']['abrev'] != 'm':
        raise ValueError('Requires directly measured gage height in metres; simulations/other variables rejected')
    if payload['estacion'].get('real') is not True:
        raise ValueError('Requires a real monitoring station')
    return payload, source


def observations(payload: dict) -> tuple[list[dict], dict]:
    counts: dict[str, int] = {}
    by_time: dict[datetime, list[dict]] = {}
    def excluded(reason):
        counts[reason] = counts.get(reason, 0) + 1
    for raw in payload['observaciones']:
        try:
            observed, published = utc(raw['timestart']), utc(raw['timeupdate'])
            value = float(raw['valor'])
            if not isinstance(raw.get('id'), int):
                raise ValueError('Missing source row identifier')
            if isinstance(raw['valor'], bool) or not math.isfinite(value) or published < observed:
                raise ValueError('Invalid measurement or publication time')
            if raw.get('series_id') != payload['id']:
                raise ValueError('Wrong station series')
        except (TypeError, KeyError, ValueError):
            excluded('missing_invalid_value_or_availability_timestamp')
            continue
        by_time.setdefault(observed, []).append({'observed_at': observed, 'available_at': published,
                                                 'level': value, 'source_row_id': raw['id']})
    clean = []
    for group in by_time.values():
        if len({r['level'] for r in group}) != 1:
            counts['conflicting_duplicate_timestamp'] = counts.get('conflicting_duplicate_timestamp', 0) + len(group)
            continue
        clean.append(min(group, key=lambda r: r['available_at']))
        counts['identical_duplicate_timestamp'] = counts.get('identical_duplicate_timestamp', 0) + len(group) - 1
    return sorted(clean, key=lambda r: r['observed_at']), counts


def inputs(history: list[dict], issued_at: datetime) -> dict | None:
    if len(history) < 4:
        return None
    last = history[-4:][::-1]
    if any(r['available_at'] > issued_at or r['observed_at'] > issued_at for r in last):
        raise ValueError('Future observation or publication used as predictor')
    age = (issued_at - last[0]['observed_at']).total_seconds() / 3600
    span = (last[0]['observed_at'] - last[-1]['observed_at']).total_seconds() / 3600
    if age > 6 or span > 48:
        return None
    values = [r['level'] for r in last]
    day, hour = issued_at.timetuple().tm_yday, issued_at.hour
    return dict(zip(FEATURES, values + [values[0] - v for v in values[1:]] + [age, span,
        math.sin(2 * math.pi * day / 365.2425), math.cos(2 * math.pi * day / 365.2425),
        math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24)]))


def examples(clean: list[dict], horizon: int) -> tuple[list[dict], dict]:
    if horizon not in (3, 6) or not clean:
        raise ValueError('Observed 3h/6h targets and nonempty history required')
    by_observed = {r['observed_at']: r for r in clean}
    events = sorted(clean, key=lambda r: r['available_at'])
    first = min(r['available_at'] for r in clean)
    issue = first.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    end = max(r['observed_at'] for r in clean)
    available_times, records = [], {}
    pointer, rows, rejected = 0, [], {'no_exact_observed_target': 0, 'insufficient_fresh_available_history': 0}
    while issue + timedelta(hours=horizon) <= end:
        while pointer < len(events) and events[pointer]['available_at'] <= issue:
            record = events[pointer]
            insort(available_times, record['observed_at'])
            records[record['observed_at']] = record
            pointer += 1
        offset = bisect_right(available_times, issue)
        history = [records[t] for t in available_times[max(0, offset - 4):offset]]
        x = inputs(history, issue)
        target_at = issue + timedelta(hours=horizon)
        target = by_observed.get(target_at)
        if target is None:
            rejected['no_exact_observed_target'] += 1
        elif x is None:
            rejected['insufficient_fresh_available_history'] += 1
        else:
            rows.append(x | {'issued_at': issue.isoformat(), 'target_at': target_at.isoformat(),
                              'observed': target['level'], 'baseline': x['latest_level_m'],
                              'latest_observed_at': history[-1]['observed_at'].isoformat(),
                              'latest_available_at': history[-1]['available_at'].isoformat(),
                              'target_available_at': target['available_at'].isoformat(),
                              'source_row_ids': [r['source_row_id'] for r in history],
                              'target_source_row_id': target['source_row_id']})
        issue += timedelta(hours=1)
    return rows, rejected


def satellite_status() -> dict:
    return {
        'snow': {'status': 'no_data', 'reason': 'earthdata_authentication_required',
                 'source': 'https://nsidc.org/data/mod10a1/versions/61', 'product': 'MOD10A1.061',
                 'target': 'Next-day observed snow cover only for valid cloud-free land pixels',
                 'constraints': ['Earthdata authentication is not configured; user requested work only with accessible sources.',
                                 'Product publication lags observation. Calendar observation date is not availability time.',
                                 'Cloud, polar darkness, water, fill and invalid QA cannot become negative snow labels.']},
        'fire_detection': {'status': 'not_approved', 'reason': 'experimental_validation_required_before_route_use',
                 'source': 'https://planetarycomputer.microsoft.com/dataset/modis-14A1-061',
                 'target': 'Next-24h nominal/high-confidence MODIS detection in a qualified Argentine land pixel',
                 'constraints': ['Actual MOD14A1 daily masks and QA are acquired separately by fire_sources.py; results are in fire-results.json.',
                                 'FIRMS positive-only CSV is not used to invent negative labels; daily observed non-fire land is class 5 with valid land QA.',
                                 'Publication can lag by weeks; classification performance and calibration must be checked before any experimental route visualization.',
                                 'No operational approval or prediction of wildfire propagation, transitability or evacuation safety.']}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    PUBLIC.mkdir(parents=True, exist_ok=True)
    reports = []
    for station in STATIONS:
        data, source = fetch_station(station, args.refresh)
        clean, excluded = observations(data)
        reports.append({'series_id': station, 'station': data['estacion']['nombre'], 'coordinates': data['estacion']['geom'],
                        'variable': data['var'], 'units': data['unidades'], 'procedure': data['procedimiento'],
                        'source': source, 'original_rows': len(data['observaciones']), 'accepted_rows': len(clean),
                        'exclusions': excluded, 'source_quality': 'Direct sensor measurements; not certified as consolidated quality-controlled SNIH data.',
                        'route_association': 'Not approved: a nearby station is not proof of hydrological applicability to a trail.'})
    (PUBLIC / 'source-audit.json').write_text(json.dumps({'river_stations': reports, 'excluded_river_stations': EXCLUDED_STATIONS, 'satellite_models': satellite_status(),
        'license_note': 'NASA data require product citation; INA public access does not by itself establish redistribution terms. No raw observations published.',
        'synthetic_observations': 0}, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps([{'id': r['series_id'], 'rows': r['accepted_rows']} for r in reports]))


if __name__ == '__main__':
    main()
