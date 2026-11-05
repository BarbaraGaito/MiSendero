"""Real-source transfer boundaries and native fitting/prediction invariants."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

import fatigue_cadence_transfer as study


@unittest.skipUnless(study.INPUT_AUDIT.exists(),"Requires audited actual public source/native inputs")
class CadenceTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.source = cls.inputs["source_fitting"]
        train = cls.inputs["train"]
        people = sorted(set(train.group_key))
        cls.fitting = train[train.group_key.isin(people[:6])]
        cls.validation = train[train.group_key.eq(people[6])]
        cls.teacher = study.fit_source(cls.source,"ridge","absolute")

    def candidate(self,member="core"):
        return next(c for c in study.plan() if c["algorithm"] == "separate_source_rpe_transfer"
                    and c["source_algorithm"] == "ridge" and c["source_feature_set"] == "absolute" and c["member"] == member)

    def fit(self,member="core"):
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
            return study.CadenceSourceBorg(self.candidate(member),self.teacher).fit(self.fitting,self.inputs["specifications"])

    def test_actual_source_people_are_reserved_and_native_missing_cases_are_preserved(self):
        self.assertEqual(len(self.source),851)
        reserved = self.inputs["source_reserved"]
        self.assertEqual(len(reserved),206)
        self.assertFalse(set(self.source.group_key)&set(reserved.group_key))
        self.assertEqual(self.source.group_key.nunique(),123)
        self.assertEqual(reserved.group_key.nunique(),32)
        self.assertEqual((len(self.inputs["frame"]),len(self.inputs["train"]),len(self.inputs["test"])),(666,487,179))
        self.assertEqual(self.inputs["frame"][study.NATIVE["lag_hr_bpm"]].isna().sum(),3)
        self.assertEqual(self.inputs["frame"][study.NATIVE["baseline_hr_bpm"]].isna().sum(),8)
        self.assertEqual(len(study.plan()),16)
        with self.assertRaisesRegex(ValueError,"source-fitting"):
            study.fit_source(reserved,"ridge","absolute")

    def test_source_estimator_receives_original6to20_targets_and_real_person_weights(self):
        actual_fit = study.Ridge.fit
        calls = []
        expected_weights = 1./self.source.groupby("group_key")["group_key"].transform("size").to_numpy()
        expected_weights *= len(self.source)/expected_weights.sum()
        def observe(features,target,weight):
            pd.testing.assert_frame_equal(features,self.source[study.SETS["absolute"]])
            np.testing.assert_array_equal(target,self.source.rpe_native.to_numpy())
            np.testing.assert_array_equal(weight,expected_weights)
            self.assertGreater(float(target.max()),10.)
        def fit(estimator,x,y,**kwargs):
            self.assertEqual(len(x),851)
            np.testing.assert_array_equal(y,self.source.rpe_native.to_numpy())
            np.testing.assert_array_equal(kwargs["sample_weight"],expected_weights)
            calls.append(1)
            return actual_fit(estimator,x,y,**kwargs)
        with patch.object(study.Ridge,"fit",new=fit):
            model = study.fit_source(self.source,"ridge","absolute",observe)
        self.assertEqual(calls,[1])
        self.assertEqual(int(model[-2].n_samples_seen_),851)
        totals = pd.DataFrame({"group":self.source.group_key,"weight":expected_weights}).groupby("group").weight.sum()
        np.testing.assert_allclose(totals,np.full(123,851/123),rtol=0,atol=1e-12)

    def test_native_fitter_sees_only_unchanged_actual_cases_and_borg_labels(self):
        classifier = study.parent.parent.parent.parent.baseline.DynamicsClassifier
        actual_fit = classifier.fit
        seen = []
        def observe(model,data):
            pd.testing.assert_frame_equal(data[self.fitting.columns],self.fitting)
            np.testing.assert_array_equal(data.label,self.fitting.label)
            self.assertEqual(len(data),len(self.fitting))
            self.assertTrue(np.isfinite(data[study.OUTPUT]).all())
            seen.append(1)
            return actual_fit(model,data)
        with patch.object(classifier,"fit",new=observe):
            model = self.fit()
        self.assertEqual(seen,[1])
        self.assertEqual(model.model.model[-1].max_iter,5000)
        self.assertEqual(model.model.model[-1].max_fun,100000)
        self.assertFalse(set(model.input_features)&{"label","row_key","group_key",study.OUTPUT})

    def test_source_coefficients_stay_frozen_and_reload_needs_no_query_truth_or_ids(self):
        before = copy.deepcopy(self.teacher[-1].coef_)
        for member in ("core","cat"):
            model = self.fit(member)
            expected = model.predict(self.validation)
            runtime = self.validation[model.input_features]
            np.testing.assert_array_equal(model.predict(runtime),expected)
            np.testing.assert_array_equal(self.teacher[-1].coef_,before)
            self.assertFalse(set(vars(model))&{"frame","source_fitting","source_reserved","pool","histories","row_keys"})
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"actual-cadence-transfer.joblib"
                joblib.dump(model,path)
                np.testing.assert_array_equal(joblib.load(path).predict(runtime),expected)


if __name__ == "__main__":
    unittest.main()
