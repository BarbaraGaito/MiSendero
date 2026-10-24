"""Evaluate whether pre-issued WRF weather improves next-day MODIS fire ranking.

The label remains a qualified satellite active-fire pixel observation. Scores
are exploratory ranking scores, not calibrated probabilities of ignition.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from environmental_sources import PUBLIC, ROOT

PRIVATE = PUBLIC / 'private'
OBSERVATIONS = PRIVATE / 'fire-observations.csv.gz'
WEATHER_DIR = PRIVATE / 'smn-wrf-modis-weather'
REPORT_DIR = ROOT / 'docs/environmental-models-2026-10-22'
FEATURES = ['latitude', 'longitude', 'day_sin', 'day_cos', 'Tmax', 'Tmin',
            'T2', 'HR2', 'wind10_ms', 'precip_27h_mm']


def dependencies():
    import numpy as np
    from scipy.optimize import minimize
    return np, minimize


def valid_label(mask: int, qa: int):
    if qa & 3 != 2:
        return None
    if mask == 5:
        return 0
    if mask in (8, 9):
        return 1
    return None


def season(day: str):
    parsed = datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    angle = 2 * math.pi * parsed.timetuple().tm_yday / 365.2425
    return math.sin(angle), math.cos(angle)


def make_database(path: Path):
    if path.exists():
        path.unlink()
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=OFF')
    db.execute('PRAGMA synchronous=OFF')
    db.execute('PRAGMA temp_store=MEMORY')
    db.execute('''CREATE TABLE labels (
        day TEXT NOT NULL, pixel_id TEXT NOT NULL, region TEXT NOT NULL, tile TEXT NOT NULL,
        latitude REAL NOT NULL, longitude REAL NOT NULL, mask INTEGER NOT NULL, qa INTEGER NOT NULL,
        label INTEGER NOT NULL, conflict INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(day,pixel_id))''')
    db.execute('''CREATE TABLE weather (
        day TEXT NOT NULL, pixel_id TEXT NOT NULL, Tmax REAL, Tmin REAL, T2 REAL, HR2 REAL,
        wind10_ms REAL, precip_27h_mm REAL, grid_distance_km REAL,
        PRIMARY KEY(day,pixel_id))''')
    db.execute('CREATE INDEX labels_day ON labels(day)')
    db.execute('CREATE INDEX weather_day ON weather(day)')

    source_counts = Counter()
    pending = []
    with gzip.open(OBSERVATIONS, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            source_counts['rows'] += 1
            label = valid_label(int(row['fire_mask']), int(row['qa']))
            if label is None:
                continue
            pixel_id = f"{row['tile']}:{row['row']}:{row['col']}"
            pending.append((row['observed_date'], pixel_id, row['region'], row['tile'],
                            float(row['latitude']), float(row['longitude']),
                            int(row['fire_mask']), int(row['qa']), label))
            if len(pending) >= 50_000:
                for record in pending:
                    old = db.execute('SELECT mask,qa FROM labels WHERE day=? AND pixel_id=?', record[:2]).fetchone()
                    if old is None:
                        db.execute('INSERT INTO labels(day,pixel_id,region,tile,latitude,longitude,mask,qa,label) VALUES(?,?,?,?,?,?,?,?,?)', record)
                    elif old != record[6:8]:
                        db.execute('UPDATE labels SET conflict=1 WHERE day=? AND pixel_id=?', record[:2])
                        source_counts['conflicting_duplicates'] += 1
                    else:
                        source_counts['identical_duplicates'] += 1
                db.commit()
                pending.clear()
    for record in pending:
        old = db.execute('SELECT mask,qa FROM labels WHERE day=? AND pixel_id=?', record[:2]).fetchone()
        if old is None:
            db.execute('INSERT INTO labels(day,pixel_id,region,tile,latitude,longitude,mask,qa,label) VALUES(?,?,?,?,?,?,?,?,?)', record)
        elif old != record[6:8]:
            db.execute('UPDATE labels SET conflict=1 WHERE day=? AND pixel_id=?', record[:2])
            source_counts['conflicting_duplicates'] += 1
        else:
            source_counts['identical_duplicates'] += 1
    db.commit()

    files_loaded = 0
    weather_rows = 0
    missing_weather = []
    for file in sorted(WEATHER_DIR.glob('????-??-??.csv.gz')):
        day = file.name[:10]
        rows = []
        with gzip.open(file, 'rt', encoding='utf-8', newline='') as stream:
            for row in csv.DictReader(stream):
                def num(key):
                    return float(row[key]) if row.get(key) else None
                rows.append((day, row['pixel_id'], num('Tmax'), num('Tmin'), num('T2'), num('HR2'),
                             num('magViento10'), num('PP'), num('grid_distance_km')))
        db.executemany('INSERT OR REPLACE INTO weather VALUES(?,?,?,?,?,?,?,?,?)', rows)
        db.commit()
        files_loaded += 1
        weather_rows += len(rows)
    # Only examples with a valid target label and a fully observed feature vector enter metrics.
    db.execute('''CREATE TABLE examples AS
        SELECT l.day,l.pixel_id,l.region,l.tile,l.latitude,l.longitude,l.label,
               w.Tmax,w.Tmin,w.T2,w.HR2,w.wind10_ms,w.precip_27h_mm,w.grid_distance_km
        FROM labels l JOIN weather w ON l.day=w.day AND l.pixel_id=w.pixel_id
        WHERE l.conflict=0 AND w.Tmax IS NOT NULL AND w.Tmin IS NOT NULL
          AND w.T2 IS NOT NULL AND w.HR2 IS NOT NULL AND w.wind10_ms IS NOT NULL
          AND w.precip_27h_mm IS NOT NULL AND w.grid_distance_km<=5''')
    db.execute('CREATE INDEX examples_day ON examples(day)')
    db.commit()
    joined = db.execute('SELECT COUNT(*),SUM(label),COUNT(DISTINCT day) FROM examples').fetchone()
    return db, {'source_rows': source_counts['rows'], 'identical_duplicates': source_counts['identical_duplicates'],
                'conflicting_duplicates': source_counts['conflicting_duplicates'],
                'weather_files': files_loaded, 'weather_rows': weather_rows,
                'joined_valid_pixel_days': joined[0], 'joined_positive_pixel_days': joined[1] or 0,
                'joined_target_dates': joined[2], 'missing_weather_reports': missing_weather}


def load_partition(db, start: str | None, end: str, np):
    where = 'day < ?'
    args = [end]
    if start:
        where = 'day >= ? AND day < ?'
        args = [start, end]
    query = f'''SELECT day,pixel_id,region,tile,label,latitude,longitude,Tmax,Tmin,T2,HR2,
                       wind10_ms,precip_27h_mm,grid_distance_km
                FROM examples WHERE {where} AND tile!='h12v13' ORDER BY day,pixel_id'''
    rows = db.execute(query, args).fetchall()
    if not rows:
        raise ValueError(f'No joined records for target period {start} .. {end}')
    features, labels = [], []
    for row in rows:
        day, pixel_id, region, tile, label, lat, lon, tmax, tmin, t2, rh, wind, rain, distance = row
        ds, dc = season(day)
        features.append([lat, lon, ds, dc, tmax, tmin, t2, rh, wind, rain])
        labels.append(label)
    return {'rows': rows, 'X': np.asarray(features, dtype='float64'), 'y': np.asarray(labels, dtype='int8')}


def average_precision(y, scores):
    import numpy as np
    order = np.argsort(-scores, kind='stable')
    sorted_y = y[order]
    positives = int(sorted_y.sum())
    if positives == 0:
        return None
    cumulative = np.cumsum(sorted_y)
    ranks = np.arange(1, len(y) + 1)
    precision_at_rank = cumulative / ranks
    return float((precision_at_rank * sorted_y).sum() / positives)


def classification(y, scores, threshold):
    import numpy as np
    from scipy.stats import beta
    predicted = scores >= threshold
    tp = int(np.sum(predicted & (y == 1)))
    fp = int(np.sum(predicted & (y == 0)))
    fn = int(np.sum(~predicted & (y == 1)))
    tn = int(np.sum(~predicted & (y == 0)))
    alerts = tp + fp
    interval = None
    if alerts:
        interval = [float(beta.ppf(.025, tp, fp + 1)) if tp else 0.0,
                    float(beta.ppf(.975, tp + 1, fp)) if fp else 1.0]
    return {'threshold': float(threshold), 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'alerts': alerts, 'precision_exact_95pct': interval}


def select_threshold(y, scores):
    import numpy as np
    order = np.argsort(-scores, kind='stable')
    sorted_scores, sorted_y = scores[order], y[order]
    cumulative_tp = np.cumsum(sorted_y)
    ranks = np.arange(1, len(y) + 1)
    ends = np.r_[np.flatnonzero(sorted_scores[:-1] != sorted_scores[1:]), len(y) - 1]
    alert_counts = ends + 1
    tp_counts = cumulative_tp[ends]
    eligible = (alert_counts >= 5) & (tp_counts > 0) & (tp_counts / alert_counts >= .90)
    positions = np.flatnonzero(eligible)
    if not len(positions):
        return None
    # Max recall means retain the greatest number of validation alerts while
    # satisfying the precision target. Collapse ties at the chosen score.
    position = int(positions[-1])
    threshold = float(sorted_scores[ends[position]])
    return classification(y, scores, threshold) | {'average_precision': average_precision(y, scores)}


def best_precision_with_minimum_alerts(y, scores, minimum=5):
    import numpy as np
    thresholds = np.unique(scores)
    eligible = [classification(y, scores, float(threshold)) for threshold in thresholds]
    eligible = [row for row in eligible if row['alerts'] >= minimum]
    if not eligible:
        return None
    return max(eligible, key=lambda row: (row['precision'] or 0, row['recall'] or 0, -row['alerts']))


def region_day_rows(part, scores, np):
    groups = {}
    for row, score in zip(part['rows'], scores):
        key = (row[0], row[2])
        previous = groups.get(key)
        if previous is None:
            groups[key] = [int(row[4]), float(score)]
        else:
            previous[0] = max(previous[0], int(row[4]))
            previous[1] = max(previous[1], float(score))
    ordered = sorted(groups.items())
    labels = np.asarray([value[0] for _, value in ordered], dtype='int8')
    group_scores = np.asarray([value[1] for _, value in ordered], dtype='float64')
    return labels, group_scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rebuild-database', action='store_true')
    args = parser.parse_args()
    np, minimize = dependencies()
    db_path = PRIVATE / 'smn-wrf-modis-evaluation.sqlite'
    if args.rebuild_database or not db_path.exists():
        db, counts = make_database(db_path)
    else:
        db = sqlite3.connect(db_path)
        counts = {'database_reused': True}

    train = load_partition(db, None, '2023-01-01', np)
    valid = load_partition(db, '2023-01-01', '2023-07-01', np)
    test = load_partition(db, '2023-07-01', '2024-01-01', np)
    mean, scale = train['X'].mean(axis=0), train['X'].std(axis=0)
    scale[scale == 0] = 1
    x_train = (train['X'] - mean) / scale
    x_valid = (valid['X'] - mean) / scale
    x_test = (test['X'] - mean) / scale
    y_train, y_valid, y_test = train['y'], valid['y'], test['y']
    if min(int(y_train.sum()), int(y_valid.sum()), int(y_test.sum())) < 5:
        raise SystemExit('Insufficient positive labels for the frozen train/validation/test protocol')

    pos_weight = len(y_train) / (2 * int(y_train.sum()))
    neg_weight = len(y_train) / (2 * (len(y_train) - int(y_train.sum())))
    sample_weights = np.where(y_train == 1, pos_weight, neg_weight)

    def objective(beta):
        logits = np.clip(x_train @ beta[1:] + beta[0], -40, 40)
        loss = np.sum(sample_weights * (np.logaddexp(0, logits) - y_train * logits))
        regularization = .5 * np.sum(beta[1:] ** 2)
        residual = sample_weights * (1 / (1 + np.exp(-logits)) - y_train)
        gradient = np.r_[residual.sum(), x_train.T @ residual] + np.r_[0., beta[1:]]
        return loss + regularization, gradient

    fit = minimize(objective, np.zeros(x_train.shape[1] + 1), jac=True, method='L-BFGS-B',
                   options={'maxiter': 500, 'ftol': 1e-10})
    if not fit.success and fit.status != 1:
        raise RuntimeError(f'Logistic fit failed: {fit.message}')

    def score(x):
        logits = np.clip(x @ fit.x[1:] + fit.x[0], -40, 40)
        return 1 / (1 + np.exp(-logits))

    valid_score, test_score = score(x_valid), score(x_test)
    valid_region_y, valid_region_score = region_day_rows(valid, valid_score, np)
    test_region_y, test_region_score = region_day_rows(test, test_score, np)
    threshold = select_threshold(valid_region_y, valid_region_score)
    chosen = threshold['threshold'] if threshold else None

    def summary(part, scores):
        y = part['y']
        group_y, group_score = region_day_rows(part, scores, np)
        return {'rows': len(y), 'positive_pixel_days': int(y.sum()),
                'positive_fraction': float(y.mean()), 'average_precision': average_precision(y, scores),
                'prevalence_baseline_ap': float(y.mean()),
                'metrics_at_validation_threshold': classification(y, scores, chosen) if chosen is not None else None,
                'metrics_at_score_0_5': classification(y, scores, .5),
                'region_day_groups': len(group_y), 'positive_region_day_groups': int(group_y.sum()),
                'region_day_average_precision': average_precision(group_y, group_score),
                'region_day_prevalence_baseline_ap': float(group_y.mean()),
                'region_day_metrics_at_validation_threshold': classification(group_y, group_score, chosen) if chosen is not None else None,
                'region_day_metrics_at_score_0_5': classification(group_y, group_score, .5),
                'best_region_day_precision_with_at_least_5_alerts': best_precision_with_minimum_alerts(group_y, group_score, 5)}

    scores_by_id = {}
    for row, value in zip(test['rows'], test_score):
        scores_by_id[(row[0], row[1])] = float(value)
    out_path = PRIVATE / 'smn-wrf-modis-test-predictions.csv.gz'
    with gzip.open(out_path, 'wt', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['target_date', 'pixel_id', 'region', 'label', 'risk_score'])
        for row, value in zip(test['rows'], test_score):
            writer.writerow([row[0], row[1], row[2], row[4], f'{value:.10g}'])

    report = {
        'experiment_id': 'smn-wrf-weather-only-vs-modis-next-day-fire-2022-2023',
        'source': 'SMN WRF-DET hourly and daily archives, joined to existing NASA MOD14A1.061 qualified target labels',
        'protocol': {'train_target_before': '2023-01-01', 'validation_target_period': '[2023-01-01,2023-07-01)',
                     'test_target_period': '[2023-07-01,2024-01-01)', 'geographic_holdout_tile': 'h12v13 excluded',
                     'forecast_issue': '12 UTC on the previous calendar day',
                     'valid_time': '15 UTC on the MODIS target date', 'lead_hours': 27,
                     'target': 'same MODIS pixel nominal/high-confidence active-fire label on target date',
                     'features': FEATURES, 'model': 'class-weighted L2 logistic regression; no feature or threshold tuning',
                     'threshold_selection': 'validation precision >= 0.90 and at least 5 validation alerts; maximize recall',
                     'meaning': 'ranking of satellite fire-mask labels, not ignition probability or trail safety'},
        'data_counts': counts,
        'partitions': {'train': {'rows': len(y_train), 'positive_pixel_days': int(y_train.sum())},
                       'validation': summary(valid, valid_score), 'test': summary(test, test_score)},
        'validation_threshold_region_day': threshold,
        'validation_best_precision_with_at_least_5_region_day_alerts':
            best_precision_with_minimum_alerts(valid_region_y, valid_region_score, 5),
        'frozen_research_model_parameters': {
            'features': FEATURES,
            'standardization_mean': [float(value) for value in mean],
            'standardization_scale': [float(value) for value in scale],
            'intercept': float(fit.x[0]),
            'standardized_coefficients': [float(value) for value in fit.x[1:]],
            'purpose': 'Reproducible scoring of prespecified external event days; not an app artifact.'},
        'standardized_coefficients': {name: float(value) for name, value in zip(FEATURES, fit.x[1:])},
        'fit_converged': bool(fit.success), 'fit_message': str(fit.message),
        'test_predictions': str(out_path.relative_to(ROOT)),
        'synthetic_observations': 0, 'deployment_approved': False,
        'limitations': ['MODIS labels are satellite active-fire observations, not exact ignition times.',
                        'Pixel-day metrics are spatially and temporally correlated.',
                        'Only fixed sampled regions are represented; no calibrated probability is produced.',
                        'A small positive validation/test cohort cannot support a high-confidence accuracy claim.']}
    report_path = REPORT_DIR / 'fire-smn-wrf-modis-evaluation.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(report_path), 'counts': counts,
                      'train': report['partitions']['train'],
                      'validation': report['partitions']['validation'],
                      'test': report['partitions']['test'],
                      'threshold_region_day': threshold, 'fit_converged': fit.success}, indent=2))
    db.close()


if __name__ == '__main__':
    main()
