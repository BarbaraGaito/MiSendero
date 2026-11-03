import unittest

import numpy as np
import pandas as pd

from fatigue_source_teachers import add_teacher_features, fit_teacher


class SourceTeacherTests(unittest.TestCase):
    def data(self):
        return pd.DataFrame({"hr_last": [70., 90., 110., 130.], "hr_history_mean": [65., 85., 105., 125.],
                             "borg_native": [.5, 2., 4., 6.], "label": ["Borg 0"] * 4, "prior_borg": [1.] * 4})

    def test_teacher_fits_native_fractional_cells(self):
        data = self.data()
        first = fit_teacher(data, "ridge")
        changed = data.copy()
        changed["borg_native"] = changed["borg_native"].round()
        second = fit_teacher(changed, "ridge")
        self.assertFalse(np.allclose(first.predict(data[["hr_last", "hr_history_mean"]]), second.predict(data[["hr_last", "hr_history_mean"]])))

    def test_current_walking_labels_do_not_enter_auxiliary_features(self):
        data = self.data()
        model = fit_teacher(data, "ridge")
        before = add_teacher_features(data, {"post_trial": model})
        changed = data.copy()
        changed["label"] = "Borg 10"
        changed["borg_native"] = 10.
        after = add_teacher_features(changed, {"post_trial": model})
        for feature in ("post_trial_external_estimate", "post_trial_estimate_minus_prior"):
            np.testing.assert_array_equal(before[feature], after[feature])


if __name__ == "__main__":
    unittest.main()
