"""Actual public-target, causal sensor, and native fitting checks for runnerHR."""
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
from sklearn.model_selection import GroupKFold

import fatigue_furukawa_hr_transfer as study
from audit_fatigue_furukawa_hr_transfer import independently_compute_features,observed_native_fit,observed_source_fit,original_source_values


class OriginalRunnerHRTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.teachers = {}
        cls.source_evidence = []
        for algorithm in ("ridge","svr"):
            for task in ("state","delta"):
                head,evidence = observed_source_fit(cls.inputs["runner_fitting"],algorithm,task)
                cls.teachers[algorithm+"-"+task] = head
                cls.source_evidence.append(evidence)
        train = cls.inputs["train"]
        cls.fit,cls.val = next(GroupKFold(n_splits=5).split(train,groups=train.group_key))
        cls.fitting,cls.validation = train.iloc[cls.fit],train.iloc[cls.val]

    def test_01_original_people_targets_fixed_plan_and_real_missing_inputs(self):
        i = self.inputs
        self.assertEqual((len(i["frame"]),len(i["train"]),len(i["test"])),(666,487,179))
        self.assertEqual((len(i["runner_fitting"]),i["runner_fitting"].group_key.nunique(),len(i["runner_reserved"]),i["runner_reserved"].group_key.nunique()),(252,12,84,4))
        self.assertFalse(set(i["runner_fitting"].group_key)&set(i["runner_reserved"].group_key))
        self.assertEqual(len(study.plan()),14)
        self.assertEqual(sum(c["algorithm"] == "furukawa_source_function" for c in study.plan()),8)
        for task in ("state","delta"):
            head = self.teachers["ridge-"+task]
            candidate = next(c for c in study.plan() if c["algorithm"] == "furukawa_source_function" and c["source_task"] == task and c["member"] == "core" and c["source_algorithm"] == "ridge")
            actual = study.RunnerHRBorg(candidate,head).add_features(i["train"])
            expected = independently_compute_features(i["train"],head,task)
            for name,value in expected.items():
                np.testing.assert_allclose(actual[name],value,rtol=0,atol=0,equal_nan=True)
            both = np.isfinite(i["train"][[study.CURRENT,study.PRIOR]].to_numpy(float)).all(axis=1)
            self.assertEqual(int((~both).sum()),2)
            missing = study.CHANGE if task == "state" else study.DELTA
            self.assertEqual(int(actual[missing].isna().sum()),2)

    def test_02_actual_source_estimator_targets_weights_and_reserved_exclusion(self):
        self.assertEqual(len(self.source_evidence),4)
        self.assertEqual(sorted(v["actual_source_targets_observed"] for v in self.source_evidence),[168,168,252,252])
        for evidence in self.source_evidence:
            self.assertEqual(evidence["actual_source_target_calls"],1)
            self.assertEqual(evidence["actual_source_people"],12)
            self.assertEqual(evidence["reserved_source_targets_fitted"],0)
            self.assertTrue(evidence["actual_original_target_points_or_differences_and_weights_verified"])
        for task in ("state","delta"):
            _,x,y,_ = original_source_values(self.inputs["runner_fitting"],task)
            self.assertEqual(len(x),252 if task == "state" else 168)
            if task == "state":
                self.assertGreater(float(max(y)),10)
            else:
                self.assertIn(-1.,y)
                self.assertIn(2.,y)
        with self.assertRaises(ValueError):
            study.fit_source(self.inputs["runner_reserved"],"ridge","state")

    def fit_native(self,member,task=None,algorithm="ridge"):
        candidate = next(c for c in study.plan() if c.get("member") == member and c["algorithm"] == ("furukawa_source_function" if task else "native_measured_hr_control")
            and (not task or c["source_task"] == task and c["source_algorithm"] == algorithm))
        teacher = self.teachers[algorithm+"-"+task] if task else None
        before = {name:joblib.hash(head) for name,head in self.teachers.items()}
        model,evidence = observed_native_fit(candidate,self.fitting,self.inputs["specifications"],teacher)
        self.assertEqual(evidence["actual_native_rows_observed"],len(self.fitting))
        self.assertEqual(evidence["actual_native_delta_targets_observed"],len(self.fitting))
        runtime = self.validation[model.input_features]
        prediction = model.predict(runtime)
        self.assertEqual(len(prediction),len(self.validation))
        self.assertTrue(set(prediction)<={f"Borg {value}" for value in range(11)})
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory)/"original-runner-hr-native.joblib"
            joblib.dump(model,artifact)
            np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),prediction)
        self.assertEqual({name:joblib.hash(head) for name,head in self.teachers.items()},before)
        return model

    def test_03_actual_core_targets_fold_statistics_state_source_and_measured_control(self):
        self.fit_native("core","state")
        model = self.fit_native("core")
        self.assertFalse(set(model.model_features)&{study.STATE,study.CHANGE,study.DELTA})

    def test_04_actual_cat_targets_delta_source_and_input_only_reload(self):
        self.fit_native("cat","delta","svr")


if __name__ == "__main__":
    unittest.main()
