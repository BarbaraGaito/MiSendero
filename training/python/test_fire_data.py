"""Software fixtures only, separate from all scientific fire observations."""
from datetime import timedelta
import csv
import gzip
from pathlib import Path
import tempfile
import unittest
import pandas as pd

from environmental_sources import EXCLUDED_STATIONS, STATIONS, fetch_station, utc
from fire_sources import valid_land_label, tile_at
from fire_features import examples, inputs, load_cells, partitions
from predict_fire import visualization_gate


class FireDataTests(unittest.TestCase):
    def test_only_independently_observed_land_classes_can_supply_labels(self):
        self.assertEqual(valid_land_label(5, 2), 0)
        self.assertEqual(valid_land_label(8, 6), 1)
        self.assertEqual(valid_land_label(9, 2), 1)
        for mask in (0, 1, 2, 3, 4, 6, 7):
            self.assertIsNone(valid_land_label(mask, 2))
        for qa in (0, 1, 3, 4, 5, 7):
            self.assertIsNone(valid_land_label(5, qa))

    def history(self):
        start = utc('2022-01-01T00:00:00Z')
        return [{'day': start + timedelta(days=i), 'available_at': start + timedelta(days=i + 10),
            'label': int(i == 2), 'item_id': f'fixture-{i}'} for i in range(25)]

    def test_later_published_daily_layer_cannot_enter_the_history(self):
        history = self.history()
        issue = utc('2022-01-16T00:00:00Z')
        with self.assertRaisesRegex(ValueError, 'Future'):
            inputs(history[:8], issue, -31, -64)
        available = [r for r in history if r['available_at'] <= issue]
        x = inputs(available, issue, -31, -64)
        self.assertEqual(x['latest_age_days'], 9)
        self.assertEqual(x['latest_fire'], 0)
        self.assertIsNone(inputs(available, issue + timedelta(days=50), -31, -64))

    def test_daily_target_covers_the_24_hours_after_issue_and_is_not_an_input(self):
        records = self.history()
        cells = {'fixture': {'region': 'fixture', 'tile': 'h12v11', 'pixel_id': 'fixture',
            'latitude': -31, 'longitude': -64, 'records': records}}
        rows, _ = examples(cells, {'maximum_latest_age_days': 45})
        row = next(r for r in rows if r['issued_at'] == '2022-01-16T00:00:00+00:00')
        self.assertEqual(utc(row['target_at']) - utc(row['issued_at']), timedelta(hours=24))
        self.assertEqual(row['target_item_id'], 'fixture-15')
        self.assertNotIn(row['target_item_id'], row['input_item_ids'])
        self.assertTrue(all(utc(v) <= utc(row['issued_at']) for v in row['input_available_at']))

    def test_whole_tile_and_late_labels_are_excluded_from_training_selection(self):
        plan = {'training_target_before': '2023-01-01T00:00:00Z', 'validation_target_before': '2023-07-01T00:00:00Z',
            'test_target_before': '2024-01-01T00:00:00Z', 'geographic_holdout_tiles': ['h12v13']}
        frame = pd.DataFrame([
            {'tile': 'h12v11', 'issued_at': '2022-12-01T00:00:00Z', 'target_at': '2022-12-02T00:00:00Z', 'target_available_at': '2022-12-15T00:00:00Z'},
            {'tile': 'h12v11', 'issued_at': '2022-12-20T00:00:00Z', 'target_at': '2022-12-21T00:00:00Z', 'target_available_at': '2023-01-15T00:00:00Z'},
            {'tile': 'h12v13', 'issued_at': '2023-02-01T00:00:00Z', 'target_at': '2023-02-02T00:00:00Z', 'target_available_at': '2023-02-15T00:00:00Z'},
            {'tile': 'h12v11', 'issued_at': '2023-02-01T00:00:00Z', 'target_at': '2023-02-02T00:00:00Z', 'target_available_at': '2023-02-15T00:00:00Z'}])
        split = partitions(frame, plan)
        self.assertEqual(split['train'].tolist(), [True, False, False, False])
        self.assertEqual(split['validation'].tolist(), [False, False, False, True])
        self.assertEqual(split['geographic_test'].tolist(), [False, False, True, False])

    def test_excluded_river_series_cannot_be_fetched_or_reactivated(self):
        self.assertNotIn(32926, STATIONS)
        self.assertIn(32926, EXCLUDED_STATIONS)
        with self.assertRaises(ValueError):
            fetch_station(32926)
        self.assertEqual(tile_at(-41.1904696, -71.4612884), 'h12v13')

    def test_overlapping_packages_deduplicate_identical_values_and_drop_conflicts(self):
        row = {'region': 'software fixture', 'tile': 'h12v11', 'row': 1, 'col': 1, 'latitude': -31, 'longitude': -64,
            'observed_date': '2022-01-01', 'available_at': '2022-01-12T00:00:00Z', 'fire_mask': 5, 'qa': 2, 'item_id': 'fixture-one'}
        duplicate = row | {'item_id': 'fixture-two', 'available_at': '2022-01-10T00:00:00Z'}
        cloudy = row | {'observed_date': '2022-01-02', 'fire_mask': 4}
        conflicting = cloudy | {'fire_mask': 5, 'item_id': 'fixture-three'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'software.csv.gz'
            with gzip.open(path, 'wt', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                writer.writerows([row, duplicate, cloudy, conflicting])
            cells, counts = load_cells(path)
            records = cells['h12v11:1:1']['records']
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['item_id'], 'fixture-two')
            self.assertEqual(counts['identical_duplicate_pixel_days'], 1)
            self.assertEqual(counts['conflicting_duplicate_pixel_days'], 1)

    def test_private_candidate_probabilities_cannot_bypass_a_failed_evaluation_gate(self):
        baselines = {name: {'positive_observations': 10, 'pr_auc_average_precision': .1, 'brier': .05}
            for name in ('training_prevalence', 'seasonal_training_prevalence', 'persistence')}
        scores = baselines | {'random_forest': {'positive_observations': 10, 'pr_auc_average_precision': .3, 'brier': .04}}
        report = {'selection': 'random_forest', 'test': {'temporal_test': scores, 'geographic_test': dict(scores)}}
        self.assertTrue(visualization_gate(report))
        report['test']['geographic_test']['random_forest'] = {'positive_observations': 10, 'pr_auc_average_precision': .3, 'brier': .2}
        self.assertFalse(visualization_gate(report))


if __name__ == '__main__':
    unittest.main()
