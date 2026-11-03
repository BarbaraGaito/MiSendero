import unittest

import numpy as np
import pandas as pd

from fatigue_auxiliary_transfer import SENSOR_FEATURES, fit_teacher


class AuxiliaryTransferTests(unittest.TestCase):
    def inputs(self):
        target = pd.DataFrame({"hr_last": [90., 100.], "hr_history_mean": [85., 95.], "elapsed_minutes": [5., 10.],
                               "label": ["Borg 2", "Borg 3"], "group_key": ["walk-a", "walk-b"]})
        external = pd.DataFrame({"hr_last": [190., 150.], "hr_history_mean": [180., 140.], "elapsed_minutes": [1., 2.],
                                 "label": ["Borg 0.5", "Borg 10"], "group_key": ["sts-a", "worker-b"]})
        config = {"algorithm": "random_forest", "params": {"n_estimators": 2, "bootstrap": False, "max_depth": None}, "external_weight": 1.}
        return target, external, config

    def test_measured_fractional_borg_is_preserved_as_regression_supervision(self):
        target, external, config = self.inputs()
        teacher = fit_teacher(target, external, config)
        np.testing.assert_allclose(teacher.predict(external[SENSOR_FEATURES]), [.5, 10.])

    def test_zero_weight_control_excludes_external_rows_from_preprocessing_and_fit(self):
        target, external, config = self.inputs()
        teacher = fit_teacher(target, external, {**config, "external_weight": 0.})
        np.testing.assert_allclose(teacher.steps[0][1].statistics_, [95., 90., 7.5])
        np.testing.assert_allclose(teacher.predict(target[SENSOR_FEATURES]), [2., 3.])

    def test_source_participant_collision_is_rejected_before_combining(self):
        target, external, config = self.inputs()
        external.loc[0, "group_key"] = "walk-a"
        with self.assertRaises(AssertionError):
            fit_teacher(target, external, config)


if __name__ == "__main__":
    unittest.main()
