"""Real public association targets and causal native representation contracts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPClassifier

import fatigue_cadence_association as study


@unittest.skipUnless(study.INPUT_AUDIT.exists(),"Requires independently audited original source/native observations")
class AssociationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.source = cls.inputs["source_fitting"]
        cls.teacher = study.fit_source(cls.source,"ridge","absolute")
        people = sorted(set(cls.inputs["train"].group_key))
        cls.fitting = cls.inputs["train"][cls.inputs["train"].group_key.isin(people[:6])]
        cls.validation = cls.inputs["train"][cls.inputs["train"].group_key.eq(people[6])]

    def candidate(self,member="core"):
        return next(c for c in study.plan() if c["algorithm"] == "retrospective_source_association" and c["member"] == member
                    and c["source_algorithm"] == "ridge" and c["source_feature_set"] == "absolute" and c["representation"] == "current_and_change")

    def test_source_and_native_person_holdouts_and_original_cases_remain_fixed(self):
        self.assertEqual(len(study.plan()),30)
        self.assertEqual(len({c["id"] for c in study.plan()}),30)
        reserved = self.inputs["source_reserved"]
        self.assertEqual((len(self.source),self.source.group_key.nunique()),(976,124))
        self.assertEqual((len(reserved),reserved.group_key.nunique()),(238,32))
        self.assertFalse(set(self.source.group_key)&set(reserved.group_key))
        self.assertEqual((len(self.inputs["frame"]),len(self.inputs["train"]),len(self.inputs["test"])),(666,487,179))
        self.assertFalse(set(self.inputs["train"].group_key)&set(self.inputs["test"].group_key))
        pd.testing.assert_frame_equal(self.inputs["frame"][self.inputs["previous"]["frame"].columns],self.inputs["previous"]["frame"])
        self.assertEqual(self.inputs["frame"][study.NATIVE["current_hr_bpm"]].isna().sum(),0)
        self.assertEqual(self.inputs["frame"][study.NATIVE["prior_hr_bpm"]].isna().sum(),3)
        self.assertEqual(self.inputs["frame"][study.NATIVE["baseline_hr_bpm"]].isna().sum(),8)
        with self.assertRaisesRegex(ValueError,"source-fitting976"):
            study.fit_source(reserved,"ridge","absolute")

    def test_actual_source_regressor_receives_original976_6to20_targets_and_person_weights(self):
        actual_fit = study.Ridge.fit
        weight = 1./self.source.groupby("group_key")["group_key"].transform("size").to_numpy()
        weight *= len(self.source)/weight.sum()
        raw_calls,fit_calls = [],[]
        def observe(x,y,w):
            pd.testing.assert_frame_equal(x,self.source[["hr_bpm","baseline_hr_bpm"]])
            np.testing.assert_array_equal(y,self.source.rpe_native)
            np.testing.assert_array_equal(w,weight)
            raw_calls.append(len(x))
        def fit(estimator,x,y,**kwargs):
            self.assertEqual(x.shape,(976,2))
            np.testing.assert_array_equal(y,self.source.rpe_native)
            np.testing.assert_array_equal(kwargs["sample_weight"],weight)
            self.assertGreater(float(np.max(y)),10)
            fit_calls.append(len(y))
            return actual_fit(estimator,x,y,**kwargs)
        with patch.object(study.Ridge,"fit",new=fit):
            model = study.fit_source(self.source,"ridge","absolute",observe)
        self.assertEqual(raw_calls,fit_calls)
        self.assertEqual(fit_calls,[976])
        self.assertEqual(int(model[-2].n_samples_seen_),976)
        total = pd.DataFrame({"person":self.source.group_key,"weight":weight}).groupby("person").weight.sum()
        np.testing.assert_allclose(total,np.full(124,976/124),rtol=0,atol=1e-12)

    def check_reload(self,model):
        predicted = model.predict(self.validation)
        runtime = self.validation[model.input_features]
        np.testing.assert_array_equal(model.predict(runtime),predicted)
        self.assertFalse(set(model.input_features)&{"label","row_key","group_key",study.STATE,study.CHANGE})
        self.assertFalse(set(vars(model))&{"frame","pool","histories","row_keys","source_fitting","source_reserved"})
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory)/"actual-association-native-borg.joblib"
            joblib.dump(model,artifact)
            np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),predicted)

    def test_native_actual_fitter_receives_original_rows_delta_targets_and_computed_features(self):
        actual_native,actual_mlp = study.DynamicsClassifier.fit,MLPClassifier.fit
        seen_rows,seen_targets = [],[]
        expected = (self.fitting.label.str.removeprefix("Borg ").astype(int)-self.fitting.prior_borg.astype(int)).astype(str)
        def native(model,data):
            pd.testing.assert_frame_equal(data[self.fitting.columns],self.fitting)
            self.assertEqual(len(model.candidate["features"]),15)
            self.assertEqual(model.candidate["features"][-2:],[study.STATE,study.CHANGE])
            self.assertFalse(set(study.NATIVE.values())&set(model.candidate["features"]))
            seen_rows.append(len(data))
            return actual_native(model,data)
        def mlp(estimator,x,y,**kwargs):
            np.testing.assert_array_equal(y,expected)
            self.assertEqual((estimator.max_iter,estimator.max_fun,estimator.alpha),(5000,100000,10))
            self.assertEqual(list(estimator.hidden_layer_sizes),[16,8])
            seen_targets.append(len(y))
            return actual_mlp(estimator,x,y,**kwargs)
        before = joblib.hash(self.teacher)
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")), \
                patch.object(study,"fit_source",side_effect=AssertionError("Native fitting must not refit source functions")), \
                patch.object(study.DynamicsClassifier,"fit",new=native),patch.object(MLPClassifier,"fit",new=mlp):
            model = study.AssociationBorg(self.candidate(),self.teacher).fit(self.fitting,self.inputs["specifications"])
        self.assertEqual(seen_rows,seen_targets)
        self.assertEqual(seen_rows,[len(self.fitting)])
        self.assertEqual(int(model.model.model[1].n_samples_seen_),len(self.fitting))
        self.assertEqual(joblib.hash(self.teacher),before)
        self.check_reload(model)

    def test_natural_missing_states_and_differences_and_catboost_reload(self):
        frame = self.inputs["frame"]
        candidate = self.candidate()
        model = study.AssociationBorg(candidate,self.teacher)
        enriched = model.add_features(frame)
        pd.testing.assert_frame_equal(enriched[frame.columns],frame)
        self.assertEqual(enriched[study.STATE].isna().sum(),8)
        self.assertEqual(enriched[study.CHANGE].isna().sum(),11)
        currents = frame[[study.NATIVE["current_hr_bpm"],study.NATIVE["baseline_hr_bpm"]]].notna().all(axis=1)
        priors = frame[[study.NATIVE["prior_hr_bpm"],study.NATIVE["baseline_hr_bpm"]]].notna().all(axis=1)
        current_query = frame.loc[currents,[study.NATIVE["current_hr_bpm"],study.NATIVE["baseline_hr_bpm"]]].copy()
        current_query.columns = ["hr_bpm","baseline_hr_bpm"]
        np.testing.assert_array_equal(enriched.loc[currents,study.STATE],self.teacher.predict(current_query))
        both = currents&priors
        prior_query = frame.loc[both,[study.NATIVE["prior_hr_bpm"],study.NATIVE["baseline_hr_bpm"]]].copy()
        prior_query.columns = ["hr_bpm","baseline_hr_bpm"]
        np.testing.assert_array_equal(enriched.loc[both,study.CHANGE],enriched.loc[both,study.STATE]-self.teacher.predict(prior_query))
        self.assertGreater(float(enriched[study.STATE].max()),10)
        before = joblib.hash(self.teacher)
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")), \
                patch.object(study,"fit_source",side_effect=AssertionError("Source functions must remain frozen during native fitting")):
            cat = study.AssociationBorg(self.candidate("cat"),self.teacher).fit(self.fitting,self.inputs["specifications"])
            self.check_reload(cat)
            control = next(c for c in study.plan() if c["algorithm"] == "native_measured_physiology_control" and c["member"] == "core")
            measured = study.AssociationBorg(control).fit(self.fitting,self.inputs["specifications"])
            self.assertEqual(len(measured.model_features),16)
            self.assertFalse(set(measured.model_features)&{study.STATE,study.CHANGE})
            self.check_reload(measured)
        self.assertEqual(joblib.hash(self.teacher),before)


if __name__ == "__main__":
    unittest.main()
