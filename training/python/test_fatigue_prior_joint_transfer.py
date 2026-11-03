"""Joint-learning safeguards exercised only on actual public observations."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch

import fatigue_prior_joint_transfer as study


@unittest.skipUnless((study.parent.source.DIRECTORY/"dataset.csv").exists(),"Requires the verified actual public report snapshots")
class PriorJointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        _,train,_,cls.external,cls.evidence = cls.inputs
        groups = sorted(set(train.group_key))
        cls.fitting,cls.validation = train[train.group_key.isin(groups[:6])],train[train.group_key.eq(groups[6])]
        cls.specification = cls.evidence["native_members"]["member_specifications"]["core"]
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
            cls.cache = study.prepare_base(cls.fitting,cls.specification)

    def candidate(self,epochs):
        return {**study.plan()[-1],"epochs":epochs}

    def fit(self,epochs,observer=None):
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")),patch("torch.rand",side_effect=AssertionError("Artificial masking prohibited")):
            return study.PriorJointBorg(self.candidate(epochs)).fit(self.fitting,self.external,self.specification,self.evidence["context_features"],self.cache,observer)

    def test_source_exposure_is_the_original_published_feature_not_an_invented_survey_clock(self):
        originals,_,_ = study.parent.parent.source_inputs()
        for domain in ("worker","sts"):
            actual = self.external[self.external.source_domain.eq(domain)]
            expected = originals[domain].set_index("row_key").loc[actual.row_key]
            np.testing.assert_array_equal(actual.elapsed_minutes.to_numpy(),expected.elapsed_minutes.to_numpy())
            self.assertFalse(set(actual.row_key) & set(self.inputs[2].row_key))
        self.assertEqual(len(self.external),302)
        self.assertEqual(len(study.plan()),14)
        self.assertFalse(set(self.evidence["context_features"]) & {"label","row_key","group_key"})
        self.assertFalse(any("age" in c for c in self.external.columns))

    def test_nested_offsets_exclude_each_report_person_and_zero_correction_preserves_the_original_model(self):
        groups = self.fitting.set_index("row_key").group_key.to_dict()
        seen = []
        for fold in self.cache["inner_folds"]:
            self.assertFalse({groups[k] for k in fold["fit_row_keys"]} & {groups[k] for k in fold["validation_row_keys"]})
            seen.extend(fold["validation_row_keys"])
        self.assertEqual(sorted(seen),sorted(self.fitting.row_key))
        model = self.fit(0)
        np.testing.assert_array_equal(model.predict(self.validation),model.base.global_predict(self.validation))
        self.assertEqual(int(model.shared_scaler.n_samples_seen_),len(self.fitting)+302)
        self.assertEqual(int(model.context_scaler.n_samples_seen_),len(self.fitting))
        with self.assertRaisesRegex(ValueError,"baseline cache"):
            study.PriorJointBorg(self.candidate(0)).fit(self.validation,self.external,self.specification,self.evidence["context_features"],self.cache)

    def test_backprop_uses_only_original_source_and_native_rows_and_leaves_the_baseline_frozen(self):
        calls = []
        def observer(kind,domain,features,current,prior):
            if kind == "source":
                expected = self.external[self.external.source_domain.eq(domain)]
                pd.testing.assert_frame_equal(features,expected[self.candidate(2)["common_features"]])
                np.testing.assert_array_equal(current,expected.borg_native.to_numpy())
                np.testing.assert_array_equal(prior,expected.prior_borg.to_numpy())
            else:
                columns = list(dict.fromkeys(self.evidence["context_features"]+self.candidate(2)["common_features"]))
                pd.testing.assert_frame_equal(features,self.fitting[columns])
                np.testing.assert_array_equal(current,self.fitting.label.str.removeprefix("Borg ").to_numpy(int))
            calls.append((kind,domain))
        initial = self.fit(0)
        base_before = copy.deepcopy(initial.base.model.state_dict())
        fitted = self.fit(2,observer)
        self.assertEqual(set(calls),{("source","worker"),("source","sts"),("native","native")})
        self.assertTrue(any(not torch.equal(value,fitted.network.state_dict()[key]) for key,value in initial.network.state_dict().items()))
        self.assertTrue(all(torch.equal(value,fitted.base.model.state_dict()[key]) for key,value in base_before.items()))
        self.assertTrue(all(not p.requires_grad for p in fitted.base.model.parameters()))
        self.assertTrue(all(not p.requires_grad and p.grad is None for p in fitted.network.parameters()))
        self.assertTrue(all(np.isfinite(row["total"]) for row in fitted.loss_endpoints))
        self.assertEqual(fitted.training_summary["synthetic_training_rows"],0)

    def test_model_reload_needs_no_current_labels_query_identifiers_or_stored_report_pool(self):
        model = self.fit(2)
        predicted = model.predict(self.validation)
        runtime = self.validation[model.input_features]
        np.testing.assert_array_equal(model.predict(runtime),predicted)
        self.assertFalse(set(vars(model)) & {"fit_logits","inner_folds","fit_row_keys","pool","histories","external"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"actual-prior-joint.joblib"
            joblib.dump(model,path)
            np.testing.assert_array_equal(joblib.load(path).predict(runtime),predicted)


if __name__ == "__main__":
    unittest.main()
