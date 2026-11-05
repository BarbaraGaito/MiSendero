"""Behavioral tests on real public native reports, without generated examples."""
import io
import unittest
import joblib
import numpy as np
from sklearn.model_selection import GroupKFold
import fatigue_observed_change_factorization as study


class ObservedChangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.fit,cls.val = next(GroupKFold(5).split(cls.inputs['train'],groups=cls.inputs['train'].group_key))
        cls.fitting,cls.validation = cls.inputs['train'].iloc[cls.fit],cls.inputs['train'].iloc[cls.val]
        cls.models,cls.seen = {},{}
        for member in ('core','cat'):
            c = next(c for c in study.plan()[2:] if c['member']==member and c['feature_set']=='history' and c['structure']=='factorized')
            calls = []
            cls.models[member] = study.ObservedChangeBorg(c).fit(cls.fitting,cls.inputs['specifications'][member],
                observer=lambda name,frame,target:calls.append((name,frame,target)))
            cls.seen[member] = calls

    def test_actual_binary_and_conditional_targets_preserve_negatives(self):
        delta = study.actual_delta(self.fitting)
        self.assertGreater((delta<0).sum(),0)
        for member,calls in self.seen.items():
            self.assertEqual([x[0] for x in calls],['change','magnitude'])
            np.testing.assert_array_equal(calls[0][2],(delta!=0).astype(int))
            np.testing.assert_array_equal(calls[1][2],delta[delta!=0])
            self.assertEqual(calls[0][1].row_key.tolist(),self.fitting.row_key.tolist())
            self.assertEqual(calls[1][1].row_key.tolist(),self.fitting.loc[delta!=0].row_key.tolist())
            self.assertIn(-1,self.models[member].models['magnitude'].classes_.astype(int))
            self.assertEqual(self.models[member].fitting_summary['synthetic_rows'],0)

    def test_exact_factorized_distribution_and_native_decisions(self):
        for model in self.models.values():
            query = self.validation[model.input_features]
            gate = model.raw_probabilities('change',query)
            mag = model.raw_probabilities('magnitude',query)
            conditional = np.full((len(query),21),.0001)
            conditional[:,10] = 0.
            conditional[:,model.models['magnitude'].classes_.astype(int)+10] = np.maximum(mag,.0001)
            conditional /= conditional.sum(axis=1,keepdims=True)
            p_change = gate[:,np.flatnonzero(model.models['change'].classes_.astype(int)==1)[0]]
            expected = conditional*p_change[:,None]
            expected[:,10] = 1-p_change
            np.testing.assert_allclose(model.probabilities(query),expected,atol=1e-14)
            delta = model.priority[expected[:,model.priority].argmax(axis=1)]-10
            labels = [f'Borg {int(v)}' for v in np.clip(query.prior_borg.to_numpy(int)+delta,0,10)]
            np.testing.assert_array_equal(model.predict(query),labels)

    def test_fresh_flat_controls_match_frozen_native_bases(self):
        for member in ('core','cat'):
            c = next(c for c in study.plan()[2:] if c['member']==member and c['feature_set']=='history' and c['structure']=='flat')
            model = study.ObservedChangeBorg(c).fit(self.fitting,self.inputs['specifications'][member])
            cache = study.predecessor.read_cache(self.inputs['predecessor_inputs'],member,0,self.fit,self.val)
            query = self.validation[model.input_features]
            np.testing.assert_array_equal(model.predict(query),cache['base'].predict(query))

    def test_submodel_preprocessing_fits_its_actual_rows(self):
        model = self.models['core']
        delta = study.actual_delta(self.fitting)
        for stage,frame in (('change',self.fitting),('magnitude',self.fitting.loc[delta!=0])):
            raw = frame[model.input_features].to_numpy(float)
            imputer,scaler = model.models[stage].steps[0][1],model.models[stage].steps[1][1]
            medians = np.nanmedian(raw,axis=0)
            np.testing.assert_allclose(imputer.statistics_,medians,atol=1e-12)
            filled = np.where(np.isnan(raw),medians,raw)
            encoded = np.column_stack([filled,np.isnan(raw[:,imputer.indicator_.features_]).astype(float)])
            np.testing.assert_allclose(scaler.mean_,encoded.mean(axis=0),atol=1e-12)
            np.testing.assert_allclose(scaler.var_,encoded.var(axis=0),atol=1e-12)
            self.assertTrue(set(frame.group_key).isdisjoint(self.validation.group_key))

    def test_reload_requires_input_only_features_and_no_personal_memory(self):
        for model in self.models.values():
            stream = io.BytesIO()
            joblib.dump(model,stream)
            stream.seek(0)
            restored = joblib.load(stream)
            query = self.validation[model.input_features]
            np.testing.assert_array_equal(restored.predict(query),model.predict(query))
            self.assertEqual(set(vars(restored)),{'candidate','specification','input_features','models','stage_summary',
                'convergence_warnings','priority','fitting_summary'})
            with self.assertRaises(ValueError):
                restored.predict(self.validation)


if __name__=='__main__':
    unittest.main()
