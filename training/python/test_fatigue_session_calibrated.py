"""Technical fixtures: causal personal calibration across task boundaries."""
import unittest

import numpy as np
import pandas as pd

from fatigue_session_calibrated import session_history_features


class SessionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.start = pd.Timestamp("2020-01-01T12:00:00Z")
        self.tasks = [{"start_time": self.start.isoformat(), "end_time": (self.start+pd.Timedelta(minutes=10)).isoformat(), "label": "flat_trail"},
                      {"start_time": (self.start+pd.Timedelta(minutes=12)).isoformat(), "end_time": (self.start+pd.Timedelta(minutes=22)).isoformat(), "label": "stairs"}]
        self.responses = pd.DataFrame({"time": [self.start+pd.Timedelta(minutes=i) for i in (-5, 0, 5, 10, 15, 17, 20)],
                                       "borg_scale": [9, 0, 2, 3, 4, 6, 7],
                                       "task_label": ["seated", "seated", "flat_trail", "flat_trail", "stairs", "stairs", "stairs"]})

    def test_current_and_future_ratings_cannot_change_personal_scale_features(self):
        now = self.start+pd.Timedelta(minutes=17)
        original, history = session_history_features(self.responses, self.tasks, self.start, now)
        changed = self.responses.copy()
        changed.loc[changed.time >= now, "borg_scale"] = 10
        modified, _ = session_history_features(changed, self.tasks, self.start, now)
        np.testing.assert_equal(list(original.values()), list(modified.values()))
        self.assertTrue((history.time < now).all())
        self.assertEqual(original["session_max"], 4.)

    def test_completed_task_scores_are_real_past_reports_not_future_task_targets(self):
        features, _ = session_history_features(self.responses, self.tasks, self.start, self.start+pd.Timedelta(minutes=17))
        self.assertEqual(features["completed_task_count"], 1)
        self.assertEqual(features["last_completed_first_borg"], 2.)
        self.assertEqual(features["last_completed_last_borg"], 3.)

    def test_previous_session_and_uncompleted_task_are_excluded(self):
        features, _ = session_history_features(self.responses, self.tasks, self.start, self.start+pd.Timedelta(minutes=7))
        self.assertEqual(features["session_count"], 2)
        self.assertEqual(features["session_max"], 2.)
        self.assertEqual(features["completed_task_count"], 0)


if __name__ == "__main__":
    unittest.main()
