import unittest

import numpy as np
import pandas as pd

from fatigue_online_calibration import adapt_one, history_indices, shifted_scores


class OnlineCalibrationTests(unittest.TestCase):
    def test_native_shift_scores_preserve_probability_when_clipped(self):
        scores = np.zeros((1, 11))
        scores[0, [0, 1]] = [.4, .6]
        values = shifted_scores(scores)
        np.testing.assert_allclose(values.sum(axis=2), 1.)
        self.assertEqual(values[0, 0, 0], 1.)
        self.assertEqual(values[0, 4, 3], .6)

    def test_feedback_indices_exclude_future_current_other_person_and_other_session(self):
        now = pd.Timestamp("2020-01-01T12:10Z")
        meta = pd.DataFrame({"group_key": ["a", "a", "a", "b", "a"],
                             "session_start": [now.floor("h")] * 4 + [now - pd.Timedelta(hours=3)],
                             "task_start": [now.floor("h")] * 5,
                             "response_time": [now-pd.Timedelta(minutes=5), now, now+pd.Timedelta(minutes=5),
                                               now-pd.Timedelta(minutes=5), now-pd.Timedelta(minutes=6)]})
        indices = history_indices(meta, "session")
        self.assertEqual(indices[1].tolist(), [0])
        self.assertEqual(indices[0].tolist(), [])

    def test_personal_correction_consumes_only_explicit_past_observations(self):
        current = np.full(11, .01)
        current[3] = .9
        previous = np.tile(current, (3, 1))
        recipe = {"kind": "personal_bias_posterior", "prior_std": 1., "strength": 1., "decay": 1.}
        result = adapt_one(current, previous, [4, 4, 4], recipe)
        self.assertEqual(result.argmax(), 4)
        self.assertAlmostEqual(result.sum(), 1.)
        np.testing.assert_array_equal(adapt_one(current, [], [], recipe), current)
        with self.assertRaises(ValueError):
            adapt_one(current, previous, [4, 4.5, 4], recipe)


if __name__ == "__main__":
    unittest.main()
