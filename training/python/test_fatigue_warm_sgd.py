import unittest

import numpy as np
import pandas as pd
import torch

from fatigue_meta_adaptation import context_keys
from fatigue_warm_sgd import WarmPersonalBorg, core_candidate


class WarmSGDTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({"row_key": [f"r{i}" for i in range(12)], "group_key": ["a"]*12,
                             "prior_borg": [0, 1, 2, 2, 3, 3]*2, "prior_age_minutes": [5.]*12,
                             "label": ["Borg 1", "Borg 2", "Borg 2", "Borg 3", "Borg 3", "Borg 4"]*2})

    def contexts(self, frame):
        start = pd.Timestamp("2026-01-01", tz="UTC")
        metadata = pd.DataFrame({"group_key": ["a"]*12, "session_start": [start]*12, "task_start": [start]*12,
                                 "response_time": [start+pd.Timedelta(minutes=5*i) for i in range(12)]})
        return context_keys(frame, metadata, "session")

    def model(self, frame, steps):
        core = core_candidate({"calibration_features": []})
        core["features"] = ["prior_borg", "prior_age_minutes"]
        candidate = {"steps": steps, "learning_rate": .05, "proximity": 1., "update_layers": "head"}
        return WarmPersonalBorg(candidate).fit(frame, core)

    def test_conversion_and_zero_step_keep_original_native_predictions(self):
        frame = self.frame()
        model = self.model(frame, 0)
        np.testing.assert_array_equal(model.global_predict(frame), model.core.predict(frame))
        np.testing.assert_array_equal(model.predict(frame, frame, self.contexts(frame)), model.core.predict(frame))

    def test_current_and_future_features_are_unused_and_population_stays_fixed(self):
        frame = self.frame()
        model = self.model(frame, 3)
        context = self.contexts(frame)
        query = frame.iloc[[4]].drop(columns="label")
        before = model.predict(query, frame, context)
        weights = {k: v.detach().clone() for k, v in model.model.named_parameters()}
        changed = frame.copy().astype({"prior_borg": float})
        changed.loc[4:, "prior_borg"] = np.inf
        changed.loc[4:, "label"] = "future_target_unavailable"
        np.testing.assert_array_equal(before, model.predict(query, changed, context))
        self.assertTrue(all(torch.equal(weights[k], v) for k, v in model.model.named_parameters()))


if __name__ == "__main__":
    unittest.main()
