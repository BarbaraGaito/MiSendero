"""Descriptive statistics from original observed series; no generated samples."""
import json
from collections import Counter
from statistics import median

from environmental_sources import ROOT, STATIONS, fetch_station, observations


def main():
    summaries = []
    for station in STATIONS:
        payload, source = fetch_station(station)
        clean, excluded = observations(payload)
        intervals = [(b['observed_at'] - a['observed_at']).total_seconds() / 3600 for a, b in zip(clean, clean[1:])]
        delays = [(r['available_at'] - r['observed_at']).total_seconds() / 3600 for r in clean]
        levels = [r['level'] for r in clean]
        summaries.append({'series_id': station, 'station': payload['estacion']['nombre'],
            'coordinates': payload['estacion']['geom'], 'source_sha256': source['sha256'],
            'original_observations': len(payload['observaciones']), 'accepted_observations': len(clean),
            'excluded': excluded, 'first_observed_at': clean[0]['observed_at'].isoformat(),
            'last_observed_at': clean[-1]['observed_at'].isoformat(),
            'level_m': {'minimum': min(levels), 'median': median(levels), 'maximum': max(levels)},
            'observed_interval_hours': {'median': median(intervals), 'maximum': max(intervals),
                'most_common': [{'hours': h, 'count': n} for h, n in Counter(intervals).most_common(5)]},
            'final_update_delay_hours': {'median': median(delays), 'maximum': max(delays)}})
    destination = ROOT / 'docs/environmental-models-2026-10-22/river-data-summary.json'
    destination.write_text(json.dumps({'stations': summaries, 'caution': 'timeupdate is a final-version update timestamp, not a logged first-publication time.'},
        indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print('Described', sum(s['original_observations'] for s in summaries), 'real observations')


if __name__ == '__main__':
    main()
