import unittest

import numpy as np
import pandas as pd
import torch

from fatigue_meta_adaptation import AdaptiveNetwork, MetaAdaptiveBorg, context_keys


class MetaAdaptationTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({"row_key": [f"r{i}" for i in range(6)], "group_key": ["a"] * 5 + ["b"],
                             "prior_borg": [0, 1, 2, 2, 3, 0], "prior_age_minutes": [5.] * 6,
                             "label": ["Borg 1", "Borg 2", "Borg 2", "Borg 3", "Borg 4", "Borg 1"]})

    def metadata(self):
        start = pd.Timestamp("2026-01-01", tz="UTC")
        return pd.DataFrame({"group_key": ["a"] * 5 + ["b"], "session_start": [start] * 6,
                             "task_start": [start] * 3 + [start + pd.Timedelta(minutes=15)] * 2 + [start],
                             "response_time": [start + pd.Timedelta(minutes=m) for m in (5, 10, 15, 20, 25, 5)]})

    def candidate(self):
        return {"features": ["prior_borg", "prior_age_minutes"], "width": 4, "ridge_regularization": 1., "epochs": 2}

    def test_context_resets_task_and_excludes_current_future_and_other_people(self):
        frame = self.frame()
        local = context_keys(frame, self.metadata(), "task")
        session = context_keys(frame, self.metadata(), "session")
        self.assertEqual([r["row_key"] for r in local["r4"]], ["r3"])
        self.assertEqual([r["row_key"] for r in session["r2"]], ["r0", "r1"])
        self.assertEqual(session["r5"], [])
        self.assertTrue(all(r["age_minutes"] >= 1 for rows in session.values() for r in rows))

    def test_current_and_future_labels_cannot_change_a_forecast(self):
        frame = self.frame()
        histories = context_keys(frame, self.metadata(), "session")
        model = MetaAdaptiveBorg(self.candidate()).fit(frame, histories)
        query = frame.iloc[[2]].drop(columns=["label"])
        before = model.batch(query, frame, histories)
        changed = frame.copy()
        changed.loc[2:, "label"] = "Borg 10"
        after = model.batch(query, changed, histories)
        for a, b in zip(before, after):
            np.testing.assert_array_equal(a.numpy(), b.numpy())
        np.testing.assert_array_equal(model.predict(query, frame, histories), model.predict(query, changed, histories))
        changed.loc[0, "label"] = "Borg 5"
        changed_past = model.batch(query, changed, histories)
        self.assertFalse(np.array_equal(before[2], changed_past[2]))

    def test_empty_support_is_exactly_global_and_gradients_are_finite(self):
        torch.manual_seed(42)
        model = AdaptiveNetwork(2, 4, 1.)
        query = torch.ones((2, 2))
        support = torch.zeros((2, 3, 2))
        delta = torch.zeros((2, 3), dtype=torch.int64)
        mask = torch.zeros((2, 3))
        prior = torch.tensor([0, 10])
        actual = model(query, support, delta, mask, prior)
        model.ridge = None
        global_only = model(query, support, delta, mask, prior)
        np.testing.assert_array_equal(actual.detach().numpy(), global_only.detach().numpy())
        model.ridge = 1.
        mask[:] = .8
        actual = model(query, support, delta, mask, prior)
        self.assertEqual(actual.shape, (2, 11))
        np.testing.assert_allclose(actual.detach().sum(1).numpy(), [1., 1.], atol=1e-6)
        (-torch.log(actual[:, 5]).mean()).backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters()))


if __name__ == "__main__":
    unittest.main()
