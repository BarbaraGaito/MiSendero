"""Chronological feedback and physiological pairing must exclude the target."""
import unittest

import numpy as np
import pandas as pd

from fatigue_dynamics import complete_signal_at, feedback_dynamics, physiological_calibration


class FeedbackDynamicsTests(unittest.TestCase):
    def setUp(self):
        self.start = pd.Timestamp("2020-01-01T12:00:00Z")
        self.now = self.start + pd.Timedelta(minutes=10)
        self.task = {"start_time": self.start.isoformat(), "end_time": (self.start + pd.Timedelta(minutes=20)).isoformat(), "label": "stairs"}
        self.reports = pd.DataFrame({"time": [self.start + pd.Timedelta(minutes=i) for i in (-20, 0, 3, 6, 9, 10, 12)],
                                     "borg_scale": [9., 1., 2., 3., 3., 5., 8.], "task": [1] * 7, "task_label": ["stairs"] * 7})

    def test_current_future_and_other_session_responses_never_change_dynamics(self):
        expected, past = feedback_dynamics(self.reports, [self.task], self.start, self.now, self.task)
        self.assertTrue((past["time"] <= self.now - pd.Timedelta(minutes=1)).all())
        self.assertEqual(expected["task_feedback_count"], 4)
        self.assertEqual(expected["task_feedback_delta_1"], 0.)
        altered = self.reports.copy()
        altered.loc[(altered["time"] >= self.now) | (altered["time"] < self.start), "borg_scale"] = 10.
        actual, _ = feedback_dynamics(altered, [self.task], self.start, self.now, self.task)
        np.testing.assert_allclose(list(expected.values()), list(actual.values()), equal_nan=True)

    def test_only_completed_prior_tasks_supply_comparison_inputs(self):
        prior = {"start_time": (self.start - pd.Timedelta(minutes=30)).isoformat(), "end_time": (self.start - pd.Timedelta(minutes=15)).isoformat(), "label": "stairs"}
        values, _ = feedback_dynamics(self.reports, [prior, self.task], self.start - pd.Timedelta(minutes=40), self.now, self.task)
        self.assertEqual(values["previous_task_at_similar_elapsed_last"], 9.)
        current_only, _ = feedback_dynamics(self.reports, [self.task], self.start, self.now, self.task)
        self.assertTrue(np.isnan(current_only["previous_task_at_similar_elapsed_last"]))

    def test_feedback_hr_requires_minutes_completed_before_that_past_report(self):
        index = pd.date_range(self.start - pd.Timedelta(minutes=2), periods=15, freq="min")
        signal = pd.Series(np.arange(15) + 80., index=index)
        self.assertEqual(complete_signal_at(signal, self.start), 81.)
        _, past = feedback_dynamics(self.reports, [self.task], self.start, self.now, self.task)
        expected = physiological_calibration(past, signal, 100., self.now, self.task)
        changed = signal.copy()
        changed.loc[changed.index >= past["time"].max()] = 230.
        actual = physiological_calibration(past, changed, 100., self.now, self.task)
        np.testing.assert_allclose(list(expected.values()), list(actual.values()), equal_nan=True)
        self.assertTrue(np.isnan(complete_signal_at(signal, self.start + pd.Timedelta(minutes=30))))


if __name__ == "__main__":
    unittest.main()
