import unittest

import numpy as np
import pandas as pd

from fatigue_runner_windows import AXES, GYRO, CLOCK, BIN_NS, LENGTH, dimensionless_window, runner_bins


class RunnerWindowTests(unittest.TestCase):
    def samples(self):
        random = np.random.default_rng(7)
        axes = random.normal(size=(LENGTH+50, 3)) + [0., 0., 9.8]
        gyro = random.normal(size=(LENGTH+50, 3))
        values = np.column_stack((np.linalg.norm(axes, axis=1), np.linalg.norm(gyro, axis=1), axes))
        return np.arange(len(values))*BIN_NS, values

    def test_independent_positive_sensor_unit_scaling_and_rotation_cancel(self):
        times, values = self.samples()
        expected = dimensionless_window(times, values, LENGTH*BIN_NS, 0)
        for acceleration, gyro in [(1e-6, 1e6), (1000., 180./np.pi), (.01, .0001)]:
            transformed = values.copy()
            transformed[:, [0, 2, 3, 4]] *= acceleration
            transformed[:, 1] *= gyro
            actual = dimensionless_window(times, transformed, LENGTH*BIN_NS, 0)
            np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-6)
        rotation, _ = np.linalg.qr(np.random.default_rng(2).normal(size=(3, 3)))
        transformed = values.copy()
        transformed[:, 2:] = transformed[:, 2:] @ rotation
        np.testing.assert_allclose(dimensionless_window(times, transformed, LENGTH*BIN_NS, 0), expected, rtol=0, atol=1e-6)

    def test_future_and_previous_task_values_cannot_change_current_window(self):
        times, values = self.samples()
        start = 10*BIN_NS
        expected = dimensionless_window(times, values, LENGTH*BIN_NS, start)
        poison = values.copy()
        poison[(times < start) | (times >= LENGTH*BIN_NS)] = 1e12
        np.testing.assert_array_equal(dimensionless_window(times, poison, LENGTH*BIN_NS, start), expected)
        self.assertFalse(expected[:, :10].any())

    def test_missing_is_not_interpolated_or_confused_with_observed_zero(self):
        times, values = self.samples()
        values[:] = np.nan
        self.assertFalse(dimensionless_window(times, values, LENGTH*BIN_NS, 0).any())
        values[:] = 0.
        actual = dimensionless_window(times, values, LENGTH*BIN_NS, 0)
        self.assertFalse(actual[:3].any())
        self.assertTrue((actual[3:5] == 1).all())
        self.assertFalse(actual[5].any())
        values[100:110] = np.nan
        self.assertFalse(dimensionless_window(times, values, LENGTH*BIN_NS, 0)[:, 100:110].any())

    def test_clock_resets_and_conflicting_duplicates_are_kept_out_of_bins(self):
        clock = [0., 50., 50., 100., 100., 200., 90., 190.]
        frame = pd.DataFrame({CLOCK: clock, **{c: np.ones(8) for c in [*AXES, *GYRO]}})
        frame.loc[2, AXES[0]] = 99.
        frame["Borg"] = "never a numeric target"
        segments, quality = runner_bins(frame)
        self.assertEqual(len(segments), 2)
        self.assertEqual(quality["clock_reversals"], 1)
        self.assertEqual(quality["ambiguous_timestamp_rows"], 2)
        self.assertEqual(quality["identical_duplicate_rows"], 1)
        changed = frame.assign(Borg="unavailable label", System_Timestamp=0.)
        repeated, _ = runner_bins(changed)
        for first, second in zip(segments, repeated):
            np.testing.assert_array_equal(first[0], second[0])
            np.testing.assert_array_equal(first[1], second[1])


if __name__ == "__main__":
    unittest.main()
