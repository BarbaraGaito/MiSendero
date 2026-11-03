"""Causality checks using only the actual frozen public waveform snapshot."""
import unittest
import zipfile

import numpy as np

import fatigue_physiology_pairs as source


@unittest.skipUnless((source.DIRECTORY/"windows.npz").exists(), "Requires actual public AVRO input cache")
class PhysiologyPairsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arrays, cls.manifest = source.load()
        cls.rows = cls.manifest["lineage"]
        cls.row = next(row for row in cls.rows if all(row["windows"][name]["channels"][channel]["actual_samples"] > 0
            for name in ("fast_current", "fast_prior") for channel in ("bvp", "acc_magnitude")))
        with zipfile.ZipFile(source.ARCHIVE) as archive:
            cls.signals, _ = source.read_signals(archive, cls.row["source_prefixes"])

    def test_existing_cases_and_missing_windows_remain_in_the_cache(self):
        self.assertEqual(len(self.rows), 722)
        self.assertEqual(sum(row["cohort"] == "canonical" for row in self.rows), 666)
        self.assertEqual(sum(row["cohort"] == "extra_fitting_only" for row in self.rows), 56)
        self.assertEqual(self.manifest["cohort"]["original_test_cases"], 179)
        self.assertFalse(self.manifest["current_targets_in_tensor_cache"])
        self.assertEqual(set(self.arrays), {"row_keys", "fast_current", "fast_prior", "slow_current", "slow_prior"})
        for name, values in self.arrays.items():
            if name == "row_keys":
                continue
            self.assertTrue(np.isfinite(values).all())
            self.assertTrue(np.isin(values[:, 2:], [0, 1]).all())
            self.assertTrue((values[:, :2][values[:, 2:] == 0] == 0).all())
            self.assertGreater(sum(values[:, 2:].sum(axis=(1, 2)) == 0), 0)

    def test_removing_all_future_and_pre_boundary_actual_samples_preserves_each_window(self):
        for band, (rate, channels) in source.RATES.items():
            for phase in ("current", "prior"):
                time = self.row[f"{phase}_time_us"]
                lower = self.row[f"{phase}_lower_bound_us"]
                truncated = {name: (t[(t >= lower) & (t < time)], v[(t >= lower) & (t < time)], frequency)
                             for name, (t, v, frequency) in self.signals.items()}
                original, proof = source.observed_window(self.signals, time, lower, rate, channels)
                past, past_proof = source.observed_window(truncated, time, lower, rate, channels)
                np.testing.assert_array_equal(original, past)
                self.assertEqual(proof, past_proof)

    def test_genuine_start_of_task_reports_keep_empty_current_window_and_observed_earlier_window(self):
        indexes = [i for i, row in enumerate(self.rows) if row["current_time_us"] == row["current_lower_bound_us"]]
        self.assertGreater(len(indexes), 0)
        for name in ("fast", "slow"):
            self.assertFalse(self.arrays[name+"_current"][indexes].any())
            self.assertTrue(self.arrays[name+"_prior"][indexes, 2:].any())

    def test_prior_windows_use_real_earlier_reports_and_no_post_prior_samples(self):
        crossing = set()
        for row in self.rows:
            age = (row["current_time_us"]-row["prior_time_us"])/60_000_000
            self.assertEqual(age, row["prior_age_minutes"])
            self.assertTrue(1 <= age <= 15)
            self.assertTrue(0 <= row["prior_observed_borg"] <= 10)
            if len(row["source_prefixes"]) > 1:
                crossing.add(tuple(row["source_prefixes"]))
            for phase in ("current", "prior"):
                for band in source.RATES:
                    proof = row["windows"][band+"_"+phase]
                    self.assertLessEqual(proof["end_exclusive_us"], row[phase+"_time_us"])
                    for stats in proof["channels"].values():
                        if stats["latest_sample_us"] is not None:
                            self.assertLess(stats["latest_sample_us"], row[phase+"_time_us"])
                            self.assertGreaterEqual(stats["earliest_sample_us"], row[phase+"_lower_bound_us"])
        self.assertEqual(len(crossing), 7)


if __name__ == "__main__":
    unittest.main()
