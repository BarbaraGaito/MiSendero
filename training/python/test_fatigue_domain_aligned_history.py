"""Original public targets, zero-source equivalence and actual backpropagation."""
import tempfile
import unittest
from pathlib import Path
import joblib
import numpy as np
from sklearn.model_selection import GroupKFold

import fatigue_domain_aligned_history as study
from audit_fatigue_domain_aligned_history import observe_actual_fit


class RealDomainAlignedJointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        train = cls.inputs['train']
        cls.fit,cls.val = next(GroupKFold(n_splits=5).split(train,groups=train.group_key))
        cls.fitting,cls.validation = train.iloc[cls.fit],train.iloc[cls.val]
        cls.caches = {m:study.base.previous.read_base_cache(cls.inputs['base_inputs']['previous_inputs'],m,0,cls.fit,cls.val) for m in ('core','cat')}

    def test_01_original_sources_and_natural_missing_histories(self):
        i = self.inputs
        self.assertEqual((len(i['train']),len(i['test'])),(487,179))
        self.assertEqual((len(i['source']),len(i['reserved_source'])),(2336,312))
        self.assertFalse(set(i['source'].group_key)&set(i['reserved_source'].group_key))
        part = i['source'][i['source'].source_domain.eq('shoulder')]
        self.assertEqual((len(part),part.group_key.nunique(),part[study.source.SECOND].notna().sum()),(920,27,758))
        self.assertTrue(part.original_shoulder_rpe.between(6,20).all())
        self.assertTrue(part[['borg_native','current_rpe','original_resistance_rpe']].isna().all().all())
        self.assertEqual(len(study.plan()),10)
        with self.assertRaises(AssertionError):
            study.AlignedHistoryBorg(study.plan()[4]).fit(self.fitting,i['reserved_source'],i['specifications']['core'],i['context_features'],cached=self.caches['core'])

    def actual_fit(self,member,weight):
        c = next(c for c in study.plan()[4:] if c['member']==member and c['shoulder_weight']==weight)
        model,evidence = observe_actual_fit(c,self.fitting,self.inputs['source'],self.inputs['specifications'][member],
            self.inputs['context_features'],self.caches[member])
        self.assertEqual(evidence['actual_total_losses_independently_checked'],80)
        self.assertEqual(evidence['actual_source_targets_per_step'],2336 if weight else 1416)
        self.assertEqual(evidence['actual_shoulder_targets_per_step'],920 if weight else 0)
        self.assertEqual(evidence['actual_source_target_calls'],400 if weight else 320)
        runtime = self.validation[model.input_features]
        self.assertFalse({'label','row_key','group_key'}&set(runtime))
        predicted = model.predict(runtime)
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder)/'real-history.joblib'
            joblib.dump(model,file)
            np.testing.assert_array_equal(joblib.load(file).predict(runtime),predicted)
        return model,predicted

    def test_02_independent_domain_statistics_and_binary_missingness(self):
        c = study.plan()[4]
        model = study.AlignedHistoryBorg(c).prepare_normalizers(self.fitting,self.inputs['source'])
        before = joblib.hash(self.inputs['source'])
        parts = {'native':self.fitting,**{d:p for d,p in self.inputs['source'].groupby('source_domain')}}
        for domain,part in parts.items():
            actual = model.history_transform(part).numpy()
            missing = part.prior2_borg.isna() if domain=='native' else part[study.source.SECOND].isna()
            np.testing.assert_array_equal(actual[:,2],missing.to_numpy(float))
            np.testing.assert_allclose(actual[:,:2].mean(axis=0),0,rtol=0,atol=1e-6)
            self.assertEqual(model.normalization_summary[domain]['fitting_rows'],len(part))
        self.assertEqual(model.normalization_summary['native']['fitting_rows'],len(self.fit))
        self.assertLess(len(self.fit),487)
        self.assertEqual(joblib.hash(self.inputs['source']),before)

    def test_03_actual_zero_and_positive_source_targets_reach_core(self):
        for weight in (0.,1.):
            model,_ = self.actual_fit('core',weight)
            self.assertEqual(model.training_summary['source_targets_transformed'],False)
            self.assertEqual(model.training_summary['initial_shoulder_only_encoder_gradient_l2']>0,weight>0)

    def test_04_actual_zero_and_positive_source_targets_with_frozen_cat(self):
        for weight in (0.,.1):
            model,_ = self.actual_fit('cat',weight)
            self.assertEqual(model.training_summary['initial_shoulder_only_encoder_gradient_l2']>0,weight>0)


if __name__=='__main__':
    unittest.main(verbosity=2)
