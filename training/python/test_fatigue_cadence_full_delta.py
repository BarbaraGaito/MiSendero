"""Real-public physiology/history tests for the new source gate."""
import io
import unittest
import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupKFold
import fatigue_cadence_full_delta as study


class CadenceBinaryGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.fit,cls.val = next(GroupKFold(5).split(cls.inputs['train'],groups=cls.inputs['train'].group_key))
        cls.fitting,cls.validation = cls.inputs['train'].iloc[cls.fit],cls.inputs['train'].iloc[cls.val]
        cls.cache = study.read_cache(cls.inputs,'core',0,cls.fit,cls.val)
        cls.before = joblib.hash(cls.cache)
        c = next(c for c in study.plan()[6:] if c['member']=='core' and c['auxiliary_weight']==.1)
        cls.calls,cls.steps = [],[]
        def step(epoch,batch):
            z,y,correction = batch['native_logits'],batch['native_target'],batch['correction']
            native = torch.nn.functional.cross_entropy(z,y)
            source_z,source_y,weight = batch['source_batches']['cadence']
            source_loss = (torch.nn.functional.binary_cross_entropy_with_logits(source_z,source_y,reduction='none')*weight).sum()/weight.sum()
            expected = native+.1*source_loss+c['correction_penalty']*correction.square().mean()
            torch.testing.assert_close(batch['total'],expected,rtol=1e-12,atol=1e-12)
            derivative = torch.autograd.grad(batch['total'],correction,retain_graph=True)[0]
            onehot = torch.nn.functional.one_hot(y,21).to(torch.float64)
            expected_derivative = (torch.softmax(z,dim=1)-onehot)/len(y)+2*c['correction_penalty']*correction/(len(y)*21)
            torch.testing.assert_close(derivative,expected_derivative,rtol=1e-12,atol=1e-14)
            cls.steps.append(epoch)
        cls.model = study.FullDeltaCadenceBorg(c).fit(cls.fitting,cls.inputs['gate_source'],cls.inputs['specifications']['core'],
            cls.inputs['context_features'],cls.cache,observer=lambda *args:cls.calls.append(args),step_observer=step)

    def test_actual_original_source_and_native_targets(self):
        self.assertEqual(len(self.calls),2)
        kind,domain,features,current,prior = self.calls[0]
        self.assertEqual((kind,domain),('source','cadence'))
        source = self.inputs['gate_source']
        self.assertEqual(list(features),study.prepared.FEATURES)
        np.testing.assert_array_equal(current,source.current_rpe.to_numpy(float))
        np.testing.assert_array_equal(prior,source.prior.to_numpy(float))
        self.assertEqual(int(np.sum(current==prior)),299)
        self.assertEqual(int(np.sum(current!=prior)),552)
        self.assertEqual(int(np.sum(current<prior)),4)
        self.assertNotIn('current_rpe',list(features))
        self.assertEqual(self.calls[1][2].index.tolist(),self.fitting.index.tolist())

    def test_actual_losses_and_source_gradients(self):
        self.assertEqual(self.steps,list(range(80)))
        self.assertGreater(self.model.training_summary['initial_source_only_encoder_gradient_l2'],0)
        self.assertEqual(self.model.training_summary['source_fitting_targets_in_objective'],851)
        self.assertEqual(self.model.training_summary['source_reserved_pairs_not_fitted'],206)
        self.assertEqual(self.model.training_summary['synthetic_rows'],0)

    def test_fitting_only_numeric_stats_and_real_availability_flags(self):
        for domain,frame in [('native',self.fitting),('cadence',self.inputs['gate_source'])]:
            values = study.state_values(frame)
            raw = values.to_numpy(float)
            median = np.nanmedian(raw,axis=0)
            imputer,scaler = self.model.history_normalizers[domain]
            np.testing.assert_allclose(imputer.statistics_,median,atol=1e-12)
            filled = np.where(np.isnan(raw),median,raw)
            np.testing.assert_allclose(scaler.mean_,filled.mean(axis=0),atol=1e-12)
            np.testing.assert_allclose(scaler.var_,filled.var(axis=0),atol=1e-12)
            transformed = self.model.history_transform(frame,domain).numpy()
            self.assertEqual(transformed.shape[1],11)
            np.testing.assert_array_equal(transformed[:,6:],np.isnan(raw[:,1:]).astype(float))
        self.assertTrue(set(self.fitting.group_key).isdisjoint(self.validation.group_key))

    def test_frozen_native_weights_with_trainable_nonzero_ratios(self):
        query = self.validation[self.model.input_features]
        before,after = self.model.base.logits(query).exp(),self.model.probabilities(query)
        keep = torch.arange(21)!=10
        changed = torch.max(torch.abs(before[:,keep]/before[:,keep].sum(dim=1,keepdim=True)-after[:,keep]/after[:,keep].sum(dim=1,keepdim=True)))
        self.assertGreater(float(changed),1e-8)
        self.assertEqual(joblib.hash(self.cache),self.before)

    def test_zero_source_control_and_input_only_reload(self):
        c = next(c for c in study.plan()[6:] if c['member']=='core' and c['auxiliary_weight']==0)
        calls = []
        model = study.FullDeltaCadenceBorg(c).fit(self.fitting,self.inputs['gate_source'],self.inputs['specifications']['core'],
            self.inputs['context_features'],self.cache,observer=lambda *args:calls.append(args))
        self.assertEqual([row[0] for row in calls],['native'])
        self.assertEqual(model.training_summary['source_fitting_targets_in_objective'],0)
        stream = io.BytesIO()
        joblib.dump(self.model,stream)
        stream.seek(0)
        restored = joblib.load(stream)
        query = self.validation[restored.input_features]
        np.testing.assert_array_equal(restored.predict(query),self.model.predict(query))
        self.assertTrue(set(study.prepared.NATIVE_COLUMNS.values())<=set(restored.input_features))
        with self.assertRaises(ValueError):
            restored.predict(self.validation)
        self.assertEqual(joblib.hash(self.cache),self.before)


    def test_actual_recent_context_is_private_and_fitting_only(self):
        self.assertEqual(len(self.inputs['context_features']),16)
        self.assertEqual(self.model.context_features[-3:],study.added.COLUMNS)
        self.assertFalse(set(study.added.COLUMNS)&set(self.inputs['gate_source']))
        raw = pd.read_csv(study.added.recent.NATIVE_DIRECTORY/'dataset.csv').set_index('row_key')
        matched = raw.loc[self.fitting.row_key]
        expected = np.column_stack([matched.current_hr_bpm,matched.current_hr_bpm-matched.prior_hr_bpm,
            matched.current_hr_bpm/matched.prior_hr_bpm])
        np.testing.assert_allclose(self.fitting[study.added.COLUMNS],expected,atol=1e-12,equal_nan=True)
        values = self.fitting[self.model.context_features].to_numpy(float)
        np.testing.assert_allclose(self.model.context_imputer.statistics_,np.nanmedian(values,axis=0),atol=1e-12)
        transformed = self.model.context_imputer.transform(self.fitting[self.model.context_features])
        np.testing.assert_allclose(self.model.context_scaler.mean_,transformed.mean(axis=0),atol=1e-12)
        np.testing.assert_allclose(self.model.context_scaler.var_,transformed.var(axis=0),atol=1e-12)
        self.assertEqual(self.model.network.encoder[0].in_features,11)
        self.assertEqual(self.model.network.corrector[-1].out_features,21)


if __name__=='__main__':
    unittest.main()
