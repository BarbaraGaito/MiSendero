"""Prepare independent physiology/source verification; preserve old evidence."""
import ast
import json
from pathlib import Path
import fatigue_cadence_binary_gate as study
from public_sources import digest

root = Path(__file__).parent
old_path = root/'audit_fatigue_public_change_gate.py'
code = old_path.read_text()


def replace_function(text,name,replacement):
    tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines = text.splitlines(keepends=True)
    return ''.join(lines[:node.lineno-1])+replacement+'\n'+''.join(lines[node.end_lineno:])


history = '''def history_array(frame):
    columns = study.prepared.FEATURES if 'prior' in frame else ['prior_borg','prior2_borg',*study.prepared.NATIVE_COLUMNS.values()]
    raw = frame[columns].to_numpy(float)
    median = np.nanmedian(raw,axis=0)
    assert np.isfinite(median).all()
    filled = np.where(np.isnan(raw),median,raw)
    mean,var = filled.mean(axis=0),filled.var(axis=0)
    scale = np.sqrt(var)
    scale[scale==0] = 1.
    return np.column_stack([(filled-mean)/scale,np.isnan(raw[:,1:]).astype(float)]),median,mean,var
'''
verify = '''def verify_model(model,c,fitting,external,specification,context_features,cache):
    assert model.candidate==c and model.base.specification==specification
    assert joblib.hash(model.base)==joblib.hash(cache['base'])
    expected_features = list(dict.fromkeys(cache['base'].input_features+context_features+list(study.prepared.NATIVE_COLUMNS.values())))
    assert model.input_features==expected_features and model.context_features==context_features
    assert set(model.history_normalizers)=={'native','cadence'}
    expected_summary = {}
    for domain,frame in {'native':fitting,'cadence':external}.items():
        transformed,median,mean,var = history_array(frame)
        imputer,scaler = model.history_normalizers[domain]
        np.testing.assert_allclose(imputer.statistics_,median,atol=1e-12)
        np.testing.assert_allclose(scaler.mean_,mean,atol=1e-12)
        np.testing.assert_allclose(scaler.var_,var,atol=1e-12)
        np.testing.assert_allclose(model.history_transform(frame,domain).numpy(),transformed.astype(np.float32),atol=1e-6)
        columns = study.prepared.FEATURES if 'prior' in frame else ['prior_borg','prior2_borg',*study.prepared.NATIVE_COLUMNS.values()]
        missing = frame[columns].isna().sum().astype(int).tolist()
        expected_summary[domain] = {'fitting_rows':len(frame),'fitting_people':frame.group_key.nunique(),
            'actual_missing_inputs':dict(zip(study.prepared.FEATURES,missing)),'numeric_columns':6,'unscaled_availability_bits':5}
    assert model.normalization_summary==expected_summary
    transformed,median,missing,mean,var = independent_preprocessing(fitting,context_features)
    np.testing.assert_allclose(model.context_imputer.statistics_,median,atol=1e-12)
    np.testing.assert_array_equal(model.context_imputer.indicator_.features_,missing)
    np.testing.assert_allclose(model.context_scaler.mean_,mean,atol=1e-12)
    np.testing.assert_allclose(model.context_scaler.var_,var,atol=1e-12)
    np.testing.assert_allclose(model.context_transform(fitting).numpy(),transformed.astype(np.float32),atol=1e-6)
    summary = model.training_summary
    assert summary['actual_native_targets']==len(fitting) and summary['actual_native_people']==fitting.group_key.nunique()
    assert summary['source_fitting_pairs_available']==851 and summary['source_fitting_actual_second_priors']==727
    assert summary['source_fitting_targets_in_objective']==(851 if c['auxiliary_weight'] else 0)
    assert summary['source_targets_by_separate_head']==({'cadence':851} if c['auxiliary_weight'] else {})
    assert summary['source_reserved_pairs_not_fitted']==206 and summary['other_source_domains_fitted']==0
    assert summary['gradient_steps']==80 and summary['base_weights_frozen'] and summary['nonzero_delta_relative_probabilities_frozen']
    assert summary['native_loss_equivalent_to_joint_nll_up_to_frozen_conditional'] and not summary['source_current_values_or_context_used_as_predictors']
    assert summary['synthetic_rows']==summary['artificial_history_views']==summary['invented_source_times_or_sensor_joins']==0
    assert summary['initial_native_output_gradient_l2']>0
    assert (summary['initial_source_only_encoder_gradient_l2']>0)==bool(c['auxiliary_weight'])
    return True
'''
code = replace_function(code,'history_array',history)
code = replace_function(code,'verify_model',verify)
changes = {'fatigue_public_change_gate':'fatigue_cadence_binary_gate','public-change-gate':'cadence-binary-gate',
    'joint_public_binary_change_gate':'cadence_physiology_binary_gate',
    'study.PublicChangeGateBorg(c)':'study.CadenceBinaryGateBorg(c)',
    'part[[study.source.PRIOR,study.source.SECOND]]':'part[study.prepared.FEATURES]',
    '+10*np.mean(correction**2)':"+c['correction_penalty']*np.mean(correction**2)",
    "len(selected['results'])==10":"len(selected['results'])==6",'study.plan()[4:]':'study.plan()[2:]',
    "len(artifacts)==60":"len(artifacts)==40",'len(calls)==(5 if':'len(calls)==(2 if',
    'len(source_forwards)==(320 if':'len(source_forwards)==(80 if',
    "'actual_source_target_steps':320 if":"'actual_source_target_steps':80 if",
    "'all_10_oof_recipes_recomputed'":"'all_6_oof_recipes_recomputed'",
    "'all_30_fold_artifacts_recomputed'":"'all_20_fold_artifacts_recomputed'",
    "'source_fitting_actual_pairs':2287":"'source_fitting_actual_pairs':851",
    "'excluded_single_class_sts_pairs':49":"'other_source_domains_fitted':0",
    "'source_reserved_pairs_not_fitted':312":"'source_reserved_pairs_not_fitted':206"}
for old,new in changes.items():
    assert old in code,old
    code = code.replace(old,new)
old_eval = root/'evaluate_fatigue_public_change_gate.py'
evaluation = old_eval.read_text().replace('fatigue_public_change_gate','fatigue_cadence_binary_gate')
evaluation = evaluation.replace('public-change-gate','cadence-binary-gate')
evaluation = evaluation.replace('joint_public_binary_change_gate','cadence_physiology_binary_gate')
evaluation = evaluation.replace('PublicChangeGateBorg','CadenceBinaryGateBorg')
outputs = {'audit_fatigue_cadence_binary_gate.py':code,'evaluate_fatigue_cadence_binary_gate.py':evaluation}
for name,text in outputs.items():
    compile(text,name,'exec')
    path = root/name
    if path.exists():
        assert path.read_text()==text,name
    else:
        path.write_text(text,encoding='utf-8')
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_sources_sha256':{p.name:digest(p) for p in (old_path,old_eval)},
    'derived_files_sha256':{name:digest(root/name) for name in outputs},'historical_sources_modified':False,
    'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'changes':'Independent six-numeric/five-availability input checks,two fitting domains,one actual851pair source head,penalty1,all20fold artifacts and6OOFrecipes;all20network refits preserve80loss/backward checks and full qualified179case test path.'}
(study.DOCS/'cadence-binary-gate-verifier-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
