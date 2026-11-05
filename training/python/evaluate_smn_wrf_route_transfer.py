"""Test the frozen SMN WRF score on later MODIS labels along in-app routes.

The model and threshold come only from the original route-sector cohort. This
is a transfer test, not independent ground truth for ignition or safety.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.stats import beta

from environmental_sources import PUBLIC, ROOT, sha256

PRIVATE = PUBLIC / 'private'
DB = PRIVATE / 'smn-wrf-modis-evaluation.sqlite'
OBS = PRIVATE / 'argentina-trail-modis-labels' / 'observations.csv.gz'
WEATHER = PRIVATE / 'smn-wrf-argentina-routes-weather'
REPORT = ROOT / 'docs/environmental-models-2026-10-22/fire-smn-wrf-route-transfer-evaluation.json'
FEATURES = ['latitude', 'longitude', 'day_sin', 'day_cos', 'Tmax', 'Tmin', 'T2', 'HR2', 'wind10_ms', 'precip_27h_mm']
LEGACY_ROUTE_IDS = {'macuco', 'frey', 'condorito', 'ventana', 'bosqueTallado',
                    'mburucuya-che-roga', 'mburucuya-tape-pora', 'el-rey-la-chuna',
                    'el-rey-laguna-patitos', 'namuncura', 'condorito-secretos-pies'}


def season(day):
    parsed = datetime.strptime(day, '%Y-%m-%d')
    angle = 2 * math.pi * parsed.timetuple().tm_yday / 365.2425
    return math.sin(angle), math.cos(angle)


def exact_interval(tp, fp):
    if tp + fp == 0:
        return None
    return [float(beta.ppf(.025, tp, fp + 1)) if tp else 0.0,
            float(beta.ppf(.975, tp + 1, fp)) if fp else 1.0]


def metrics(y, score, threshold=None):
    y, score = np.asarray(y, dtype=np.uint8), np.asarray(score, dtype=np.float64)
    positives = int(y.sum())
    order = np.argsort(-score, kind='stable')
    sy = y[order]
    ap = float(((np.cumsum(sy) / np.arange(1, len(y) + 1)) * sy).sum() / positives) if positives else None
    out = {'observations': int(len(y)), 'positives': positives,
           'prevalence': float(y.mean()) if len(y) else None,
           'average_precision': ap, 'prevalence_baseline_ap': float(y.mean()) if len(y) else None}
    if threshold is not None:
        predicted = score >= threshold
        tp = int(np.sum(predicted & (y == 1))); fp = int(np.sum(predicted & (y == 0)))
        fn = positives - tp
        out['at_frozen_threshold'] = {'threshold': float(threshold), 'tp': tp, 'fp': fp, 'fn': fn,
            'alerts': tp + fp, 'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / positives if positives else None,
            'precision_exact_95pct': exact_interval(tp, fp)}
    return out


def grouped_route_days(rows, scores, allowed_routes=None):
    groups = {}
    for row, score in zip(rows, scores):
        day, label, route_ids = row[0], row[1], row[2]
        for route in route_ids.split('|'):
            if allowed_routes is not None and route not in allowed_routes:
                continue
            key = (day, route)
            value = groups.setdefault(key, [0, 0.0])
            value[0] = max(value[0], int(label))
            value[1] = max(value[1], float(score))
    keys = sorted(groups)
    return keys, np.asarray([groups[k][0] for k in keys], dtype=np.uint8), \
           np.asarray([groups[k][1] for k in keys], dtype=np.float64)


def choose_threshold(y, score):
    choices = []
    for threshold in np.unique(score):
        predicted = score >= threshold
        alerts = int(predicted.sum()); tp = int(np.sum(predicted & (y == 1)))
        if alerts >= 5 and tp / alerts >= .90:
            choices.append((tp / int(y.sum()), tp / alerts, -alerts, float(threshold), alerts, tp))
    if not choices:
        return None
    recall, precision, _, threshold, alerts, tp = max(choices)
    return {'threshold': threshold, 'alerts': alerts, 'tp': tp, 'precision': precision,
            'recall': recall, 'precision_exact_95pct': exact_interval(tp, alerts - tp)}


def best_precision_threshold(y, score, minimum_alerts=5):
    choices = []
    for threshold in np.unique(score):
        predicted = score >= threshold
        alerts = int(predicted.sum())
        if alerts < minimum_alerts:
            continue
        tp = int(np.sum(predicted & (y == 1)))
        choices.append((tp / alerts, tp / int(y.sum()) if y.sum() else 0,
                        -alerts, float(threshold), alerts, tp))
    if not choices:
        return None
    precision, recall, _, threshold, alerts, tp = max(choices)
    return {'threshold': threshold, 'alerts': alerts, 'tp': tp, 'precision': precision,
            'recall': recall, 'precision_exact_95pct': exact_interval(tp, alerts - tp)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DB)
    parser.add_argument('--observations', type=Path, default=OBS)
    parser.add_argument('--weather-dir', type=Path, default=WEATHER)
    parser.add_argument('--output', type=Path, default=REPORT)
    args = parser.parse_args()
    db = sqlite3.connect(args.database)
    # Refit the previously frozen feature/model objective. Only the base
    # cohort's 2022 rows train; its 2023 H1 data select the threshold.
    def base_partition(start, end):
        query = '''SELECT day,latitude,longitude,label,Tmax,Tmin,T2,HR2,wind10_ms,precip_27h_mm
                   FROM examples WHERE tile!='h12v13' AND day>=? AND day<?
                     AND grid_distance_km<=5 ORDER BY day,pixel_id'''
        rows = db.execute(query, (start, end)).fetchall()
        X = []
        for row in rows:
            ds, dc = season(row[0])
            X.append([row[1], row[2], ds, dc, *row[4:]])
        return np.asarray(X, dtype=np.float64), np.asarray([r[3] for r in rows], dtype=np.uint8), rows

    train_x, train_y, train_rows = base_partition('0000-01-01', '2023-01-01')
    valid_x, valid_y, valid_rows = base_partition('2023-01-01', '2023-07-01')
    if not train_y.sum() or not valid_y.sum():
        raise ValueError('Frozen base cohort lacks positive train or validation labels')
    mean, scale = train_x.mean(axis=0), train_x.std(axis=0)
    scale[scale == 0] = 1
    train_x, valid_x = (train_x - mean) / scale, (valid_x - mean) / scale
    pos_w = len(train_y) / (2 * int(train_y.sum()))
    neg_w = len(train_y) / (2 * int(len(train_y) - train_y.sum()))
    weights = np.where(train_y == 1, pos_w, neg_w)

    def objective(parameters):
        logits = np.clip(train_x @ parameters[1:] + parameters[0], -40, 40)
        loss = np.sum(weights * (np.logaddexp(0, logits) - train_y * logits))
        residual = weights * (1 / (1 + np.exp(-logits)) - train_y)
        gradient = np.r_[residual.sum(), train_x.T @ residual] + np.r_[0., parameters[1:]]
        return loss + .5 * np.sum(parameters[1:] ** 2), gradient
    fit = minimize(objective, np.zeros(train_x.shape[1] + 1), jac=True, method='L-BFGS-B',
                   options={'maxiter': 500, 'ftol': 1e-10})
    if not fit.success and fit.status != 1:
        raise RuntimeError(f'Logistic fit failed: {fit.message}')
    def score(X):
        z = np.clip(X @ fit.x[1:] + fit.x[0], -40, 40)
        return 1 / (1 + np.exp(-z))
    # The original validation-only best-precision operating point is frozen,
    # although it missed the requested 90% precision target by a wide margin.
    base_report = json.loads((REPORT.parent / 'fire-smn-wrf-modis-evaluation.json').read_text(encoding='utf-8'))
    base_operating_point = base_report['validation_best_precision_with_at_least_5_region_day_alerts']
    frozen_threshold = base_operating_point['threshold'] if base_operating_point else None
    if frozen_threshold is None:
        raise ValueError('Frozen original validation operating point is missing')

    mapping = json.loads((args.weather_dir / 'mapping-manifest.json').read_text(encoding='utf-8'))
    obs_manifest = json.loads((args.observations.parent / 'manifest.json').read_text(encoding='utf-8'))
    if mapping['observation_sha256'] != sha256(args.observations):
        raise ValueError('Weather mapping does not match the current route label cohort')
    evaluation_dates = {record['date'] for record in mapping['files'] if record['date'] >= '2023-01-01'}
    labels = defaultdict(dict)
    with gzip.open(args.observations, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            day = row['observed_date']
            if day not in evaluation_dates or int(row['qa']) & 3 != 2:
                continue
            mask = int(row['fire_mask'])
            if mask not in (5, 8, 9):
                continue
            pixel_id = f"{row['tile']}:{row['row']}:{row['col']}"
            labels[day][pixel_id] = (int(mask in (8, 9)), row['route_ids'],
                                     float(row['latitude']), float(row['longitude']))

    partitions = {'validation': [[], [], [], []], 'test': [[], [], [], []]}
    days_loaded = defaultdict(int)
    for day in sorted(evaluation_dates):
        part_name = 'validation' if day < '2023-07-01' else 'test'
        part_rows, part_X, part_y, part_tiles = partitions[part_name]
        path = args.weather_dir / f'{day}.csv.gz'
        if not path.is_file():
            continue
        day_rows = []
        with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
            for weather in csv.DictReader(stream):
                item = labels.get(day, {}).get(weather['pixel_id'])
                if item is None:
                    continue
                label, route_ids, lat, lon = item
                if float(weather['grid_distance_km']) > 5:
                    continue
                names = ['Tmax','Tmin','T2','HR2','magViento10','PP']
                if any(weather.get(k) in ('', None) for k in names):
                    continue
                ds, dc = season(day)
                x = [lat,lon,ds,dc,float(weather['Tmax']),float(weather['Tmin']),
                     float(weather['T2']),float(weather['HR2']),float(weather['magViento10']),float(weather['PP'])]
                tile = weather['pixel_id'].split(':')[0]
                day_rows.append(((day, label, route_ids, weather['pixel_id']), x, label, tile))
        if day_rows:
            days_loaded[part_name] += 1
            for row, x, label, tile in day_rows:
                part_rows.append(row); part_X.append(x); part_y.append(label); part_tiles.append(tile)
    valid_rows, valid_X, valid_y, _valid_tiles = partitions['validation']
    test_rows, test_X, test_y, test_tiles = partitions['test']
    valid_scores = score((np.asarray(valid_X, dtype=np.float64) - mean) / scale)
    valid_keys, valid_route_y, valid_route_score = grouped_route_days(valid_rows, valid_scores)
    route_threshold = choose_threshold(valid_route_y, valid_route_score)
    validation_best = best_precision_threshold(valid_route_y, valid_route_score)
    all_route_ids = set(obs_manifest['routes'])
    novel_route_ids = all_route_ids - LEGACY_ROUTE_IDS
    valid_novel_keys, valid_novel_y, valid_novel_score = grouped_route_days(
        valid_rows, valid_scores, novel_route_ids)
    novel_route_threshold = choose_threshold(valid_novel_y, valid_novel_score)
    novel_validation_best = best_precision_threshold(valid_novel_y, valid_novel_score)
    if not test_rows:
        raise ValueError('No external route test rows were joined')
    test_scores = score((np.asarray(test_X, dtype=np.float64) - mean) / scale)

    keys, route_y, route_score = grouped_route_days(test_rows, test_scores)
    test_at_route_threshold = metrics(route_y, route_score, route_threshold['threshold']) if route_threshold else None
    test_at_validation_best = metrics(route_y, route_score, validation_best['threshold']) if validation_best else None
    novel_keys, novel_test_y, novel_test_score = grouped_route_days(test_rows, test_scores, novel_route_ids)
    test_at_novel_threshold = metrics(novel_test_y, novel_test_score, novel_route_threshold['threshold']) if novel_route_threshold else None
    test_at_novel_validation_best = metrics(novel_test_y, novel_test_score, novel_validation_best['threshold']) if novel_validation_best else None
    by_tile = {}
    for tile in sorted(set(test_tiles)):
        indexes = [i for i, value in enumerate(test_tiles) if value == tile]
        tile_rows = [test_rows[i] for i in indexes]
        tile_scores = test_scores[indexes]
        _, ty, ts = grouped_route_days(tile_rows, tile_scores)
        by_tile[tile] = metrics(ty, ts, frozen_threshold)
    result = {'experiment_id': 'smn-wrf-base-model-external-route-transfer-test-2023h2',
        'candidate_status': 'not_reliable',
        'conclusion': 'No route-day threshold reached 90% precision in validation; the novel-route subset had no positive MODIS route-days in validation or test. This cohort cannot support a reliable wildfire prediction claim.',
        'source': 'Frozen 2022 train / 2023 H1 validation model and threshold transferred to MODIS labels along catalog routes.',
        'protocol': {'base_training_period': '<2023-01-01', 'threshold_selection_period': '2023-01-01 to 2023-06-30',
            'external_route_test_period': '2023-07-01 to 2023-12-31',
            'frozen_threshold': frozen_threshold,
            'base_validation_precision_at_threshold': base_operating_point['precision'],
            'base_validation_alerts': base_operating_point['alerts'],
            'target_validation_precision': .90,
            'forecast_lead_hours': 27,
            'target': 'MOD14A1 nominal/high-confidence fire detection, not ignition.',
            'route_day': 'Positive if any valid MODIS pixel in an 11x11 route window is positive; score is maximum pixel score.'},
        'validation': {'weather_days': days_loaded['validation'],
            'pixel_day': metrics([row[1] for row in valid_rows], valid_scores),
            'route_day': metrics(valid_route_y, valid_route_score),
            'route_day_unique_positive_dates': len({day for (day, _route), label in zip(valid_keys, valid_route_y) if label}),
            'route_day_unique_positive_routes': len({route for (_day, route), label in zip(valid_keys, valid_route_y) if label}),
            'threshold_meeting_90pct_target': route_threshold,
            'best_precision_at_least_5_alerts': validation_best,
            'novel_routes': {'route_ids': sorted(novel_route_ids),
                'route_day': metrics(valid_novel_y, valid_novel_score),
                'unique_positive_dates': len({day for (day, _route), label in zip(valid_novel_keys, valid_novel_y) if label}),
                'unique_positive_routes': len({route for (_day, route), label in zip(valid_novel_keys, valid_novel_y) if label}),
                'threshold_meeting_90pct_target': novel_route_threshold,
                'best_precision_at_least_5_alerts': novel_validation_best}},
        'counts': {'catalog_routes_with_MODIS_coverage': len(obs_manifest['routes']),
            'catalog_routes_excluded_for_missing_tiles': len(obs_manifest['excluded_routes']),
            'catalog_routes_in_base_study_geography': len(all_route_ids & LEGACY_ROUTE_IDS),
            'catalog_routes_outside_base_study_geography': len(novel_route_ids),
            'route_validation_weather_days': days_loaded['validation'],
            'route_test_weather_days': days_loaded['test'], 'route_test_pixel_days': len(test_rows),
            'route_test_positive_pixel_days': int(sum(test_y)),
            'route_test_positive_dates': len({row[0][0] for row in test_rows if row[2]}),
            'route_test_positive_route_days': int(route_y.sum()),
            'route_test_unique_positive_routes': len({route for (day, route), label in zip(keys, route_y) if label}),
            'novel_route_test_positive_route_days': int(novel_test_y.sum()),
            'novel_route_test_positive_dates': len({day for (day, _route), label in zip(novel_keys, novel_test_y) if label})},
        'test': {'pixel_day': metrics(test_y, test_scores, frozen_threshold),
                 'pixel_day_at_route_validation_best_precision':
                    metrics(test_y, test_scores, validation_best['threshold']) if validation_best else None,
                 'route_day': metrics(route_y, route_score, frozen_threshold),
                 'route_day_at_validation_threshold': test_at_route_threshold,
                 'route_day_at_validation_best_precision': test_at_validation_best,
                 'novel_routes': {'route_day': metrics(novel_test_y, novel_test_score, frozen_threshold),
                    'route_day_at_validation_threshold': test_at_novel_threshold,
                    'route_day_at_validation_best_precision': test_at_novel_validation_best},
                 'route_day_by_MODIS_tile': by_tile},
        'cohort': {'routes': len(obs_manifest['routes']), 'route_pixels': obs_manifest['counts']['unique_MODIS_pixels'],
            'weather_mapped_pixels': mapping['mapping']['mapped_pixels'],
            'MODIS_target_dates': mapping['counts']['observation_dates'],
            'weather_dates_mapped': mapping['counts']['weather_days_mapped'],
            'MODIS_dates_without_weather': mapping['counts']['observation_dates_without_weather'],
            'weather_mapping_distance_limit_km': mapping['mapping']['maximum_distance_km']},
        'limitations': ['Only later satellite labels test transfer; independent physical fire confirmations are unavailable.',
            'The frozen threshold had only 4.24% precision in validation and did not meet the predeclared 90% target.',
            'The all-route test includes legacy route sectors represented in base training; the outside-base route subset is reported separately.',
            'The 2023 H2 test includes only a few positive MODIS dates and correlated neighboring pixels.',
            'Route-day precision intervals are descriptive binomial intervals; nearby routes/dates may share one wildfire.',
            'The frozen score is not a calibrated probability and cannot support an app fire-safety recommendation.'],
        'source_hashes': {'route_observations': sha256(args.observations),
            'weather_mapping_manifest': sha256(args.weather_dir / 'mapping-manifest.json'),
            'base_database': sha256(args.database)}, 'synthetic_observations': 0, 'deployment_approved': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'report': args.output.relative_to(ROOT).as_posix(), 'counts': result['counts'],
                      'test': result['test']}, ensure_ascii=False, indent=2), flush=True)
    db.close()


if __name__ == '__main__':
    main()
