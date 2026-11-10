"""Verify separate source-order tasks on original public observations."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier

import fatigue_emap_ordered_functions as study


class ActualOrderedFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.existing = study.parent.read_sources(study.parent.fingerprint(cls.inputs["parent_inputs"]))
        cls.functions,cls.calls = {},[]
        for algorithm in study.parent.ALGORITHMS:
            kind = type(study.parent.estimator(algorithm))
            original = kind.fit
            def observe(estimator,x,y,*args,_algorithm=algorithm,_original=original,**kwargs):
                cls.calls.append((_algorithm,np.asarray(x).copy(),np.asarray(y).copy(),kwargs.copy()))
                return _original(estimator,x,y,*args,**kwargs)
            with patch.object(kind,"fit",new=observe),patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories forbidden")):
                cls.functions[algorithm] = study.fit_ordered_functions(cls.inputs["source"],algorithm)
        cls.fit,cls.val = next(GroupKFold(n_splits=5).split(cls.inputs["train"],groups=cls.inputs["train"].group_key))

    def test_01_frozen_plan_uses_only_preceding_cv_and_original_cases(self):
        inputs = self.inputs
        self.assertEqual((len(inputs["frame"]),len(inputs["train"]),len(inputs["test"])),(666,487,179))
        candidates = study.plan(inputs["previous_audit"])
        self.assertEqual(len(candidates),10)
        self.assertEqual(len({c["id"] for c in candidates}),10)
        self.assertFalse(set(inputs["train"].group_key)&set(inputs["test"].group_key))
        for candidate in candidates[4:]:
            self.assertEqual(candidate["include_worker_sts"],inputs["previous_audit"]["best_new_by_member"][candidate["member"]]["candidate"]["include_worker_sts"])
            self.assertFalse(candidate["native_phase_equivalence_assumed"])
        self.assertEqual(study.FEATURES,{"T2":["prior_borg"],"T3":["prior_borg","prior2_borg"],"T4":["prior_borg","prior2_borg"]})

    def test_02_nine_actual_source_estimator_calls_cover248distinct_targets_each_algorithm(self):
        self.assertEqual(len(self.calls),9)
        data = self.inputs["source"]
        source = data[data.source_domain.eq("emap")&data.source_partition.eq("fitting")]
        seen = {}
        for (algorithm,x,y,kwargs),(expected_algorithm,slot) in zip(self.calls,
                ((a,s) for a in study.parent.ALGORITHMS for s in study.FEATURES)):
            self.assertEqual(algorithm,expected_algorithm)
            part = source[source.current_slot.eq(int(slot[1:]))]
            np.testing.assert_array_equal(y,part.current_rpe.to_numpy()-part.prior_borg.to_numpy())
            self.assertNotIn("sample_weight",kwargs)
            model = self.functions[algorithm][slot]
            self.assertEqual(int(model[1].n_samples_seen_),len(part))
            self.assertEqual(model[0].n_features_in_,1 if slot == "T2" else 2)
            self.assertFalse(part[study.FEATURES[slot]].isna().any().any())
            np.testing.assert_allclose(model[1].mean_,part[study.FEATURES[slot]].mean().to_numpy(),rtol=0,atol=1e-12)
            np.testing.assert_allclose(x,model[1].transform(model[0].transform(part[study.FEATURES[slot]])),rtol=0,atol=1e-12)
            seen.setdefault(algorithm,[]).extend(part.row_key)
        for keys in seen.values():
            self.assertEqual(len(keys),248)
            self.assertEqual(len(set(keys)),248)

    def actual_native(self,member):
        candidate = next(c for c in study.plan(self.inputs["previous_audit"])[4:] if c["source_algorithm"] == "ridge" and c["member"] == member)
        ordered,existing = self.functions["ridge"],self.existing["ridge"]
        before = joblib.hash((ordered,existing))
        fitting,validation = self.inputs["train"].iloc[self.fit],self.inputs["train"].iloc[self.val]
        rows,targets = [],[]
        kind = study.parent.DynamicsClassifier if member == "core" else study.parent.native.CatBoostBorg
        estimator_kind = MLPClassifier if member == "core" else CatBoostClassifier
        original,estimator_original = kind.fit,estimator_kind.fit
        def observe(model,data):
            pd.testing.assert_frame_equal(data[fitting.columns],fitting)
            for slot in ("T2","T3","T4"):
                query = fitting[["prior_borg"]] if slot == "T2" else fitting[["prior_borg","prior2_borg"]]
                np.testing.assert_allclose(data[study.OUTPUTS[slot]],ordered[slot].predict(query),rtol=0,atol=0)
            rows.append(len(data))
            return original(model,data)
        def observe_estimator(model,x,y,**kwargs):
            expected = fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()-fitting.prior_borg.to_numpy(int)
            np.testing.assert_array_equal(np.asarray(y).astype(int),expected)
            targets.append(len(y))
            return estimator_original(model,x,y,**kwargs)
        with patch.object(kind,"fit",new=observe),patch.object(estimator_kind,"fit",new=observe_estimator),\
                patch.object(study,"fit_ordered_functions",side_effect=AssertionError("Native fitting cannot refit source")),\
                patch.object(study.parent,"fit_sources",side_effect=AssertionError("Native fitting cannot refit earlier source")),\
                patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories forbidden")):
            model = study.OrderedHistoryBorg(candidate,ordered,existing).fit(fitting,self.inputs["specifications"])
        self.assertEqual(rows,targets)
        self.assertEqual(rows,[len(fitting)])
        self.assertEqual(len(model.model_features),len(self.inputs["specifications"][member]["features"])+3+(2 if candidate["include_worker_sts"] else 0))
        if member == "core":
            self.assertEqual(int(model.model.model[1].n_samples_seen_),len(fitting))
            self.assertEqual((model.model.model[-1].max_iter,model.model.model[-1].max_fun),(5000,100000))
        self.assertEqual(before,joblib.hash((ordered,existing)))
        runtime = validation[model.input_features]
        predicted = model.predict(runtime)
        self.assertEqual(len(predicted),len(validation))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"actual-ordered-functions.joblib"
            joblib.dump(model,path)
            np.testing.assert_array_equal(joblib.load(path).predict(runtime),predicted)
        self.assertEqual(before,joblib.hash((ordered,existing)))

    def test_03_actual_mlp_folds_preserve_rows_and_frozen_functions(self):
        self.actual_native("core")

    def test_04_actual_catboost_folds_preserve_rows_and_frozen_functions(self):
        self.actual_native("cat")


if __name__ == "__main__":
    unittest.main()
