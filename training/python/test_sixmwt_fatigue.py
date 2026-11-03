import unittest

import numpy as np

from sixmwt_fatigue import extract


class SixMWTTests(unittest.TestCase):
    def source(self):
        t = np.arange(0., 363., .01)
        axes = np.c_[np.zeros(len(t)), np.sin(2*np.pi*1.8*t), 9.8+np.sin(2*np.pi*1.8*t)]
        return {"BorgScale": .5, "HR_post": 90., "RawData": {"Time": t, "Acc": axes, "Frequency": 100}}

    def test_native_fraction_and_later_samples_do_not_enter_predictors(self):
        source = self.source()
        before, target = extract(source)
        self.assertEqual(target, .5)
        source["RawData"]["Acc"][source["RawData"]["Time"] >= 360] = 1e6
        source["BorgScale"] = 9.
        after, changed = extract(source)
        self.assertEqual(changed, 9.)
        np.testing.assert_allclose(list(before.values()), list(after.values()), rtol=0, atol=0, equal_nan=True)
        self.assertLess(abs(before["spectral60_acc_mag_peak_hz"]-1.8), .04)

    def test_missing_target_is_rejected_instead_of_filled(self):
        source = self.source()
        for invalid in (np.nan, -1., 11.):
            source["BorgScale"] = invalid
            with self.assertRaises(ValueError):
                extract(source)

    def test_mismatched_sensor_clock_keeps_report_and_marks_acceleration_missing(self):
        from sixmwt_fatigue import ACC_FEATURES
        source = self.source()
        source["RawData"]["Acc"] = source["RawData"]["Acc"][:-100]
        result, target = extract(source)
        self.assertEqual(target, .5)
        self.assertEqual(result["hr_last"], 90.)
        self.assertTrue(all(np.isnan(result[f]) for f in ACC_FEATURES))


if __name__ == "__main__":
    unittest.main()
