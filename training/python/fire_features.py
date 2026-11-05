"""Causal next-24h examples from real daily MODIS pixels, without imputation."""
from bisect import insort
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
import csv
import gzip
import math
import sys

from environmental_sources import utc
from fire_sources import OBSERVATIONS, valid_land_label

FEATURES = ['latitude', 'longitude', 'day_sin', 'day_cos', 'latest_fire', 'previous_fire_1',
    'previous_fire_2', 'previous_fire_3', 'historical_fire_fraction', 'latest_age_days',
    'previous_age_1_days', 'previous_age_2_days', 'previous_age_3_days', 'history_span_days']


@dataclass(slots=True)
class Observation:
    day: object
    available_at: object
    label: int | None
    mask: int
    qa: int
    item_id: str

    def __getitem__(self, name):
        return getattr(self, name)


def load_cells(path=OBSERVATIONS):
    cells, dates, availability, counts, conflicts = {}, {}, {}, Counter(), set()
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            counts['sampled_pixel_days'] += 1
            label = valid_land_label(int(row['fire_mask']), int(row['qa']))
            if label is None:
                counts['excluded_invalid_quality'] += 1
            key = f"{row['tile']}:{row['row']}:{row['col']}"
            cell = cells.setdefault(key, {'region': row['region'], 'tile': row['tile'], 'pixel_id': key,
                'latitude': float(row['latitude']), 'longitude': float(row['longitude']), 'records': {}})
            day = dates.setdefault(row['observed_date'], utc(row['observed_date'] + 'T00:00:00Z'))
            published = availability.setdefault(row['available_at'], utc(row['available_at']))
            if published < day + timedelta(days=1):
                raise ValueError('Daily composite availability cannot precede its acquisition window end')
            record = Observation(day, published, label, int(row['fire_mask']), int(row['qa']), sys.intern(row['item_id']))
            conflict_key = key, day
            if conflict_key in conflicts:
                continue
            old = cell['records'].get(day)
            if old:
                if old['mask'] != record['mask'] or old['qa'] != record['qa']:
                    counts['conflicting_duplicate_pixel_days'] += 1
                    conflicts.add(conflict_key)
                    del cell['records'][day]
                    continue
                counts['identical_duplicate_pixel_days'] += 1
                record = min((old, record), key=lambda r: r['available_at'])
            cell['records'][day] = record
    for cell in cells.values():
        cell['records'] = sorted((r for r in cell['records'].values() if r['label'] is not None), key=lambda r: r['day'])
        for record in cell['records']:
            counts[f"unique_label_{record['label']}"] += 1
    return cells, dict(counts)


def inputs(history, issued_at, latitude, longitude, max_age=45):
    if len(history) < 4:
        return None
    recent = history[-4:][::-1]
    if any(r['available_at'] > issued_at or r['day'] + timedelta(days=1) > issued_at for r in recent):
        raise ValueError('Future daily pixel/publication cannot be an input')
    ages = [(issued_at - r['day'] - timedelta(days=1)).total_seconds() / 86400 for r in recent]
    if ages[0] > max_age:
        return None
    flags = [r['label'] for r in recent]
    angle = 2 * math.pi * issued_at.timetuple().tm_yday / 365.2425
    return dict(zip(FEATURES, [latitude, longitude, math.sin(angle), math.cos(angle), *flags,
        sum(flags) / len(flags), *ages, (recent[0]['day'] - recent[-1]['day']).days]))


def iter_examples(cells, plan, rejected=None):
    if rejected is None:
        rejected = Counter()
    for cell in cells.values():
        records = cell['records']
        events = sorted(records, key=lambda r: r['available_at'])
        ready, by_ready, pointer = [], {}, 0
        for target in records:
            issue = target['day']
            while pointer < len(events) and events[pointer]['available_at'] <= issue:
                event = events[pointer]
                insort(ready, event['day'])
                by_ready[event['day']] = event
                pointer += 1
            history = [by_ready[d] for d in ready[-4:]]
            x = inputs(history, issue, cell['latitude'], cell['longitude'], plan['maximum_latest_age_days'])
            if x is None:
                rejected['insufficient_or_stale_available_history'] += 1
                continue
            yield x | {'region': cell['region'], 'tile': cell['tile'], 'pixel_id': cell['pixel_id'],
                'issued_at': issue.isoformat(), 'target_at': (issue + timedelta(days=1)).isoformat(),
                'target_available_at': target['available_at'].isoformat(), 'observed': target['label'],
                'target_item_id': target['item_id'], 'input_item_ids': [r['item_id'] for r in history],
                'input_dates': [r['day'].isoformat() for r in history],
                'input_available_at': [r['available_at'].isoformat() for r in history]}


def examples(cells, plan):
    rejected = Counter()
    return list(iter_examples(cells, plan, rejected)), dict(rejected)


def partitions(frame, plan):
    import pandas as pd
    issue = pd.to_datetime(frame.issued_at, utc=True)
    target = pd.to_datetime(frame.target_at, utc=True)
    available = pd.to_datetime(frame.target_available_at, format='ISO8601', utc=True)
    fit_end, valid_end, test_end = [utc(plan[k]) for k in ('training_target_before', 'validation_target_before', 'test_target_before')]
    held = frame.tile.isin(plan['geographic_holdout_tiles'])
    return {'train': ~held & (target < fit_end) & (available < fit_end),
        'validation': ~held & (issue >= fit_end) & (target < valid_end) & (available < valid_end),
        'temporal_test': ~held & (issue >= valid_end) & (target < test_end),
        'geographic_test': held & (issue >= fit_end) & (target < test_end)}
