"""Source expansion checks against the actual verified public observations."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

import fatigue_survey_prior_teachers as study


@unittest.skipUnless((study.source.DIRECTORY/"dataset.csv").exists(),"Requires actual verified public questionnaire snapshots")
class SurveyPriorTeacherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()

    def test_frozen_comparison_changes_source_eligibility_without_new_native_cases(self):
        _,train,test,members,expanded,provenance,previous,_ = self.inputs
        candidates = study.plan()
        self.assertEqual((len(train),len(test),len(expanded)),(487,179,302))
        self.assertFalse(set(train.group_key) & set(test.group_key))
        self.assertEqual(len(candidates),16)
        self.assertEqual(len([c for c in candidates if c["algorithm"]=="previous_real_control"]),10)
        self.assertEqual([c["parent_candidate_id"] for c in candidates[:10]],[r["candidate"]["id"] for r in previous["results"]])
        self.assertEqual(set(members["member_specifications"]),{"core","cat"})
        self.assertEqual(provenance["new_native_borg_targets"],0)
        self.assertEqual(provenance["assumed_zero_priors"],0)
        self.assertEqual(provenance["additional_real_current_targets_with_an_observed_prior"],53)
        self.assertEqual(provenance["pre_experiment_prior_value_counts"]["0.0"],12)
        self.assertEqual(sum(provenance["pre_experiment_prior_value_counts"].values()),51)

    def test_source_teacher_fit_receives_exact_real_source_inputs_and_unmodified_delta_targets(self):
        expanded = self.inputs[4]
        original_fit = Pipeline.fit
        domains = []
        def observe(model,x,y,**kwargs):
            domain = ("worker","sts")[len(domains)]
            expected = expanded[expanded.source_domain.eq(domain)]
            pd.testing.assert_frame_equal(x,expected[study.parent.FEATURES])
            np.testing.assert_array_equal(y,expected.borg_native.to_numpy()-expected.prior_borg.to_numpy())
            self.assertEqual(len(x),len(expected))
            weights = kwargs[model.steps[-1][0]+"__sample_weight"]
            totals = pd.Series(weights,index=expected.index).groupby(expected.group_key).sum()
            np.testing.assert_allclose(totals,totals.iloc[0],rtol=0,atol=1e-10)
            domains.append(domain)
            return original_fit(model,x,y,**kwargs)
        with patch.object(Pipeline,"fit",observe):
            teachers = study.parent.fit_teachers(expanded,"ridge")
        self.assertEqual(domains,["worker","sts"])
        self.assertEqual(set(teachers),{"worker","sts"})

    def test_worker_survey_expansion_leaves_the_unmodified_sts_teacher_unchanged(self):
        old,_ = study.parent.load_sources()
        expanded = self.inputs[4]
        old_models = study.parent.fit_teachers(old,"ridge")
        new_models = study.parent.fit_teachers(expanded,"ridge")
        frame = self.inputs[1][study.parent.FEATURES]
        np.testing.assert_allclose(old_models["sts"].predict(frame),new_models["sts"].predict(frame),rtol=0,atol=1e-9)
        self.assertEqual(int(expanded.source_domain.eq("worker").sum()),253)
        self.assertEqual(int(old.source_domain.eq("worker").sum()),200)
        self.assertTrue(set(old.row_key) <= set(expanded.row_key))

    def test_real_native_fit_and_reload_need_no_current_outcome_or_identifiers(self):
        _,train,_,members,expanded,_,_,_ = self.inputs
        groups = sorted(set(train.group_key))
        fitting,validation = train[train.group_key.isin(groups[:4])],train[train.group_key.eq(groups[4])]
        teachers = study.parent.fit_teachers(expanded,"ridge")
        teacher_before = joblib.hash(teachers)
        candidate = study.plan()[10]
        native_class = study.parent.baseline.DynamicsClassifier
        original_fit = native_class.fit
        def real_rows_only(estimator,data):
            np.testing.assert_array_equal(data.row_key,fitting.row_key)
            np.testing.assert_array_equal(data.label,fitting.label)
            np.testing.assert_array_equal(data.group_key,fitting.group_key)
            return original_fit(estimator,data)
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")),patch.object(native_class,"fit",real_rows_only):
            model = study.parent.TransitionBorg(candidate,teachers).fit(fitting,members["member_specifications"])
        predicted = model.predict(validation)
        np.testing.assert_array_equal(model.predict(validation[model.input_features]),predicted)
        np.testing.assert_array_equal(model.predict(validation.drop(columns=["label","row_key","group_key"])),predicted)
        self.assertEqual(joblib.hash(teachers),teacher_before)
        self.assertEqual(set(vars(model)),{"candidate","teachers","input_features","model"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"survey-prior.joblib"
            joblib.dump(model,path)
            np.testing.assert_array_equal(joblib.load(path).predict(validation[model.input_features]),predicted)


if __name__ == "__main__":
    unittest.main()
