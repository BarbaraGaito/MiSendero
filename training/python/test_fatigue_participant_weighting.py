import unittest

import numpy as np

from fatigue_participant_weighting import fitting_weights


class ParticipantWeightTests(unittest.TestCase):
    def test_each_participant_has_equal_loss_mass_at_unit_power(self):
        groups = np.asarray(["pilot"] * 8 + ["person"] * 2)
        w = fitting_weights(groups, 1.)
        self.assertAlmostEqual(w.sum(), len(groups))
        self.assertAlmostEqual(w[groups == "pilot"].sum(), w[groups == "person"].sum())
        self.assertTrue((w > 0).all())

    def test_control_is_unit_weight_and_names_do_not_affect_weights(self):
        groups = ["a", "a", "b", "b", "b"]
        np.testing.assert_array_equal(fitting_weights(groups, 0.), np.ones(5))
        np.testing.assert_array_equal(fitting_weights(groups, .5), fitting_weights(["x", "x", "y", "y", "y"], .5))

    def test_empty_or_invalid_strength_is_rejected(self):
        for power in (-1., float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                fitting_weights(["a"], power)
        with self.assertRaises(ValueError):
            fitting_weights([], 1.)


if __name__ == "__main__":
    unittest.main()
