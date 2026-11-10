import unittest

import numpy as np

from oxbioz_fatigue import episode_features


class OxBioZTests(unittest.TestCase):
    def test_partial_final_minute_never_changes_episode_predictors(self):
        t = 1710000000. + np.arange(150.)
        hr = np.r_[np.full(60, 80.), np.full(60, 100.), np.full(30, 200.)]
        result = episode_features(t, hr)
        self.assertEqual(result["hr_last"], 100.)
        self.assertEqual(result["hr_history_mean"], 90.)
        self.assertEqual(result["elapsed_complete_bins"], 2)
        self.assertEqual(result["last_predictor_time_offset_seconds"], 120.)
        hr[120:] = 30.
        self.assertEqual(episode_features(t, hr)["hr_last"], result["hr_last"])

    def test_missing_bins_are_not_filled_and_invalid_hr_is_not_used(self):
        t = np.r_[np.arange(60.), np.arange(120., 181.)]
        hr = np.r_[np.full(60, 80.), np.full(60, 120.), [999.]]
        result = episode_features(t, hr)
        self.assertEqual(result["elapsed_complete_bins"], 2)
        self.assertEqual(result["hr_history_mean"], 100.)
        self.assertEqual(result["source_aligned_sample_rows"], 121)

    def test_nonmonotonic_and_unaligned_recordings_are_rejected(self):
        for t, hr in (([1, 1, 65], [70, 80, 90]), ([1, 65], [70]), ([1, 30], [70, 80])):
            with self.assertRaises(ValueError):
                episode_features(t, hr)


if __name__ == "__main__":
    unittest.main()
