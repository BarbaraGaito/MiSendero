import unittest

import numpy as np
import pandas as pd

from fatigue_augmented_feedback import fitting_rows


class AugmentedFeedbackTests(unittest.TestCase):
    def test_extra_outcomes_of_validation_people_never_enter_fit(self):
        original = pd.DataFrame({"row_key": ["a1", "a2"], "group_key": ["fit_a", "fit_a"], "label": ["Borg 2", "Borg 3"]})
        extra = pd.DataFrame({"row_key": ["extra_a", "extra_b"], "group_key": ["fit_a", "validation_b"], "label": ["Borg 0", "Borg 9"]})
        combined, weights, keys = fitting_rows(original, extra, .5)
        self.assertEqual(keys, ["extra_a"])
        self.assertEqual(combined["row_key"].tolist(), ["a1", "a2", "extra_a"])
        self.assertEqual(combined["label"].tolist(), ["Borg 2", "Borg 3", "Borg 0"])
        np.testing.assert_array_equal(weights, [1., 1., .5])

    def test_control_preserves_exact_original_rows(self):
        original = pd.DataFrame({"row_key": ["a"], "group_key": ["fit"], "label": ["Borg 2"]}, index=[12])
        extra = pd.DataFrame({"row_key": ["b"], "group_key": ["fit"], "label": ["Borg 0"]})
        data, weights, keys = fitting_rows(original, extra, 0.)
        pd.testing.assert_frame_equal(data, original)
        self.assertIsNone(weights)
        self.assertEqual(keys, [])

    def test_duplicate_real_target_cannot_be_counted_twice(self):
        original = pd.DataFrame({"row_key": ["a"], "group_key": ["fit"]})
        for keys in (["a"], ["b", "b"]):
            extra = pd.DataFrame({"row_key": keys, "group_key": ["fit"]*len(keys)})
            with self.assertRaises(ValueError):
                fitting_rows(original, extra, 1.)


if __name__ == "__main__":
    unittest.main()
