import unittest

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from fatigue_dynamics_regression import ContinuousBorg


class ContinuousBorgTests(unittest.TestCase):
    def training_frame(self):
        return pd.DataFrame({"prior_borg": [1., 2., 3., 4.] * 3,
                             "prior_age_minutes": [5.] * 12, "context": [1., 2., np.nan, 4.] * 3,
                             "label": ["Borg 2", "Borg 3", "Borg 4", "Borg 5"] * 3})

    def test_native_predictions_and_preprocessing_depend_only_on_fit_partition(self):
        train = self.training_frame()
        candidate = {"algorithm": "ridge", "params": {"alpha": 1.}, "features": ["prior_borg", "prior_age_minutes", "context"],
                     "target_mode": "change_from_prior"}
        with threadpool_limits(limits=1):
            model = ContinuousBorg(candidate).fit(train)
        held_out = train.copy()
        held_out["context"] = 10000.
        held_out["label"] = "Borg 10"
        before = model.model.steps[0][1].statistics_.copy()
        values = model.predict(held_out)
        np.testing.assert_array_equal(model.model.steps[0][1].statistics_, before)
        np.testing.assert_array_equal(values, train["label"].to_numpy())
        np.testing.assert_allclose(before, [2.5, 5., 2.])

    def test_missing_or_current_borg_is_not_a_valid_regression_input(self):
        train = self.training_frame()
        candidate = {"algorithm": "ridge", "params": {"alpha": 1.}, "features": ["prior_borg", "prior_age_minutes"],
                     "target_mode": "absolute_borg"}
        model = ContinuousBorg(candidate).fit(train)
        for column, value in (("prior_borg", np.nan), ("prior_borg", 2.5), ("prior_age_minutes", 0), ("prior_age_minutes", 16)):
            bad = train.copy()
            bad.loc[0, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                model.predict(bad)


if __name__ == "__main__":
    unittest.main()
