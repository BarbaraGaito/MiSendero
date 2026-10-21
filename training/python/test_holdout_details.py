"""Methodology regression tests; these examples are never exported as training observations."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from common.evaluation import holdout_details
import refresh_evaluation
from public_sources import OUTPUT


class HoldoutDetailsTests(unittest.TestCase):
    def test_high_accuracy_on_majority_class_does_not_hide_zero_minority_recall(self):
        report = holdout_details(["A", "A", "B"], ["A"] * 9 + ["B"], ["A"] * 10,
                                 ["A", "B"], ["train1", "train1", "train2"], ["test"] * 10)
        self.assertEqual(report["model"]["accuracy"], 0.9)
        self.assertEqual(report["model"]["balanced_accuracy"], 0.5)
        self.assertLess(report["model"]["f1_macro"], 0.5)
        self.assertEqual(report["group_support"], {"training": 2, "test": 1})
        self.assertEqual(report["difference_from_baseline"], {"accuracy": 0, "f1_macro": 0, "balanced_accuracy": 0})

    def test_baseline_uses_only_training_counts_even_when_test_majority_differs(self):
        report = holdout_details(["A", "A", "B"], ["B", "B", "B", "A"], ["B"] * 4,
                                 ["A", "B"], ["train"] * 3, ["test"] * 4)
        self.assertEqual(report["baseline"]["label"], "A")
        self.assertEqual(report["baseline"]["accuracy"], 0.25)
        self.assertEqual(report["model"]["accuracy"], 0.75)
        self.assertGreater(report["difference_from_baseline"]["f1_macro"], 0)

    def test_missing_classes_remain_explicit_in_both_partitions_and_f1_vocabulary(self):
        report = holdout_details(["A", "A", "C"], ["A", "B"], ["A", "A"],
                                 ["A", "B", "C"], ["train"] * 3, ["test"] * 2)
        self.assertEqual(report["class_coverage"]["missing_in_training"], ["B"])
        self.assertEqual(report["class_coverage"]["missing_in_test"], ["C"])
        self.assertEqual(report["class_coverage"]["test_counts"], {"A": 1, "B": 1, "C": 0})
        self.assertEqual(report["model"]["balanced_accuracy"], 0.5)
        self.assertAlmostEqual(report["model"]["f1_macro"], 2 / 9)

    def test_tied_training_baseline_keeps_first_occurrence_without_using_test_scores(self):
        report = holdout_details(["B", "A"], ["A", "A"], ["A", "A"],
                                 ["A", "B"], ["train"] * 2, ["test"] * 2)
        self.assertEqual(report["baseline"]["label"], "B")
        self.assertEqual(report["baseline"]["accuracy"], 0)

    def test_leaking_groups_mismatched_rows_and_unknown_labels_are_refused(self):
        cases = [
            (["A"], ["A"], ["A"], ["A"], ["same"], ["same"]),
            (["A"], ["A"], [], ["A"], ["train"], ["test"]),
            (["A"], ["A"], ["A"], ["A"], [], ["test"]),
            (["A"], ["A"], ["unknown"], ["A"], ["train"], ["test"]),
            (["A"], ["A"], ["A"], ["A", "A"], ["train"], ["test"]),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                holdout_details(*args)

    def test_extending_real_evaluation_preserves_original_measurements_and_results(self):
        directory = OUTPUT / "fatigue"
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
        rows = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
        predictions = pd.read_csv(directory / "test_predictions.csv", dtype=str)
        original_metrics, original_rows, original_predictions = copy.deepcopy(metrics), rows.copy(), predictions.copy()
        result = refresh_evaluation.extend_evaluation(metrics, rows, provenance["lineage"], predictions)
        self.assertEqual(metrics, original_metrics)
        pd.testing.assert_frame_equal(rows, original_rows)
        pd.testing.assert_frame_equal(predictions, original_predictions)
        self.assertEqual(result["trained_at"], metrics["trained_at"])
        self.assertEqual(result["evaluation_validity"], metrics["evaluation_validity"])
        self.assertAlmostEqual(result["evaluation_details"]["model"]["f1_macro"], metrics["metrics"]["test"]["f1_macro"])

    def test_refresh_never_writes_reports_if_any_source_validation_fails(self):
        with patch.object(refresh_evaluation, "ADAPTERS", {"fatigue": None, "physio_risk": None}), \
                patch.object(refresh_evaluation, "validate", side_effect=[None, ValueError("Changed source")]), \
                patch.object(Path, "write_text") as write:
            with self.assertRaisesRegex(ValueError, "Changed source"):
                refresh_evaluation.main()
            write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
