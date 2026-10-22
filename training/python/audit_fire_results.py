"""Independently verify real-source joins and held-out fire prediction scores."""
import ast
from array import array
from collections import Counter
import csv
import gzip
import json
import math

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss

from environmental_sources import sha256, utc
from fire_sources import DIRECTORY, ID_PATTERN, OBSERVATIONS, PRIVATE, PROTOCOL, REPORT_DIR, protocol
from fire_features import iter_examples, load_cells


def main():
    report_path = REPORT_DIR / 'fire-results.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report['status'] != 'experimental':
        raise ValueError('No trained fire model to audit')
    source_path = REPORT_DIR / 'fire-source-audit.json'
    source = json.loads(source_path.read_text(encoding='utf-8'))
    assert report['source_audit_sha256'] == sha256(source_path)
    assert report['protocol_sha256'] == source['protocol_sha256'] == sha256(PROTOCOL)
    assert source['summary']['observations_sha256'] == sha256(OBSERVATIONS)
    manifest_path = PRIVATE / 'fire-source-manifest.json'
    assert source['manifest_sha256'] == sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    original_files = 0
    for identifier, pair in manifest.items():
        for band in ('FireMask', 'QA'):
            # Paths are constructed from the reviewed manifest identifiers,
            # not followed from a potentially edited path field.
            assert ID_PATTERN.fullmatch(identifier)
            assert sha256(DIRECTORY / f'{identifier}_{band}.tif') == pair[band]['sha256']
            original_files += 1
    cells, _ = load_cells()
    plan = protocol()
    fit_end, valid_end, test_end = [utc(plan[k]) for k in ('training_target_before', 'validation_target_before', 'test_target_before')]
    held = set(plan['geographic_holdout_tiles'])
    selection = max(report['validation'], key=lambda name: report['validation'][name]['pr_auc_average_precision'])
    assert report['selection'] == selection
    audited, streams, readers = {}, {}, {}
    values = {split: {'y': array('b'), 'probabilities': {candidate: array('d') for candidate in report['validation']}}
        for split in ('temporal_test', 'geographic_test')}
    counts = {name: Counter() for name in report['partitions']}
    for split in ('temporal_test', 'geographic_test'):
        evidence = report['prediction_files'][split]
        path = PRIVATE / f'fire-{split}-predictions.csv.gz'
        assert evidence['sha256'] == sha256(path)
        streams[split] = gzip.open(path, 'rt', encoding='utf-8', newline='')
        readers[split] = csv.DictReader(streams[split])
    for original in iter_examples(cells, plan):
        issue, target, available = [utc(original[k]) for k in ('issued_at', 'target_at', 'target_available_at')]
        held_out = original['tile'] in held
        eligible = {'train': not held_out and target < fit_end and available < fit_end,
            'validation': not held_out and issue >= fit_end and target < valid_end and available < valid_end,
            'temporal_test': not held_out and issue >= valid_end and target < test_end,
            'geographic_test': held_out and issue >= fit_end and target < test_end}
        for split, included in eligible.items():
            if not included:
                continue
            counts[split]['observations'] += 1
            counts[split]['positive_observations'] += original['observed']
            if split not in readers:
                continue
            row = next(readers[split])
            assert int(row['observed']) == original['observed']
            for name in ('pixel_id', 'issued_at', 'target_at', 'target_available_at', 'target_item_id', 'tile', 'region'):
                assert row[name] == original[name], f'Prediction/source join mismatch: {name}'
            for name in ('input_dates', 'input_available_at', 'input_item_ids'):
                assert ast.literal_eval(row[name]) == original[name]
            assert all(utc(d) <= utc(row['issued_at']) for d in original['input_available_at'])
            values[split]['y'].append(int(row['observed']))
            for candidate in values[split]['probabilities']:
                p = float(row[candidate])
                assert 0 <= p <= 1 and math.isfinite(p)
                values[split]['probabilities'][candidate].append(p)
    for name in counts:
        for key in ('observations', 'positive_observations'):
            assert counts[name][key] == report['partitions'][name][key]
    for split, reader in readers.items():
        assert next(reader, None) is None, 'Unmatched prediction row'
        streams[split].close()
        y = np.frombuffer(values[split]['y'], dtype=np.int8)
        for candidate, probabilities in values[split]['probabilities'].items():
            p = np.frombuffer(probabilities, dtype=np.float64)
            if not len(y):
                continue
            score = report['test'][split][candidate]
            predicted = p >= .5
            matrix = [[int(((y == actual) & (predicted == decision)).sum()) for decision in (0, 1)] for actual in (0, 1)]
            assert matrix == score['confusion_matrix']
            # XGBoost emits float32. Restore that original dtype after decimal
            # CSV roundtrip; sklearn's two-class calculation rounds differently
            # from direct binary squared error by about 1e-11 on this cohort.
            recovered = p.astype(np.float32) if candidate == 'xgboost' else p
            assert math.isclose(float(brier_score_loss(y.astype(float), recovered)), score['brier'], rel_tol=1e-10, abs_tol=1e-12)
            assert math.isclose(float(np.mean((p - y) ** 2)), score['brier'], rel_tol=1e-8, abs_tol=1e-9)
            if y.sum():
                assert math.isclose(float(average_precision_score(y, recovered)), score['pr_auc_average_precision'], rel_tol=1e-10)
        audited[split] = {'verified_predictions': len(y), 'positive_observations': int(y.sum())}
    artifact = report['artifact']
    if artifact['model_file']:
        assert artifact['model_file'] == 'fire-mod14a1.joblib'
        assert sha256(PRIVATE / 'fire-mod14a1.joblib') == artifact['model_sha256']
    (REPORT_DIR / 'fire-results-audit.json').write_text(json.dumps({'status': 'passed',
        'report_sha256': sha256(report_path), 'original_cogs_verified': original_files, 'partitions': audited,
        'checks': ['original COG hashes', 'qualified pixel/date labels', 'causal publication joins',
            'temporal and entire-tile partitions', 'validation-only selection', 'probabilities, AP, Brier and confusion matrices', 'model hash']},
        indent=2) + '\n', encoding='utf-8')
    print('Verified', original_files, 'original COGs and', audited, flush=True)


if __name__ == '__main__':
    main()
