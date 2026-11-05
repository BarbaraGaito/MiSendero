import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from fatigue_initialization_ensemble import InitializationEnsemble, decide, ensemble_predict
from fatigue_conditional_borg import make_source


class InitializationEnsembleTests(unittest.TestCase):
    def fixture(self):
        n = 24
        frame = pd.DataFrame({"prior_borg": np.tile([1., 2., 3., 4.], 6), "prior_age_minutes": 5., "elapsed_minutes": np.arange(n, dtype=float),
            "terrain_stairs": 0, "terrain_ramp": 1, "terrain_flat_trail": 0,
            "label": [f"Borg {i%4+1+(i//4)%2}" for i in range(n)], "row_key": [f"q{i}" for i in range(n)], "group_key": [f"p{i//4}" for i in range(n)]})
        features = ["prior_borg", "prior_age_minutes", "elapsed_minutes", "terrain_stairs", "terrain_ramp", "terrain_flat_trail"]
        core = {"algorithm": "mlp", "features": features, "target_mode": "change_from_prior",
            "params": {"hidden_layer_sizes": [4, 3], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}}
        view = {**core, "view_policy": "prefix", "view_mass": .6}
        pool = frame.rename(columns={"row_key": "target_row_key"}).assign(view_key=[f"v{i}" for i in range(n)], prefix_only=True, prior_age_minutes=10.)
        return frame, pool, frame.iloc[:0].copy(), {"core": core, "view": view}

    def test_native_mass_vote_ties_and_original_point_control_have_distinct_defined_decisions(self):
        points = np.array([[3, 5], [4, 6], [4, 5]])
        scores = np.eye(11)[points]
        np.testing.assert_array_equal(ensemble_predict(scores, points, [4, 4], "majority_vote", 2), ["Borg 4", "Borg 5"])
        np.testing.assert_array_equal(ensemble_predict(scores, points, [4, 4], "mean_probability", 3), ["Borg 4", "Borg 5"])
        np.testing.assert_array_equal(ensemble_predict(scores, points, [4, 4], "point_control", 1), ["Borg 3", "Borg 5"])
        with self.assertRaisesRegex(ValueError, "conserve"):
            ensemble_predict(scores*.5, points, [4, 4], "mean_probability", 3)
        with self.assertRaises(ValueError):
            decide(scores[0], [-1, 4])

    def test_original_seed_matches_source_and_other_initializations_keep_report_weight(self):
        frame, pool, extra, specifications = self.fixture()
        for family in ["core", "view"]:
            source = make_source(frame, pool, family, specifications)
            c = {"family": family, "members": 3, "method": "mean_probability"}
            model = InitializationEnsemble(c).fit(frame, pool, extra, specifications, source)
            expected = np.clip(source["classifier"].predict(source["preprocessor"].transform(frame[source["features"]])).astype(int)+frame.prior_borg.to_numpy(int), 0, 10)
            probabilities, points = model.member_scores(frame)
            np.testing.assert_array_equal(points[0], expected)
            np.testing.assert_allclose(probabilities.sum(axis=2), 1., atol=1e-12)
            self.assertAlmostEqual(model.training_summary["total_supervision_weight"], len(frame))
            self.assertEqual([r["seed"] for r in model.training_diagnostics], [42, 0, 1])

    def test_inference_and_reload_need_no_current_labels_identifiers_or_history_pool(self):
        frame, pool, extra, specifications = self.fixture()
        c = {"family": "core", "members": 3, "method": "mean_probability"}
        model = InitializationEnsemble(c).fit(frame, pool, extra, specifications)
        expected = model.predict(frame)
        np.testing.assert_array_equal(model.predict(frame[model.features]), expected)
        np.testing.assert_array_equal(model.predict(frame.assign(label="unknown", row_key="unused", group_key="unused")), expected)
        self.assertEqual(set(vars(model)), {"candidate", "features", "preprocessing", "training_summary", "models", "training_diagnostics"})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"ensemble.joblib"
            joblib.dump(model, path)
            np.testing.assert_array_equal(joblib.load(path).predict(frame[model.features]), expected)

    def test_template_from_a_different_fit_and_excluded_view_outcomes_cannot_enter_fitting(self):
        frame, pool, extra, specifications = self.fixture()
        fitting = frame.iloc[:12]
        source = make_source(fitting, pool, "view", specifications)
        c = {"family": "view", "members": 3, "method": "mean_probability"}
        with self.assertRaisesRegex(ValueError, "different fitting cases"):
            InitializationEnsemble(c).fit(frame, pool, extra, specifications, source)
        poison = pool.copy()
        poison.loc[~poison.target_row_key.isin(fitting.row_key), "label"] = "unavailable held outcome"
        clean = InitializationEnsemble(c).fit(fitting, pool, extra, specifications, source)
        changed = InitializationEnsemble(c).fit(fitting, poison, extra, specifications, source)
        np.testing.assert_array_equal(clean.predict(frame), changed.predict(frame))


if __name__ == "__main__":
    unittest.main()
