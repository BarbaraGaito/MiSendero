"""Technical fixtures only: leakage, selection and portable prediction checks."""
import copy
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from common.audit_selection import audit_selection
from common.export_classifier import export_classifier, predict_json, predict_proba_json
from common.selection import candidate_plan, cross_validate_candidate, fit_candidate, make_estimator, select_candidate
from compare_public import paired_group_bootstrap
from common.promotion import publication_decision


class ModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.x = pd.DataFrame({"sensor": np.arange(36, dtype=float), "time": np.tile([1., 2., 3.], 12)})
        self.y = pd.Series(["A", "B", "C"] * 12)
        self.groups = pd.Series([f"participant-{i // 3}" for i in range(36)])

    def small_plan(self):
        return [dict(item, params={**item["params"], "n_estimators": 3}) for item in candidate_plan()[:2]]

    def test_scaling_is_fitted_only_on_each_folds_observed_training_rows(self):
        observed = []
        original_fit = StandardScaler.fit

        def spy(scaler, x, *args, **kwargs):
            observed.append(x.index.tolist())
            return original_fit(scaler, x, *args, **kwargs)

        candidate = {"algorithm": "sgd", "params": {"alpha": 0.1}}
        with patch.object(StandardScaler, "fit", spy):
            cv = cross_validate_candidate(self.x, self.y, self.groups, candidate)
        for fitted, fold in zip(observed, cv["partitions"]):
            self.assertEqual(fitted, self.x.index[self.groups.isin(fold["train_groups"])].tolist())
            self.assertFalse(set(self.groups.loc[fitted]) & set(fold["validation_groups"]))

    def test_native_json_matches_sklearn_probabilities_for_all_algorithms_and_label_counts(self):
        plan = [candidate_plan()[0],
                {"algorithm": "extra_trees", "params": {"n_estimators": 3}},
                {"algorithm": "logistic_regression", "params": {"C": 1.}},
                {"algorithm": "sgd", "params": {"alpha": 0.1}},
                {"algorithm": "mlp", "params": {"hidden_layer_sizes": [4], "solver": "lbfgs", "alpha": 1.}}]
        validity = {"deployment_approved": False}
        for candidate in plan:
            for y in (self.y, self.y.replace({"C": "A"})):
                with self.subTest(algorithm=candidate["algorithm"], classes=y.nunique()):
                    estimator = make_estimator(candidate)
                    fit_candidate(estimator, candidate, self.x, y)
                    payload = export_classifier(estimator, list(self.x), candidate["algorithm"], validity)
                    np.testing.assert_allclose(predict_proba_json(payload, self.x), estimator.predict_proba(self.x), rtol=1e-10, atol=1e-10)
                    np.testing.assert_array_equal(predict_json(payload, self.x), estimator.predict(self.x))

    def test_trees_use_sklearn_float32_threshold_semantics(self):
        candidate = {"algorithm": "extra_trees", "params": {"n_estimators": 2, "max_depth": 2}}
        estimator = make_estimator(candidate)
        fit_candidate(estimator, candidate, self.x, self.y)
        payload = export_classifier(estimator, list(self.x), candidate["algorithm"], {"deployment_approved": False})
        thresholds = [t for tree in estimator.estimators_ for t in tree.tree_.threshold if t >= 0]
        probes = pd.DataFrame({"sensor": thresholds, "time": np.ones(len(thresholds))})
        np.testing.assert_allclose(predict_proba_json(payload, probes), estimator.predict_proba(probes), rtol=1e-12, atol=1e-12)

    def test_neural_network_early_stopping_never_randomly_splits_participants(self):
        for solver in ("lbfgs", "adam", "sgd"):
            estimator = make_estimator({"algorithm": "mlp", "params": {"solver": solver}})
            self.assertFalse(estimator.named_steps["classifier"].early_stopping)
        self.assertFalse(make_estimator({"algorithm": "sgd", "params": {}}).named_steps["classifier"].early_stopping)

    def test_selected_candidate_and_scores_are_recomputed_without_holdout_access(self):
        plan = self.small_plan()
        with patch("common.selection.candidate_plan", return_value=plan), patch("common.audit_selection.candidate_plan", return_value=plan):
            candidate, cv, report = select_candidate(self.x, self.y, self.groups)
            report["inputs"] = {"train_row_keys": self.x.index.tolist()}
            winner = audit_selection(report, self.x, self.y, self.groups, report["inputs"])
            self.assertEqual(winner["candidate"], candidate)
            self.assertFalse(report["test_used_for_selection"])
            self.assertGreaterEqual(report["cv_gain_over_legacy"], 0)
            for mutation in ("score", "winner", "predictions", "plan", "inputs"):
                bad = copy.deepcopy(report)
                if mutation == "score":
                    bad["results"][0]["cv"]["f1_macro_mean"] += 0.1
                elif mutation == "winner":
                    bad["winner_id"] = "unknown"
                elif mutation == "predictions":
                    bad["results"][0]["cv"]["oof_predictions"].pop()
                elif mutation == "plan":
                    bad["results"][0]["candidate"]["params"]["max_depth"] = 100
                else:
                    bad["inputs"]["train_row_keys"].pop()
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    audit_selection(bad, self.x, self.y, self.groups, report["inputs"])

    def test_nonfinite_or_wrong_feature_count_cannot_be_predicted(self):
        candidate = self.small_plan()[0]
        estimator = make_estimator(candidate)
        fit_candidate(estimator, candidate, self.x, self.y)
        payload = export_classifier(estimator, list(self.x), candidate["algorithm"], {"deployment_approved": False})
        for values in ([[float("nan"), 1]], [[1, 2, 3]]):
            with self.assertRaises(ValueError):
                predict_json(payload, values)

    def test_uncertainty_resamples_paired_independent_groups_and_is_reproducible(self):
        observed = ["A", "B", "A", "B"]
        before = ["B", "A", "B", "A"]
        groups = ["person1", "person1", "person2", "person2"]
        result = paired_group_bootstrap(observed, before, observed, groups, ["A", "B"])
        self.assertEqual(result["independent_groups"], 2)
        self.assertEqual(result["intervals"], {"accuracy_delta": [1., 1.], "f1_macro_delta": [1., 1.]})
        self.assertEqual(result, paired_group_bootstrap(observed, before, observed, groups, ["A", "B"]))

    def test_many_windows_from_one_person_cannot_produce_group_uncertainty(self):
        result = paired_group_bootstrap(["A"] * 20, ["A"] * 20, ["A"] * 20, ["one"] * 20, ["A"])
        self.assertIsNone(result["intervals"])
        self.assertEqual(result["independent_groups"], 1)

    def test_better_selection_cv_cannot_publish_a_candidate_with_worse_holdout(self):
        incumbent = {"dataset": {"features": ["hr"]}, "evaluation_protocol": {
            "train_row_keys": ["train"], "test_row_keys": ["test"], "train_groups": ["train"], "test_groups": ["test"]},
            "metrics": {"test": {"accuracy": 0.625, "f1_macro": 0.619}}}
        candidate = copy.deepcopy(incumbent)
        candidate["metrics"]["test"] = {"accuracy": 0.5, "f1_macro": 0.5}
        decision = publication_decision(incumbent, candidate)
        self.assertEqual(decision["decision"], "retained_incumbent")
        self.assertTrue(decision["test_used_for_promotion"])
        candidate["metrics"]["test"] = {"accuracy": 0.75, "f1_macro": 0.619}
        self.assertEqual(publication_decision(incumbent, candidate)["decision"], "published_candidate")
        candidate["evaluation_protocol"]["test_row_keys"] = ["different"]
        self.assertEqual(publication_decision(incumbent, candidate)["decision"], "published_new_evaluation")


if __name__ == "__main__":
    unittest.main()
