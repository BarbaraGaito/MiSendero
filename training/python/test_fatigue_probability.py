"""Technical tests for native-class score mapping and calibration boundaries."""
import unittest

import numpy as np
import pandas as pd

from fatigue_probability import native_scores, sharpen, validate_calibration


class FixedScores:
    classes_ = np.array([-1, 0, 2])

    def predict_proba(self, x):
        return np.tile([.4, .5, .1], (len(x), 1))


class ProbabilityTests(unittest.TestCase):
    def test_transition_probabilities_are_added_when_clipping_maps_to_same_native_class(self):
        scores = native_scores(FixedScores(), np.zeros((2, 1)), np.array([0., 9.]))
        np.testing.assert_allclose(scores.sum(axis=1), 1.)
        self.assertAlmostEqual(scores[0, 0], .9)
        self.assertAlmostEqual(scores[0, 2], .1)
        self.assertAlmostEqual(scores[1, 8], .4)
        self.assertAlmostEqual(scores[1, 9], .5)
        self.assertAlmostEqual(scores[1, 10], .1)

    def test_temperature_changes_scores_without_changing_native_class_vocabulary(self):
        scores = np.array([[0., .2, .8]])
        transformed = sharpen(scores, .5)
        self.assertEqual(transformed.shape, scores.shape)
        np.testing.assert_allclose(transformed.sum(axis=1), 1.)
        self.assertEqual(transformed[0, 0], 0.)

    def test_current_future_expired_or_missing_borg_cannot_be_used_as_feedback(self):
        for value, age in [(3., 0.), (3., -1.), (3., 16.), (np.nan, 5.), (3.5, 5.)]:
            with self.subTest(value=value, age=age), self.assertRaises(ValueError):
                validate_calibration(pd.DataFrame({"prior_borg": [value], "prior_age_minutes": [age]}))


if __name__ == "__main__":
    unittest.main()
