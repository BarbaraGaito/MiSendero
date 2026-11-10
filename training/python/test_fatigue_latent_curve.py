import unittest

import numpy as np

from fatigue_latent_curve import GRID, pack_query, probabilities, predict_query


class LatentCurveTests(unittest.TestCase):
    def prior(self):
        return {"power": 1., "priors": {"ramp": {"mean": [1., 1.], "covariance": [[.1, 0.], [0., .025]]}}}

    def query(self):
        return {"terrain": "ramp", "elapsed_minutes": 10., "prior_borg": 2., "prior_age_minutes": 5., "history": [
            {"terrain": "ramp", "elapsed_minutes": 0., "observed_borg": 1., "age_minutes": 10.},
            {"terrain": "ramp", "elapsed_minutes": 5., "observed_borg": 2., "age_minutes": 5.}]}

    def recipe(self):
        return {"observation_sigma": .1, "prior_covariance_scale": 1., "memory_minutes": None}

    def test_quantized_curve_predicts_native_score_with_finite_probability_mass(self):
        packed = pack_query(self.query(), self.prior())
        p = probabilities(packed, self.recipe())
        self.assertEqual(len(p), 11)
        self.assertTrue(np.isfinite(p).all())
        self.assertAlmostEqual(float(p.sum()), 1.)
        self.assertEqual(predict_query(self.prior(), self.query(), self.recipe()), "Borg 3")
        self.assertEqual(packed["current"].shape, (len(GRID),))

    def test_current_target_is_not_a_prediction_input(self):
        query = self.query()
        a = predict_query(self.prior(), query, self.recipe())
        query["current_borg"] = 10.
        self.assertEqual(a, predict_query(self.prior(), query, self.recipe()))

    def test_repeated_terrain_is_not_mistaken_for_current_task(self):
        query = self.query()
        before = probabilities(pack_query(query, self.prior()), self.recipe())
        query["history"].insert(0, {"terrain": "ramp", "elapsed_minutes": 20., "age_minutes": 30., "observed_borg": 8.})
        after = probabilities(pack_query(query, self.prior()), self.recipe())
        np.testing.assert_array_equal(before, after)

    def test_future_stale_non_native_or_disordered_feedback_is_rejected(self):
        for age in (0., 16., float("nan")):
            query = self.query()
            query["prior_age_minutes"] = age
            with self.assertRaises(ValueError):
                pack_query(query, self.prior())
        query = self.query()
        query["history"][0]["age_minutes"] = 0.
        with self.assertRaises(ValueError):
            pack_query(query, self.prior())
        query = self.query()
        query["history"][0]["observed_borg"] = .5
        with self.assertRaises(ValueError):
            pack_query(query, self.prior())


if __name__ == "__main__":
    unittest.main()
