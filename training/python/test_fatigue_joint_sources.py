import unittest

import numpy as np
import pandas as pd

from fatigue_joint_sources import combine


class JointSourcesTests(unittest.TestCase):
    def inputs(self):
        frame = pd.DataFrame({"hr_last": [80., 100.], "borg_native": [.5, 3.], "row_key": ["s1", "s2"], "group_key": ["p1", "p2"]})
        split = {"train_row_keys": ["s1", "s2"], "test_row_keys": ["s3"], "test_groups": ["p3"]}
        return {"study": frame}, {"study": split}

    def test_native_half_points_and_absent_sensors_are_preserved(self):
        sources, splits = self.inputs()
        result, counts = combine(sources, splits)
        np.testing.assert_array_equal(result.borg_native, [.5, 3.])
        self.assertTrue(result.hr_history_mean.isna().all())
        self.assertEqual(counts["study"]["fractional_native_reports"], 1)

    def test_reserved_people_or_non_CR10_outcomes_cannot_enter_combination(self):
        for mutation in ("person", "target"):
            sources, splits = self.inputs()
            if mutation == "person":
                sources["study"].loc[0, "group_key"] = "p3"
            else:
                sources["study"].loc[0, "borg_native"] = 15.
            with self.assertRaises(ValueError):
                combine(sources, splits)


if __name__ == "__main__":
    unittest.main()
