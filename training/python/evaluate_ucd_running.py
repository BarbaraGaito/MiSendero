"""Person-held-out benchmark of original UCD pre/post-exhaustion conditions.

No questionnaire-derived or synthetic labels. This evaluates running strides
from a lumbar IMU, not fatigue during trekking or a phone/wrist deployment.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, precision_score, recall_score

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'training/data/raw/ucd-running/Accel_mag_all.csv'
OUTPUT = ROOT / 'docs/fatigue-trekking-evaluation-2026-10-22/ucd-running-results.json'
URL = 'https://zenodo.org/api/records/7997851/files/Accel_mag_all.csv/content'
MD5 = '054b2be68060e0e4543a431fe49c4f14'


def load() -> tuple[pd.DataFrame, str]:
    if not RAW.exists():
        RAW.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=45) as response:
            content = response.read()
        if hashlib.md5(content).hexdigest() != MD5:
            raise ValueError('Source checksum mismatch')
        RAW.write_bytes(content)
    raw = RAW.read_bytes()
    if hashlib.md5(raw).hexdigest() != MD5:
        raise ValueError('Cached source checksum mismatch')
    # The deposited file has no header: its first row is an actual stride.
    return pd.read_csv(RAW, header=None), hashlib.sha256(raw).hexdigest()


def feature_matrix(signal: np.ndarray) -> np.ndarray:
    if not np.isfinite(signal).all():
        raise ValueError('Missing or nonfinite sensor samples; no imputation allowed')
    mean = np.mean(signal, axis=1)
    std = np.std(signal, axis=1)
    centered = signal - mean[:, None]
    return np.column_stack([mean, std, np.median(signal, axis=1),
                            np.quantile(signal, .1, axis=1), np.quantile(signal, .9, axis=1),
                            np.sqrt(np.mean(signal ** 2, axis=1)),
                            np.ptp(signal, axis=1),
                            np.sqrt(np.mean(np.diff(signal, axis=1) ** 2, axis=1))])


def metrics(y, p) -> dict:
    return {'accuracy': float(accuracy_score(y, p)),
            'balanced_accuracy': float(balanced_accuracy_score(y, p)),
            'fatigued_condition_precision_ppv': float(precision_score(y, p, zero_division=0)),
            'fatigued_condition_sensitivity': float(recall_score(y, p, zero_division=0)),
            'confusion_matrix_NF_F': confusion_matrix(y, p, labels=[0, 1]).tolist()}


def evaluate(frame: pd.DataFrame, digest: str) -> dict:
    people = frame.iloc[:, 0].astype(str).to_numpy()
    labels = frame.iloc[:, 1].astype(str)
    if set(labels) != {'F', 'NF'}:
        raise ValueError('Unexpected original labels')
    y = labels.eq('F').astype(int).to_numpy()
    x = feature_matrix(frame.iloc[:, 2:].to_numpy(dtype=float))
    predicted = np.zeros(len(y), dtype=int)
    baseline = np.zeros(len(y), dtype=int)
    groups = sorted(set(people), key=int)
    if len(groups) != 19:
        raise ValueError('Expected 19 original participants')
    participant_results, sessions = [], []
    for person in groups:
        train, test = people != person, people == person
        if set(y[test]) != {0, 1}:
            raise ValueError('Participant missing one condition')
        model = RandomForestClassifier(n_estimators=150, max_depth=5, min_samples_leaf=10,
                                       class_weight='balanced', random_state=42, n_jobs=-1)
        model.fit(x[train], y[train])
        predicted[test] = model.predict(x[test])
        baseline[test] = int(np.sum(y[train] == 1) > np.sum(y[train] == 0))
        participant_results.append({'person': person, 'strides': int(np.sum(test)),
                                    'model': metrics(y[test], predicted[test]),
                                    'majority_baseline': metrics(y[test], baseline[test])})
        for condition in (0, 1):
            subset = test & (y == condition)
            # Strict majority; ties map to NF. A whole recording is one session.
            vote = int(np.mean(predicted[subset]) > .5)
            sessions.append({'person': person, 'condition': 'F' if condition else 'NF',
                             'strides': int(np.sum(subset)), 'observed': condition, 'predicted': vote})
    rng = np.random.default_rng(42)
    participant_balanced = np.array([p['model']['balanced_accuracy'] for p in participant_results])
    intervals = np.quantile([np.mean(rng.choice(participant_balanced, len(groups), replace=True))
                             for _ in range(10000)], [.025, .975]).tolist()
    return {'source': 'https://doi.org/10.5281/zenodo.7997851', 'license': 'CC-BY-4.0',
            'file_md5': MD5, 'file_sha256': digest,
            'task': 'Original NF/F running condition before/after a beep test to inability to keep pace',
            'scope': 'Exploratory source benchmark; no trekking, walking, wrist, phone, or real-time fatigue-onset validation',
            'participants': len(groups), 'strides': len(y), 'samples_per_segment': frame.shape[1] - 2,
            'model': 'Fixed RandomForest: 150 trees, depth 5, min leaf 10, balanced weights, seed 42',
            'features': 'Acceleration magnitude mean, std, median, p10, p90, RMS, range, RMS first difference',
            'validation': 'Leave one complete participant out; all strides from both conditions stay together',
            'stride_level_model': metrics(y, predicted),
            'stride_level_majority_baseline': metrics(y, baseline),
            'mean_participant_balanced_accuracy': float(np.mean(participant_balanced)),
            'participant_bootstrap_95pct_balanced_accuracy': intervals,
            'session_majority_vote': metrics([s['observed'] for s in sessions], [s['predicted'] for s in sessions]),
            'participant_results': participant_results, 'sessions': sessions,
            'limitations': ['Protocol phase is a condition label, not a continuous independent measure of physiological fatigue.',
                            'All NF recordings precede the fatiguing protocol; phase/order/speed can confound prediction.',
                            'Segments are strides provided by the source, not independent fatigue assessments.',
                            'Lumbar sensor location and stride segmentation differ from current app inputs.',
                            'No threshold or deployment decision was tuned to these held-out results.']}


def main() -> None:
    data, digest = load()
    report = evaluate(data, digest)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('participants', 'strides', 'stride_level_model',
                      'stride_level_majority_baseline', 'mean_participant_balanced_accuracy',
                      'participant_bootstrap_95pct_balanced_accuracy', 'session_majority_vote')}, indent=2))


if __name__ == '__main__':
    main()
