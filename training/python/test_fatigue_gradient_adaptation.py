import unittest

import numpy as np
import pandas as pd
import torch

from fatigue_gradient_adaptation import GradientAdaptiveBorg, GradientNetwork, episode_scores, native_probability
from fatigue_meta_adaptation import context_keys


class GradientAdaptationTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({"row_key": [f"r{i}" for i in range(6)], "group_key": ["a"]*5+["b"],
                             "prior_borg": [0, 1, 2, 2, 3, 0], "prior_age_minutes": [5.]*6,
                             "label": ["Borg 1", "Borg 2", "Borg 2", "Borg 3", "Borg 4", "Borg 1"]})

    def histories(self, frame):
        start = pd.Timestamp("2026-01-01", tz="UTC")
        metadata = pd.DataFrame({"group_key": ["a"]*5+["b"], "session_start": [start]*6,
                                 "task_start": [start]*3+[start+pd.Timedelta(minutes=15)]*2+[start],
                                 "response_time": [start+pd.Timedelta(minutes=i) for i in (5, 10, 15, 20, 25, 5)]})
        return context_keys(frame, metadata, "session")

    def candidate(self):
        return {"features": ["prior_borg", "prior_age_minutes"], "inner_steps": 2,
                "inner_learning_rate": .3, "first_order": False, "epochs": 2}

    def test_future_features_and_labels_cannot_change_a_prediction_or_global_parameters(self):
        frame = self.frame()
        context = self.histories(frame)
        model = GradientAdaptiveBorg(self.candidate()).fit(frame, context)
        query = frame.iloc[[2]].drop(columns="label")
        before = model.predict_scores(query, frame, context)
        params = {name: value.detach().clone() for name, value in model.model.named_parameters()}
        changed = frame.copy().astype({"prior_borg": float})
        changed.loc[2:, "label"] = "unavailable_current_or_future_target"
        changed.loc[2:, "prior_borg"] = np.inf
        after = model.predict_scores(query, changed, context)
        np.testing.assert_array_equal(before, after)
        for name, value in model.model.named_parameters():
            self.assertTrue(torch.equal(value, params[name]))
        changed.loc[0, "label"] = "Borg 5"
        self.assertGreater(np.max(np.abs(before-model.predict_scores(query, changed, context))), 1e-6)

    def test_empty_support_is_global_and_full_maml_has_finite_outer_gradients(self):
        torch.manual_seed(42)
        network = GradientNetwork(2)
        params = dict(network.named_parameters())
        candidate = self.candidate()
        query, prior = torch.ones(2), torch.tensor(0.)
        sx, sp, target, weight = torch.ones((3, 2)), torch.tensor([0., 2., 10.]), torch.tensor([1, 3, 9]), torch.zeros(3)
        actual = episode_scores(network, candidate, params, query, prior, sx, sp, target, weight)
        expected = native_probability(network(query), prior)
        np.testing.assert_array_equal(actual.detach().numpy(), expected.detach().numpy())
        weight[:] = .8
        adapted = episode_scores(network, candidate, params, query, prior, sx, sp, target, weight)
        self.assertAlmostEqual(float(adapted.detach().sum()), 1., places=6)
        (-torch.log(adapted[2])).backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in network.parameters()))
        edges = native_probability(torch.zeros((2, 21)), torch.tensor([0., 10.]))
        np.testing.assert_allclose(edges.detach().sum(1), [1., 1.], atol=1e-6)
        self.assertAlmostEqual(float(edges[0, 0]), 11/21, places=6)
        self.assertAlmostEqual(float(edges[1, 10]), 11/21, places=6)

    def test_first_order_preserves_forward_but_changes_meta_gradient(self):
        torch.manual_seed(42)
        network = GradientNetwork(2)
        params = dict(network.named_parameters())
        candidate = self.candidate()
        inputs = (torch.ones(2), torch.tensor(2.), torch.ones((3, 2)), torch.tensor([0., 2., 3.]),
                  torch.tensor([1, 3, 4]), torch.full((3,), .8))
        full = episode_scores(network, candidate, params, *inputs)
        full_gradient = torch.autograd.grad(-torch.log(full[3]), tuple(params.values()))
        first = episode_scores(network, {**candidate, "first_order": True}, params, *inputs)
        first_gradient = torch.autograd.grad(-torch.log(first[3]), tuple(params.values()))
        np.testing.assert_array_equal(full.detach(), first.detach())
        self.assertGreater(sum(float(torch.abs(a-b).sum()) for a, b in zip(full_gradient, first_gradient)), 1e-5)

    def test_other_person_or_current_support_is_rejected(self):
        frame = self.frame()
        context = self.histories(frame)
        model = GradientAdaptiveBorg(self.candidate()).fit(frame, context)
        query = frame.iloc[[2]]
        for key in ("r2", "r5"):
            altered = {**context, "r2": [{"row_key": key, "age_minutes": 5.}]}
            with self.assertRaises(ValueError):
                model.predict(query, frame, altered)


if __name__ == "__main__":
    unittest.main()
