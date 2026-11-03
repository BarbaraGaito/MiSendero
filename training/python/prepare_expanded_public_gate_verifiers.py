"""Independent weighted-source loss and new-source gradient checks."""
import ast
import json
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent
old_audit = root/'audit_fatigue_public_change_gate.py'
text = old_audit.read_text()
text = text.replace('fatigue_public_change_gate','fatigue_expanded_public_gate').replace('public-change-gate','expanded-public-gate')
text = text.replace('joint_public_binary_change_gate','expanded_public_history_gate').replace('PublicChangeGateBorg','ExpandedHistoryGateBorg')
text = text.replace("len(selected['results'])==10","len(selected['results'])==24").replace('plan()[4:]','plan()[8:]')
text = text.replace('all_10_oof_recipes_recomputed','all_24_oof_recipes_recomputed').replace('all_30_fold_artifacts_recomputed','all_80_fold_artifacts_recomputed')
text = text.replace('len(artifacts)==60 and len(refits)==20','len(artifacts)==160 and len(refits)==80')
text = text.replace("'independent_joint_refits':20","'independent_joint_refits':80")
text = text.replace("'source_fitting_actual_pairs':2287","'source_fitting_actual_pairs':3548").replace("'source_reserved_pairs_not_fitted':312","'source_reserved_pairs_not_fitted':518")
text = text.replace("'excluded_single_class_sts_pairs':49","'gait_reserved_people_not_received':5")


def function_replace(code,name,replacement):
    node = next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines = code.splitlines(keepends=True)
    return ''.join(lines[:node.lineno-1])+replacement+'\n'+''.join(lines[node.end_lineno:])


helper = '''def independent_weights(c):
    return {d:float(c['gait_weight'] if d=='gait_forecasting' else c['auxiliary_weight']/5.) for d in sorted(study.COUNTS)}


'''
text = text.replace('def raw_probability(base,frame):',helper+'def raw_probability(base,frame):')
start = text.index("    summary = model.training_summary")
end = text.index('    return history,context.astype(np.float32)',start)
summary = '''    summary = model.training_summary
    weights = independent_weights(c)
    active = {d for d,w in weights.items() if w}
    assert study.source_weights(c)==weights and len(context_features)==20
    assert summary['actual_native_targets']==len(fitting) and summary['actual_native_people']==fitting.group_key.nunique()
    assert summary['source_fitting_pairs_available']==3548 and summary['source_fitting_actual_second_priors']==3042
    assert summary['source_fitting_targets_in_objective']==sum(study.COUNTS[d] for d in active)
    assert summary['source_targets_by_separate_head']=={d:study.COUNTS[d] for d in sorted(active)}
    assert summary['source_loss_weights']==weights and summary['actual_new_gait_targets_in_objective']==(410 if 'gait_forecasting' in active else 0)
    assert summary['source_reserved_pairs_not_fitted']==518 and summary['gait_reserved_people_not_received']==5
    assert summary['gradient_steps']==80 and summary['base_weights_frozen'] and summary['nonzero_delta_relative_probabilities_frozen']
    assert summary['native_loss_equivalent_to_joint_nll_up_to_frozen_conditional'] and not summary['source_current_values_or_context_used_as_predictors']
    assert summary['native_private_context_features']==20
    assert summary['synthetic_rows']==summary['artificial_history_views']==summary['invented_source_times_or_sensor_joins']==0
    assert summary['initial_native_output_gradient_l2']>0
    assert (summary['initial_source_only_encoder_gradient_l2']>0)==bool(active)
    assert (summary['initial_new_gait_only_encoder_gradient_l2']>0)==('gait_forecasting' in active)
'''
text = text[:start]+summary+text[end:]
needle = "    first_source_gradient = [0.]"
assert needle in text
text = text.replace(needle,needle+"\n    first_gait_gradient = [0.]\n    task_weights = independent_weights(c)\n    active = {d for d,w in task_weights.items() if w}")
text = text.replace('per_source = []','per_source = {}')
text = text.replace("assert set(batch['source_batches'])==(set(study.COUNTS) if c['auxiliary_weight'] else set())",
    "assert set(batch['source_batches'])==active and batch['source_weights']==task_weights")
text = text.replace('per_source.append(float(np.sum((np.logaddexp(0,s)-source_target[domain]*s)*w)/w.sum()))',
    'per_source[domain] = float(np.sum((np.logaddexp(0,s)-source_target[domain]*s)*w)/w.sum())')
text = text.replace("expected = loss+c['auxiliary_weight']*(np.mean(per_source) if per_source else 0.)+10*np.mean(correction**2)",
    "expected = loss+sum(task_weights[d]*v for d,v in per_source.items())+c['correction_penalty']*np.mean(correction**2)")
start = text.index('                observed_losses = [')
end = text.index('        pending_total[0]',start)
block = '''                observed_losses = {d:(torch.nn.functional.binary_cross_entropy_with_logits(a,b,reduction='none')*w).sum()/w.sum()
                    for d,(a,b,w) in batch['source_batches'].items()}
                weighted = sum((task_weights[d]*v for d,v in observed_losses.items()),torch.tensor(0.))
                gradients = torch.autograd.grad(weighted,tuple(model.network.encoder.parameters()),retain_graph=True)
                first_source_gradient[0] = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
                assert first_source_gradient[0]>0
                if 'gait_forecasting' in observed_losses:
                    gradients = torch.autograd.grad(task_weights['gait_forecasting']*observed_losses['gait_forecasting'],
                        tuple(model.network.encoder.parameters()),retain_graph=True)
                    first_gait_gradient[0] = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
                    assert first_gait_gradient[0]>0
'''
text = text[:start]+block+text[end:]
text = text.replace("assert len(calls)==(5 if c['auxiliary_weight'] else 1)","assert len(calls)==len(active)+1")
text = text.replace("assert len(source_forwards)==(320 if c['auxiliary_weight'] else 0)",
    "assert len(source_forwards)==80*len(active) and all(source_forwards.count(d)==80 for d in active)")
needle = "    verify_model(model,c,fitting,external,specification,context_features,cache)\n    return model,"
assert needle in text
text = text.replace(needle,"    np.testing.assert_allclose(first_gait_gradient[0],model.training_summary['initial_new_gait_only_encoder_gradient_l2'],atol=1e-12)\n"+needle)
text = text.replace("'actual_source_target_steps':320 if c['auxiliary_weight'] else 0", "'actual_source_target_steps':80*len(active),'actual_new_gait_target_steps':80 if 'gait_forecasting' in active else 0")
text = text.replace("'source_context_not_fabricated':True", "'actual_new_gait_encoder_gradient':first_gait_gradient[0],'source_weights_independently_verified':True,'inactive_source_labels_excluded':True,'source_context_not_fabricated':True")
text = text.replace("row['candidate'].get('auxiliary_weight',0)>0", "row['candidate'].get('gait_weight',0)>0")
old = "zeros = {m:next(row for row in selected['results'] if row['candidate'].get('member')==m and row['candidate'].get('auxiliary_weight')==0) for m in best}"
assert old in text
new = """matched = lambda mode:{m:next(row for row in selected['results'] if row['candidate'].get('member')==m and row['candidate'].get('source_mode')==mode and row['candidate']['correction_penalty']==best[m]['candidate']['correction_penalty']) for m in best}
    zeros,legacy,mass = matched('native_only'),matched('legacy_sources'),matched('matched_total_weight')"""
text = text.replace(old,new)
text = text.replace("refit_ids = {row['candidate']['id'] for row in [*best.values(),*zeros.values()]}","refit_ids = {c['id'] for c in study.plan()[8:]}")
text = text.replace("'matched_zero_source_controls':{m:compact(row) for m,row in zeros.items()},", "'matched_zero_source_controls':{m:compact(row) for m,row in zeros.items()},\n        'matched_legacy_source_controls':{m:compact(row) for m,row in legacy.items()},\n        'matched_total_weight_controls':{m:compact(row) for m,row in mass.items()},")
text = text.replace('Independent public change-gate audit','Independent expanded-history gate audit')
old_eval = root/'evaluate_fatigue_public_change_gate.py'
evaluation = (old_eval.read_text().replace('fatigue_public_change_gate','fatigue_expanded_public_gate')
    .replace('public-change-gate','expanded-public-gate').replace('joint_public_binary_change_gate','expanded_public_history_gate')
    .replace('PublicChangeGateBorg','ExpandedHistoryGateBorg'))
outputs = {'audit_fatigue_expanded_public_gate.py':text,'evaluate_fatigue_expanded_public_gate.py':evaluation}
for name,code in outputs.items():
    compile(code,name,'exec')
    path = root/name
    if path.exists():
        assert path.read_text()==code
    else:
        path.write_text(code,encoding='utf-8')
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_sources_sha256':{p.name:digest(p) for p in (old_audit,old_eval)},
    'derived_files_sha256':{name:digest(root/name) for name in outputs},'historical_sources_modified':False,
    'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'changes':'Independent six-head weighted BCE/loss/gradient,including gait-only encoder gradient and inactive-source exclusion. All24OOFmetrics/80fold artifacts and80independent refits with80actual backward steps each. Matched legacy/total-mass/native-only controls;original179qualified-test path.'}
(ROOT/'docs/fatigue-80-2026-10-25/expanded-public-gate-verifier-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
