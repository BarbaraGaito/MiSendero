import unittest

import numpy as np

from fatigue_temporal_windows import BIN_NS, LENGTH, make_window


class TemporalWindowTests(unittest.TestCase):
    def test_future_and_pre_task_values_cannot_change_normalization_or_gravity(self):
        times = np.arange(1000, dtype=np.int64)*BIN_NS
        t = np.arange(1000)*.1
        values = np.c_[9.8+np.sin(t), 1.+.1*np.cos(t), np.sin(t), np.zeros(1000), 9.8+np.sin(t)]
        now, start = 60_050_000_000, 10_000_000_000
        before, stats = make_window(times, values, now, start)
        changed = values.copy()
        changed[(times < start) | (times+BIN_NS > now)] = 1e6
        after, after_stats = make_window(times, changed, now, start)
        np.testing.assert_array_equal(before, after)
        np.testing.assert_array_equal(stats, after_stats)

    def test_gaps_and_empty_queries_have_masks_without_measured_zero_filling(self):
        times = np.asarray([0, BIN_NS, 5*BIN_NS])
        values = np.tile([9.8, 1., 0., 0., 9.8], (3, 1))
        window, stats = make_window(times, values, 6*BIN_NS, 0)
        self.assertEqual(window.shape, (6, LENGTH))
        self.assertEqual(window[3].sum(), 3)
        self.assertEqual(window[3, -2], 0)
        self.assertAlmostEqual(stats[2], 3/LENGTH)
        empty, empty_stats = make_window(times, values, 0, 0)
        self.assertFalse(empty.any())
        self.assertTrue(np.isnan(empty_stats[[0, 1, 3, 4, 6, 7]]).all())
        np.testing.assert_array_equal(empty_stats[[2, 5, 8]], [0., 0., 0.])


if __name__ == "__main__":
    unittest.main()
