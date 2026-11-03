"""Fitting-boundary checks using temporary technical fixtures only."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold

from fatigue_experiment import cv_candidate
from fatigue_transfer import evaluate


class FatigueExperimentTests(unittest.TestCase):
    def setUp(self):
        self.target = pd.DataFrame({"x": np.arange(36, dtype=float), "label": ["Borg 1", "Borg 2", "Borg 3"] * 12,
                                    "group_key": [f"target-{i // 3}" for i in range(36)]})
        self.external = pd.DataFrame({"x": np.arange(100, 109, dtype=float), "label": ["Borg 1", "Borg 2", "Borg 3"] * 3,
                                      "group_key": [f"external-{i // 3}" for i in range(9)]})
        self.candidate = {"algorithm": "random_forest", "params": {"n_estimators": 3, "min_samples_leaf": 1},
                          "features": ["x"], "external_weight": 1.}

    def test_imputation_is_fitted_only_on_each_target_training_partition(self):
        fitted = []
        original_fit = SimpleImputer.fit

        def spy(imputer, features, *args, **kwargs):
            fitted.append(features["x"].tolist())
            return original_fit(imputer, features, *args, **kwargs)

        with patch.object(SimpleImputer, "fit", spy):
            result = cv_candidate(self.target, self.candidate)
        for values, fold in zip(fitted, result["folds"]):
            expected = self.target[self.target["group_key"].isin(fold["train_groups"])]["x"].tolist()
            self.assertEqual(values, expected)

    def test_external_rows_augment_fit_but_never_validation_denominator(self):
        fitted = []
        original_fit = SimpleImputer.fit

        def spy(imputer, features, *args, **kwargs):
            fitted.append(features["x"].tolist())
            return original_fit(imputer, features, *args, **kwargs)

        with patch.object(SimpleImputer, "fit", spy):
            result = evaluate(self.target, self.external, self.candidate)
        self.assertEqual(len(result["oof_predictions"]), len(self.target))
        for values, fold in zip(fitted, result["folds"]):
            expected = self.target[self.target["group_key"].isin(fold["target_train_groups"])]["x"].tolist() + self.external["x"].tolist()
            self.assertEqual(values, expected)
            self.assertFalse(set(fold["target_train_groups"]) & set(fold["validation_groups"]))


if __name__ == "__main__":
    unittest.main()
