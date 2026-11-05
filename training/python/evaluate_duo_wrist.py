"""Evaluate original DUO-GAIT pre/post-fatigue walking conditions with left wrist.

Train on single-task walking from other people; hold out both visits of each
person. Cognitive-task walking is a prespecified secondary transfer check.
This is an indoor condition benchmark, not validated fatigue alerts in trekking.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import zlib

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier

from duo_gait_remote import read_member
from evaluate_ucd_running import feature_matrix
from evaluate_ucd_windows import metrics

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'training/data/raw/duo-gait'
OUTPUT = ROOT / 'docs/fatigue-trekking-evaluation-2026-10-22/duo-wrist-results.json'
WINDOW_SECONDS = 5.0
START_SECONDS = 20.0
END_SECONDS = 320.0


def references() -> tuple[list[dict], list[dict], list[dict]]:
    payload, source = read_member('raw.zip', 3377688584, 'raw/subject_info.csv')
    source['sha256'] = hashlib.sha256(payload).hexdigest()
    table = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
    # Exclude demographics: only audit original reference measurements here.
    keep = ['sub', 'st_lac_baseline1', 'st_lac_baseline2', 'st_lac_fatigue',
            'st_borg_scale', 'dt_lac_baseline1', 'dt_lac_baseline2',
            'dt_lac_fatigue', 'dt_borg_scale']
    evidence = [{k: row[k] for k in keep} for row in table]
    payload, interruptions_source = read_member('interim.zip', 3025750473, 'interim/interruptions.csv')
    interruptions_source['sha256'] = hashlib.sha256(payload).hexdigest()
    interruptions = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
    return evidence, interruptions, [source, interruptions_source]


def extract(record: dict, interruptions: list[dict]) -> tuple[list[dict], dict]:
    path = RAW / 'wrist' / record['cache_name']
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != record['sha256'] or f'{zlib.crc32(content):08x}' != record['zip_crc32']:
        raise ValueError(f'Cached sensor checksum mismatch: {path.name}')
    frame = pd.read_csv(io.BytesIO(content), usecols=['timestamp', 'GyrX', 'GyrY', 'GyrZ', 'AccX', 'AccY', 'AccZ'])
    values = frame[['timestamp', 'GyrX', 'GyrY', 'GyrZ', 'AccX', 'AccY', 'AccZ']].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('Nonfinite sensor measurements; no imputation permitted')
    time = values[:, 0] - values[0, 0]
    if np.any(np.diff(time) <= 0):
        raise ValueError('Nonmonotonic time; no repair permitted')
    gyro = np.linalg.norm(values[:, 1:4], axis=1)
    accel = np.linalg.norm(values[:, 4:7], axis=1) * 9.80665
    pauses = [(float(p['start(s)']), float(p['end(s)'])) for p in interruptions
              if p['sub'] == record['person'] and p['run'] == f"{record['task']}_{record['condition']}"]
    # Same five-minute interval for every recording, fixed before predictions.
    # Do not select windows using a percentage of eventual recording duration.
    candidates = int((END_SECONDS - START_SECONDS) / WINDOW_SECONDS)
    rows, exclusions = [], []
    for index in range(candidates):
        start = START_SECONDS + index * WINDOW_SECONDS
        end = start + WINDOW_SECONDS
        left, right = np.searchsorted(time, [start, end], side='left')
        local = time[left:right]
        if any(start < b and end > a for a, b in pauses):
            reason = 'overlaps_author_annotated_interruption'
        elif len(local) < 600:
            reason = 'fewer_than_600_samples'
        elif local[0] - start > .025 or end - local[-1] > .025 or np.max(np.diff(local)) > .025:
            reason = 'gap_above_25ms'
        else:
            reason = None
        if reason:
            exclusions.append({'index': index, 'reason': reason})
            continue
        features = np.concatenate([feature_matrix(accel[None, left:right])[0][:7],
                                   feature_matrix(gyro[None, left:right])[0][:7]])
        rows.append({'person': record['person'], 'task': record['task'], 'recording': path.stem,
                     'observed': int(record['condition'] == 'fatigue'), 'index': index,
                     'start_seconds_in_segment': start, 'end_seconds_in_segment': end,
                     'samples': len(local), 'median_dt_seconds': float(np.median(np.diff(local))),
                     'features': features.tolist()})
    return rows, record | {'total_sensor_rows': len(frame), 'duration_seconds': float(time[-1]),
                            'median_dt_seconds': float(np.median(np.diff(time))),
                            'fixed_interval_candidate_windows': candidates,
                            'accepted_windows': len(rows), 'exclusions': exclusions,
                            'author_annotated_interruptions': pauses}


def summarize(rows: list[dict], predictions: np.ndarray, baseline: np.ndarray) -> dict:
    y = np.array([r['observed'] for r in rows])
    people = np.array([r['person'] for r in rows])
    by_person = [{'person': p, 'windows': int(np.sum(people == p)),
                  'model': metrics(y[people == p], predictions[people == p])}
                 for p in sorted(set(people))]
    balanced = np.array([p['model']['balanced_accuracy'] for p in by_person])
    rng = np.random.default_rng(42)
    draws = rng.integers(0, len(by_person), (10000, len(by_person)))
    summed = np.array([p['model']['confusion_matrix_NF_F'] for p in by_person])[draws].sum(axis=1)
    tn, fp, fn, tp = (summed[:, i, j].astype(float) for i, j in ((0, 0), (0, 1), (1, 0), (1, 1)))
    with np.errstate(divide='ignore', invalid='ignore'):
        values = {'accuracy': (tn + tp) / (tn + fp + fn + tp),
                  'fatigued_condition_precision_ppv': tp / (tp + fp),
                  'fatigued_condition_sensitivity': tp / (tp + fn)}
    intervals = {key: {'interval_95pct': np.quantile(v, [.025, .975]).tolist() if np.isfinite(v).all() else None,
                       'undefined_replicates': int(np.sum(~np.isfinite(v)))} for key, v in values.items()}
    return {'participants': len(by_person), 'windows': len(rows), 'model': metrics(y, predictions),
            'majority_baseline': metrics(y, baseline), 'participant_results': by_person,
            'mean_participant_balanced_accuracy': float(np.mean(balanced)),
            'participant_bootstrap_95pct_mean_balanced_accuracy': np.quantile(balanced[draws].mean(axis=1), [.025, .975]).tolist(),
            'participant_bootstrap_95pct_pooled_metrics': intervals,
            'predictions': [{k: r[k] for k in ('person', 'task', 'recording', 'observed', 'index',
                                             'start_seconds_in_segment', 'end_seconds_in_segment')} |
                            {'predicted': int(p), 'majority_baseline': int(b)}
                            for r, p, b in zip(rows, predictions, baseline)]}


def evaluate(rows: list[dict], control=False) -> dict:
    people = np.array([r['person'] for r in rows])
    tasks = np.array([r['task'] for r in rows])
    y = np.array([r['observed'] for r in rows])
    x = np.array([[r['samples'], r['median_dt_seconds']] if control else r['features'] for r in rows])
    predictions, baseline = np.zeros(len(y), dtype=int), np.zeros(len(y), dtype=int)
    groups = sorted(set(people))
    if len(groups) != 16:
        raise ValueError('Expected 16 complete people')
    for person in groups:
        train = (people != person) & (tasks == 'st')
        test = people == person
        for task in ('st', 'dt'):
            if set(y[test & (tasks == task)]) != {0, 1}:
                raise ValueError(f'Missing paired conditions for {person}/{task}')
        model = RandomForestClassifier(n_estimators=150, max_depth=5, min_samples_leaf=10,
                                       class_weight='balanced', random_state=42, n_jobs=-1)
        model.fit(x[train], y[train])
        predictions[test] = model.predict(x[test])
        baseline[test] = int(np.sum(y[train] == 1) > np.sum(y[train] == 0))
    return {task: summarize([r for r in rows if r['task'] == task], predictions[tasks == task], baseline[tasks == task])
            for task in ('st', 'dt')}


def main() -> None:
    manifest = json.loads((RAW / 'wrist-manifest.json').read_text(encoding='utf-8'))
    evidence, interruptions, reference_sources = references()
    rows, audits = [], []
    for record in manifest['records']:
        extracted, audit = extract(record, interruptions)
        rows.extend(extracted)
        audits.append(audit)
    if len(audits) != 64 or {r['person'] for r in rows} != {r['sub'] for r in evidence}:
        raise ValueError('Subject inventory and source reference mismatch')
    report = {'source': 'https://zenodo.org/records/8244887',
              'paper': 'https://doi.org/10.1038/s41597-023-02391-w',
              'data_license': 'No dataset license field in inspected Zenodo metadata; article CC-BY-4.0 and code MIT do not independently license the dataset.',
              'integrity': manifest['integrity'], 'archive_md5_verified': False,
              'window_seconds': WINDOW_SECONDS, 'scored_interval_seconds': [START_SECONDS, END_SECONDS],
              'quality_rule': 'Nonoverlapping causal windows; finite signals, increasing time, >=600 samples and no internal/boundary gap above 25ms; discard windows intersecting original annotated interruptions.',
              'features': 'Seven magnitude statistics (mean,std,median,p10,p90,RMS,range) each for left wrist acceleration in m/s2 and angular velocity in degrees/s. No raw index, elapsed time, ID, task, RPE, lactate or pulse as inputs.',
              'model': 'Fixed RF: 150 trees, depth5, min_leaf10, balanced, seed42; no hyperparameter search.',
              'validation': '16 leave-person-out folds. Train only single-task walking of 15 other people; evaluate single-task and secondary cognitive-task walking of held-out person. Both visits and all windows of test person excluded from training.',
              'versions': {'numpy': np.__version__, 'pandas': pd.__version__, 'sklearn': sklearn.__version__},
              'reference_measurements_original': evidence, 'reference_sources': reference_sources,
              'recording_audits': audits, 'left_wrist_movement': evaluate(rows),
              'sampling_only_control': evaluate(rows, control=True), 'deployment_approved': False,
              'limitations': ['Indoor hallway walking after weighted sit-to-stand exhaustion; not trekking, elevation, backpack walking or outdoor validation.',
                              'Original condition label is a pre/post protocol reference; Borg/lactate were not repeated for each walking window, so recovery during six minutes is not independently labelled.',
                              'Fixed pre/post order, speed and arm swing can affect prediction. A sampling control cannot rule out every confound.',
                              'Research-grade Physilog5 left wrist IMU at 128Hz, not actual watch/phone validation; no heart rate used because precise cross-device temporal alignment remains unverified.',
                              'Secondary cognitive-task results share participants with primary results and are not an independent population.',
                              'Timestamp zeroing and units follow author code; annotated interruptions interpreted relative to cut segment start.',
                              'Fixed 20-320s interval is relative to source manual walking segmentation; automatic walking segmentation and live interruption recognition are not evaluated.',
                              'Bootstrap resamples complete participants and fixed held-out predictions, not independent windows or repeated full model selection.',
                              'Partial ZIP member CRC verified, not full archive MD5. Dataset redistribution/license needs clarification before publication or deployment.']}
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({kind: {task: {k: result[k] for k in ('participants', 'windows', 'model',
                     'majority_baseline', 'mean_participant_balanced_accuracy',
                     'participant_bootstrap_95pct_mean_balanced_accuracy')}
                     for task, result in report[kind].items()}
                     for kind in ('left_wrist_movement', 'sampling_only_control')}, indent=2))


if __name__ == '__main__':
    main()
