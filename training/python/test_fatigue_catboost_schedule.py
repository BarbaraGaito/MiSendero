"""Actual-native CatBoost schedule targets, fixed budgets and prefix reloads."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

import fatigue_catboost_schedule as study
from fatigue_catboost import CatBoostBorg


class RealNativeCatBoostScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        train = cls.inputs["train"]
        cls.fit,cls.val = next(GroupKFold(n_splits=5).split(train,groups=train.group_key))
        cls.fitting,cls.validation = train.iloc[cls.fit],train.iloc[cls.val]
        cls.models = {}

    def test_01_original_real_cases_exact_history_features_and_schedule(self):
        i = self.inputs
        self.assertEqual((len(i["frame"]),len(i["train"]),len(i["test"])),(666,487,179))
        self.assertEqual((i["train"].group_key.nunique(),i["test"].group_key.nunique()),(28,12))
        self.assertFalse(set(i["train"].group_key)&set(i["test"].group_key))
        self.assertEqual(len(study.plan()),16)
        native = study.plan()[4:]
        self.assertEqual({(c["learning_rate"],c["iterations"]) for c in native},
            {(rate,n) for rate in (.01,.03,.09) for n in (300,900,1800,2700)})
        self.assertEqual(sum(c["matched_historical_candidate_id"] is None for c in native),10)
        self.assertEqual(len(study.FEATURES),29)
        self.assertNotIn("label",study.FEATURES)
        self.assertNotIn("row_key",study.FEATURES)
        self.assertNotIn("group_key",study.FEATURES)
        self.assertTrue(i["train"][list(study.FEATURES)].isna().any().any())
        self.assertFalse(set(self.fitting.group_key)&set(self.validation.group_key))
        for row in i["baseline_rows"].values():
            self.assertEqual(row["candidate"]["features"],list(study.FEATURES))

    def test_02_actual_all_rate_fits_targets_parameters_and_no_validation_set(self):
        expected_x = self.fitting[list(study.FEATURES)]
        expected_y = self.fitting.label.str.removeprefix("Borg ").to_numpy(int)-self.fitting.prior_borg.to_numpy(int)
        original = study.CatBoostClassifier.fit
        calls = []

        def observed(estimator,x,y,*args,**kwargs):
            pd.testing.assert_frame_equal(x,expected_x)
            np.testing.assert_array_equal(y,expected_y)
            self.assertFalse(args)
            self.assertEqual(kwargs,{"cat_features":["current_terrain"]})
            actual = estimator.get_params()
            self.assertEqual(actual["iterations"],2700)
            self.assertIn(actual["learning_rate"],study.RATES)
            self.assertEqual(actual["depth"],3)
            self.assertEqual(actual["l2_leaf_reg"],30.)
            self.assertEqual(actual["boosting_type"],"Ordered")
            self.assertFalse(actual["use_best_model"])
            self.assertFalse(actual["allow_writing_files"])
            self.assertFalse({"label","row_key","group_key"}&set(x))
            calls.append(actual.copy())
            return original(estimator,x,y,*args,**kwargs)

        with patch.object(study.CatBoostClassifier,"fit",observed):
            for rate in study.RATES:
                c = next(c for c in study.plan()[4:] if c["learning_rate"] == rate and c["iterations"] == 2700)
                model = study.ScheduledCatBoostBorg(c).fit(self.fitting)
                self.models[rate] = model
                self.assertEqual(model.model.get_params(),study.parameters(c))
                self.assertEqual(model.model.tree_count_,2700)
                self.assertEqual(model.optimizer_summary["actual_native_delta_targets"],len(self.fitting))
                self.assertEqual(model.optimizer_summary["source_outcomes_fitted"],0)
        self.assertEqual(len(calls),3)
        self.assertEqual({c["learning_rate"] for c in calls},set(study.RATES))

    def test_03_all_fixed_prefixes_real_missing_histories_and_input_only_reload(self):
        self.assertEqual(set(self.models),set(study.RATES))
        runtime = self.validation[list(study.FEATURES)]
        self.assertTrue(runtime.isna().any().any())
        self.assertFalse({"label","row_key","group_key"}&set(runtime))
        with tempfile.TemporaryDirectory() as directory:
            for rate,model in self.models.items():
                path = Path(directory)/f"{study.rate_key(rate)}.joblib"
                joblib.dump(model,path)
                reloaded = joblib.load(path)
                for count in study.PREFIXES:
                    actual = model.predict_prefix(runtime,count)
                    np.testing.assert_array_equal(actual,reloaded.predict(runtime,ntree_end=count))
                    self.assertEqual(len(actual),len(runtime))
                    self.assertTrue(set(actual)<={f"Borg {n}" for n in range(11)})
                self.assertEqual(reloaded.model.get_params(),model.model.get_params())
                self.assertEqual(reloaded.input_features,list(study.FEATURES))
        with self.assertRaises(ValueError):
            self.models[.03].predict_prefix(runtime,100)

    def test_04_prefixes_equal_actual_historical_300_and_900_tree_fits(self):
        self.assertIn(.03,self.models)
        runtime = self.validation[list(study.FEATURES)]
        for count,key in ((300,"catboost-021"),(900,"catboost-023")):
            c = self.inputs["baseline_rows"][key]["candidate"]
            actual = CatBoostBorg(c).fit(self.fitting)
            self.assertEqual(actual.model.tree_count_,count)
            predicted = actual.predict(runtime)
            np.testing.assert_array_equal(predicted,self.models[.03].predict_prefix(runtime,count))
            np.testing.assert_array_equal(predicted,np.asarray(self.inputs["baseline_rows"][key]["oof_predictions"])[self.val])


if __name__ == "__main__":
    unittest.main()
