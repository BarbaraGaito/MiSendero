import unittest

import numpy as np
import pandas as pd

from fetch_whamap_sensors import PHONE_COLUMNS
from whamap_phone_bins import EPOCH, segments


class WHAMAPPhoneBinsTests(unittest.TestCase):
    def raw(self):
        result = pd.DataFrame({"time": ["01:00:00.000", "01:00:00.020", "01:00:00.500", "01:00:00.520", "01:00:00.600"],
                               "f-level": [0, 0, 1, 1, 1]})
        for name in PHONE_COLUMNS:
            result[name] = 9.8 if name == "phone_accelZ" else 0.
        return result

    def test_gaps_stay_missing_and_f_level_never_changes_phone_bins(self):
        raw = self.raw()
        before, quality = segments(raw)
        raw["f-level"] = "unavailable_native_mapping"
        after, _ = segments(raw)
        pd.testing.assert_frame_equal(before[0], after[0], check_exact=True)
        self.assertEqual(len(before[0]), 2)
        self.assertEqual((before[0].index[1]-before[0].index[0]).total_seconds(), .5)
        self.assertEqual(quality["identical_consecutive_export_rows"], 4)

    def test_clock_reversal_splits_segments_without_assuming_a_day(self):
        raw = self.raw()
        raw.loc[2:, "time"] = ["00:00:00.000", "00:00:00.100", "00:00:00.200"]
        parts, quality = segments(raw)
        self.assertEqual(len(parts), 2)
        self.assertEqual(quality["clock_reversals"], 1)
        self.assertTrue(parts[0].empty)
        self.assertEqual(parts[1].index[0], EPOCH)
        np.testing.assert_allclose(parts[1]["acc_mag"], 9.8)


if __name__ == "__main__":
    unittest.main()
