import unittest

import numpy as np
import pandas as pd

from fatigue_spectral_correction import corrected_predictions, fit_corrector


class SpectralCorrectionTests(unittest.TestCase):
    def test_margin_preserves_incumbent_and_native_boundary_clipping(self):
        p = np.asarray([[.1, .4, .5], [.1, .8, .1], [.8, .1, .1]])
        classes = [-1, 0, 1]
        np.testing.assert_array_equal(corrected_predictions([3, 10, 0], p, classes, 0.), ["Borg 4", "Borg 10", "Borg 0"])
        np.testing.assert_array_equal(corrected_predictions([3, 10, 0], p, classes, .15), ["Borg 3", "Borg 10", "Borg 0"])
        with self.assertRaises(ValueError):
            corrected_predictions([3]*3, p*.5, classes, 0.)

    def test_corrector_has_no_current_target_or_identity_predictors(self):
        frame = pd.DataFrame({"base_predicted_borg": [1., 2., 3., 4.]*5, "spectral60_peak_hz": [2., np.nan, 1., 1.8]*5,
                              "label": ["Borg 4"]*20, "group_key": ["unused"]*20})
        candidate = {"algorithm": "logistic", "features": ["base_predicted_borg", "spectral60_peak_hz"], "params": {"C": .01, "max_iter": 100}}
        model = fit_corrector(frame, [0, 0, 1, -1]*5, candidate)
        before = model.predict_proba(frame[candidate["features"]])
        frame["label"], frame["group_key"] = "Borg 0", "changed"
        np.testing.assert_array_equal(before, model.predict_proba(frame[candidate["features"]]))


if __name__ == "__main__":
    unittest.main()
