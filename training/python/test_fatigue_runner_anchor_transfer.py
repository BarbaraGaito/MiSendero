import tempfile
import unittest
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from fatigue_runner_anchor_transfer import ADDED, AnchoredRunnerBorg, paired_features
from fatigue_runner_transfer import FrozenRunnerEncoder, encoder_plan


class DeterministicEncoder:
    def extract(self, windows):
        result = np.zeros((len(windows), 20), dtype=np.float32)
        result[:, :17] = windows[:, :3].mean(axis=(1, 2))[:, None]+np.arange(17)
        result[:, 17:] = windows[:, 3:].mean(axis=2)
        result[windows[:, 3:].sum(axis=(1, 2)) == 0, :17] = 0.
        return result


class AnchoredRunnerTests(unittest.TestCase):
    def windows(self, n, value):
        return np.concatenate((np.full((n, 3, 256), value, dtype=np.float32), np.ones((n, 3, 256), dtype=np.float32)), axis=1)

    def test_paired_change_is_neutral_when_either_observation_is_missing(self):
        current, prior = self.windows(3, 2.), self.windows(3, .5)
        prior[1], current[2] = 0., 0.
        result = paired_features(pd.DataFrame({"input": [1, 2, 3]}), current, prior, DeterministicEncoder())
        np.testing.assert_allclose(result.loc[0, ADDED[:17]].to_numpy(float), 1.5)
        np.testing.assert_array_equal(result.loc[1:, ADDED[:17]].to_numpy(), np.zeros((2, 17)))
        np.testing.assert_array_equal(result["runner_anchor_pair_available"], [1., 0., 0.])
        self.assertEqual(len(result), 3)

    def test_source_features_never_consult_current_label_or_query_identifier(self):
        frame = pd.DataFrame({"label": ["unknown", "unknown"], "row_key": ["a", "b"]})
        windows = self.windows(2, 1.)
        expected = paired_features(frame, windows, windows, DeterministicEncoder())[ADDED]
        actual = paired_features(frame.assign(label=-1e12, row_key="unused"), windows, windows, DeterministicEncoder())[ADDED]
        np.testing.assert_array_equal(actual, expected)

    def test_native_inference_and_reload_require_no_current_outcome_and_keep_source_frozen(self):
        rng = np.random.default_rng(42)
        windows = self.windows(16, 0.)
        windows[:, :3] = rng.normal(size=(16, 3, 256))
        states, people = np.tile([0, 1], 8), np.repeat("006", 16)
        encoder = FrozenRunnerEncoder(encoder_plan()[0]).fit(windows, states, people)
        before = {k: v.clone() for k, v in encoder.network.state_dict().items()}
        frame = pd.DataFrame({"prior_borg": np.tile([1., 2., 3., 4.], 4), "prior_age_minutes": 5., "elapsed_minutes": np.arange(16.),
            "label": [f"Borg {i%4+1+(i//4)%2}" for i in range(16)], "row_key": [f"q{i}" for i in range(16)]})
        specification = {"algorithm": "mlp", "features": ["prior_borg", "prior_age_minutes", "elapsed_minutes"],
            "target_mode": "change_from_prior", "params": {"hidden_layer_sizes": [4], "solver": "lbfgs", "alpha": 10., "max_iter": 100}}
        candidate = {"id": "fixture", "member": "core", "alpha": 10.}
        prior = windows[::-1].copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = AnchoredRunnerBorg(candidate, encoder).fit(frame, windows, prior, {"core": specification})
        expected = model.predict(frame, windows, prior)
        np.testing.assert_array_equal(model.predict(frame[model.input_features], windows, prior), expected)
        self.assertTrue(all(torch.equal(value, encoder.network.state_dict()[key]) for key, value in before.items()))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"paired.joblib"
            joblib.dump(model, path)
            np.testing.assert_array_equal(joblib.load(path).predict(frame.assign(label="unknown"), windows, prior), expected)

    def test_misaligned_reference_batches_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "align with every native query"):
            paired_features(pd.DataFrame({"x": [1, 2]}), self.windows(2, 1.), self.windows(1, 1.), DeterministicEncoder())


if __name__ == "__main__":
    unittest.main()
