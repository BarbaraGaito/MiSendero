"""Technical checks on minute coverage and cross-study participant separation."""
import unittest

import numpy as np
import pandas as pd

from fatigue_features import causal_statistics
from worker_fatigue import completed_minute_means
from public_sources import group_key


class WorkerFatigueTests(unittest.TestCase):
    def test_minute_aggregation_does_not_turn_samples_into_labeled_observations(self):
        frame = pd.DataFrame({"Time": np.arange(240) * 500, "HR_Processed": np.full(240, 80.)})
        result = completed_minute_means(frame, "HR_Processed", 30, 240)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.tolist(), [80., 80.])

    def test_sparse_and_invalid_sensor_minutes_are_left_missing(self):
        frame = pd.DataFrame({"Time": np.arange(120) * 500, "HR_Processed": np.full(120, 80.)})
        frame.loc[:15, "HR_Processed"] = -2
        self.assertTrue(completed_minute_means(frame, "HR_Processed", 30, 240).empty)
        self.assertTrue(completed_minute_means(frame.iloc[:50], "HR_Processed", 30, 240).empty)

    def test_minute_that_ends_after_repetition_cannot_predict_its_response(self):
        frame = pd.DataFrame({"Time": np.arange(240) * 500, "HR_Processed": np.repeat([80., 200.], 120)})
        signal = completed_minute_means(frame, "HR_Processed", 30, 240)
        stats = causal_statistics(signal, pd.Timedelta(seconds=90), pd.Timedelta(0), pd.Timedelta(0))
        self.assertEqual(stats["last"], 80.)
        self.assertEqual(stats["history_count"], 1)

    def test_empty_sensor_stream_has_no_invented_last_value(self):
        frame = pd.DataFrame({"Time": [0, 500], "HR_Processed": [-2, -2]})
        signal = completed_minute_means(frame, "HR_Processed", 30, 240)
        stats = causal_statistics(signal, pd.Timedelta(minutes=5), pd.Timedelta(0), pd.Timedelta(0))
        self.assertTrue(np.isnan(stats["last"]))
        self.assertEqual(stats["history_count"], 0)

    def test_equal_subject_numbers_from_different_studies_are_not_same_person(self):
        self.assertNotEqual(group_key("WorkerFatigue-participant:1"), group_key("GeoFatigue:p1"))


if __name__ == "__main__":
    unittest.main()
