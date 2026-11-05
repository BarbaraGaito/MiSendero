"""Exploratory nested person-grouped model selection for DUO-GAIT left wrist.

Designed after inspecting the fixed RF benchmark; does not create a fresh
external test population or validation for trekking.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from evaluate_duo_wrist import RAW, extract, summarize

ROOT = Path(__file__).resolve().parents[2]
FIRST = ROOT / 'docs/fatigue-trekking-evaluation-2026-10-22/duo-wrist-results.json'
OUTPUT = FIRST.with_name('duo-wrist-nested-results.json')


def rhythm_features(signal: np.ndarray, fs: float) -> list[float]:
    centered = signal - np.mean(signal)
    power = np.abs(np.fft.rfft(centered * np.hanning(len(signal)))) ** 2
    frequency = np.fft.rfftfreq(len(signal), d=1 / fs)
    gait = (frequency >= .5) & (frequency <= 4)
    broad = (frequency >= .5) & (frequency <= 10)
    broad_power = float(np.sum(power[broad]))
    if broad_power <= 1e-12 or float(np.dot(centered, centered)) <= 1e-12:
        return [0.0] * 6
    normalized = power[broad] / broad_power
    nonzero = normalized > 0
    entropy = -np.sum(normalized[nonzero] * np.log(normalized[nonzero])) / np.log(len(normalized))
    index = int(np.argmax(power[gait]))
    dominant = frequency[gait][index]
    peak_fraction = power[gait][index] / broad_power
    gait_fraction = np.sum(power[gait]) / broad_power
    auto = np.correlate(centered, centered, mode='full')[len(signal) - 1:]
    low, high = int(np.ceil(.3 * fs)), int(np.floor(1.5 * fs))
    lag = low + int(np.argmax(auto[low:high + 1]))
    return [float(dominant), float(peak_fraction), float(gait_fraction), float(entropy),
            float(auto[lag] / auto[0]), float(lag / fs)]


def enrich(rows: list[dict], records: list[dict]) -> list[dict]:
    enriched = []
    for record in records:
        name = Path(record['cache_name']).stem
        subset = [row for row in rows if row['recording'] == name]
        content = (RAW / 'wrist' / record['cache_name']).read_bytes()
        if hashlib.sha256(content).hexdigest() != record['sha256']:
            raise ValueError('Sensor source changed')
        frame = pd.read_csv(io.BytesIO(content))
        time = frame.timestamp.to_numpy() - frame.timestamp.iloc[0]
        accel = np.linalg.norm(frame[['AccX', 'AccY', 'AccZ']].to_numpy(), axis=1) * 9.80665
        gyro = np.linalg.norm(frame[['GyrX', 'GyrY', 'GyrZ']].to_numpy(), axis=1)
        for row in subset:
            left, right = np.searchsorted(time, [row['start_seconds_in_segment'], row['end_seconds_in_segment']])
            fs = 1 / np.median(np.diff(time[left:right]))
            extra = rhythm_features(accel[left:right], fs) + rhythm_features(gyro[left:right], fs)
            enriched.append(row | {'features': row['features'] + extra})
    if not np.isfinite([row['features'] for row in enriched]).all():
        raise ValueError('Nonfinite features')
    return enriched


def main() -> None:
    initial_bytes = FIRST.read_bytes()
    initial = json.loads(initial_bytes)
    # Reuse original audited pause list; do not require another network call.
    pauses = []
    for record in initial['recording_audits']:
        pauses.extend({'sub': record['person'], 'run': f"{record['task']}_{record['condition']}",
                       'start(s)': start, 'end(s)': end} for start, end in record['author_annotated_interruptions'])
    records = initial['recording_audits']
    rows = [row for record in records for row in extract(record, pauses)[0]]
    rows = enrich(rows, records)
    people = np.array([r['person'] for r in rows])
    tasks = np.array([r['task'] for r in rows])
    x = np.array([r['features'] for r in rows])
    y = np.array([r['observed'] for r in rows])
    candidates = [
        ('constant', DummyClassifier(strategy='most_frequent')),
        ('logistic_C1', make_pipeline(StandardScaler(), LogisticRegression(C=1, class_weight='balanced', max_iter=3000, random_state=42))),
        ('svm_rbf_C1', make_pipeline(StandardScaler(), SVC(C=1, kernel='rbf', class_weight='balanced'))),
        ('svm_rbf_C10', make_pipeline(StandardScaler(), SVC(C=10, kernel='rbf', class_weight='balanced'))),
        ('RF_depth5', RandomForestClassifier(n_estimators=150, max_depth=5, min_samples_leaf=10, class_weight='balanced', random_state=42, n_jobs=-1))]
    predicted, baseline = np.zeros(len(y), dtype=int), np.zeros(len(y), dtype=int)
    selections = []
    for person in sorted(set(people)):
        train, test = (people != person) & (tasks == 'st'), people == person
        folds = list(GroupKFold(n_splits=3).split(x[train], y[train], people[train]))
        training_people = people[train]
        if person in training_people:
            raise ValueError('Outer participant leakage')
        for inner_train, inner_test in folds:
            if set(training_people[inner_train]) & set(training_people[inner_test]):
                raise ValueError('Inner participant leakage')
        scores = [float(np.mean(cross_val_score(model, x[train], y[train], cv=folds,
                                               scoring='balanced_accuracy', n_jobs=1))) for _, model in candidates]
        # Candidate order breaks exact ties, preferring the constant.
        selected = int(np.argmax(scores))
        fitted = clone(candidates[selected][1]).fit(x[train], y[train])
        predicted[test] = fitted.predict(x[test])
        baseline[test] = int(np.sum(y[train] == 1) > np.sum(y[train] == 0))
        selections.append({'held_out_person': person, 'selected': candidates[selected][0],
                            'inner_grouped_balanced_accuracy': dict(zip([n for n, _ in candidates], scores))})
        print(person, candidates[selected][0], flush=True)
    results = {task: summarize([r for r in rows if r['task'] == task], predicted[tasks == task], baseline[tasks == task])
               for task in ('st', 'dt')}
    report = {'source': initial['source'], 'initial_report_sha256': hashlib.sha256(initial_bytes).hexdigest(),
              'source_and_coverage': 'Same audited CSV members, interval 20-320s, interruptions and participant exclusions as fixed benchmark.',
              'features': '14 magnitude statistics from fixed benchmark plus 6 rhythm features per acceleration/gyro magnitude: dominant frequency 0.5-4Hz, peak/broad power, gait/broad power, spectral entropy 0.5-10Hz, autocorrelation peak and lag 0.3-1.5s. Signal windows 5s; no outcome-derived features.',
              'validation': '16 outer leave-person-out rounds. Select from 5 prespecified candidates with 3-fold GroupKFold of single-task training participants, maximizing mean balanced accuracy. All scaling fitted inside pipelines and folds. Test both visits of held-out person; no cognitive-task data used for model selection or fitting.',
              'candidate_order': [name for name, _ in candidates], 'selections': selections,
              'results': results, 'deployment_approved': False,
              'limitations': initial['limitations'] + [
                  'Features and model comparison designed after seeing fixed RF results on this source: exploratory follow-up, not a new independent external test.',
                  'Inner scores weight validation folds equally; windows are not independent participants.',
                  'Dominant movement frequencies are engineered descriptors, not clinically validated fatigue biomarkers.']}
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({task: {k: result[k] for k in ('windows', 'model', 'majority_baseline',
                     'mean_participant_balanced_accuracy', 'participant_bootstrap_95pct_mean_balanced_accuracy')}
                     for task, result in results.items()}, indent=2))


if __name__ == '__main__':
    main()
