"""Compact features on genuine public observations; no generated fitting rows."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPClassifier

import fatigue_cadence_compact as study


@unittest.skipUnless(study.PARENT_AUDIT.exists(),"Requires independently audited actual CADENCE/native snapshots")
class CompactCadenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.heads = study.read_sources(cls.inputs)
        train = cls.inputs["train"]
        people = sorted(set(train.group_key))
        cls.fitting = train[train.group_key.isin(people[:6])]
        cls.validation = train[train.group_key.eq(people[6])]

    def candidate(self,member="core"):
        return next(c for c in study.plan() if c.get("input_mode") == "source_proxy" and c["member"] == member
            and c["source_algorithm"] == "random_forest" and c["source_feature_set"] == "relative"
            and (member == "cat" or c["params"]["hidden_layer_sizes"] == [16,8] and c["params"]["alpha"] == 10))

    def test_original_person_boundaries_and_predeclared_capacity_grid(self):
        self.assertEqual(len(study.plan()),32)
        self.assertEqual(len({c["id"] for c in study.plan()}),32)
        new = study.plan()[6:]
        self.assertEqual(sum(c["member"] == "core" and c["input_mode"] == "source_proxy" for c in new),18)
        self.assertEqual(sum(c["member"] == "cat" and c["input_mode"] == "source_proxy" for c in new),6)
        self.assertEqual((len(self.inputs["train"]),len(self.inputs["test"])),(487,179))
        self.assertFalse(set(self.inputs["train"].group_key)&set(self.inputs["test"].group_key))
        self.assertEqual((len(self.inputs["source_fitting"]),len(self.inputs["source_reserved"])),(851,206))
        self.assertFalse(set(self.inputs["source_fitting"].group_key)&set(self.inputs["source_reserved"].group_key))

    def test_source_feature_preserves_real_missing_pairs_without_label_conversion(self):
        candidate = self.candidate()
        teacher = self.heads["random_forest","relative"]
        frame = self.inputs["frame"]
        fields = ["cadence_input_hr_delta_baseline","cadence_input_hr_ratio_baseline"]
        actual = np.isfinite(frame[fields].to_numpy(float)).all(axis=1)
        self.assertEqual(int((~actual).sum()),11)
        model = study.CompactCadenceBorg(candidate,teacher)
        enriched = model.add_features(frame)
        pd.testing.assert_frame_equal(enriched[frame.columns],frame)
        self.assertEqual(len(enriched),666)
        self.assertTrue(enriched.loc[~actual,study.OUTPUT].isna().all())
        expected = teacher.predict(frame.loc[actual,fields].rename(columns={
            fields[0]:"hr_delta_baseline",fields[1]:"hr_ratio_baseline"}))
        np.testing.assert_array_equal(enriched.loc[actual,study.OUTPUT],expected)
        self.assertGreater(float(expected.max()),10)

    def test_actual_mlp_sees_original_rows_delta_targets_and_compact_predictors(self):
        candidate = self.candidate()
        teacher = self.heads["random_forest","relative"]
        before = joblib.hash(teacher)
        actual_native,actual_mlp = study.DynamicsClassifier.fit,MLPClassifier.fit
        rows,targets = [],[]
        expected_y = (self.fitting.label.str.removeprefix("Borg ").astype(int)-self.fitting.prior_borg.astype(int)).astype(str)
        def native(model,data):
            pd.testing.assert_frame_equal(data[self.fitting.columns],self.fitting)
            self.assertEqual(len(model.candidate["features"]),14)
            self.assertEqual(model.candidate["features"][-1],study.OUTPUT)
            self.assertFalse(set(study.parent.NATIVE.values())&set(model.candidate["features"]))
            rows.append(len(data))
            return actual_native(model,data)
        def mlp(estimator,x,y,**kwargs):
            np.testing.assert_array_equal(y,expected_y)
            self.assertEqual(estimator.max_iter,5000)
            self.assertEqual(estimator.max_fun,100000)
            self.assertEqual(estimator.alpha,10)
            self.assertEqual(list(estimator.hidden_layer_sizes),[16,8])
            targets.append(len(y))
            return actual_mlp(estimator,x,y,**kwargs)
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")), \
                patch.object(study.parent,"fit_source",side_effect=AssertionError("Frozen source functions must not refit")), \
                patch.object(study.DynamicsClassifier,"fit",new=native),patch.object(MLPClassifier,"fit",new=mlp):
            model = study.CompactCadenceBorg(candidate,teacher).fit(self.fitting,self.inputs["specifications"])
        self.assertEqual(rows,targets)
        self.assertEqual(rows,[len(self.fitting)])
        self.assertEqual(int(model.model.model[1].n_samples_seen_),len(self.fitting))
        self.assertEqual(joblib.hash(teacher),before)
        self.check_reload(model)

    def check_reload(self,model):
        predicted = model.predict(self.validation)
        runtime = self.validation[model.input_features]
        np.testing.assert_array_equal(model.predict(runtime),predicted)
        self.assertFalse(set(model.input_features)&{"label","row_key","group_key",study.OUTPUT})
        self.assertFalse(set(vars(model))&{"frame","pool","histories","row_keys","source_fitting","source_reserved"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"compact-actual-public-borg.joblib"
            joblib.dump(model,path)
            np.testing.assert_array_equal(joblib.load(path).predict(runtime),predicted)

    def test_catboost_reload_and_matched_measured_control_preserve_source_functions(self):
        teacher = self.heads["random_forest","relative"]
        before = joblib.hash(teacher)
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")), \
                patch.object(study.parent,"fit_source",side_effect=AssertionError("Frozen source functions must not refit")):
            model = study.CompactCadenceBorg(self.candidate("cat"),teacher).fit(self.fitting,self.inputs["specifications"])
            self.assertEqual(len(model.model_features),len(self.inputs["specifications"]["cat"]["features"])+1)
            self.check_reload(model)
            candidate = next(c for c in study.plan() if c.get("input_mode") == "measured_relative" and c["member"] == "core")
            control = study.CompactCadenceBorg(candidate).fit(self.fitting,self.inputs["specifications"])
            self.assertEqual(len(control.model_features),15)
            self.assertNotIn(study.OUTPUT,control.model_features)
            self.check_reload(control)
        self.assertEqual(joblib.hash(teacher),before)


if __name__ == "__main__":
    unittest.main()
