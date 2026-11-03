"""Technical fixtures for causal sensor features; never training observations."""
import unittest

import numpy as np
import pandas as pd

from fatigue_features import causal_statistics


class FatigueFeatureTests(unittest.TestCase):
    def setUp(self):
        self.start = pd.Timestamp("2020-01-01T12:00:00Z")
        self.times = pd.date_range(self.start - pd.Timedelta(minutes=5), periods=20, freq="min")
        self.values = pd.Series(np.arange(20, dtype=float) + 70, index=self.times)

    def test_future_measurements_and_incomplete_minutes_cannot_change_predictors(self):
        response = self.start + pd.Timedelta(minutes=5, seconds=30)
        original = causal_statistics(self.values, response, self.start, self.times[0])
        modified = self.values.copy()
        modified.loc[modified.index + pd.Timedelta(minutes=1) > response] = 1000000
        changed = causal_statistics(modified, response, self.start, self.times[0])
        self.assertEqual(original, changed)
        self.assertEqual(original["last"], 79.)

    def test_baseline_is_computed_only_from_completed_pre_task_minutes(self):
        response = self.start + pd.Timedelta(minutes=5)
        result = causal_statistics(self.values, response, self.start, self.times[0])
        self.assertEqual(result["baseline_mean"], 72.)
        self.assertEqual(result["last"], 79.)
        self.assertEqual(result["delta_baseline"], 7.)
        self.assertEqual(result["history_count"], 5)

    def test_missing_or_stale_reading_is_not_fabricated_or_carried_forward(self):
        sparse = self.values.iloc[:8]
        result = causal_statistics(sparse, self.start + pd.Timedelta(minutes=10), self.start, self.times[0])
        self.assertTrue(np.isnan(result["last"]))
        self.assertTrue(np.isnan(result["recent_mean"]))
        self.assertTrue(np.isnan(result["delta_baseline"]))
        self.assertEqual(result["history_count"], 3)

    def test_baseline_start_excludes_prior_work(self):
        response = self.start + pd.Timedelta(minutes=5)
        result = causal_statistics(self.values, response, self.start, self.start - pd.Timedelta(minutes=2))
        self.assertEqual(result["baseline_mean"], 73.5)


if __name__ == "__main__":
    unittest.main()
