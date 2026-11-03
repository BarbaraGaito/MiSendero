"""Technical fixtures for raw-signal time units and strict past-only windows."""
import unittest

import numpy as np

from fatigue_raw_features import combine_chunks, describe_window, pulse_features, signal_chunk


class RawFatigueFeatureTests(unittest.TestCase):
    def test_avro_microsecond_start_and_hertz_are_converted_without_unit_guessing(self):
        times, values, frequency = signal_chunk({"timestampStart": 1000000, "samplingFrequency": 2.}, [1, 2, 3])
        self.assertEqual(times.tolist(), [1000000, 1500000, 2000000])
        self.assertEqual(frequency, 2.)

    def test_future_raw_samples_cannot_change_response_predictors(self):
        times = np.arange(240) * 500000
        values = np.sin(np.arange(240)) + 10
        original = describe_window((times, values, 2.), 60000000, 60)
        modified = values.copy()
        modified[times >= 60000000] = 1e8
        changed = describe_window((times, modified, 2.), 60000000, 60)
        self.assertEqual(original, changed)

    def test_different_samples_at_same_timestamp_fail_instead_of_being_averaged(self):
        chunk_a = (np.array([0, 1000000]), np.array([1., 2.]), 1.)
        chunk_b = (np.array([1000000, 2000000]), np.array([999., 3.]), 1.)
        with self.assertRaisesRegex(ValueError, "Conflicting waveform"):
            combine_chunks([chunk_a, chunk_b])
        chunk_b = (np.array([1000000, 2000000]), np.array([2., 3.]), 1.)
        self.assertEqual(combine_chunks([chunk_a, chunk_b])[1].tolist(), [1., 2., 3.])

    def test_rmssd_never_bridges_an_invalid_pulse_interval(self):
        peaks = np.array([0, 1000, 2200, 6200, 7000, 7900], dtype=np.int64) * 1000
        result = pulse_features(peaks, 8000000)
        self.assertEqual(result["valid_interval_count"], 4)
        self.assertAlmostEqual(result["rmssd_ms"], np.sqrt((200**2 + 100**2) / 2))
        with_future = np.r_[peaks, [8100000, 8200000, 8300000]]
        self.assertEqual(result, pulse_features(with_future, 8000000))

    def test_gaps_do_not_get_interpolated_into_spectral_data(self):
        times = np.r_[np.arange(60) * 500000, 45000000 + np.arange(30) * 500000]
        result = describe_window((times, np.ones(len(times)), 2.), 60000000, 60)
        self.assertEqual(result["mean"], 1.)
        self.assertTrue(np.isnan(result["dominant_hz"]))
        self.assertLess(result["coverage"], .8)


if __name__ == "__main__":
    unittest.main()
