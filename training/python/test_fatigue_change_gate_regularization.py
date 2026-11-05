"""Actual-public-pair checks focused on the new correction penalties."""
import io
import unittest
import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold
import fatigue_change_gate_regularization as study


class GateRegularizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.fit,cls.val = next(GroupKFold(5).split(cls.inputs['train'],groups=cls.inputs['train'].group_key))
        cls.fitting,cls.validation = cls.inputs['train'].iloc[cls.fit],cls.inputs['train'].iloc[cls.val]
        cls.cache = study.read_cache(cls.inputs,'core',0,cls.fit,cls.val)
        cls.before = joblib.hash(cls.cache)
        cls.models,cls.checks,cls.initial,cls.actual_calls = {},{}, {},{}
        for penalty in (0.,1.):
            c = next(c for c in study.plan()[6:] if c['member']=='core' and c['auxiliary_weight']==.1 and c['correction_penalty']==penalty)
            model = study.RegularizedChangeGateBorg(c)
            rows,calls = [],[]
            def step(epoch,batch):
                correction = batch['correction']
                y = batch['native_target']
                native = torch.nn.functional.binary_cross_entropy_with_logits(batch['native_logits'],y)
                losses = [(torch.nn.functional.binary_cross_entropy_with_logits(z,t,reduction='none')*w).sum()/w.sum()
                    for z,t,w in batch['source_batches'].values()]
                expected = native+.1*torch.stack(losses).mean()+penalty*correction.square().mean()
                torch.testing.assert_close(batch['total'],expected,rtol=1e-12,atol=1e-12)
                derivative = torch.autograd.grad(batch['total'],correction,retain_graph=True)[0]
                expected_derivative = (torch.sigmoid(batch['native_logits'])-y+2*penalty*correction)/len(y)
                torch.testing.assert_close(derivative,expected_derivative,rtol=1e-12,atol=1e-14)
                if epoch==0:
                    cls.initial[penalty] = {name:value.detach().clone() for name,value in model.network.state_dict().items()}
                rows.append(epoch)
            model.fit(cls.fitting,cls.inputs['gate_source'],cls.inputs['specifications']['core'],cls.inputs['context_features'],
                cls.cache,observer=lambda *args:calls.append(args),step_observer=step)
            cls.models[penalty],cls.checks[penalty],cls.actual_calls[penalty] = model,rows,calls

    def test_declared_grid_and_actual_penalty10_controls(self):
        recipes = study.plan()
        self.assertEqual(len(recipes),18)
        self.assertEqual({(c['member'],c['auxiliary_weight'],c['correction_penalty']) for c in recipes[6:]},
            {(m,w,p) for m in ('core','cat') for w in (0.,.1) for p in (0.,.1,1.)})
        old = {r['candidate']['id']:r for r in self.inputs['parent_selection']['results']}
        for c in recipes[2:6]:
            self.assertEqual(old[c['parent_candidate_id']]['candidate']['correction_penalty'],10.)

    def test_penalty_coefficients_reach_actual_objective_and_gradients(self):
        for penalty,steps in self.checks.items():
            self.assertEqual(steps,list(range(80)))
            self.assertEqual(self.models[penalty].candidate['correction_penalty'],penalty)
            self.assertGreater(self.models[penalty].training_summary['initial_source_only_encoder_gradient_l2'],0)
        for name in self.initial[0.]:
            torch.testing.assert_close(self.initial[0.][name],self.initial[1.][name],rtol=0,atol=0)

    def test_only_original_native_and_source_pairs_supervise(self):
        for calls in self.actual_calls.values():
            self.assertEqual(len(calls),5)
            for kind,domain,features,current,prior in calls:
                original = self.fitting if kind=='native' else self.inputs['gate_source'][self.inputs['gate_source'].source_domain.eq(domain)]
                expected = original.label.str.removeprefix('Borg ').to_numpy(int) if kind=='native' else original[study.source.TARGETS[domain]].to_numpy(float)
                old = original.prior_borg.to_numpy(int) if kind=='native' else original[study.source.PRIOR].to_numpy(float)
                np.testing.assert_array_equal(current,expected)
                np.testing.assert_array_equal(prior,old)
                self.assertEqual(len(features),len(original))
        self.assertTrue(set(self.fitting.group_key).isdisjoint(self.validation.group_key))

    def test_native_bases_and_relative_nonzero_probabilities_are_frozen(self):
        self.assertEqual(joblib.hash(self.cache),self.before)
        keep = torch.arange(21)!=10
        for model in self.models.values():
            query = self.validation[model.input_features]
            before,after = model.base.logits(query).exp(),model.probabilities(query)
            torch.testing.assert_close(before[:,keep]/before[:,keep].sum(dim=1,keepdim=True),
                after[:,keep]/after[:,keep].sum(dim=1,keepdim=True),rtol=1e-12,atol=1e-15)
            self.assertEqual(model.training_summary['synthetic_rows'],0)
        self.assertEqual(joblib.hash(self.cache),self.before)

    def test_reload_uses_input_only_actual_features(self):
        for model in self.models.values():
            stream = io.BytesIO()
            joblib.dump(model,stream)
            stream.seek(0)
            restored = joblib.load(stream)
            query = self.validation[restored.input_features]
            np.testing.assert_array_equal(restored.predict(query),model.predict(query))
            with self.assertRaises(ValueError):
                restored.predict(self.validation)


if __name__=='__main__':
    unittest.main()
