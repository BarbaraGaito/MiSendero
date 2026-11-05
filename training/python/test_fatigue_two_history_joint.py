"""Observe actual public rows, native targets and source gradients in joint fitting."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch
from catboost import CatBoostClassifier
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier

import fatigue_two_history_joint as study


class ActualTwoHistoryJointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.fit,cls.val = next(GroupKFold(n_splits=5).split(cls.inputs["train"],groups=cls.inputs["train"].group_key))
        cls.fitting,cls.validation = cls.inputs["train"].iloc[cls.fit],cls.inputs["train"].iloc[cls.val]
        cls.caches,cls.base_calls = {},[]
        inner = list(GroupKFold(n_splits=3).split(cls.fitting,groups=cls.fitting.group_key))
        expected = [cls.fitting.iloc[fit] for fit,_ in inner]+[cls.fitting]
        for member in ("core","cat"):
            native_kind = study.DynamicsClassifier if member == "core" else study.CatBoostBorg
            estimator_kind = MLPClassifier if member == "core" else CatBoostClassifier
            original,estimator_original = native_kind.fit,estimator_kind.fit
            seen = []
            def observe(model,data,_member=member,_original=original):
                pd.testing.assert_frame_equal(data,expected[len(seen)])
                seen.append(data)
                return _original(model,data)
            def observe_estimator(model,x,y,_member=member,_original=estimator_original,**kwargs):
                frame = seen[-1]
                target = frame.label.str.removeprefix("Borg ").astype(int).to_numpy()-frame.prior_borg.to_numpy(int)
                np.testing.assert_array_equal(np.asarray(y).astype(int),target)
                if _member == "core":
                    assert model.max_iter == 5000 and model.max_fun == 100000 and model.alpha == 10 and not model.early_stopping
                else:
                    pd.testing.assert_frame_equal(x,frame[cls.inputs["specifications"][_member]["features"]])
                    assert model.get_params()["iterations"] == 900 and model.get_params()["depth"] == 3 and model.get_params()["l2_leaf_reg"] == 30
                cls.base_calls.append({"member":_member,"actual_rows":len(y),"row_keys":frame.row_key.tolist()})
                return _original(model,x,y,**kwargs)
            with patch.object(native_kind,"fit",new=observe),patch.object(estimator_kind,"fit",new=observe_estimator),\
                    patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial fitting histories prohibited")):
                cls.caches[member] = study.prepare_base(cls.fitting,member,cls.inputs["specifications"][member])

    def test_01_original_cases_public_pairs_and_fixed_plan(self):
        i = self.inputs
        self.assertEqual((len(i["frame"]),len(i["train"]),len(i["test"])),(666,487,179))
        self.assertEqual((len(i["source"]),len(i["reserved_source"])),(550,57))
        self.assertEqual(int(i["source"][study.source.SECOND].notna().sum()),367)
        self.assertEqual(i["source"].groupby("source_domain").size().to_dict(),study.SOURCE_COUNTS)
        self.assertFalse(set(i["source"].group_key)&set(i["reserved_source"].group_key))
        self.assertFalse(set(i["frame"].group_key)&set(i["source"].group_key))
        self.assertFalse(set(i["train"].group_key)&set(i["test"].group_key))
        candidates = study.plan(i["previous_audit"])
        self.assertEqual(len(candidates),16)
        self.assertEqual(len({c["id"] for c in candidates}),16)
        self.assertEqual(sum(c.get("auxiliary_weight") == 0 for c in candidates),4)
        pd.testing.assert_frame_equal(study.history_query(i["source"]),i["source"][study.COMMON])
        np.testing.assert_array_equal(study.history_query(i["train"])[study.source.PRIOR],i["train"].prior_borg)
        np.testing.assert_allclose(study.history_query(i["train"])[study.source.SECOND],i["train"].prior2_borg,rtol=0,atol=0,equal_nan=True)

    def test_02_actual_native_bases_and_person_disjoint_inner_logits(self):
        self.assertEqual(len(self.base_calls),8)
        folds = list(GroupKFold(n_splits=3).split(self.fitting,groups=self.fitting.group_key))
        for member,cache in self.caches.items():
            self.assertEqual(cache["fit_row_keys"],self.fitting.row_key.tolist())
            for number,(fit,val) in enumerate(folds):
                saved = cache["inner_folds"][number]
                self.assertEqual(saved["fit_row_keys"],self.fitting.iloc[fit].row_key.tolist())
                self.assertEqual(saved["validation_row_keys"],self.fitting.iloc[val].row_key.tolist())
                self.assertFalse(set(self.fitting.iloc[fit].group_key)&set(self.fitting.iloc[val].group_key))
                base = cache["inner_models"][number]
                np.testing.assert_array_equal(cache["fit_logits"][val].numpy(),base.logits(self.fitting.iloc[val]).numpy())
                np.testing.assert_array_equal(study.predictions(cache["fit_logits"][val],base.priority,self.fitting.iloc[val]),base.predict(self.fitting.iloc[val]))
            for model,frame in [(cache["inner_models"][n],self.fitting.iloc[fit]) for n,(fit,_) in enumerate(folds)]+[(cache["base"],self.fitting)]:
                if member == "core":
                    pipeline = model.classifier.model
                    self.assertEqual(int(pipeline[1].n_samples_seen_),len(frame))
                    np.testing.assert_array_equal(pipeline[0].statistics_,np.nan_to_num(np.nanmedian(frame[model.input_features].to_numpy(float),axis=0),nan=0))
                    np.testing.assert_allclose(pipeline[1].mean_,pipeline[0].transform(frame[model.input_features]).mean(axis=0),rtol=0,atol=1e-12)
            base = cache["base"]
            np.testing.assert_array_equal(study.predictions(base.logits(self.validation),base.priority,self.validation),base.predict(self.validation))

    def actual_joint_fit(self,member,weight):
        candidate = next(c for c in study.plan(self.inputs["previous_audit"])[4:] if c["member"] == member and c["auxiliary_weight"] == weight and c["epochs"] == 80)
        external = self.inputs["source"]
        original_native,original_source = self.fitting.copy(deep=True),external.copy(deep=True)
        before = joblib.hash(self.caches[member])
        observations,epochs,native_losses,source_losses = [],[],[],[]
        expected_target = self.fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()-self.fitting.prior_borg.to_numpy(int)+10
        source_order = sorted(study.SOURCE_COUNTS)
        def observe(kind,domain,x,current,prior):
            if kind == "native":
                pd.testing.assert_frame_equal(x,self.fitting[model.input_features])
                np.testing.assert_array_equal(current,self.fitting.label.str.removeprefix("Borg ").to_numpy(int))
                np.testing.assert_array_equal(prior,self.fitting.prior_borg)
            else:
                part = external[external.source_domain.eq(domain)]
                pd.testing.assert_frame_equal(x,part[study.COMMON])
                np.testing.assert_array_equal(current,part[study.TARGETS[domain]])
                np.testing.assert_array_equal(prior,part[study.source.PRIOR])
            observations.append((kind,domain,len(current)))
        def observe_batch(epoch,x,y,auxiliary):
            epochs.append(epoch)
            np.testing.assert_array_equal(y,expected_target)
            np.testing.assert_array_equal(x,model.history_transform(self.fitting).numpy())
            self.assertEqual(set(auxiliary),set(source_order) if weight else set())
            for domain,(shared,target,w) in auxiliary.items():
                part = external[external.source_domain.eq(domain)]
                np.testing.assert_array_equal(shared,model.history_transform(part).numpy())
                np.testing.assert_array_equal(target,(part[study.TARGETS[domain]].to_numpy()-part[study.source.PRIOR].to_numpy()).astype(np.float32))
                weights = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
                weights *= len(part)/weights.sum()
                np.testing.assert_array_equal(w,weights.astype(np.float32))
        ce = torch.nn.functional.cross_entropy
        smooth = torch.nn.functional.smooth_l1_loss
        def observe_ce(logits,target,*args,**kwargs):
            np.testing.assert_array_equal(target.numpy(),expected_target)
            self.assertEqual(tuple(logits.shape),(len(self.fitting),21))
            native_losses.append(len(target))
            return ce(logits,target,*args,**kwargs)
        def observe_source(prediction,target,*args,**kwargs):
            self.assertGreater(weight,0)
            domain = source_order[len(source_losses)%3]
            part = external[external.source_domain.eq(domain)]
            np.testing.assert_array_equal(target.numpy(),(part[study.TARGETS[domain]].to_numpy()-part[study.source.PRIOR].to_numpy()).astype(np.float32))
            source_losses.append(len(target))
            return smooth(prediction,target,*args,**kwargs)
        model = study.JointHistoryBorg(candidate)
        with patch.object(torch.nn.functional,"cross_entropy",new=observe_ce),patch.object(torch.nn.functional,"smooth_l1_loss",new=observe_source),\
                patch.object(study,"prepare_base",side_effect=AssertionError("Frozen native base cache must be reused")),\
                patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial fitting histories prohibited")):
            model.fit(self.fitting,external,self.inputs["specifications"][member],self.inputs["context_features"],cached=self.caches[member],observer=observe,batch_observer=observe_batch)
        self.assertEqual(epochs,list(range(80)))
        self.assertEqual(len(native_losses),80)
        self.assertEqual(len(source_losses),240 if weight else 0)
        self.assertEqual(sum(v[2] for v in observations if v[0] == "source"),550 if weight else 0)
        self.assertEqual(sum(v[2] for v in observations if v[0] == "native"),len(self.fitting))
        self.assertEqual(model.training_summary["actual_source_targets_in_objective"],550 if weight else 0)
        self.assertEqual(model.training_summary["gradient_steps"],80)
        self.assertEqual(model.training_summary["synthetic_rows"],0)
        if weight:
            self.assertGreater(model.training_summary["initial_encoder_gradient_l2"],0)
        else:
            self.assertEqual(model.training_summary["initial_encoder_gradient_l2"],0)
        union = pd.concat([study.history_query(self.fitting),study.history_query(external)],ignore_index=True)
        self.assertEqual(int(model.history_scaler.n_samples_seen_),len(union))
        np.testing.assert_array_equal(model.history_imputer.statistics_,np.nanmedian(union.to_numpy(float),axis=0))
        self.assertEqual(int(model.context_scaler.n_samples_seen_),len(self.fitting))
        self.assertEqual(before,joblib.hash(self.caches[member]))
        pd.testing.assert_frame_equal(self.fitting,original_native)
        pd.testing.assert_frame_equal(external,original_source)
        self.assertFalse(set(vars(model))&{"frame","external","cache","targets","row_keys","pool"})
        runtime = self.validation[model.input_features]
        predicted = model.predict(runtime)
        self.assertEqual(len(predicted),len(self.validation))
        self.assertTrue(set(predicted)<={f"Borg {i}" for i in range(11)})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"actual-two-history-joint.joblib"
            joblib.dump(model,path)
            np.testing.assert_array_equal(joblib.load(path).predict(runtime),predicted)
        self.assertEqual(before,joblib.hash(self.caches[member]))

    def test_03_actual_backpropagation_uses550_original_source_targets(self):
        self.actual_joint_fit("core",.1)

    def test_04_matched_cat_zero_auxiliary_uses_no_source_labels(self):
        self.actual_joint_fit("cat",0.)


if __name__ == "__main__":
    unittest.main()
