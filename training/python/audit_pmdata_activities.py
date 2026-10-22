"""Audit original PMData session labels; do not reinterpret them as trekking fatigue."""
from __future__ import annotations

import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'training/data/raw/pmdata-audit'
OUTPUT = ROOT / 'docs/fatigue-trekking-evaluation-2026-10-22/pmdata-activities-audit.json'
FOLDER = 'https://api.osf.io/v2/nodes/vx4bk/files/osfstorage/5e99d05ef135350590d5316d/'


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=45) as response:
        return response.read()


def listing(url: str) -> list[dict]:
    key = hashlib.sha256(url.encode()).hexdigest()
    cache = RAW / f'{key}.json'
    if not cache.exists():
        cache.write_bytes(get(url))
    page = json.loads(cache.read_bytes())
    return page['data'] + (listing(page['links']['next']) if page['links'].get('next') else [])


def child_url(entry: dict) -> str:
    return entry['relationships']['files']['links']['related']['href']


def check_person(person: dict) -> dict:
    name = person['attributes']['name']
    children = listing(child_url(person))
    labels = listing(child_url(next(x for x in children if x['attributes']['name'] == 'pmsys')))
    source = next(x for x in labels if x['attributes']['name'] == 'srpe.csv')
    path = RAW / f'{name}-srpe.csv'
    if not path.exists():
        path.write_bytes(get(source['links']['download']))
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != source['attributes']['extra']['hashes']['sha256']:
        raise ValueError(f'Official SHA256 mismatch for {name}')
    rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    activities, combinations, counts = Counter(), Counter(), Counter()
    walk_rows = []
    unspecified_activity_rows = 0
    for row in rows:
        tags = ast.literal_eval(row['activity_names'])
        # p16 contains literal {} instead of an activity list. Preserve that
        # absence; it supplies no evidence for walking, hiking or any sport.
        if tags == {}:
            unspecified_activity_rows += 1
            tags = []
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ValueError('Unexpected original activity list')
        activities.update(tags)
        combinations.update([row['activity_names']])
        counts.update([row['perceived_exertion']])
        if any(t.lower() in {'hiking', 'trekking', 'walking'} for t in tags):
            walk_rows.append({k: row[k] for k in ('activity_names', 'perceived_exertion', 'duration_min')})
    fitbit = listing(child_url(next(x for x in children if x['attributes']['name'] == 'fitbit')))
    heart = [x for x in fitbit if x['attributes']['name'] == 'heart_rate.json']
    return {'person': name, 'session_rows': len(rows), 'activity_tags': dict(activities),
            'activity_combinations': dict(combinations), 'original_RPE_counts': dict(counts),
            'unspecified_activity_rows': unspecified_activity_rows,
            'explicit_walking_hiking_trekking_rows': walk_rows,
            'srpe_sha256': digest, 'srpe_bytes': len(data), 'srpe_download': source['links']['download'],
            'heart_rate_files_in_inventory': [{'id': x['id'], 'size': x['attributes']['size'],
                                                'sha256': x['attributes']['extra']['hashes']['sha256']}
                                               for x in heart]}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    people = sorted((x for x in listing(FOLDER) if re.fullmatch(r'p\d{2}', x['attributes']['name'])),
                    key=lambda x: x['attributes']['name'])
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(check_person, people))
    tags, combinations, ratings = Counter(), Counter(), Counter()
    for person in results:
        tags.update(person['activity_tags'])
        combinations.update(person['activity_combinations'])
        ratings.update(person['original_RPE_counts'])
    report = {'source': 'https://osf.io/vx4bk/', 'description': 'https://datasets.simula.no/pmdata/',
              'participants': len(results), 'session_rows': sum(p['session_rows'] for p in results),
              'activity_tag_counts': dict(tags), 'activity_combinations': dict(combinations),
              'original_RPE_counts': dict(ratings), 'participants_with_explicit_walking_hiking_trekking':
                  [p['person'] for p in results if p['explicit_walking_hiking_trekking_rows']],
              'participant_audits': results,
              'limitations': ['Session RPE describes effort for a completed session, not time-resolved fatigue during a hike.',
                              'Daily wellness fatigue and session RPE are different outcomes; do not copy daily ratings onto activity windows.',
                              'An inventory entry for heart rate does not establish temporal alignment, coverage, signal quality or outdoor location.',
                              'Activity labels are retained verbatim; generic endurance labels are not relabelled as trekking.',
                              'No heart-rate training or deployment was performed.']}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('participants', 'session_rows', 'activity_tag_counts',
                                           'original_RPE_counts', 'participants_with_explicit_walking_hiking_trekking')}, indent=2))


if __name__ == '__main__':
    main()
