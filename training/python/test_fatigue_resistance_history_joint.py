"""Meaningful real-public-data checks for the resistance transfer comparison."""
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
from sklearn.model_selection import GroupKFold

import fatigue_resistance_history_joint as study
from audit_fatigue_resistance_history_joint import observe_actual_fit


class OriginalResistanceJointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        train = cls.inputs["train"]
        cls.fit,cls.val = next(GroupKFold(n_splits=5).split(train,groups=train.group_key))
        cls.fitting,cls.validation = train.iloc[cls.fit],train.iloc[cls.val]
        cls.caches = {member:study.previous.read_base_cache(cls.inputs["previous_inputs"],member,0,cls.fit,cls.val) for member in ("core","cat")}

    def test_01_original_cases_real_source_reservations_and_fixed_plan(self):
        i = self.inputs
        self.assertEqual((len(i["frame"]),len(i["train"]),len(i["test"])),(666,487,179))
        self.assertEqual((len(i["source"]),len(i["reserved_source"])),(1416,125))
        self.assertEqual(i["source"].groupby("source_domain").size().to_dict(),study.SOURCE_COUNTS)
        self.assertEqual(int(i["source"][study.source.SECOND].notna().sum()),1169)
        self.assertFalse(set(i["source"].group_key)&set(i["reserved_source"].group_key))
        part = i["source"][i["source"].source_domain.eq("resistance")]
        held = i["reserved_source"][i["reserved_source"].source_domain.eq("resistance")]
        self.assertEqual((len(part),part.group_key.nunique(),len(held),held.group_key.nunique()),(866,4,68,1))
        self.assertTrue(part[["borg_native","current_rpe","hr_last","hr_history_mean"]].isna().all().all())
        candidates = study.plan(i["previous_audit"])
        self.assertEqual(len(candidates),22)
        self.assertEqual(sum(c.get("resistance_weight") == 0 for c in candidates),6)
        self.assertEqual({c["correction_penalty"] for c in candidates[4:]},{.1,1.,10.})
        self.assertEqual({c["epochs"] for c in candidates[4:]},{80})
        with self.assertRaisesRegex(ValueError,"1416original fitting-source"):
            study.ResistanceHistoryBorg(candidates[4]).fit(self.fitting,i["reserved_source"],i["specifications"]["core"],i["context_features"],cached=self.caches["core"])

    def fit_actual(self,member,weight,penalty):
        candidate = next(c for c in study.plan(self.inputs["previous_audit"])[4:] if c["member"] == member
            and c["resistance_weight"] == weight and c["correction_penalty"] == penalty)
        model,evidence = observe_actual_fit(candidate,self.fitting,self.inputs["source"],self.inputs["specifications"][member],self.inputs["context_features"],self.caches[member])
        self.assertEqual(evidence["actual_resistance_targets_per_step"],866 if weight else 0)
        self.assertEqual(evidence["actual_source_targets_per_step"],1416 if weight else 550)
        self.assertEqual(evidence["actual_total_losses_independently_checked"],80)
        self.assertEqual(evidence["actual_source_target_calls"],320 if weight else 240)
        self.assertTrue(evidence["old_initial_parameters_preserved"])
        self.assertTrue(evidence["native_base_weights_frozen"])
        runtime = self.validation[model.input_features]
        predicted = model.predict(runtime)
        self.assertTrue(set(predicted)<={f"Borg {n}" for n in range(11)})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"actual-original-resistance.joblib"
            joblib.dump(model,path)
            np.testing.assert_array_equal(joblib.load(path).predict(runtime),predicted)
        return candidate,model,predicted

    def test_02_zero_new_weight_reproduces_both_previous_controls(self):
        for member in ("core","cat"):
            candidate,model,predicted = self.fit_actual(member,0.,.1)
            old = next(r for r in self.inputs["previous"]["results"] if r["candidate"]["id"] == candidate["previous_candidate_id"])
            np.testing.assert_array_equal(predicted,np.asarray(old["oof_predictions"])[self.val])
            self.assertEqual(model.loss_endpoints,old["folds"][0]["loss_endpoints"])
            self.assertEqual(model.training_summary["initial_resistance_only_encoder_gradient_l2"],0)

    def test_03_actual866_manual_targets_reach_core_encoder(self):
        _,model,_ = self.fit_actual("core",1.,1.)
        self.assertGreater(model.training_summary["initial_resistance_only_encoder_gradient_l2"],0)

    def test_04_actual_resistance_mixture_and_strong_cat_regularization(self):
        _,model,_ = self.fit_actual("cat",.1,10.)
        self.assertGreater(model.training_summary["initial_resistance_only_encoder_gradient_l2"],0)


if __name__ == "__main__":
    unittest.main()
