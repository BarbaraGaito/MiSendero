import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn

from fatigue_conditional_borg import ConditionalBorg, make_source, native_logits, plan, training_data


class ConditionalBorgTests(unittest.TestCase):
    def test_impossible_delta_logits_cannot_absorb_native_probability(self):
        logits = torch.zeros((2, 21), dtype=torch.float64)
        logits[0, 9], logits[0, 13] = 100., 5.  # prior=0: -1 impossible, +3 valid
        logits[1, 11], logits[1, 7] = 100., 5.  # prior=10: +1 impossible, -3 valid
        bounded = native_logits(logits, torch.tensor([0, 10]))
        self.assertEqual(bounded.argmax(dim=1).tolist(), [3, 7])
        self.assertEqual(np.clip(logits.argmax(dim=1).numpy()-10+np.asarray([0, 10]), 0, 10).tolist(), [0, 10])
        torch.testing.assert_close(bounded.softmax(dim=1).sum(dim=1), torch.ones(2, dtype=torch.float64))
        with self.assertRaisesRegex(ValueError, "integer prior"):
            native_logits(logits, torch.tensor([.5, 10.]))

    def test_conditional_likelihood_has_zero_gradient_on_query_impossible_heads(self):
        logits = torch.zeros((2, 21), dtype=torch.float64, requires_grad=True)
        loss = nn.functional.cross_entropy(native_logits(logits, torch.tensor([0, 10])), torch.tensor([3, 7]))
        loss.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())
        self.assertFalse(logits.grad[0, :10].any())
        self.assertFalse(logits.grad[1, 11:].any())
        self.assertLess(logits.grad[0, 13], 0.)
        self.assertLess(logits.grad[1, 7], 0.)

    def fixture(self):
        size = 32
        frame = pd.DataFrame({"prior_borg": np.tile([0., 1., 2., 3.], 8), "prior_age_minutes": 5.,
                              "elapsed_minutes": np.arange(1., 33.), "terrain_flat_trail": 0, "terrain_stairs": 0, "terrain_ramp": 1,
                              "row_key": [f"q{i}" for i in range(size)], "group_key": [f"p{i//4}" for i in range(size)],
                              "label": [f"Borg {i%4+(i//4)%2+1}" for i in range(size)]})
        columns = ["prior_borg", "prior_age_minutes", "elapsed_minutes", "terrain_flat_trail", "terrain_stairs", "terrain_ramp"]
        core = {"features": columns, "algorithm": "mlp", "target_mode": "change_from_prior",
                "params": {"hidden_layer_sizes": [4, 3], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}}
        view = {**core, "view_policy": "prefix", "view_mass": .6}
        pool = frame.rename(columns={"row_key": "target_row_key"}).assign(view_key=[f"v{i}" for i in range(size)], prefix_only=True, prior_age_minutes=10.)
        extra = pd.DataFrame([{**frame.iloc[0].to_dict(), "row_key": "extra-real", "prior_borg": 3., "label": "Borg 2"},
                              {**frame.iloc[0].to_dict(), "row_key": "held-extra", "group_key": "excluded_person", "label": "unavailable_held_target"}])
        return frame, pool, extra, {"core": core, "view": view}

    def test_actual_extra_reports_are_filtered_before_parsing_and_views_keep_unit_weight(self):
        frame, pool, extra, _ = self.fixture()
        data, weights, target, summary = training_data(frame, pool, extra, "view", .5)
        self.assertEqual(summary["extra_actual_targets"], 1)
        self.assertEqual(summary["optimization_input_views"], len(frame))
        self.assertAlmostEqual(weights.sum(), len(frame)+.5)
        self.assertEqual(len(target), 2*len(frame)+1)
        self.assertNotIn("excluded_person", data.group_key.tolist())

    def test_both_optimizers_leave_source_unchanged_and_inference_needs_no_targets_or_pool(self):
        frame, pool, extra, specifications = self.fixture()
        source = make_source(frame, pool, "core", specifications)
        original_weights = [value.copy() for value in source["classifier"].coefs_]
        for optimizer in ("lbfgs", "adam"):
            candidate = {"initialization": "core", "mode": "fine_tune", "objective": "conditional_native",
                         "extra_weight": .5, "optimizer": optimizer, "budget": 3}
            model = ConditionalBorg(candidate).fit(frame, pool, extra, specifications, source)
            self.assertEqual(model.initialized_new_deltas, [-1])
            expected = model.predict(frame)
            changed = frame.copy()
            changed["label"], changed["row_key"], changed["group_key"] = "unavailable", "unused", "unused"
            np.testing.assert_array_equal(model.predict(changed), expected)
            np.testing.assert_array_equal(model.predict(frame[source["features"]]), expected)
            self.assertTrue(all(not p.requires_grad and p.grad is None for p in model.model.parameters()))
            self.assertEqual(set(vars(model)), {"candidate", "features", "preprocessing", "model", "regularization",
                                                "loss_endpoints", "iterations", "initialized_new_deltas", "training_summary"})
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"model.joblib"
                joblib.dump(model, path)
                np.testing.assert_array_equal(joblib.load(path).predict(frame[source["features"]]), expected)
            for actual, original in zip(source["classifier"].coefs_, original_weights):
                np.testing.assert_array_equal(actual, original)
        self.assertEqual(len(plan(specifications)), 36)


if __name__ == "__main__":
    unittest.main()
