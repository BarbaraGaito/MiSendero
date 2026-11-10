"""Exercise source targets, native real-row fitting and reload on public observations."""
import io
import json
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

import fatigue_emap_history_transfer as study
import fatigue_prior_view_training as forbidden


class ActualHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.heads,cls.actual_source_calls = {},[]
        for algorithm in study.ALGORITHMS:
            kind = type(study.estimator(algorithm))
            original = kind.fit
            def observe(estimator,x,y,*args,_original=original,_algorithm=algorithm,**kwargs):
                cls.actual_source_calls.append((_algorithm,np.asarray(x).copy(),np.asarray(y).copy(),np.asarray(kwargs["sample_weight"]).copy()))
                return _original(estimator,x,y,*args,**kwargs)
            with patch.object(kind,"fit",observe),patch.object(forbidden,"fitting_views",side_effect=AssertionError("Artificial history fitting forbidden")):
                cls.heads[algorithm] = study.fit_sources(cls.inputs["source"],algorithm)
        cls.fit,cls.val = next(GroupKFold(n_splits=5).split(cls.inputs["train"],groups=cls.inputs["train"].group_key))

    def test_01_plan_original_native_members_and_genuine_source_split(self):
        i = self.inputs
        self.assertEqual((len(i["frame"]),len(i["train"]),len(i["test"])),(666,487,179))
        self.assertFalse(set(i["train"].group_key)&set(i["test"].group_key))
        self.assertEqual(len(study.plan()),16)
        self.assertEqual(len({c["id"] for c in study.plan()}),16)
        self.assertEqual(sum(c["algorithm"] == "separate_actual_history_heads" for c in study.plan()),12)
        source = i["source"]
        self.assertEqual(source.groupby(["source_domain","source_partition"]).size().to_dict(),
            {("emap","fitting"):248,("emap","reserved"):57,("worker","fitting"):253,("sts","fitting"):49})
        self.assertEqual(source[source.source_domain.eq("emap")].prior2_borg.isna().sum(),102)
        self.assertFalse(source[source.source_domain.eq("emap")][["hr_last","hr_history_mean","borg_native"]].notna().any().any())
        data = study.add_features(i["frame"],self.heads["ridge"])
        pd.testing.assert_frame_equal(data[i["frame"].columns],i["frame"])

    def test_02_actual_source_estimator_targets_weights_and_source_only_scaling(self):
        self.assertEqual(len(self.actual_source_calls),9)
        for (algorithm,x,y,weight),(expected_algorithm,domain) in zip(self.actual_source_calls,
                ((a,d) for a in study.ALGORITHMS for d in study.source.FEATURES)):
            self.assertEqual(algorithm,expected_algorithm)
            part = self.inputs["source"]
            part = part[part.source_domain.eq(domain)&part.source_partition.eq("fitting")]
            np.testing.assert_array_equal(y,part[study.source.TARGET_COLUMNS[domain]].to_numpy()-part.prior_borg.to_numpy())
            expected = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
            expected *= len(part)/expected.sum()
            np.testing.assert_allclose(weight,expected,rtol=0,atol=0)
            head = self.heads[algorithm][domain]
            raw = part[study.source.FEATURES[domain]]
            transformed = head[0].transform(raw)
            np.testing.assert_allclose(head[1].mean_,transformed.mean(axis=0),rtol=0,atol=1e-12)
            self.assertEqual(int(head[1].n_samples_seen_),len(part))
            np.testing.assert_allclose(x,head[1].transform(transformed),rtol=0,atol=1e-12)

    def fit_and_check_native(self,member,combined):
        candidate = next(c for c in study.plan() if c.get("member") == member and c["source_algorithm"] == "ridge" and c["include_worker_sts"] == combined)
        fitting,validation = self.inputs["train"].iloc[self.fit],self.inputs["train"].iloc[self.val]
        heads = self.heads["ridge"]
        before = joblib.hash(heads)
        calls = []
        kind = MLPClassifier if member == "core" else CatBoostClassifier
        original = kind.fit
        def observe(model,x,y,*args,**kwargs):
            calls.append((model,x.copy(),np.asarray(y).copy()))
            return original(model,x,y,*args,**kwargs)
        with patch.object(kind,"fit",observe),patch.object(study,"fit_sources",side_effect=AssertionError("Source refit during native fitting")),\
                patch.object(forbidden,"fitting_views",side_effect=AssertionError("Artificial history fitting forbidden")):
            model = study.EmapHistoryBorg(candidate,heads).fit(fitting,self.inputs["specifications"])
        self.assertEqual(len(calls),1)
        estimator,x,y = calls[0]
        target = fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()-fitting.prior_borg.to_numpy(int)
        np.testing.assert_array_equal(y.astype(int),target)
        expected = fitting[self.inputs["specifications"][member]["features"]].copy()
        for domain in model.heads:
            expected[study.OUTPUTS[domain]] = heads[domain].predict(fitting[study.source.FEATURES[domain]])
        if member == "core":
            pipeline = model.model.model
            values = pipeline[0].transform(expected)
            np.testing.assert_allclose(pipeline[1].mean_,values.mean(axis=0),rtol=0,atol=1e-12)
            self.assertEqual(int(pipeline[1].n_samples_seen_),len(fitting))
            np.testing.assert_allclose(x,pipeline[1].transform(values),rtol=0,atol=1e-12)
            self.assertEqual((estimator.alpha,estimator.max_iter,estimator.max_fun,estimator.early_stopping),(10.,5000,100000,False))
        else:
            pd.testing.assert_frame_equal(x,expected)
            self.assertEqual(estimator.get_params()["iterations"],900)
        self.assertEqual(before,joblib.hash(heads))
        self.assertEqual(model.optimizer_summary["actual_native_fit_rows"],len(fitting))
        self.assertEqual(model.optimizer_summary["actual_auxiliary_source_targets"],550 if combined else 248)
        self.assertEqual(model.optimizer_summary["synthetic_rows"],0)
        query = validation[model.input_features].copy()
        predicted = model.predict(query)
        self.assertEqual(len(predicted),len(validation))
        self.assertTrue(set(predicted)<={f"Borg {i}" for i in range(11)})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"actual-history-model.joblib"
            joblib.dump(model,path)
            np.testing.assert_array_equal(joblib.load(path).predict(query),predicted)
        self.assertEqual(before,joblib.hash(heads))

    def test_03_actual_mlp_combined_heads_real_targets_and_reload(self):
        self.fit_and_check_native("core",True)

    def test_04_actual_catboost_emap_only_real_targets_and_reload(self):
        self.fit_and_check_native("cat",False)


if __name__ == "__main__":
    unittest.main()
