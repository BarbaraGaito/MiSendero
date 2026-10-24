#!/usr/bin/env python3
"""Summarize VIIRS pass coverage over trail routes on SNMF event-start days."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs/environmental-models-2026-10-22'
EVENTS = DOCS / 'fire-snmf-polyline-event-coverage-2025.json'
SCREEN_TEMPLATE = 'fire-viirs-efire-orbit-screen-{date}-15min.json'
OUT = DOCS / 'fire-viirs-snmf-event-route-pass-audit-2025.json'
FIRE_MASK_CODES = {'7', '8', '9'}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> None:
    event_audit = load_json(EVENTS)
    route_days: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for event in event_audit['events_within_50km']:
        if event['line_distance_km'] <= 20:
            route_days[(event['route_sector'], event['reported_start_date'])].append(event)

    mask_audits = {}
    mask_sources = []
    for path in sorted(DOCS.glob('fire-viirs-efire-route-mask-*.json')):
        data = load_json(path)
        filename = data.get('source', {}).get('efire_filename')
        if filename:
            mask_audits[filename] = (path, data)
            mask_sources.append({'path': str(path.relative_to(ROOT)), 'sha256': sha256(path)})

    results = []
    screen_sources = []
    for (route, day), incidents in sorted(route_days.items(), key=lambda item: (item[0][1], item[0][0])):
        screen_path = DOCS / SCREEN_TEMPLATE.format(date=day)
        if screen_path.exists():
            screen = load_json(screen_path)
            screen_sources.append({'path': str(screen_path.relative_to(ROOT)), 'sha256': sha256(screen_path)})
            screen_rows = screen['scans']
            route_candidates = [row for row in screen_rows
                                if route in row.get('candidate_routes_within_40km', [])]
            screen_status = {
                'expected_granules': len(screen_rows),
                'successfully_inspected_granules': sum(row.get('status') == 'ok' for row in screen_rows),
                'failed_or_missing_granules': sum(row.get('status') != 'ok' for row in screen_rows),
                'candidate_granules_with_coarse_sample_within_40km_of_route': len(route_candidates),
            }
        else:
            screen_rows = []
            route_candidates = []
            screen_status = {'status': 'screen_missing'}

        passes = []
        for candidate in route_candidates:
            filename = candidate['key'].rsplit('/', 1)[-1]
            audit_pair = mask_audits.get(filename)
            item = {
                'efire_filename': filename,
                'time_coverage_start_utc': candidate.get('time_coverage_start'),
                'minimum_distance_to_coarse_route_sample_km': candidate.get(
                    'minimum_distance_to_coarse_swath_sample_km', {}).get(route),
            }
            if audit_pair:
                audit_path, audit = audit_pair
                route_result = next(row for row in audit['per_route'] if row['route'] == route)
                counts = route_result['nearest_pixel_mask_and_dqf_counts']
                item.update({
                    'mask_audit_path': str(audit_path.relative_to(ROOT)),
                    'sampled_vertices': route_result['sampled_vertices'],
                    'vertices_resolved_to_swath_pixels': route_result['vertices_resolved_to_swath_pixels'],
                    'mask_and_dqf_counts': counts,
                    'fire_class_vertices': sum(counts.get(code, 0) for code in FIRE_MASK_CODES),
                    'clear_land_vertices': counts.get('5', 0),
                    'cloud_vertices': counts.get('4', 0),
                    'median_distance_to_nearest_pixel_km': route_result['median_nearest_pixel_distance_km'],
                })
            else:
                item['mask_status'] = 'candidate_not_refined_with_full_geolocation'
            passes.append(item)

        results.append({
            'route_sector': route,
            'reported_start_date': day,
            'minimum_snmf_incident_distance_to_route_km': min(row['line_distance_km'] for row in incidents),
            'incident_names': sorted({str(row.get('incident_name')) for row in incidents}),
            'screen': screen_status,
            'candidate_passes': passes,
            'interpretation': (
                'observed_viirs_fire_mask_on_route' if any(p.get('fire_class_vertices', 0) for p in passes)
                else 'candidate_passes_but_no_viirs_fire_class_on_route' if any('fire_class_vertices' in p for p in passes)
                else 'candidate_passes_unresolved' if passes
                else 'no_coarse_route_candidate_or_incomplete_screen_unknown'
            ),
        })

    complete_screens = [row for row in results
                        if row['screen'].get('expected_granules') == 288
                        and row['screen'].get('successfully_inspected_granules') == 288]
    event_days_with_candidate = [row for row in results if row['candidate_passes']]
    refined_passes = [p for row in results for p in row['candidate_passes'] if 'fire_class_vertices' in p]
    event_days_with_viirs_fire = [row for row in results
                                  if any(p.get('fire_class_vertices', 0) for p in row['candidate_passes'])]
    point_audits = []
    point_observations = []
    for path in sorted(DOCS.glob('fire-viirs-snmf-event-point-2025-*.json')):
        data = load_json(path)
        point_audits.append({'path': str(path.relative_to(ROOT)), 'sha256': sha256(path)})
        point_observations.extend(data['observations'])
    point_status_counts: dict[str, int] = defaultdict(int)
    for observation in point_observations:
        point_status_counts[observation['mask_status']] += 1
    result = {
        'experiment_id': 'viirs-efire-v1r3-snmf-route-line-event-pass-audit-2025',
        'purpose': 'Availability and active-fire-mask cross-check only; not a forecast evaluation.',
        'target': 'VIIRS E-FIRE fire-mask classes 7-9 at sampled points on reviewed trail polylines, on dates with an SNMF incident start within 20 km of the line.',
        'results_summary': {
            'snmf_route_start_days_within_20km_of_line': len(results),
            'days_with_complete_288_of_288_screen': len(complete_screens),
            'days_with_at_least_one_coarse_route_candidate': len(event_days_with_candidate),
            'fully_refined_candidate_passes': len(refined_passes),
            'days_with_viirs_fire_class_on_sampled_route_vertices': len(event_days_with_viirs_fire),
        },
        'snmf_event_coordinate_cross_check': {
            'granules_with_full_geolocation_audit': len(point_audits),
            'event_coordinate_pass_records': len(point_observations),
            'unique_route_date_incident_name_records': len({
                (row['route_sector'], row['reported_start_date'], row['incident_name'])
                for row in point_observations
            }),
            'unique_event_coordinates': len({
                (row.get('event_latitude'), row.get('event_longitude'))
                for row in point_observations if row.get('event_latitude') is not None
            }),
            'mask_status_counts': dict(sorted(point_status_counts.items())),
            'observations': point_observations,
            'audits': point_audits,
        },
        'event_route_days': results,
        'sources': {
            'snmf_route_polyline_event_audit': {
                'path': str(EVENTS.relative_to(ROOT)), 'sha256': sha256(EVENTS),
            },
            'overpass_screens': screen_sources,
            'full_geolocation_mask_audits': mask_sources,
            'full_geolocation_snmf_event_point_audits': point_audits,
        },
        'limitations': [
            'SNMF incident start dates are not exact ignition times, and the event inventory is not exhaustive.',
            'Events are selected at up to 20 km from a route line; many are not fires on the route itself.',
            'No coarse route candidate is not proof of no swath coverage; incomplete screens remain unknown.',
            'Clear land is an observed sensor classification, not proof that no fire occurred between satellite passes or below detection limits.',
            'Cloud, bowtie, invalid, and unresolved pixels are unknown, never negative labels.',
            'A VIIRS active-fire mask is a sensor detection target, not field-confirmed fire truth.',
            'This audit does not measure model precision, recall, probability calibration, lead time, or operational reliability.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(OUT.relative_to(ROOT)), 'results_summary': result['results_summary']}, indent=2))


if __name__ == '__main__':
    main()
