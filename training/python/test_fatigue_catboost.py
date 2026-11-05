import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_catboost import CatBoostBorg


class CatBoostTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({"prior_borg": [1, 2, 3, 4] * 4, "prior_age_minutes": [2.] * 16,
                             "current_terrain": ["stairs", "ramp", "flat_trail", "ramp"] * 4,
                             "label": ["Borg 2", "Borg 2", "Borg 3", "Borg 5"] * 4,
                             "person_identifier": ["ignored"] * 16})

    def candidate(self):
        return {"features": ["prior_borg", "prior_age_minutes", "current_terrain"], "iterations": 3,
                "depth": 2, "l2_leaf_reg": 3., "target_mode": "change_from_prior"}

    def test_native_round_trip_requires_no_pickle_or_current_target(self):
        frame = self.frame()
        model = CatBoostBorg(self.candidate()).fit(frame)
        before = model.predict(frame)
        with tempfile.TemporaryDirectory() as directory:
            model_path, descriptor_path = Path(directory) / "model.cbm", Path(directory) / "model.json"
            model.save(model_path, descriptor_path)
            restored = CatBoostBorg.load(model_path, descriptor_path)
            np.testing.assert_array_equal(before, restored.predict(frame))
            mutated = frame.copy()
            mutated["label"], mutated["person_identifier"] = "Borg 10", "changed"
            np.testing.assert_array_equal(before, restored.predict(mutated))
            self.assertTrue(set(before) <= {f"Borg {i}" for i in range(11)})

    def test_missing_current_future_or_stale_prior_is_rejected(self):
        frame = self.frame()
        model = CatBoostBorg(self.candidate()).fit(frame)
        for age in (0., 16., float("nan")):
            invalid = frame.copy()
            invalid["prior_age_minutes"] = age
            with self.assertRaises(ValueError):
                model.predict(invalid)


if __name__ == "__main__":
    unittest.main()
