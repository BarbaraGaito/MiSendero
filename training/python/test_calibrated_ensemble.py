"""Native-value aggregation checks; no tolerance or relabeling of targets."""
import unittest

import numpy as np

from common.calibrated_ensemble import aggregate_borg


class CalibratedEnsembleTests(unittest.TestCase):
    def test_votes_use_member_priority_only_for_actual_vote_ties(self):
        values = [[5, 3], [4, 4], [3, 4]]
        self.assertEqual(aggregate_borg(values, "majority_vote").tolist(), [5, 4])

    def test_rounded_mean_and_median_produce_native_integer_values(self):
        values = [[3, 1], [4, 7], [5, 8]]
        self.assertEqual(aggregate_borg(values, "rounded_mean").tolist(), [4, 5])
        self.assertEqual(aggregate_borg(values, "rounded_median").tolist(), [4, 7])

    def test_non_native_predictions_and_unknown_aggregation_are_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_borg([[11]], "majority_vote")
        with self.assertRaises(ValueError):
            aggregate_borg([[1]], "unknown")


if __name__ == "__main__":
    unittest.main()
