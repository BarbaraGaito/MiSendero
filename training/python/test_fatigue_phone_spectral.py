import unittest

import numpy as np
import pandas as pd

from fatigue_phone_spectral import BIN_COLUMNS, causal_features, observed_bins, spectrum


class PhoneSpectralTests(unittest.TestCase):
    def test_periodogram_recovers_frequency_without_filling_gaps(self):
        t = np.arange(0., 60., .1)
        good = (t < 20.) | (t >= 25.)
        time = pd.Timestamp("2026-01-01", tz="UTC")+pd.to_timedelta(t[good], unit="s")
        y = np.sin(2*np.pi*2.*t[good])
        result = spectrum(time, y)
        self.assertEqual(result["valid_bins"], int(good.sum()))
        self.assertLess(abs(result["peak_hz"]-2.), .04)
        self.assertGreater(result["peak_normalized_power"], .8)
        self.assertAlmostEqual(sum(result["band_"+b+"_share"] for b in ("low", "mid", "gait", "high")), 1.)

    def test_future_samples_cannot_change_current_or_baseline_features(self):
        start = pd.Timestamp("2026-01-01", tz="UTC")
        t = np.arange(0., 80., .1)
        index = start+pd.to_timedelta(t, unit="s")
        bins = pd.DataFrame({"acc_mag": 9.8+np.sin(2*np.pi*t), "gyro_mag": 1.+.1*np.cos(2*np.pi*t),
                             "ax": np.sin(2*np.pi*t), "ay": np.zeros(len(t)), "az": np.full(len(t), 9.8)}, index=index)
        now = start+pd.Timedelta(seconds=40)
        before = causal_features(bins, now, start, start+pd.Timedelta(seconds=20))
        bins.loc[bins.index >= now, BIN_COLUMNS] = 77.
        after = causal_features(bins, now, start, start+pd.Timedelta(seconds=20))
        np.testing.assert_allclose(list(before.values()), list(after.values()), rtol=0, atol=0, equal_nan=True)

    def test_conflicting_timestamp_rows_are_both_excluded(self):
        start = pd.Timestamp("2026-01-01", tz="UTC")
        raw = pd.DataFrame({"time": [start, start, start+pd.Timedelta(milliseconds=150), start+pd.Timedelta(milliseconds=150)],
                            "ax": [1., 2., 3., 3.], "ay": [0.]*4, "az": [9.8]*4, "wx": [0.]*4, "wy": [0.]*4,
                            "wz": [0.]*4, "speed": [1.]*4, "altitude": [10.]*4})
        bins = observed_bins(raw)
        self.assertEqual(len(bins), 1)
        self.assertEqual(bins.attrs["quality"]["excluded_ambiguous_sample_rows"], 2)
        self.assertEqual(bins.attrs["quality"]["identical_duplicate_sample_rows"], 1)
        self.assertEqual(bins.index[0], start+pd.Timedelta(milliseconds=100))


if __name__ == "__main__":
    unittest.main()
