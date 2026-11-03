"""Actual session-rest measurements, frozen source functions and native fits."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPClassifier

import fatigue_cadence_session_rest as study


@unittest.skipUnless(study.INPUT_AUDIT.exists(),"Requires independently audited real pre-first-task pulse")
class SessionRestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.heads = study.read_sources(cls.inputs)
        people = sorted(set(cls.inputs["train"].group_key))
        cls.fitting = cls.inputs["train"][cls.inputs["train"].group_key.isin(people[:6])]
        cls.validation = cls.inputs["train"][cls.inputs["train"].group_key.eq(people[6])]

    def candidate(self,member="core",baseline="session_mean"):
        return next(c for c in study.plan() if c["algorithm"] == "session_rest_source_representation" and c["member"] == member
                    and c["baseline"] == baseline and c["source_algorithm"] == "ridge" and c["source_feature_set"] == "relative")

    def test_original_cases_person_boundaries_and_natural_baseline_missingness_are_preserved(self):
        self.assertEqual(len(study.plan()),34)
        self.assertEqual(len({c["id"] for c in study.plan()}),34)
        self.assertEqual(sum(c["algorithm"] == "session_rest_source_representation" for c in study.plan()),24)
        self.assertEqual((len(self.inputs["frame"]),len(self.inputs["train"]),len(self.inputs["test"])),(666,487,179))
        self.assertFalse(set(self.inputs["train"].group_key)&set(self.inputs["test"].group_key))
        previous = self.inputs["previous"]["frame"]
        pd.testing.assert_frame_equal(self.inputs["frame"][previous.columns],previous)
        for column in study.REST.values():
            self.assertEqual(self.inputs["frame"][column].isna().sum(),30)
        self.assertEqual(study.MODES,{"core":"current_state","cat":"current_and_change"})
        self.assertEqual(len(self.heads),6)
        for head in self.heads.values():
            self.assertEqual(int(head[-2].n_samples_seen_),976)

    def test_queries_use_each_actual_session_baseline_and_preserve_missing_values(self):
        frame = self.inputs["frame"]
        for baseline in study.BASELINES:
            for feature_set in ("absolute","relative"):
                candidate = {**self.candidate(baseline=baseline),"source_feature_set":feature_set}
                for role in ("current","prior"):
                    actual = study.source_query(frame,candidate,role)
                    hr = frame[study.parent.NATIVE[role+"_hr_bpm"]]
                    base = frame[study.REST[baseline]]
                    expected = pd.DataFrame({"hr_bpm":hr,"baseline_hr_bpm":base}) if feature_set == "absolute" else pd.DataFrame({
                        "hr_delta_baseline":hr-base,"hr_ratio_baseline":hr/base})
                    pd.testing.assert_frame_equal(actual,expected)
                model = study.SessionRestBorg(candidate,self.heads["ridge",feature_set])
                enriched = model.add_features(frame)
                pd.testing.assert_frame_equal(enriched[frame.columns],frame)
                self.assertEqual(enriched[study.STATE].isna().sum(),30)
                measured = frame[study.REST[baseline]].notna()
                np.testing.assert_array_equal(enriched.loc[measured,study.STATE],self.heads["ridge",feature_set].predict(study.source_query(frame.loc[measured],candidate,"current")))

    def check_reload(self,model):
        expected = model.predict(self.validation)
        runtime = self.validation[model.input_features]
        np.testing.assert_array_equal(model.predict(runtime),expected)
        self.assertFalse(set(model.input_features)&{"label","row_key","group_key",study.STATE,study.CHANGE})
        self.assertFalse(set(vars(model))&{"frame","pool","histories","row_keys","source_fitting","source_reserved"})
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory)/"real-session-rest-borg.joblib"
            joblib.dump(model,artifact)
            np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),expected)

    def test_actual_native_mlp_receives_original_rows_delta_targets_and_fixed_hyperparameters(self):
        actual_native,actual_mlp = study.DynamicsClassifier.fit,MLPClassifier.fit
        observed_rows,observed_targets = [],[]
        expected = (self.fitting.label.str.removeprefix("Borg ").astype(int)-self.fitting.prior_borg.astype(int)).astype(str)
        def native(model,data):
            pd.testing.assert_frame_equal(data[self.fitting.columns],self.fitting)
            self.assertEqual(len(model.candidate["features"]),14)
            self.assertEqual(model.candidate["features"][-1],study.STATE)
            self.assertFalse(set(study.REST.values())&set(model.candidate["features"]))
            observed_rows.append(len(data))
            return actual_native(model,data)
        def mlp(estimator,x,y,**kwargs):
            np.testing.assert_array_equal(y,expected)
            self.assertEqual((estimator.max_iter,estimator.max_fun,estimator.alpha),(5000,100000,10))
            self.assertEqual(list(estimator.hidden_layer_sizes),[16,8])
            observed_targets.append(len(y))
            return actual_mlp(estimator,x,y,**kwargs)
        before = {key:joblib.hash(head) for key,head in self.heads.items()}
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")), \
                patch.object(study.parent,"fit_source",side_effect=AssertionError("Audited source functions must remain frozen")), \
                patch.object(study.DynamicsClassifier,"fit",new=native),patch.object(MLPClassifier,"fit",new=mlp):
            model = study.SessionRestBorg(self.candidate(),self.heads["ridge","relative"]).fit(self.fitting,self.inputs["specifications"])
        self.assertEqual(observed_rows,observed_targets)
        self.assertEqual(observed_rows,[len(self.fitting)])
        self.assertEqual(int(model.model.model[1].n_samples_seen_),len(self.fitting))
        self.assertEqual({key:joblib.hash(head) for key,head in self.heads.items()},before)
        self.check_reload(model)

    def test_actual_catboost_difference_and_raw_control_need_no_query_truth_or_source_refit(self):
        before = {key:joblib.hash(head) for key,head in self.heads.items()}
        frame = self.inputs["frame"]
        candidate = self.candidate("cat","session_lowest")
        teacher = self.heads["ridge","relative"]
        unfit = study.SessionRestBorg(candidate,teacher)
        data = unfit.add_features(frame)
        current = study.source_state(frame,candidate,teacher,"current")
        prior = study.source_state(frame,candidate,teacher,"prior")
        np.testing.assert_allclose(data[study.CHANGE],current-prior,rtol=0,atol=0,equal_nan=True)
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")), \
                patch.object(study.parent,"fit_source",side_effect=AssertionError("Source functions must not refit")):
            model = study.SessionRestBorg(candidate,teacher).fit(self.fitting,self.inputs["specifications"])
            self.check_reload(model)
            control = next(c for c in study.plan() if c["algorithm"] == "session_rest_measured_control" and c["member"] == "core" and c["baseline"] == "session_lowest")
            measured = study.SessionRestBorg(control).fit(self.fitting,self.inputs["specifications"])
            self.assertEqual(measured.model_features[-3:],[study.parent.NATIVE["current_hr_bpm"],study.parent.NATIVE["prior_hr_bpm"],study.REST["session_lowest"]])
            self.assertEqual(len(measured.model_features),16)
            self.check_reload(measured)
        self.assertEqual({key:joblib.hash(head) for key,head in self.heads.items()},before)


if __name__ == "__main__":
    unittest.main()
