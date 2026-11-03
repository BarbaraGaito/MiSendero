import unittest

import numpy as np
import pandas as pd

from sts_fatigue import recording_observations


class OriginalSTSTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({"Time": ["0", "1", "30", "31", "60", "61", "90", "91", "Start_time:"],
                             "Heart_Beat": [90., 91., 100., np.nan, 110., np.nan, 120., np.nan, np.nan],
                             "Borg10_Value": [np.nan, np.nan, np.nan, .5, np.nan, 4., np.nan, 6., np.nan]})

    def test_only_measured_sparse_reports_become_labels_and_native_half_point_is_preserved(self):
        result, evidence = recording_observations(self.frame())
        self.assertEqual(result["label"].tolist(), ["Borg 0.5", "Borg 4", "Borg 6"])
        self.assertEqual(len(evidence), 3)
        self.assertEqual(result["hr_last"].tolist(), [100., 110., 120.])
        self.assertTrue(result["prior_borg"].iloc[:2].isna().all())
        self.assertEqual(result["prior_borg"].iloc[-1], .5)
        self.assertEqual(result["prior_age_minutes"].iloc[-1], 1.)

    def test_future_physiology_and_reports_cannot_change_earlier_inputs(self):
        original = self.frame()
        expected, _ = recording_observations(original)
        changed = original.copy()
        later = pd.to_numeric(changed["Time"], errors="coerce") >= 31
        changed.loc[later, "Heart_Beat"] = 230.
        changed.loc[changed["Borg10_Value"].notna() & (pd.to_numeric(changed["Time"], errors="coerce") > 31), "Borg10_Value"] = 10.
        actual, _ = recording_observations(changed)
        np.testing.assert_allclose(expected.drop(columns="label").iloc[0], actual.drop(columns="label").iloc[0], equal_nan=True)
        self.assertEqual(actual["label"].iloc[0], "Borg 0.5")

    def test_ambiguous_or_non_native_supervision_is_rejected(self):
        for change in ("out_of_range", "duplicate_time", "dense"):
            data = self.frame()
            if change == "out_of_range":
                data.loc[3, "Borg10_Value"] = 11
            elif change == "duplicate_time":
                data.loc[5, "Time"] = "31"
            else:
                data = pd.DataFrame({"Time": np.arange(10), "Heart_Beat": [100.] * 10, "Borg10_Value": [3.] * 10})
            with self.subTest(change=change), self.assertRaises(ValueError):
                recording_observations(data)


if __name__ == "__main__":
    unittest.main()
