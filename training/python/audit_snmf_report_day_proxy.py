"""Build route-day labels for SNMF-reported fire incidents.

The positive class includes incidents reported active/unresolved on the report
date and incidents whose reported start date is that day. A negative means
only that no such incident was listed near a route center in the available
daily report; it does not mean that no physical fire occurred.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from environmental_sources import PUBLIC, ROOT, sha256

DEFAULT_YEAR = 2024
GEOGRAPHY = PUBLIC / 'geography.json'
ACTIVE_STATUSES = {'ACTIVO', 'CONTROLADO', 'CONTENIDO', 'GUARDIA DE CENIZAS', 'UNKNOWN'}
RADII_KM = (10, 20)


def haversine_km(lat1, lon1, lat2, lon2):
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def main(year=DEFAULT_YEAR, reports_path=None, manifest_path=None, out_path=None):
    reports_path = reports_path or ROOT / f'docs/environmental-models-2026-10-22/snmf-{year}-daily-occurrence-events.json'
    manifest_path = manifest_path or PUBLIC / f'private/snmf-daily-occurrence-{year}/source-manifest.json'
    out_path = out_path or ROOT / f'docs/environmental-models-2026-10-22/snmf-{year}-route-day-report-proxy.json'
    reports = json.loads(reports_path.read_text(encoding='utf-8'))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    regions = json.loads(GEOGRAPHY.read_text(encoding='utf-8'))['fire_regions']
    report_dates = sorted(item['date'] for item in manifest['reports']
                          if item.get('status') in ('downloaded', 'cached'))
    report_date_set = set(report_dates)
    snapshots = [row for row in reports.get('snapshots', [])
                 if row.get('report_date') in report_date_set]
    rows = []
    positives = {str(radius): [] for radius in RADII_KM}
    positive_on_unreported_day = Counter()
    by_region = Counter()
    for region in regions:
        start_events = []
        for event in reports.get('deduplicated_events', []):
            lat, lon = event.get('latitude'), event.get('longitude')
            start_day = event.get('reported_start_date')
            if (not start_day or not start_day.startswith(f'{year}-')
                    or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))):
                continue
            distance = haversine_km(region['latitude'], region['longitude'], lat, lon)
            if distance <= max(RADII_KM):
                start_events.append({
                    'incident_name': event.get('incident_name'),
                    'province': event.get('province'),
                    'reported_start_date': start_day,
                    'status': event.get('status', 'UNKNOWN'),
                    'distance_km': round(distance, 3),
                    'source': 'deduplicated_incident_reported_start_date',
                })
        candidate_dates = sorted(report_date_set | {event['reported_start_date'] for event in start_events})
        for report_day in candidate_dates:
            starts_on_date = [event for event in start_events
                              if event['reported_start_date'] == report_day]
            if report_day not in report_date_set and not starts_on_date:
                continue
            nearby = []
            for event in snapshots:
                lat, lon = event.get('latitude'), event.get('longitude')
                status = event.get('status', 'UNKNOWN')
                started_today = event.get('reported_start_date') == report_day
                if (event.get('report_date') != report_day
                        or (status not in ACTIVE_STATUSES and not (status == 'EXTINGUIDO' and started_today))
                        or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))):
                    continue
                distance = haversine_km(region['latitude'], region['longitude'], lat, lon)
                if distance <= max(RADII_KM):
                    nearby.append({
                        'incident_name': event.get('incident_name'),
                        'province': event.get('province'),
                        'reported_start_date': event.get('reported_start_date'),
                        'status': status,
                        'distance_km': round(distance, 3),
                        'source': 'same_date_daily_report_snapshot',
                    })
            nearby.extend(event for event in starts_on_date
                          if not any(item.get('incident_name') == event['incident_name']
                              and item.get('province') == event['province'] for item in nearby))
            for radius in RADII_KM:
                matches = [event for event in nearby if event['distance_km'] <= radius]
                label = int(bool(matches))
                # A start date documented by a later report is a known positive.
                # Without a same-date PDF, its absence cannot create a negative.
                if report_day not in report_date_set and not label:
                    continue
                positives[str(radius)].append(label)
                if radius == RADII_KM[0] and label:
                    by_region[region['name']] += 1
                if label and report_day not in report_date_set:
                    positive_on_unreported_day[radius] += 1
                if radius == RADII_KM[0]:
                    rows.append({
                        'route_sector': region['name'],
                        'report_date': report_day,
                        'label': label,
                        'label_meaning': ('SNMF_reported_incident_start_or_active_unresolved_incident_within_10km'
                            if label else 'no_nearby_incident_listed_in_available_same_date_report'),
                        'nearby_incidents': [event for event in nearby if event['distance_km'] <= 10],
                    })

    period_start, period_end = (date.fromisoformat(value) for value in manifest['period'])
    calendar_days = (period_end - period_start).days
    counts = {}
    for radius in RADII_KM:
        labels = positives[str(radius)]
        counts[str(radius)] = {
            'route_days_with_known_status': len(labels),
            'route_days_with_nearby_incident_reported': sum(labels),
            'route_days_without_nearby_incident_reported': len(labels) - sum(labels),
            'unknown_route_days_without_a_daily_pdf': max(0, (calendar_days - len(report_dates)) * len(regions)
                - positive_on_unreported_day[radius]),
            'positive_route_days_documented_only_by_later_report': positive_on_unreported_day[radius],
        }

    result = {
        'experiment_id': f'snmf-reported-fire-route-day-proxy-{year}',
        'target': 'Whether an SNMF report documents an incident starting on that date (even if first published later), or lists an active/unresolved incident in an available report issued on that date, within a fixed radius of a route-sector center.',
        'source': 'Official Argentine SNMF daily occurrence reports, parsed from PDFs and joined to fixed route-sector centers.',
        'provenance': {
            'event_extraction_sha256': sha256(reports_path),
            'report_manifest_sha256': sha256(manifest_path),
            'geography_sha256': sha256(GEOGRAPHY),
            'period': manifest['period'],
            'report_dates_with_pdf': len(report_dates),
            'date_count': calendar_days,
            'route_sector_count': len(regions),
        },
        'spatial_protocol': {
            'distance': 'Haversine from fixed route-sector center to reported incident coordinate',
            'primary_radius_km': 10,
            'sensitivity_radius_km': 20,
            'active_statuses_included': sorted(ACTIVE_STATUSES),
            'reported_start_dates_are_used_retrospectively_even_if_first_listed_later': True,
        },
        'results': counts,
        'route_days': rows,
        'limitations': [
            'A label of 0 means no nearby incident was listed in an available report. It is not proof that no physical fire occurred.',
            'Dates without a PDF are unknown and are not included as negative examples.',
            'SNMF reports contain jurisdiction-reported incidents and may omit unreported events.',
            'Sector centers approximate trails; complete trail geometries were not used.',
            'Daily report time is not a precise ignition time, so this proxy cannot measure forecast lead from ignition.',
            'Repeated route-days from the same fire episode are correlated; episode-level grouping is required for confidence intervals.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': out_path.relative_to(ROOT).as_posix(),
        'primary_10km': counts['10'], 'sensitivity_20km': counts['20'],
        'route_days_positive_by_region': dict(by_region)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=DEFAULT_YEAR)
    parser.add_argument('--reports', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.year, args.reports, args.manifest, args.output)
