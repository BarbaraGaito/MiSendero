"""Hyperparameter fitting checked exclusively on actual public cases."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
from sklearn.neural_network import MLPClassifier

import fatigue_real_mlp_hyperparameters as study


@unittest.skipUnless(study.PARENT_AUDIT.exists(),"Requires independently audited real walking-source models")
class RealHyperparameterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        parents = cls.inputs[0]
        train = parents[1]
        people = sorted(set(train.group_key))
        cls.fitting = train[train.group_key.isin(people[:6])]
        cls.validation = train[train.group_key.eq(people[6])]
        cls.specifications = parents[3]["member_specifications"]
        cls.teachers = study.read_ridge_heads(study.fingerprint(cls.inputs))

    def candidate(self,features):
        return next(c for c in study.plan()[4:] if c["feature_set"] == features
                    and c["params"]["hidden_layer_sizes"] == [8] and c["params"]["alpha"] == 100.)

    def fit(self,features):
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
            return study.TunedRealBorg(self.candidate(features),self.teachers).fit(self.fitting,self.specifications)

    def test_predeclared_grid_changes_only_capacity_l2_and_solver_budgets(self):
        recipes = study.plan()
        self.assertEqual(len(recipes),22)
        self.assertEqual(len(recipes[4:]),18)
        self.assertEqual({tuple(c["params"]["hidden_layer_sizes"]) for c in recipes[4:]},{(8,),(16,8),(32,16)})
        self.assertEqual({c["params"]["alpha"] for c in recipes[4:]},{1.,10.,100.})
        self.assertTrue(all(c["params"]["max_iter"] == 5000 and c["params"]["max_fun"] == 100000
                            and c["params"]["tol"] == .0001 and not c["early_stopping"] for c in recipes[4:]))

    def test_actual_estimator_receives_unchanged_integer_difference_targets_and_original_row_count(self):
        expected = (self.fitting.label.str.removeprefix("Borg ").astype(int)-self.fitting.prior_borg.astype(int)).astype(str).to_numpy()
        actual_fit = MLPClassifier.fit
        for features in ("original_13","real_walking_ridge"):
            seen = []
            def observe(estimator,x,y,**kwargs):
                self.assertEqual(len(x),len(self.fitting))
                np.testing.assert_array_equal(y,expected)
                seen.append(1)
                return actual_fit(estimator,x,y,**kwargs)
            with patch.object(MLPClassifier,"fit",new=observe):
                model = self.fit(features)
            self.assertEqual(seen,[1])
            self.assertEqual(model.optimizer_summary["actual_native_fit_rows"],len(self.fitting))
            self.assertEqual(model.optimizer_summary["synthetic_rows"],0)

    def test_optimizer_parameters_and_native_only_preprocessing_are_honored(self):
        for features in ("original_13","real_walking_ridge"):
            model = self.fit(features)
            pipeline = model.model.model if features == "original_13" else model.model.model.model
            estimator = pipeline[-1]
            self.assertEqual(estimator.max_iter,5000)
            self.assertEqual(estimator.max_fun,100000)
            self.assertEqual(estimator.alpha,100.)
            self.assertEqual(estimator.hidden_layer_sizes,[8])
            self.assertEqual(estimator.random_state,42)
            self.assertFalse(estimator.early_stopping)
            self.assertEqual(int(pipeline[1].n_samples_seen_),len(self.fitting))
            self.assertLessEqual(estimator.n_iter_,5000)
            self.assertFalse(set(model.input_features)&{"label","row_key","group_key"})

    def test_source_parameters_stay_frozen_and_reload_requires_no_current_truth_or_ids(self):
        before = {name:copy.deepcopy(teacher[-1].coef_) for name,teacher in self.teachers.items()}
        for features in ("original_13","real_walking_ridge"):
            model = self.fit(features)
            expected = model.predict(self.validation)
            runtime = self.validation[model.input_features]
            np.testing.assert_array_equal(model.predict(runtime),expected)
            self.assertFalse(set(vars(model))&{"frame","histories","pool","row_keys"})
            for name,coefficient in before.items():
                np.testing.assert_array_equal(self.teachers[name][-1].coef_,coefficient)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"actual-tuned-native.joblib"
                joblib.dump(model,path)
                np.testing.assert_array_equal(joblib.load(path).predict(runtime),expected)


if __name__ == "__main__":
    unittest.main()
