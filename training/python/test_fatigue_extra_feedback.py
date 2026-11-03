import unittest

import numpy as np
import pandas as pd

from fatigue_extra_feedback import feedback_row


class ExtraFeedbackTests(unittest.TestCase):
    def fixtures(self):
        start = pd.Timestamp("2026-01-01", tz="UTC")
        task = {"label": "ramp", "start_time": start.isoformat(), "end_time": (start+pd.Timedelta(minutes=20)).isoformat()}
        session = {"start_time": (start-pd.Timedelta(minutes=15)).isoformat(), "tasks": [task]}
        frame = pd.DataFrame({"time": [start+pd.Timedelta(minutes=m) for m in (-2, 0, 5, 6, 8)],
                              "borg_scale": [0, 0, 2, 3, 4], "task": [0, 1, 1, 1, 1],
                              "task_label": ["rest", "ramp", "ramp", "ramp", "ramp"]})
        return start, task, session, frame

    def test_onset_is_real_target_context_with_previous_rest_input(self):
        start, task, session, frame = self.fixtures()
        row = feedback_row(frame, session, task, start)
        self.assertEqual(row["prior_borg"], 0.)
        self.assertEqual(row["prior_age_minutes"], 2.)
        self.assertEqual(row["prior_in_current_task"], 0)
        self.assertEqual(row["prior_count_current_task"], 0)
        self.assertEqual(row["elapsed_minutes"], 0.)

    def test_current_and_future_truth_never_change_inputs(self):
        start, task, session, frame = self.fixtures()
        now = start+pd.Timedelta(minutes=6)
        before = feedback_row(frame, session, task, now)
        frame.loc[frame["time"].ge(now), "borg_scale"] = 10
        after = feedback_row(frame, session, task, now)
        self.assertEqual(list(before), list(after))
        np.testing.assert_allclose(list(before.values()), list(after.values()), rtol=0, atol=0, equal_nan=True)

    def test_no_earlier_observation_is_not_assumed_zero(self):
        start, task, session, frame = self.fixtures()
        self.assertIsNone(feedback_row(frame[frame["time"].ge(start)], session, task, start))


if __name__ == "__main__":
    unittest.main()
