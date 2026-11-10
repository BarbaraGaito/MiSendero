import unittest

import numpy as np
import pandas as pd

from fatigue_gait_transfer import GaitTransferBorg, add_teacher, fit_teacher


class GaitTransferTests(unittest.TestCase):
    def source(self):
        return pd.DataFrame({"hr_last": np.arange(70., 90.), "borg_native": np.linspace(.5, 6., 20),
                             "group_key": [f"external-{i}" for i in range(20)]})

    def test_source_prediction_does_not_consume_current_target(self):
        teacher = {"algorithm": "ridge", "features": ["hr_last"]}
        fitted = fit_teacher(self.source(), teacher)
        frame = pd.DataFrame({"hr_last": [80., 90.], "prior_borg": [1., 3.], "label": ["Borg 9", "Borg 4"]})
        before = add_teacher(frame, fitted, teacher["features"])
        frame["label"] = "Borg 0"
        after = add_teacher(frame, fitted, teacher["features"])
        np.testing.assert_array_equal(before["sixmwt_external_estimate"], after["sixmwt_external_estimate"])
        self.assertTrue(before["sixmwt_external_estimate"].between(0, 10).all())

    def test_source_participants_cannot_become_original_fit_people(self):
        candidate = {"teacher": {"algorithm": "ridge", "features": ["hr_last"]}}
        source = self.source()
        with self.assertRaises(ValueError):
            GaitTransferBorg(candidate, source).fit(source.iloc[:2])


if __name__ == "__main__":
    unittest.main()
