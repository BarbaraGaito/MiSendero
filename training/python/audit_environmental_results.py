"""Recompute reported scores and causal joins from original cached observations.

No network, training or fixtures. Fails when original/private evidence is absent.
"""
import ast
import csv
import json
import math
from collections import Counter

from environmental_sources import RAW, ROOT, examples, observations, sha256, utc


def main():
    report_path = ROOT / 'docs/environmental-models-2026-10-22/river-results.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    train_end, valid_end, test_end = [utc(report['temporal_protocol'][k]) for k in (
        'training_target_before', 'validation_target_before', 'test_target_before')]
    verified = []
    for model in report['models']:
        station, horizon = model['series_id'], model['horizon_hours']
        raw_path = RAW / f'ina-{station}-2023-2026.json'
        assert sha256(raw_path) == model['source']['sha256'], 'Raw source changed'
        raw = json.loads(raw_path.read_bytes())
        clean, _ = observations(raw)
        rows, _ = examples(clean, horizon)
        counts = Counter()
        expected = {}
        for row in rows:
            issue, target, available = [utc(row[k]) for k in ('issued_at', 'target_at', 'target_available_at')]
            if issue < train_end and target < train_end and available < train_end:
                counts['train'] += 1
            if issue >= train_end and target < valid_end and available < valid_end:
                counts['validation'] += 1
            if issue >= valid_end and target < test_end:
                counts['test'] += 1
                expected[row['issued_at']] = row
        assert dict(counts) == model['counts'], 'Causal partition counts differ'
        prediction_path = ROOT / model['test_predictions_file']
        assert sha256(prediction_path) == model['test_predictions_sha256'], 'Test prediction hash differs'
        with prediction_path.open(encoding='utf-8', newline='') as stream:
            predicted = list(csv.DictReader(stream))
        assert len(predicted) == len(expected) == model['counts']['test']
        assert len({r['issued_at'] for r in predicted}) == len(predicted)
        for row in predicted:
            original = expected[row['issued_at']]
            for key in ('target_at', 'latest_observed_at', 'latest_available_at', 'target_available_at'):
                assert row[key] == original[key], f'Timestamp mismatch: {key}'
            assert ast.literal_eval(row['source_row_ids']) == original['source_row_ids']
            assert int(row['target_source_row_id']) == original['target_source_row_id']
            assert float(row['observed']) == original['observed']
            assert float(row['baseline']) == original['baseline']
        assert model['selection'] == min(model['validation'], key=lambda k: model['validation'][k]['mae_m'])
        for candidate, score in model['test'].items():
            errors = [float(row[candidate]) - float(row['observed']) for row in predicted]
            mae = math.fsum(abs(e) for e in errors) / len(errors)
            rmse = math.sqrt(math.fsum(e * e for e in errors) / len(errors))
            assert math.isclose(mae, score['mae_m'], rel_tol=1e-10, abs_tol=1e-12)
            assert math.isclose(rmse, score['rmse_m'], rel_tol=1e-10, abs_tol=1e-12)
        artifact = model['model_artifact']
        if artifact['model_file']:
            assert sha256(prediction_path.parent / artifact['model_file']) == artifact['model_sha256']
        verified.append({'series_id': station, 'horizon_hours': horizon, 'verified_test_rows': len(predicted)})
    destination = report_path.parent / 'results-audit.json'
    destination.write_text(json.dumps({'status': 'passed', 'report_sha256': sha256(report_path),
        'pipeline_code_sha256': {name: sha256(ROOT / 'training/python' / name) for name in (
            'environmental_sources.py', 'train_environmental.py', 'predict_environmental.py')},
        'checks': ['raw hashes', 'target and input row identities', 'publication-aware causal joins',
                   'chronological partition counts', 'validation-only selection', 'four candidate MAE/RMSE', 'model hashes'],
        'models': verified}, indent=2) + '\n', encoding='utf-8')
    print('Verified', len(verified), 'station/horizon experiments and', sum(r['verified_test_rows'] for r in verified), 'test predictions')


if __name__ == '__main__':
    main()
