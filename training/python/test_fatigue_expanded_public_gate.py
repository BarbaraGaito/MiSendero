"""Real-public-data tests of expanded source loss and native-private physiology."""
import io
import unittest
import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold
from torch.nn import functional as F
import fatigue_expanded_public_gate as study


class ExpandedPublicGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.fit,cls.val = next(GroupKFold(5).split(cls.inputs['train'],groups=cls.inputs['train'].group_key))
        cls.fitting,cls.validation = cls.inputs['train'].iloc[cls.fit],cls.inputs['train'].iloc[cls.val]
        cls.cache = study.read_cache(cls.inputs,'core',0,cls.fit,cls.val)
        cls.before = joblib.hash(cls.cache)
        c = next(c for c in study.plan()[8:] if c['member']=='core' and c['source_mode']=='expanded_sources' and c['correction_penalty']==1.)
        cls.model = study.ExpandedHistoryGateBorg(c)
        cls.calls,cls.steps,cls.gait_gradients = [],[],[]
        def step(epoch,batch):
            z,y = batch['native_logits'],batch['native_target']
            losses = {d:(F.binary_cross_entropy_with_logits(a,b,reduction='none')*w).sum()/w.sum()
                for d,(a,b,w) in batch['source_batches'].items()}
            weights = {d:.02 for d in study.COUNTS}
            expected = F.binary_cross_entropy_with_logits(z,y)+sum(weights[d]*loss for d,loss in losses.items())+batch['correction'].square().mean()
            torch.testing.assert_close(batch['total'],expected,rtol=1e-12,atol=1e-12)
            derivative = torch.autograd.grad(batch['total'],batch['correction'],retain_graph=True)[0]
            torch.testing.assert_close(derivative,(torch.sigmoid(z)-y+2*batch['correction'])/len(y),rtol=1e-12,atol=1e-14)
            if epoch==0:
                gradients = torch.autograd.grad(.02*losses['gait_forecasting'],tuple(cls.model.network.encoder.parameters()),retain_graph=True)
                cls.gait_gradients.append(float(torch.sqrt(sum(g.square().sum() for g in gradients))))
            cls.steps.append(epoch)
        cls.model.fit(cls.fitting,cls.inputs['gate_source'],cls.inputs['specifications']['core'],cls.inputs['context_features'],
            cls.cache,observer=lambda *args:cls.calls.append(args),step_observer=step)

    def test_actual_source_pairs_and_gait_targets(self):
        self.assertEqual(len(self.calls),7)
        counts = {}
        for kind,domain,features,current,prior in self.calls:
            if kind=='source':
                part = self.inputs['gate_source'][self.inputs['gate_source'].source_domain.eq(domain)]
                self.assertEqual(list(features),['prior','second'])
                np.testing.assert_array_equal(current,part.current_rpe)
                np.testing.assert_array_equal(prior,part.prior)
                self.assertEqual(set(current!=prior),{False,True})
                counts[domain] = len(part)
        self.assertEqual(counts,study.COUNTS)
        self.assertEqual(sum(counts.values()),3548)
        self.assertEqual(counts['gait_forecasting'],410)

    def test_actual_weighted_loss_and_new_source_gradient(self):
        self.assertEqual(self.steps,list(range(80)))
        self.assertGreater(self.gait_gradients[0],0.)
        self.assertAlmostEqual(self.gait_gradients[0],self.model.training_summary['initial_new_gait_only_encoder_gradient_l2'])
        self.assertEqual(self.model.training_summary['actual_new_gait_targets_in_objective'],410)
        self.assertEqual(self.model.training_summary['source_reserved_pairs_not_fitted'],518)
        self.assertEqual(self.model.training_summary['synthetic_rows'],0)

    def test_domain_fitting_only_history_stats_and_real_missing_bits(self):
        for domain,part in {'native':self.fitting,**{d:p for d,p in self.inputs['gate_source'].groupby('source_domain')}}.items():
            values = study.history_values(part).to_numpy(float)
            median = np.nanmedian(values,axis=0)
            imputer,scaler = self.model.history_normalizers[domain]
            np.testing.assert_allclose(imputer.statistics_,median,atol=1e-12)
            filled = np.where(np.isnan(values),median,values)
            np.testing.assert_allclose(scaler.mean_,filled.mean(axis=0),atol=1e-12)
            np.testing.assert_allclose(scaler.var_,filled.var(axis=0),atol=1e-12)
            np.testing.assert_array_equal(self.model.history_transform(part,domain).numpy()[:,2],np.isnan(values[:,1]).astype(float))

    def test_native_physiology_stays_private(self):
        self.assertEqual(len(self.model.context_features),20)
        self.assertTrue(set(study.previous.prepared.NATIVE_COLUMNS.values())<=set(self.model.context_features))
        self.assertFalse(set(self.model.context_features)&set(self.inputs['gate_source']))
        self.assertTrue(set(self.fitting.group_key).isdisjoint(self.validation.group_key))
        self.assertTrue(set(self.inputs['gate_source'].group_key).isdisjoint(self.inputs['test'].group_key))

    def test_frozen_base_nonzero_ratios_and_input_only_reload(self):
        query = self.validation[self.model.input_features]
        before,after = self.model.base.logits(query).exp(),self.model.probabilities(query)
        nonzero = torch.arange(21)!=10
        torch.testing.assert_close(before[:,nonzero]/before[:,nonzero].sum(dim=1,keepdim=True),
            after[:,nonzero]/after[:,nonzero].sum(dim=1,keepdim=True),rtol=1e-12,atol=1e-15)
        stream = io.BytesIO();joblib.dump(self.model,stream);stream.seek(0)
        restored = joblib.load(stream)
        np.testing.assert_array_equal(restored.predict(query),self.model.predict(query))
        with self.assertRaises(ValueError):restored.predict(self.validation)
        self.assertEqual(joblib.hash(self.cache),self.before)

    def test_source_modes_exclude_inactive_actual_targets(self):
        for mode,domains,count in [('native_only',0,0),('legacy_sources',5,3138),('matched_total_weight',5,3138)]:
            c = next(c for c in study.plan()[8:] if c['member']=='core' and c['source_mode']==mode and c['correction_penalty']==1.)
            calls = []
            model = study.ExpandedHistoryGateBorg(c).fit(self.fitting,self.inputs['gate_source'],self.inputs['specifications']['core'],
                self.inputs['context_features'],self.cache,observer=lambda *args:calls.append(args))
            self.assertEqual(len(calls),domains+1)
            self.assertFalse(any(kind=='source' and domain=='gait_forecasting' for kind,domain,*_ in calls))
            self.assertEqual(model.training_summary['source_fitting_targets_in_objective'],count)
            self.assertEqual(model.training_summary['actual_new_gait_targets_in_objective'],0)

    def test_matched_total_weight_and_unchanged_legacy_contribution(self):
        candidates = {c['source_mode']:c for c in study.plan()[8:] if c['member']=='core' and c['correction_penalty']==1.}
        legacy,expanded,mass = [study.source_weights(candidates[k]) for k in ('legacy_sources','expanded_sources','matched_total_weight')]
        for domain in study.LEGACY:self.assertEqual(legacy[domain],expanded[domain])
        self.assertAlmostEqual(sum(expanded.values()),sum(mass.values()))
        self.assertEqual(legacy['gait_forecasting'],0.)
        self.assertEqual(expanded['gait_forecasting'],.02)


if __name__=='__main__':
    unittest.main()
