import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from fatigue_phone_context import CHANNELS, cached_seconds, causal_phone_features, completed_seconds, describe_window
from public_sources import digest


class PhoneContextTests(unittest.TestCase):
    def test_data_only_cache_roundtrip_preserves_units_and_refuses_modified_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "phone.csv"
            raw = pd.DataFrame({"time": ["2020-01-01T12:00:00.010Z", "2020-01-01T12:00:00.020Z"],
                                "ax": [1., 2.], "ay": [0., 0.], "az": [0., 0.], "wx": [0., 0.], "wy": [0., 0.],
                                "wz": [0., 0.], "speed": [1., 1.], "altitude": [100., 100.]})
            raw.to_csv(path, index=False)
            source = {"path": path, "sha256": digest(path)}
            with patch("fatigue_phone_context.CACHE_DIRECTORY", root / "cache"):
                first = cached_seconds(source)
                second = cached_seconds(source)
                np.testing.assert_allclose(first, second)
                self.assertEqual(first.index[0], second.index[0])
                self.assertEqual(second.index[0], pd.Timestamp("2020-01-01T12:00:00Z"))
                raw.loc[0, "ax"] = 50.
                raw.to_csv(path, index=False)
                with self.assertRaises(ValueError):
                    cached_seconds(source)

    def test_future_and_incomplete_seconds_cannot_change_current_or_prior_windows(self):
        start = pd.Timestamp("2020-01-01T12:00Z")
        index = pd.date_range(start, periods=180, freq="s")
        seconds = pd.DataFrame({c: np.linspace(1., 2., len(index)) for c in CHANNELS + ["relative_height_source"]}, index=index)
        now, prior = start + pd.Timedelta(seconds=90.5), start + pd.Timedelta(seconds=60)
        expected = causal_phone_features(seconds, now, start, prior)
        altered = seconds.copy()
        altered.loc[altered.index + pd.Timedelta(seconds=1) > now] = 1000.
        actual = causal_phone_features(altered, now, start, prior)
        np.testing.assert_allclose(list(expected.values()), list(actual.values()), equal_nan=True)
        self.assertEqual(expected["phone_task_observed_seconds"], 90)
        self.assertEqual(expected["phone_recent30_observed_seconds"], 29)

    def test_gaps_are_not_interpolated_or_counted_as_ascent(self):
        index = pd.to_datetime(["2020-01-01T12:00:00Z", "2020-01-01T12:00:01Z", "2020-01-01T12:05:00Z"])
        window = pd.DataFrame({c: [1., 1., 2.] for c in CHANNELS}, index=index)
        window["relative_height_source"] = [100., 101., 103.]
        summary = describe_window(window)
        self.assertEqual(summary["observed_seconds"], 3)
        self.assertEqual(summary["positive_height_change"], 1.)

    def test_conflicting_same_timestamp_samples_fail_and_coordinates_are_not_output(self):
        time = pd.Timestamp("2020-01-01T12:00Z")
        raw = pd.DataFrame({"time": [time, time + pd.Timedelta(milliseconds=10)], "ax": [1., 2.], "ay": [0., 0.], "az": [0., 0.],
                            "wx": [0., 0.], "wy": [0., 0.], "wz": [0., 0.], "speed": [1., 1.], "altitude": [100., 100.],
                            "latitude": [50., 50.], "longitude": [-100., -100.]})
        result = completed_seconds(raw)
        self.assertEqual(len(result), 1)
        self.assertFalse(set(result) & {"latitude", "longitude", "altitude"})
        raw.loc[1, "time"] = time
        with self.assertRaises(ValueError):
            completed_seconds(raw)

    def test_audited_conflict_policy_excludes_both_readings_and_counts_them(self):
        time = pd.Timestamp("2020-01-01T12:00Z")
        raw = pd.DataFrame({"time": [time, time, time + pd.Timedelta(milliseconds=20)],
                            "ax": [100., 50., 2.], "ay": [0.] * 3, "az": [0.] * 3, "wx": [0.] * 3,
                            "wy": [0.] * 3, "wz": [0.] * 3, "speed": [1.] * 3, "altitude": [100.] * 3})
        result = completed_seconds(raw, conflict_policy="exclude_ambiguous")
        self.assertEqual(result.iloc[0]["acc_rms"], 2.)
        self.assertEqual(result.attrs["quality_audit"]["excluded_ambiguous_sample_rows"], 2)
        self.assertEqual(result.attrs["quality_audit"]["ambiguous_timestamps"], 1)


if __name__ == "__main__":
    unittest.main()
