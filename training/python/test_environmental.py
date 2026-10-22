"""Software fixtures for causal joins; never scientific training observations."""
from datetime import timedelta
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from environmental_sources import FEATURES, cached_json, examples, inputs, observations, satellite_status, sha256, utc


class EnvironmentalCausalityTests(unittest.TestCase):
    def history(self):
        origin = utc('2025-01-01T00:00:00Z')
        return [dict(observed_at=origin + timedelta(hours=i),
                     available_at=origin + timedelta(hours=i, minutes=10),
                     level=float(i), source_row_id=i) for i in range(15)]

    def test_features_reject_future_publication(self):
        history = self.history()[:4]
        history[-1]['available_at'] += timedelta(hours=5)
        with self.assertRaisesRegex(ValueError, 'Future'):
            inputs(history, utc('2025-01-01T04:00:00Z'))

    def test_stale_and_sparse_history_abstains(self):
        self.assertIsNone(inputs(self.history()[:3], utc('2025-01-01T04:00:00Z')))
        self.assertIsNone(inputs(self.history()[:4], utc('2025-01-01T10:00:00Z')))
        history = self.history()[:4]
        history[0]['observed_at'] -= timedelta(hours=60)
        self.assertIsNone(inputs(history, utc('2025-01-01T04:00:00Z')))

    def test_delayed_publication_not_included_in_predictors(self):
        history = self.history()
        history[3]['available_at'] += timedelta(hours=6)
        rows, _ = examples(history, 3)
        row = next(r for r in rows if r['issued_at'] == '2025-01-01T05:00:00+00:00')
        self.assertNotIn(3, row['source_row_ids'])
        self.assertEqual(row['source_row_ids'], [0, 1, 2, 4])
        self.assertEqual(row['baseline'], 4)
        self.assertEqual(row['observed'], 8)
        self.assertEqual(row['target_source_row_id'], 8)
        self.assertTrue(all(feature in row for feature in FEATURES))

    def test_no_interpolation_when_exact_target_absent(self):
        history = [r for r in self.history() if r['source_row_id'] != 8]
        rows, rejected = examples(history, 3)
        self.assertFalse(any(r['issued_at'] == '2025-01-01T05:00:00+00:00' for r in rows))
        self.assertGreater(rejected['no_exact_observed_target'], 0)
        for row in rows:
            self.assertEqual(utc(row['target_at']) - utc(row['issued_at']), timedelta(hours=3))

    def test_measurements_remove_conflicts_invalid_values_and_unknown_availability(self):
        row = dict(id=1, series_id=42, timestart='2025-01-01T00:00:00Z',
                   timeupdate='2025-01-01T00:10:00Z', valor=1.0)
        duplicate = row | {'id': 2, 'timeupdate': '2025-01-01T00:20:00Z'}
        conflict = row | {'id': 3, 'valor': 2}
        valid, counts = observations({'id': 42, 'observaciones': [row, duplicate]})
        self.assertEqual(valid[0]['source_row_id'], 1)
        self.assertEqual(counts['identical_duplicate_timestamp'], 1)
        valid, counts = observations({'id': 42, 'observaciones': [row, conflict]})
        self.assertEqual(valid, [])
        self.assertEqual(counts['conflicting_duplicate_timestamp'], 2)
        invalid = [row | {'valor': float('nan')}, row | {'valor': True},
                   row | {'timeupdate': None}, row | {'series_id': 99}]
        self.assertEqual(observations({'id': 42, 'observaciones': invalid})[0], [])

    def test_timezone_required_and_satellite_modules_remain_non_operational(self):
        with self.assertRaises(ValueError):
            utc('2025-01-01T00:00:00')
        for status in satellite_status().values():
            self.assertIn(status['status'], ('no_data', 'not_approved'))
            self.assertIn('reason', status)

    def test_refresh_preserves_original_bytes_and_changed_cache_fails_integrity(self):
        with tempfile.TemporaryDirectory() as directory, patch('environmental_sources.RAW', Path(directory)):
            original = Path(directory) / 'fixture.json'
            original.write_bytes(b'{"fixture": 1}')
            digest = sha256(original)
            with patch('environmental_sources.urllib.request.urlopen', return_value=io.BytesIO(b'{"fixture": 2}')):
                value, source = cached_json('https://example.invalid/software-fixture', 'fixture.json', refresh=True)
            self.assertEqual(value, {'fixture': 2})
            self.assertEqual((Path(directory) / 'archive' / f'{digest}.json').read_bytes(), b'{"fixture": 1}')
            original.write_bytes(b'{"tampered": true}')
            with self.assertRaisesRegex(ValueError, 'hash changed'):
                cached_json('https://example.invalid/software-fixture', 'fixture.json')


if __name__ == '__main__':
    unittest.main()
