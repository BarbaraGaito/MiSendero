import unittest

import numpy as np
import pandas as pd

from fatigue_spectral_experiment import SpectralBorg, merge_spectra


class SpectralExperimentTests(unittest.TestCase):
    def test_join_preserves_parent_float_bits_and_rejects_changed_cases(self):
        parent = pd.DataFrame({"row_key": ["a", "b"], "value": [np.nextafter(1., 2.), np.pi], "label": ["Borg 1", "Borg 2"]}, index=[7, 9])
        added = pd.DataFrame({"row_key": ["a", "b"], "spectral60_peak_hz": [2., np.nan]})
        result = merge_spectra(parent, added, ["spectral60_peak_hz"])
        pd.testing.assert_frame_equal(parent, result[parent.columns], check_exact=True)
        for invalid in (added.iloc[::-1], added.iloc[:1], added.assign(row_key="a"), added.assign(label="Borg 10")):
            with self.assertRaises(ValueError):
                merge_spectra(parent, invalid, ["spectral60_peak_hz"])

    def test_current_target_and_identity_are_not_predictors(self):
        frame = pd.DataFrame({"prior_borg": [1, 2, 3, 4]*4, "prior_age_minutes": [2.]*16,
                              "spectral60_peak_hz": [1.5, 1.8, np.nan, 2.]*4,
                              "label": ["Borg 2", "Borg 2", "Borg 3", "Borg 5"]*4, "group_key": ["ignored"]*16})
        candidate = {"algorithm": "logistic", "features": ["prior_borg", "prior_age_minutes", "spectral60_peak_hz"],
                     "params": {"C": .1, "max_iter": 100}, "target_mode": "change_from_prior"}
        model = SpectralBorg(candidate).fit(frame)
        before = model.predict(frame)
        frame["label"], frame["group_key"] = "Borg 10", "changed"
        np.testing.assert_array_equal(before, model.predict(frame))
        self.assertTrue(set(before) <= {f"Borg {i}" for i in range(11)})


if __name__ == "__main__":
    unittest.main()
