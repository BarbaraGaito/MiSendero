import unittest

import numpy as np

from diagnose_fatigue_mixture_capacity import maximum_true_margin


class MixtureCapacityTests(unittest.TestCase):
    def test_interior_mix_can_recover_a_class_that_no_member_selects(self):
        scores = np.zeros((3, 11))
        scores[:, 0] = .4
        scores[np.arange(3), [1, 2, 3]] = .6
        self.assertFalse(np.any(scores.argmax(axis=1) == 0))
        margin, status = maximum_true_margin(scores, 0)
        self.assertEqual(status, 0)
        self.assertAlmostEqual(margin, .2, places=10)

    def test_shared_wrong_ranking_cannot_be_fixed_by_convex_weights(self):
        scores = np.zeros((3, 11))
        scores[:, 0], scores[:, 1] = .1, .9
        margin, status = maximum_true_margin(scores, 0)
        self.assertEqual(status, 0)
        self.assertAlmostEqual(margin, -.8, places=10)
        log_margin, _ = maximum_true_margin(scores, 0, "geometric", 1.)
        self.assertLess(log_margin, 0.)

    def test_ties_are_only_optimistically_possible_not_a_correct_prediction(self):
        scores = np.zeros((3, 11))
        scores[:, 0], scores[:, 10] = .5, .5
        margin, status = maximum_true_margin(scores, 10)
        self.assertEqual(status, 0)
        self.assertAlmostEqual(margin, 0., places=10)
        self.assertTrue(np.all(scores.argmax(axis=1) == 0))


if __name__ == "__main__":
    unittest.main()
