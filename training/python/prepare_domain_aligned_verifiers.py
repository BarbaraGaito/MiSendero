"""Derive new verifiers while preserving every frozen preceding source file."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
code = (HERE/'audit_fatigue_shoulder_history_joint.py').read_text()
def replace(old,new):
    global code
    assert code.count(old)==1,old[:100]
    code = code.replace(old,new,1)

code = code.replace('import fatigue_shoulder_history_joint as study','import fatigue_domain_aligned_history as study')
code = code.replace('study.ShoulderHistoryBorg','study.AlignedHistoryBorg')
replace("    old = external[~external.source_domain.isin(['resistance','shoulder'])]\n    imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)\n    scaler = StandardScaler().fit(imputer.fit_transform(pd.concat([raw_history(fitting),raw_history(old,True)],ignore_index=True)))\n    transform = lambda part,is_source:scaler.transform(imputer.transform(raw_history(part,is_source))).astype(np.float32)\n    expected_history = transform(fitting,False)","""    expected_normalizers = {}
    for domain,part in {'native':fitting,**{d:p for d,p in external.groupby('source_domain')}}.items():
        imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)
        matrix = imputer.fit_transform(raw_history(part,domain!='native'))
        scaler = StandardScaler().fit(matrix[:,:2])
        assert matrix.shape[1]==3
        expected_normalizers[domain] = imputer,scaler
    def transform(part,is_source):
        domain = part.source_domain.iloc[0] if is_source else 'native'
        imputer,scaler = expected_normalizers[domain]
        matrix = imputer.transform(raw_history(part,is_source))
        expected = np.column_stack([scaler.transform(matrix[:,:2]),matrix[:,2:]])
        actual_missing = raw_history(part,is_source).iloc[:,1].isna().to_numpy(float)
        np.testing.assert_array_equal(expected[:,2],actual_missing)
        return expected.astype(np.float32)
    expected_history = transform(fitting,False)""")
replace("    np.testing.assert_allclose(model.history_scaler.mean_,scaler.mean_,rtol=0,atol=0)\n    np.testing.assert_allclose(model.history_imputer.statistics_,imputer.statistics_,rtol=0,atol=0,equal_nan=True)","""    assert set(model.domain_normalizers)==set(expected_normalizers)
    for domain,(imputer,scaler) in expected_normalizers.items():
        actual_imputer,actual_scaler = model.domain_normalizers[domain]
        np.testing.assert_allclose(actual_imputer.statistics_,imputer.statistics_,rtol=0,atol=0,equal_nan=True)
        np.testing.assert_array_equal(actual_imputer.indicator_.features_,imputer.indicator_.features_)
        np.testing.assert_allclose(actual_scaler.mean_,scaler.mean_,rtol=0,atol=0)
        np.testing.assert_allclose(actual_scaler.var_,scaler.var_,rtol=0,atol=0)
    assert model.training_summary['source_targets_transformed'] is False""")
replace("        'preprocessing_fitting_rows_only':True,'synthetic_rows':0}","        'preprocessing_fitting_rows_only':True,'domain_normalizers_independently_checked':6,\n        'missing_indicators_binary_preserved':True,'original_source_targets_untransformed':True,'synthetic_rows':0}")
replace("            old_rows = inputs['schedule_selection' if c['parent_study']=='schedule' else 'base_selection']['results']\n            old = next(r for r in old_rows if r['candidate']['id']==c['parent_candidate_id'])","            old = next(r for r in inputs['previous_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])")
replace("            if not c['shoulder_weight']:\n                previous = next(r for r in inputs['base_selection']['results'] if r['candidate']['id']==study.BASE_IDS[c['member']])\n                np.testing.assert_array_equal(prediction[val],np.asarray(previous['oof_predictions'])[val])\n                assert disk['loss_endpoints']==previous['folds'][number]['loss_endpoints']",'')
code = code.replace('study.BASE_AUDIT','study.parent.BASE_AUDIT').replace('study.INPUT_AUDIT','study.parent.INPUT_AUDIT')
code = code.replace('evaluate_fatigue_shoulder_history_joint','evaluate_fatigue_domain_aligned_history')
code = code.replace('shoulder-history-joint-verification.json','domain-aligned-history-verification.json')
code = code.replace("'old_initial_parameters_and_matched_control_predictions_preserved':True","'old_initial_parameters_preserved':True,\n        'domain_specific_numeric_stats_and_binary_missing_indicators_verified':True")
code = code.replace('Independent shoulder network:','Independent domain-aligned network:')
target = HERE/'audit_fatigue_domain_aligned_history.py'
compile(code,str(target),'exec')
if target.exists():
    assert target.read_text()==code
else:
    target.write_text(code,encoding='utf-8')

test = (HERE/'test_fatigue_shoulder_history_joint.py').read_text()
test = test.replace('import fatigue_shoulder_history_joint as study','import fatigue_domain_aligned_history as study')
test = test.replace('from audit_fatigue_shoulder_history_joint import observe_actual_fit','from audit_fatigue_domain_aligned_history import observe_actual_fit')
test = test.replace('study.ShoulderHistoryBorg','study.AlignedHistoryBorg')
start = test.index('    def test_02_zero_new_source_matches_both_previous_models(self):')
end = test.index("\n\nif __name__",start)
test = test[:start]+'''    def test_02_independent_domain_statistics_and_binary_missingness(self):
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
''' +test[end:]
test = test.replace('class RealShoulderJointTests','class RealDomainAlignedJointTests')
target = HERE/'test_fatigue_domain_aligned_history.py'
compile(test,str(target),'exec')
if target.exists():
    assert target.read_text()==test
else:
    target.write_text(test,encoding='utf-8')
evaluation = (HERE/'evaluate_fatigue_shoulder_history_joint.py').read_text()
evaluation = evaluation.replace('import fatigue_shoulder_history_joint as study','import fatigue_domain_aligned_history as study')
evaluation = evaluation.replace('study.ShoulderHistoryBorg','study.AlignedHistoryBorg')
evaluation = evaluation.replace('sole CV-qualified shoulder-transfer model','sole CV-qualified domain-aligned model')
target = HERE/'evaluate_fatigue_domain_aligned_history.py'
compile(evaluation,str(target),'exec')
if target.exists():
    assert target.read_text()==evaluation
else:
    target.write_text(evaluation,encoding='utf-8')
print('Prepared new domain-alignment auditor/tests/evaluator; frozen preceding files unchanged; no fitting',flush=True)
