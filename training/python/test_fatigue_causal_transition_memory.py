"""Behavioral checks using actual public records only."""
import io
import unittest
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
import fatigue_causal_transition_memory as study


class RealTransitionMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        cls.train = cls.inputs['train']
        cls.fit,cls.val = next(GroupKFold(5).split(cls.train,groups=cls.train.group_key))
        cls.fitting,cls.validation = cls.train.iloc[cls.fit],cls.train.iloc[cls.val]
        cls.cache = study.read_cache(cls.inputs,'cat',0,cls.fit,cls.val)
        cls.candidate = next(c for c in study.plan()[4:] if c['member']=='cat' and c['scope']=='session')
        cls.model = study.TransitionMemoryBorg(cls.candidate).fit(cls.fitting,cls.cache)
        cls.query = cls.validation[cls.model.input_features]
        cls.episodes = study.make_episodes(cls.validation.drop(columns='label'),cls.validation,
            cls.inputs['memory_manifest'],'session',cls.model.input_features)

    def test_actual_past_only_packets_and_label_free_query(self):
        meta = study.temporal_metadata(self.validation,self.inputs['memory_manifest'])
        by_key = {key:n for n,key in enumerate(self.validation.row_key)}
        links = 0
        for n,episode in enumerate(self.episodes):
            self.assertNotIn('label',self.query)
            expected = meta[(meta.group_key==meta.iloc[n].group_key)&(meta.session_start==meta.iloc[n].session_start)
                &(meta.response_time<=meta.iloc[n].response_time-pd.Timedelta(minutes=1))].sort_values('response_time')
            self.assertEqual(episode['support_keys'],self.validation.iloc[expected.index].row_key.tolist())
            for key,label in zip(episode['support_keys'],episode['support_labels']):
                self.assertEqual(label,self.validation.iloc[by_key[key]].label)
                links += 1
            study.validate_episode(self.query.iloc[[n]],episode,'session')
        self.assertGreater(links,0)
        with self.assertRaises(ValueError):
            study.make_episodes(self.validation,self.validation,self.inputs['memory_manifest'],'session',self.model.input_features)

    def test_preprocessing_uses_population_fitting_rows_only(self):
        raw = self.fitting[self.model.retrieval_features].to_numpy(float)
        median = np.nanmedian(raw,axis=0)
        np.testing.assert_allclose(self.model.imputer.statistics_,median,rtol=0,atol=1e-12)
        filled = np.where(np.isnan(raw),median,raw)
        missing = self.model.imputer.indicator_.features_
        encoded = np.column_stack([filled,np.isnan(raw[:,missing]).astype(float)])
        np.testing.assert_allclose(self.model.scaler.mean_,encoded.mean(axis=0),atol=1e-12)
        np.testing.assert_allclose(self.model.scaler.var_,encoded.var(axis=0),atol=1e-12)
        self.assertTrue(set(self.fitting.group_key).isdisjoint(self.validation.group_key))
        self.assertEqual(self.model.fitting_summary['fitting_row_keys'],self.fitting.row_key.tolist())

    def test_zero_memory_reproduces_frozen_population_predictions(self):
        for member in ('core','cat'):
            cache = study.read_cache(self.inputs,member,0,self.fit,self.val)
            c = next(c for c in study.plan()[2:4] if c['member']==member)
            model = study.TransitionMemoryBorg(c).fit(self.fitting,cache)
            episodes = study.make_episodes(self.validation.drop(columns='label'),self.validation,
                self.inputs['memory_manifest'],'session',model.input_features)
            actual = model.predict(self.validation[model.input_features],episodes)
            np.testing.assert_array_equal(actual,cache['base'].predict(self.validation[model.input_features]))
            old = self.inputs['parent_selection']['results'][0 if member=='core' else 1]
            np.testing.assert_array_equal(actual,np.asarray(old['oof_predictions'])[self.val])

    def test_observed_transition_mixture_and_delta_argmax(self):
        p,evidence = self.model.probabilities(self.query,self.episodes)
        n = next(n for n,e in enumerate(evidence) if e['support_count']>0)
        episode,c = self.episodes[n],self.candidate
        support = episode['support_features']
        target = np.asarray([int(x.removeprefix('Borg ')) for x in episode['support_labels']])-support.prior_borg.to_numpy(int)+10
        zq,zs = self.model.transform(self.query.iloc[[n]])[0],self.model.transform(support)
        ages = study.validate_episode(self.query.iloc[[n]],episode,'session')
        weights = np.asarray([np.exp(-np.sum((z-zq)**2)/(len(zq)*2*c['bandwidth']**2)-age/10)
            for z,age in zip(zs,ages)])
        counts = np.zeros(21)
        for index,weight in zip(target,weights):
            counts[index] += weight
        mass = weights.sum()
        alpha = c['strength']*mass/(mass+1)
        base = np.exp(self.model.base.logits(self.query.iloc[[n]]).numpy()[0])
        np.testing.assert_allclose(p[n],(1-alpha)*base+alpha*counts/mass,atol=1e-14)
        self.assertAlmostEqual(evidence[n]['mixture_weight'],alpha)
        self.assertLess(alpha,c['strength'])

    def test_artifact_reload_and_packets_reject_mismatched_query(self):
        stream = io.BytesIO()
        before = joblib.hash(self.cache)
        joblib.dump(self.model,stream)
        stream.seek(0)
        restored = joblib.load(stream)
        self.assertEqual(set(vars(restored)),{'candidate','base','retrieval_features','input_features','imputer','scaler','fitting_summary'})
        self.assertEqual(restored.fitting_summary['population_artifact_stored_personal_reports'],0)
        np.testing.assert_array_equal(restored.predict(self.query,self.episodes),self.model.predict(self.query,self.episodes))
        # Two different genuine queries, not generated or modified observations.
        with self.assertRaises(ValueError):
            study.validate_episode(self.query.iloc[[1]],self.episodes[0],'session')
        self.assertEqual(joblib.hash(self.cache),before)


if __name__=='__main__':
    unittest.main()
