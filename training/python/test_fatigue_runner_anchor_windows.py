import unittest

import numpy as np
import pandas as pd

from fatigue_runner_anchor_windows import anchor_time
from fatigue_runner_windows import BIN_NS, LENGTH, dimensionless_window


class PriorAnchorWindowTests(unittest.TestCase):
    def fixture(self):
        query = {"row_key": "query", "group_key": "person", "prior_borg": 3., "prior_age_minutes": 5., "prior_in_current_task": 1, "label": "unknown current outcome"}
        source = {"row_key": "query", "group_key": "person", "response_time": "2025-01-01T00:10:00Z", "task_start": "2025-01-01T00:00:00Z"}
        calibration = {"row_key": "query", "group_key": "person", "prediction_time": source["response_time"],
            "previous_observed_reports": [{"response_time": "2025-01-01T00:05:00Z", "observed_borg": 3.}]}
        return query, source, calibration

    def test_actual_report_clock_is_used_without_reading_the_current_outcome(self):
        query, source, calibration = self.fixture()
        expected = pd.Timestamp("2025-01-01T00:05:00Z").value
        self.assertEqual(anchor_time(query, source, calibration), expected)
        self.assertEqual(anchor_time({k: v for k, v in query.items() if k != "label"}, source, calibration), expected)
        self.assertEqual(anchor_time({**query, "label": -1e12}, source, calibration), expected)

    def test_current_future_or_mismatched_prior_records_are_rejected(self):
        query, source, calibration = self.fixture()
        for changes in [{"prior_age_minutes": 4.}, {"prior_borg": 4.}, {"row_key": "other"}, {"group_key": "other"}]:
            with self.assertRaises(ValueError):
                anchor_time({**query, **changes}, source, calibration)
        for time in [source["response_time"], "2025-01-01T00:11:00Z"]:
            bad = {**calibration, "previous_observed_reports": [{"response_time": time, "observed_borg": 3.}]}
            with self.assertRaises(ValueError):
                anchor_time(query, source, bad)

    def test_reference_window_never_uses_sensors_recorded_after_the_prior_report(self):
        times = np.arange(2*LENGTH)*BIN_NS
        rng = np.random.default_rng(1)
        values = rng.normal(size=(len(times), 5))
        values[:, 4] += 9.8
        expected = dimensionless_window(times, values, LENGTH*BIN_NS, 0)
        values[LENGTH:] = 1e12
        np.testing.assert_array_equal(dimensionless_window(times, values, LENGTH*BIN_NS, 0), expected)

    def test_reference_before_the_current_task_remains_an_empty_retained_input(self):
        times = np.arange(LENGTH)*BIN_NS
        windows = dimensionless_window(times, np.ones((LENGTH, 5)), 100*BIN_NS, 110*BIN_NS)
        self.assertEqual(windows.shape, (6, LENGTH))
        self.assertFalse(windows.any())


if __name__ == "__main__":
    unittest.main()
