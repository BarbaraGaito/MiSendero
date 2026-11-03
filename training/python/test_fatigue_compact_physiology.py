import tempfile
import unittest
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from fatigue_compact_physiology import HR, SCORES, CompactPhysiologyBorg, compact_scores
from fatigue_runner_transfer import FrozenRunnerEncoder, encoder_plan


class ScalarEncoder:
    def extract(self, windows):
        result = np.zeros((len(windows), 20), dtype=np.float32)
        result[:, 16] = windows[:, :3].mean(axis=(1, 2))
        result[:, 17:] = windows[:, 3:].mean(axis=2)
        return result


class CompactPhysiologyTests(unittest.TestCase):
    def windows(self, n, value):
        return np.concatenate((np.full((n, 3, 256), value, dtype=np.float32), np.ones((n, 3, 256), dtype=np.float32)), axis=1)

    def frame(self, n):
        return pd.DataFrame({"prior_borg": np.resize([1., 2., 3., 4.], n), "prior_age_minutes": 5., "elapsed_minutes": np.arange(n, dtype=float),
            "hr_last": np.arange(n, dtype=float)+100, "hr_change_after_prior": 4., "hr_recent_slope": 1.,
            "label": [f"Borg {i%4+1+(i//4)%2}" for i in range(n)], "row_key": [f"q{i}" for i in range(n)]})

    def test_genuine_zero_and_missing_motion_are_not_the_same_predictor_value(self):
        frame = self.frame(3)
        current, reference = self.windows(3, 0.), self.windows(3, 0.)
        current[1], reference[2] = 0., 0.
        result = compact_scores(frame, current, reference, ScalarEncoder())
        self.assertEqual(result.loc[0, "compact_current_logit"], 0.)
        self.assertEqual(result.loc[0, "compact_logit_delta"], 0.)
        self.assertTrue(np.isnan(result.loc[1, "compact_current_logit"]))
        self.assertTrue(np.isnan(result.loc[1, "compact_logit_delta"]))
        self.assertTrue(np.isnan(result.loc[2, "compact_logit_delta_per_minute"]))
        np.testing.assert_array_equal(result["compact_pair_available"], [1., 0., 0.])
        self.assertEqual(len(result), 3)

    def test_compact_rate_uses_actual_eligible_prior_age_and_ignores_current_outcome(self):
        frame = self.frame(2)
        current, reference = self.windows(2, 3.), self.windows(2, 1.)
        expected = compact_scores(frame, current, reference, ScalarEncoder())[SCORES]
        np.testing.assert_allclose(expected["compact_logit_delta_per_minute"], .4)
        np.testing.assert_array_equal(compact_scores(frame.assign(label="unknown", row_key="unused"), current, reference, ScalarEncoder())[SCORES], expected)
        with self.assertRaises(ValueError):
            compact_scores(frame.assign(prior_age_minutes=0.), current, reference, ScalarEncoder())
        with self.assertRaises(ValueError):
            compact_scores(frame, current, reference[:1], ScalarEncoder())

    def test_native_models_preserve_missing_hr_cases_source_parameters_and_reload(self):
        frame, current = self.frame(16), self.windows(16, 0.)
        current[:, :3] = np.random.default_rng(7).normal(size=(16, 3, 256))
        reference = current[::-1].copy()
        source = FrozenRunnerEncoder(encoder_plan()[0]).fit(current, np.tile([0, 1], 8), np.repeat("006", 16))
        before = {k: v.clone() for k, v in source.network.state_dict().items()}
        frame.loc[0, HR[1:]] = np.nan
        core = {"algorithm": "mlp", "features": ["prior_borg", "prior_age_minutes", "elapsed_minutes"], "target_mode": "change_from_prior",
            "params": {"hidden_layer_sizes": [4], "solver": "lbfgs", "alpha": 10., "max_iter": 60}}
        for mode in ("hr_only", "gait_hr"):
            c = {"id": "fixture", "mode": mode, "member": "core"}
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = CompactPhysiologyBorg(c, source if mode == "gait_hr" else None).fit(frame, current, reference, {"core": core})
            expected = model.predict(frame, current, reference)
            self.assertEqual(expected.shape, (16,))
            np.testing.assert_array_equal(model.predict(frame[model.input_features], current, reference), expected)
            self.assertTrue(all(torch.equal(value, source.network.state_dict()[key]) for key, value in before.items()))
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/"compact.joblib"
                joblib.dump(model, path)
                np.testing.assert_array_equal(joblib.load(path).predict(frame.assign(label="unknown", row_key="unused"), current, reference), expected)

    def test_current_label_or_identity_cannot_enter_a_malformed_base_feature_specification(self):
        frame = self.frame(2)
        c = {"id": "fixture", "mode": "hr_only", "member": "core"}
        for forbidden in ["label", "row_key", "group_key"]:
            with self.assertRaisesRegex(ValueError, "cannot be predictors"):
                CompactPhysiologyBorg(c).fit(frame, None, None, {"core": {"features": ["prior_borg", forbidden]}})


if __name__ == "__main__":
    unittest.main()
