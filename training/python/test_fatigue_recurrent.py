import unittest

import numpy as np
import torch

from fatigue_recurrent import HistoryNetwork, history_tokens, padded_histories


class RecurrentTests(unittest.TestCase):
    def query(self):
        return {"prior_borg": 3., "prior_age_minutes": 2., "terrain": "ramp", "history": [
            {"observed_borg": 1., "age_minutes": 5., "elapsed_minutes": 0., "terrain": "ramp"},
            {"observed_borg": 3., "age_minutes": 2., "elapsed_minutes": 3., "terrain": "ramp"}]}

    def test_history_requires_ordered_actual_earlier_feedback(self):
        query = self.query()
        tokens = history_tokens(query)
        self.assertEqual(tokens.shape, (2, 9))
        self.assertAlmostEqual(float(tokens[1, 3]), .2)
        for bad_age in (0., -1.):
            query["history"][-1]["age_minutes"] = bad_age
            with self.assertRaises(ValueError):
                history_tokens(query)
        query = self.query()
        query["history"].reverse()
        with self.assertRaises(ValueError):
            history_tokens(query)

    def test_padding_does_not_change_recurrent_prediction(self):
        torch.manual_seed(42)
        model = HistoryNetwork(2, 8).eval()
        padded, lengths = padded_histories([self.query()])
        query, prior = torch.ones((1, 2)), torch.tensor([3])
        with torch.no_grad():
            a = model(query, padded, lengths, prior)
            extra = torch.cat((padded, torch.ones((1, 5, 9)) * 999), dim=1)
            b = model(query, extra, lengths, prior)
        np.testing.assert_array_equal(a.numpy(), b.numpy())

    def test_delta_edge_probability_mass_and_backpropagation(self):
        model = HistoryNetwork(2, 8).train()
        padded, lengths = padded_histories([self.query(), self.query()])
        scores = model(torch.ones((2, 2)), padded, lengths, torch.tensor([0, 10]))
        self.assertEqual(scores.shape, (2, 11))
        np.testing.assert_allclose(scores.detach().sum(1).numpy(), [1., 1.], atol=1e-6)
        loss = -torch.log(scores[:, 5]).mean()
        loss.backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))


if __name__ == "__main__":
    unittest.main()
