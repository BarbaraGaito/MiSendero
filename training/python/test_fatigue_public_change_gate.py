"""Real-public-data tests for the constrained native gate and binary heads."""
import io
import unittest
import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold
from torch.nn import functional as F
import fatigue_public_change_gate as study


class PublicChangeGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.fit,cls.val = next(GroupKFold(5).split(cls.inputs['train'],groups=cls.inputs['train'].group_key))
        cls.fitting,cls.validation = cls.inputs['train'].iloc[cls.fit],cls.inputs['train'].iloc[cls.val]
        cls.cache = study.read_cache(cls.inputs,'core',0,cls.fit,cls.val)
        cls.before = joblib.hash(cls.cache)
        cls.calls,cls.steps,cls.gradient_checks = [],[],[]
        c = next(c for c in study.plan()[4:] if c['member']=='core' and c['auxiliary_weight']==.1)
        cls.model = study.PublicChangeGateBorg(c)
        def step(epoch,batch):
            z,y = batch['native_logits'],batch['native_target']
            native_loss = F.binary_cross_entropy_with_logits(z,y)
            source_losses = [(F.binary_cross_entropy_with_logits(a,b,reduction='none')*w).sum()/w.sum()
                for a,b,w in batch['source_batches'].values()]
            expected = native_loss+.1*torch.stack(source_losses).mean()+10*batch['correction'].square().mean()
            torch.testing.assert_close(batch['total'],expected,rtol=1e-12,atol=1e-12)
            if epoch==0:
                joint = study.recombine(batch['offset_probabilities'],z)
                exact_loss = -torch.log(joint[torch.arange(len(y)),batch['native_delta']]).mean()
                a = torch.autograd.grad(native_loss,batch['correction'],retain_graph=True)[0]
                b = torch.autograd.grad(exact_loss,batch['correction'],retain_graph=True)[0]
                torch.testing.assert_close(a,b,rtol=1e-12,atol=1e-14)
                gradients = torch.autograd.grad(.1*torch.stack(source_losses).mean(),tuple(cls.model.network.encoder.parameters()),retain_graph=True)
                cls.gradient_checks.append(float(torch.sqrt(sum(g.square().sum() for g in gradients))))
            cls.steps.append(epoch)
        cls.model.fit(cls.fitting,cls.inputs['gate_source'],cls.inputs['specifications']['core'],cls.inputs['context_features'],
            cls.cache,observer=lambda *args:cls.calls.append(args),step_observer=step)

    def test_original_pairs_define_all_binary_targets(self):
        self.assertEqual(len(self.calls),5)
        counts = {}
        for stage,domain,features,current,prior in self.calls:
            self.assertEqual(len(features),len(current))
            self.assertTrue(np.isfinite(current).all() and np.isfinite(prior).all())
            if stage=='source':
                original = self.inputs['gate_source'][self.inputs['gate_source'].source_domain.eq(domain)]
                np.testing.assert_array_equal(current,original[study.source.TARGETS[domain]])
                np.testing.assert_array_equal(prior,original[study.source.PRIOR])
                self.assertEqual(set((current!=prior).astype(int)),{0,1})
                counts[domain] = len(current)
            else:
                np.testing.assert_array_equal(current,self.fitting.label.str.removeprefix('Borg ').to_numpy(int))
                np.testing.assert_array_equal(prior,self.fitting.prior_borg.to_numpy(int))
        self.assertEqual(counts,study.COUNTS)
        self.assertEqual(sum(counts.values()),2287)

    def test_actual_losses_gradients_and_frozen_base(self):
        self.assertEqual(self.steps,list(range(80)))
        self.assertGreater(self.gradient_checks[0],0)
        self.assertAlmostEqual(self.gradient_checks[0],self.model.training_summary['initial_source_only_encoder_gradient_l2'])
        self.assertEqual(joblib.hash(self.cache),self.before)
        self.assertEqual(self.model.training_summary['synthetic_rows'],0)
        self.assertTrue(self.model.training_summary['nonzero_delta_relative_probabilities_frozen'])

    def test_per_domain_fitting_stats_and_real_missing_bits(self):
        parts = {'native':self.fitting,**{d:p for d,p in self.inputs['gate_source'].groupby('source_domain')}}
        for domain,frame in parts.items():
            values = study.history_values(frame)
            raw = values.to_numpy(float)
            medians = np.nanmedian(raw,axis=0)
            imputer,scaler = self.model.history_normalizers[domain]
            np.testing.assert_allclose(imputer.statistics_,medians,atol=1e-12)
            filled = np.where(np.isnan(raw),medians,raw)
            np.testing.assert_allclose(scaler.mean_,filled.mean(axis=0),atol=1e-12)
            np.testing.assert_allclose(scaler.var_,filled.var(axis=0),atol=1e-12)
            np.testing.assert_array_equal(self.model.history_transform(frame,domain).numpy()[:,2],values.second.isna().to_numpy(float))
        self.assertTrue(set(self.fitting.group_key).isdisjoint(self.validation.group_key))

    def test_initial_identity_and_trained_conditional_ratios(self):
        query = self.validation[self.model.input_features]
        base = self.model.base.logits(query).exp()
        initial = study.recombine(base,study.gate_logit(base))
        torch.testing.assert_close(initial,base,rtol=1e-12,atol=1e-15)
        np.testing.assert_array_equal(study.native.predictions(initial.log(),self.model.base.priority,query),self.model.base.predict(query))
        corrected = self.model.probabilities(query)
        keep = torch.arange(21)!=10
        torch.testing.assert_close(corrected[:,keep]/corrected[:,keep].sum(dim=1,keepdim=True),
            base[:,keep]/base[:,keep].sum(dim=1,keepdim=True),rtol=1e-12,atol=1e-15)

    def test_zero_source_exclusion_and_input_only_artifact_reload(self):
        c = next(c for c in study.plan()[4:] if c['member']=='core' and c['auxiliary_weight']==0)
        calls,batches = [],[]
        model = study.PublicChangeGateBorg(c).fit(self.fitting,self.inputs['gate_source'],
            self.inputs['specifications']['core'],self.inputs['context_features'],self.cache,
            observer=lambda *args:calls.append(args),step_observer=lambda n,b:batches.append(len(b['source_batches'])))
        self.assertEqual([row[0] for row in calls],['native'])
        self.assertEqual(batches,[0]*80)
        self.assertEqual(model.training_summary['source_fitting_targets_in_objective'],0)
        stream = io.BytesIO()
        joblib.dump(self.model,stream)
        stream.seek(0)
        restored = joblib.load(stream)
        query = self.validation[restored.input_features]
        np.testing.assert_array_equal(restored.predict(query),self.model.predict(query))
        self.assertEqual(set(vars(restored)),{'candidate','base','context_features','input_features','history_normalizers',
            'normalization_summary','context_imputer','context_scaler','network','loss_endpoints','training_summary'})
        with self.assertRaises(ValueError):
            restored.predict(self.validation)
        self.assertEqual(joblib.hash(self.cache),self.before)


if __name__=='__main__':
    unittest.main()
