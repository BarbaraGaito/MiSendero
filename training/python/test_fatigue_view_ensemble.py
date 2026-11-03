import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from fatigue_probability import native_scores
from fatigue_view_ensemble import MEMBERS, ViewProbabilityEnsemble, fuse_scores, native_labels, plan, prepare_frame


class StubProbabilities:
    classes_ = np.asarray([-2, 0, 3])

    def predict_proba(self, values):
        return np.tile([.2, .3, .5], (len(values), 1))


class ViewEnsembleTests(unittest.TestCase):
    def test_delta_mass_is_preserved_at_both_native_boundaries(self):
        values = native_scores(StubProbabilities(), np.zeros((2, 1)), np.asarray([0., 10.]))
        np.testing.assert_allclose(values.sum(axis=1), [1., 1.])
        self.assertEqual(values[0, 0], .5)
        self.assertEqual(values[0, 3], .5)
        self.assertEqual(values[1, 8], .2)
        self.assertEqual(values[1, 10], .8)

    def test_zero_weight_members_cannot_influence_a_recipe(self):
        selected = np.eye(11)[[2, 7]]
        recipe = {"kind": "arithmetic", "weights": [0., 1., 0.], "temperature": 1.}
        np.testing.assert_array_equal(fuse_scores({"cat": selected}, recipe), selected)

    def test_mixtures_keep_all_eleven_values_and_reject_invalid_distributions(self):
        first, second = np.eye(11)[[2, 8]], np.eye(11)[[4, 6]]
        scores = {"core": first, "cat": second, "view": (first+second)/2}
        for kind in ("arithmetic", "geometric"):
            result = fuse_scores(scores, {"kind": kind, "weights": [.25, .5, .25], "temperature": 1.})
            self.assertEqual(result.shape, (2, 11))
            np.testing.assert_allclose(result.sum(axis=1), [1., 1.], rtol=0, atol=1e-12)
        invalid = {**scores, "cat": -second}
        with self.assertRaisesRegex(ValueError, "probabilities"):
            fuse_scores(invalid, {"kind": "arithmetic", "weights": [0., 1., 0.], "temperature": 1.})
        self.assertEqual(len(plan()), 54)

    def test_terrain_is_derived_from_task_context_and_contradictions_fail(self):
        frame = pd.DataFrame({"prior_borg": [1.], "prior_age_minutes": [5.], "terrain_flat_trail": [0], "terrain_stairs": [0], "terrain_ramp": [1]})
        self.assertEqual(prepare_frame(frame).current_terrain.tolist(), ["ramp"])
        self.assertNotIn("current_terrain", frame)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            prepare_frame(frame.assign(current_terrain="stairs"))

    def test_serialized_inference_uses_features_without_current_target_or_history_pool(self):
        frame = pd.DataFrame({"prior_borg": np.tile([0., 1., 2., 3.], 8), "prior_age_minutes": 5.,
                              "elapsed_minutes": np.arange(1., 33.), "terrain_flat_trail": 0, "terrain_stairs": 0, "terrain_ramp": 1,
                              "row_key": [f"q{i}" for i in range(32)], "group_key": [f"p{i//4}" for i in range(32)],
                              "label": [f"Borg {i%4+(i//4)%2+1}" for i in range(32)]})
        columns = ["prior_borg", "prior_age_minutes", "elapsed_minutes", "terrain_flat_trail", "terrain_stairs", "terrain_ramp"]
        core = {"features": columns, "algorithm": "mlp", "target_mode": "change_from_prior",
                "params": {"hidden_layer_sizes": [4], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}}
        cat = {"features": ["prior_borg", "prior_age_minutes", "elapsed_minutes", "current_terrain"],
               "target_mode": "change_from_prior", "iterations": 5, "depth": 2, "l2_leaf_reg": 30.}
        view = {**core, "view_policy": "prefix", "view_mass": .3}
        pool = frame.rename(columns={"row_key": "target_row_key"}).assign(prefix_only=True, view_key=[f"v{i}" for i in range(32)], prior_age_minutes=10.)
        recipe = {"kind": "arithmetic", "weights": [.25, .5, .25], "temperature": 1.}
        model = ViewProbabilityEnsemble(recipe, {"core": core, "cat": cat, "view": view}).fit(frame, pool)
        expected = model.predict(frame)
        changed = frame.copy()
        changed["label"], changed["group_key"], changed["row_key"] = "unavailable", "unused", "unused"
        np.testing.assert_array_equal(model.predict(changed), expected)
        np.testing.assert_array_equal(model.predict(frame[columns]), expected)
        self.assertEqual(set(vars(model)), {"candidate", "specifications", *MEMBERS})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"model.joblib"
            joblib.dump(model, path)
            restored = joblib.load(path)
            np.testing.assert_array_equal(restored.predict(frame[columns]), expected)
        for name in MEMBERS:
            point = model.point_predictions(frame)[name]
            model.candidate = {"kind": "point_control", "member": name}
            np.testing.assert_array_equal(model.predict(frame), point)


if __name__ == "__main__":
    unittest.main()
