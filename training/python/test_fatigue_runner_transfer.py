import tempfile
import unittest
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from fatigue_runner_transfer import FrozenRunnerEncoder, RunnerTransferBorg, encoder_plan, source_weights, validate_windows


class RunnerTransferTests(unittest.TestCase):
    def fixture(self):
        rng = np.random.default_rng(12)
        windows = np.concatenate((rng.normal(size=(32, 3, 256)).astype(np.float32), np.ones((32, 3, 256), dtype=np.float32)), axis=1)
        states, people = np.tile(np.repeat([0, 1], 8), 2), np.repeat(["006", "007"], 16)
        frame = pd.DataFrame({"prior_borg": np.tile([1., 2., 3., 4.], 8), "prior_age_minutes": 5., "elapsed_minutes": np.arange(1., 33.),
            "label": [f"Borg {i%4+1+(i//4)%2}" for i in range(32)], "current_terrain": "flat_trail",
            "row_key": [f"q{i}" for i in range(32)], "group_key": [f"p{i//4}" for i in range(32)]})
        candidate = {**encoder_plan()[1], "epochs": 2}
        return windows, states, people, frame, candidate

    def test_weights_do_not_let_longer_source_runs_or_people_dominate(self):
        people = np.array(["006"]*4+["007"]*3)
        states = np.array([0, 1, 1, 1, 0, 0, 1])
        weights = source_weights(states, people)
        for person in ["006", "007"]:
            for state in (0, 1):
                self.assertAlmostEqual(float(weights[(people == person) & (states == state)].sum()), len(states)/4, places=5)
        with self.assertRaises(ValueError):
            source_weights(states, np.repeat("004", len(states)))
        with self.assertRaises(ValueError):
            source_weights(np.array([0., .5]), np.array(["006", "006"]))

    def test_source_learning_updates_then_freezes_and_reloads_all_parameters(self):
        windows, states, people, _, candidate = self.fixture()
        random = FrozenRunnerEncoder({**candidate, "epochs": 0}).fit(windows, states, people)
        model = FrozenRunnerEncoder(candidate).fit(windows, states, people)
        self.assertTrue(np.isfinite(model.loss_endpoints).all())
        self.assertTrue(any(not torch.equal(value, random.network.state_dict()[key]) for key, value in model.network.state_dict().items()))
        self.assertTrue(all(not p.requires_grad and p.grad is None for p in model.network.parameters()))
        self.assertEqual(model.source_summary["native_borg_targets_used"], 0)
        expected = model.extract(windows)
        self.assertEqual(expected.shape, (32, 20))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"encoder.joblib"
            joblib.dump(model, path)
            np.testing.assert_array_equal(joblib.load(path).extract(windows), expected)

    def test_native_models_keep_encoder_frozen_and_never_read_current_outcomes_at_inference(self):
        windows, states, people, frame, candidate = self.fixture()
        encoder = FrozenRunnerEncoder(candidate).fit(windows, states, people)
        before = {key: value.clone() for key, value in encoder.network.state_dict().items()}
        core = {"algorithm": "mlp", "features": ["prior_borg", "prior_age_minutes", "elapsed_minutes"], "target_mode": "change_from_prior",
                "params": {"hidden_layer_sizes": [4], "solver": "lbfgs", "alpha": 10., "max_iter": 60}}
        cat = {"features": core["features"]+["current_terrain"], "target_mode": "change_from_prior", "iterations": 8, "depth": 2, "l2_leaf_reg": 30.}
        for member in ["core", "cat"]:
            c = {"id": "fixture", "algorithm": "frozen_runner_features", "member": member, "alpha": 10.}
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = RunnerTransferBorg(c, encoder).fit(frame, windows, {"core": core, "cat": cat})
            expected = model.predict(frame, windows)
            changed = frame.assign(label="unknown current outcome", row_key="unused", group_key="unused")
            np.testing.assert_array_equal(model.predict(changed, windows), expected)
            np.testing.assert_array_equal(model.predict(frame[model.input_features], windows), expected)
            self.assertEqual(set(vars(model)), {"candidate", "encoder", "input_features", "model"})
            self.assertTrue(all(torch.equal(value, encoder.network.state_dict()[key]) for key, value in before.items()))

    def test_empty_native_windows_remain_and_hidden_values_cannot_leak_through_masks(self):
        windows, states, people, _, candidate = self.fixture()
        encoder = FrozenRunnerEncoder(candidate).fit(windows, states, people)
        empty = np.zeros_like(windows[:2])
        np.testing.assert_array_equal(encoder.extract(empty), np.zeros((2, 20)))
        empty[0, 0, 5] = 1000.
        with self.assertRaises(ValueError):
            validate_windows(empty)


if __name__ == "__main__":
    unittest.main()
