"""Exploratory UCD raw-window benchmark, with complete people held out.

Original F/NF protocol conditions are not continuous fatigue assessments.
Clock windows assume the exported calibrated Shimmer Timestamp is in ms.
No resampling, interpolation, synthetic labels, app integration or deployment.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import urllib.request

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier

from evaluate_ucd_running import feature_matrix, metrics as base_metrics

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'training/data/raw/ucd-running/raw'
OUTPUT = ROOT / 'docs/fatigue-trekking-evaluation-2026-10-22/ucd-windows-results.json'
API = 'https://zenodo.org/api/records/11114096'
WINDOW = 5000.0
MAX_GAP = 50.0


def metrics(y, predicted) -> dict:
    result = base_metrics(y, predicted)
    (_, fp), (fn, tp) = result['confusion_matrix_NF_F']
    result['fatigued_condition_precision_ppv'] = tp / (tp + fp) if tp + fp else None
    result['fatigued_condition_sensitivity'] = tp / (tp + fn) if tp + fn else None
    return result


def sources() -> tuple[list[dict], str]:
    RAW.mkdir(parents=True, exist_ok=True)
    metadata = RAW / 'zenodo-metadata.json'
    if not metadata.exists():
        with urllib.request.urlopen(API, timeout=60) as response:
            metadata.write_bytes(response.read())
    content = metadata.read_bytes()
    record = json.loads(content)
    if str(record['id']) != '11114096':
        raise ValueError('Unexpected source record')
    files = sorted((f for f in record['files'] if re.fullmatch(r'\d{3}_(?:NF|F)\.csv', f['key'])),
                   key=lambda f: f['key'])
    if len(files) != 38:
        raise ValueError('Expected 38 original F/NF recordings')
    return files, hashlib.sha256(content).hexdigest()


def fetch(file: dict) -> Path:
    path = RAW / file['key']
    if not path.exists():
        with urllib.request.urlopen(file['links']['self'], timeout=90) as response:
            data = response.read()
    else:
        data = path.read_bytes()
    if len(data) != file['size'] or 'md5:' + hashlib.md5(data).hexdigest() != file['checksum']:
        raise ValueError(f"Official size/checksum mismatch: {file['key']}")
    if not path.exists():
        path.write_bytes(data)
    return path


def windows(file: dict) -> tuple[list[dict], dict]:
    path = fetch(file)
    frame = pd.read_csv(path, usecols=['Timestamp', 'Accel_WR_X', 'Accel_WR_Y', 'Accel_WR_Z'])
    values = frame[['Timestamp', 'Accel_WR_X', 'Accel_WR_Y', 'Accel_WR_Z']].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f'Nonfinite time or acceleration in {path.name}; no imputation allowed')
    time = values[:, 0] - values[0, 0]
    dt = np.diff(time)
    if len(dt) == 0 or np.any(dt <= 0):
        raise ValueError(f'Nonmonotonic time in {path.name}; no sorting or time repair allowed')
    magnitude = np.linalg.norm(values[:, 1:], axis=1)
    person, condition = path.stem.split('_')
    candidates = int(np.floor(time[-1] / WINDOW))
    kept, excluded = [], []
    for index in range(candidates):
        start, end = index * WINDOW, (index + 1) * WINDOW
        left, right = np.searchsorted(time, [start, end], side='left')
        segment, times = magnitude[left:right], time[left:right]
        if len(segment) < 50:
            reason = 'fewer_than_50_samples'
        elif times[0] - start > MAX_GAP or end - times[-1] > MAX_GAP:
            reason = 'boundary_gap_above_50_timestamp_units'
        elif np.max(np.diff(times)) > MAX_GAP:
            reason = 'internal_gap_above_50_timestamp_units'
        else:
            reason = None
        if reason:
            excluded.append({'index': index, 'reason': reason})
            continue
        features = feature_matrix(segment[None, :])[0]
        kept.append({'person': person, 'recording': path.stem, 'observed': int(condition == 'F'),
                     'index': index, 'start_timestamp_offset': start, 'end_timestamp_offset': end,
                     'samples': len(segment), 'median_dt': float(np.median(np.diff(times))),
                     'features': features.tolist(), 'low_motion_std_below_1': bool(features[1] < 1.0)})
    audit = {'file': path.name, 'bytes': path.stat().st_size, 'md5': file['checksum'],
             'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'person': person,
             'condition': condition, 'samples': len(frame), 'timestamp_span': float(time[-1]),
             'dt_quantiles_min_p01_median_p99_max': np.quantile(dt, [0, .01, .5, .99, 1]).tolist(),
             'frequency_hz_if_timestamp_ms': float(1000 / np.median(dt)),
             'gaps_above_50_timestamp_units': int(np.sum(dt > MAX_GAP)),
             'complete_candidate_windows': candidates, 'accepted_windows': len(kept),
             'low_motion_windows_std_below_1': sum(w['low_motion_std_below_1'] for w in kept),
             'excluded_windows': excluded,
             'trailing_timestamp_units_not_windowed': float(time[-1] - candidates * WINDOW)}
    return kept, audit


def benchmark(rows: list[dict], feature_kind: str) -> dict:
    people = np.array([r['person'] for r in rows])
    y = np.array([r['observed'] for r in rows])
    if feature_kind == 'acceleration':
        # Omit RMS first difference: it directly depends on sampling interval.
        x = np.array([r['features'][:7] for r in rows])
    elif feature_kind == 'timing_control':
        x = np.array([[r['samples'], r['median_dt']] for r in rows])
    else:
        raise ValueError('Unknown feature kind')
    groups = sorted(set(people))
    if len(groups) < 2:
        raise ValueError('At least two complete people required after quality exclusions')
    predicted, baseline = np.zeros(len(y), dtype=int), np.zeros(len(y), dtype=int)
    results = []
    for person in groups:
        train, test = people != person, people == person
        if set(y[test]) != {0, 1}:
            raise ValueError(f'Incomplete conditions for held-out person {person}')
        model = RandomForestClassifier(n_estimators=150, max_depth=5, min_samples_leaf=10,
                                       class_weight='balanced', random_state=42, n_jobs=-1)
        model.fit(x[train], y[train])
        predicted[test] = model.predict(x[test])
        baseline[test] = int(np.sum(y[train] == 1) > np.sum(y[train] == 0))
        results.append({'person': person, 'windows': int(np.sum(test)),
                        'model': metrics(y[test], predicted[test]),
                        'majority_baseline': metrics(y[test], baseline[test])})
    balanced = np.array([r['model']['balanced_accuracy'] for r in results])
    baseline_balanced = np.array([r['majority_baseline']['balanced_accuracy'] for r in results])
    rng = np.random.default_rng(42)
    draws = rng.integers(0, len(groups), size=(10000, len(groups)))
    summed = np.array([r['model']['confusion_matrix_NF_F'] for r in results])[draws].sum(axis=1)
    tn, fp, fn, tp = (summed[:, i, j].astype(float) for i, j in ((0, 0), (0, 1), (1, 0), (1, 1)))
    with np.errstate(divide='ignore', invalid='ignore'):
        bootstrap_values = {'accuracy': (tn + tp) / (tn + fp + fn + tp),
                            'fatigued_condition_precision_ppv': tp / (tp + fp),
                            'fatigued_condition_sensitivity': tp / (tp + fn)}
    pooled_intervals = {
        key: {'interval_95pct': np.quantile(value, [.025, .975]).tolist() if np.isfinite(value).all() else None,
              'undefined_replicates': int(np.sum(~np.isfinite(value)))}
        for key, value in bootstrap_values.items()}
    predictions = [{k: r[k] for k in ('person', 'recording', 'index', 'observed',
                                     'start_timestamp_offset', 'end_timestamp_offset',
                                     'samples', 'low_motion_std_below_1')} |
                   {'predicted': int(p), 'majority_baseline': int(b)}
                   for r, p, b in zip(rows, predicted, baseline)]
    return {'participants': len(groups), 'windows': len(rows), 'model': metrics(y, predicted),
            'majority_baseline': metrics(y, baseline), 'participant_results': results,
            'mean_participant_balanced_accuracy': float(np.mean(balanced)),
            'participant_bootstrap_95pct_balanced_accuracy': np.quantile(balanced[draws].mean(axis=1), [.025, .975]).tolist(),
            'participant_bootstrap_95pct_difference_from_baseline': np.quantile(
                (balanced - baseline_balanced)[draws].mean(axis=1), [.025, .975]).tolist(),
            'participant_bootstrap_95pct_pooled_metrics': pooled_intervals,
            'predictions': predictions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    files, metadata_hash = sources()
    with ThreadPoolExecutor(max_workers=3) as pool:
        extracted = list(pool.map(windows, files))
    rows = [row for recording, _ in extracted for row in recording]
    report = {
        'source': 'https://zenodo.org/records/11114096', 'license': 'CC-BY-4.0',
        'source_metadata_sha256': metadata_hash, 'participants': len({r['person'] for r in rows}),
        'files': [audit for _, audit in extracted], 'window_timestamp_units': WINDOW,
        'time_interpretation': '5000 exported calibrated Shimmer Timestamp units, treated as ms; source CSV omits unit headers. Duration claims remain conditional on that interpretation.',
        'quality_rule': 'Finite measurements, strictly increasing time, >=50 samples/window, no internal or boundary gap >50 Timestamp units. No time repair or interpolation.',
        'features': ['magnitude_mean', 'magnitude_std', 'magnitude_median', 'magnitude_p10',
                     'magnitude_p90', 'magnitude_RMS', 'magnitude_range'],
        'model': 'Fixed RandomForest: 150 trees, max_depth=5, min_samples_leaf=10, balanced class weights, random_state=42',
        'validation': 'Leave one complete participant out, all recordings/windows from that person together. No window overlap, no full-recording vote, no hyperparameter search.',
        'versions': {'numpy': np.__version__, 'pandas': pd.__version__, 'scikit_learn': sklearn.__version__},
        'deployment_approved': False,
        'limitations': [
            'F/NF labels identify original recordings before/after a beep test; not independent continuous fatigue measurements.',
            'Running outdoors with lumbar Shimmer IMU, not trekking or phone/wrist validation; no heart rate.',
            'Source declares 256Hz but actual exported intervals differ; do not impose one sampling rate.',
            'Windows include standing, transitions and running; low-motion threshold is an engineering sensitivity check, not a validated gait or fatigue label.',
            'Five-second interpretation and m/s2 acceleration units rely on calibrated Shimmer export conventions, not unit headers in these files.',
            'Order, pace, environment and recording artifacts can confound the before/after condition.',
            'Related protocol/source to previous stride experiment: this is exploratory follow-up, not independent external validation. Participant ID sets differ between deposits.',
            'Participant bootstrap resamples fixed held-out predictions; does not include full model/source-selection or domain-transfer uncertainty.'
        ]}
    if not args.audit_only:
        report['all_windows'] = benchmark(rows, 'acceleration')
        report['timing_control'] = benchmark(rows, 'timing_control')
        moving = [r for r in rows if not r['low_motion_std_below_1']]
        people = sorted({r['person'] for r in rows})
        eligible = {p for p in people if {r['observed'] for r in moving if r['person'] == p} == {0, 1}}
        complete = [r for r in moving if r['person'] in eligible]
        report['movement_sensitivity_std_at_least_1'] = benchmark(complete, 'acceleration')
        report['movement_sensitivity_std_at_least_1']['coverage'] = {
            'input_quality_windows': len(rows), 'windows_above_motion_threshold': len(moving),
            'windows_from_complete_people': len(complete),
            'excluded_people_missing_one_moving_condition': [p for p in people if p not in eligible],
            'rule': 'After fixed std>=1 screen, retain both recordings only for people with at least one accepted window in each condition. No selection by prediction performance.'}
    destination = OUTPUT.with_name('ucd-windows-audit.json') if args.audit_only else OUTPUT
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'participants': report['participants'], 'files': len(report['files']),
                      'accepted_windows': len(rows),
                      'results': {key: {k: value[k] for k in ('windows', 'model', 'majority_baseline',
                                  'mean_participant_balanced_accuracy', 'participant_bootstrap_95pct_balanced_accuracy',
                                  'participant_bootstrap_95pct_difference_from_baseline')}
                                  for key, value in report.items() if isinstance(value, dict) and 'model' in value}}, indent=2))


if __name__ == '__main__':
    main()
