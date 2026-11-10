"""Static full-delta loss/gradient verification derived from the audited gate."""
import ast
import json
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent


def replace_function(text,name,replacement):
    node = next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines = text.splitlines(keepends=True)
    return ''.join(lines[:node.lineno-1])+replacement+'\n'+''.join(lines[node.end_lineno:])


outputs,sources = {},{}
for kind in ('audit','evaluate','test'):
    path = root/f'{kind}_fatigue_cadence_recent_gate.py'
    sources[path.name] = digest(path)
    text = path.read_text().replace('fatigue_cadence_recent_gate','fatigue_cadence_full_delta')
    text = text.replace('cadence-recent-gate','cadence-full-delta')
    text = text.replace('cadence_recent_native_gate','cadence_full_delta_residual')
    text = text.replace('CadenceBinaryGateBorg','FullDeltaCadenceBorg').replace('ChangeGateNetwork','FullDeltaNetwork')
    if kind=='audit':
        text = text.replace("len(selected['results'])==10","len(selected['results'])==14")
        text = text.replace('all_10_oof_recipes_recomputed','all_14_oof_recipes_recomputed')
        text = text.replace('all_20_fold_artifacts_recomputed','all_40_fold_artifacts_recomputed')
        text = text.replace('len(artifacts)==40 and len(refits)==20','len(artifacts)==80 and len(refits)==40')
        text = text.replace("'independent_joint_refits':20","'independent_joint_refits':40")
        text = text.replace("assert summary['gradient_steps']==80 and summary['base_weights_frozen'] and summary['nonzero_delta_relative_probabilities_frozen']",
            "assert summary['gradient_steps']==80 and summary['base_weights_frozen'] and not summary['nonzero_delta_relative_probabilities_frozen']")
        text = text.replace("assert summary['native_loss_equivalent_to_joint_nll_up_to_frozen_conditional'] and not summary['source_current_values_or_context_used_as_predictors']",
            "assert summary['native_objective']=='21_delta_cross_entropy' and summary['native_delta_probability_residuals_fitted']\n    assert not summary['source_current_values_or_context_used_as_predictors']")
        prediction = '''def independent_prediction(model,query):
    base = raw_probability(model.base,query)
    offsets = np.log(base)
    with torch.no_grad():
        history = model.history_transform(query)
        context = model.context_transform(query)
        joined = torch.cat([model.network.encoder(history),context,torch.tensor(base,dtype=torch.float32)],dim=1)
        raw_correction = model.network.corrector(joined).numpy().astype(float)
    correction = raw_correction-raw_correction.mean(axis=1,keepdims=True)
    logits = offsets+correction
    logits -= logits.max(axis=1,keepdims=True)
    expected = np.exp(logits)
    expected /= expected.sum(axis=1,keepdims=True)
    indices = model.base.priority
    delta = indices[expected[:,indices].argmax(axis=1)]-10
    labels = np.asarray([f'Borg {int(x)}' for x in np.clip(query.prior_borg.to_numpy(int)+delta,0,10)])
    return labels,expected,base
'''
        text = replace_function(text,'independent_prediction',prediction)
        text = text.replace('offset = np.log(1-raw[:,10])-np.log(raw[:,10])','offset = np.log(raw)')
        old_target = "native_target = (fitting.label.str.removeprefix('Borg ').to_numpy(int)!=fitting.prior_borg.to_numpy(int)).astype(float)"
        assert old_target in text
        text = text.replace(old_target,"native_target = fitting.label.str.removeprefix('Borg ').to_numpy(int)-fitting.prior_borg.to_numpy(int)+10")
        old_loss = 'loss = float(np.mean(np.logaddexp(0,z)-y*z))'
        assert old_loss in text
        text = text.replace(old_loss,"maximum = z.max(axis=1)\n        loss = float(np.mean(maximum+np.log(np.exp(z-maximum[:,None]).sum(axis=1))-z[np.arange(len(y)),y]))")
        start = text.index("            p = batch['offset_probabilities']")
        end = text.index('            if per_source:',start)
        replacement = '''            assert batch['native_logits'].shape==(len(native_target),21)
            assert batch['native_target'].dtype==torch.long
            expected_loss = torch.nn.functional.cross_entropy(batch['native_logits'],batch['native_target'])
            onehot = torch.nn.functional.one_hot(batch['native_target'],21).to(torch.float64)
            actual_gradient = torch.autograd.grad(batch['total'],batch['correction'],retain_graph=True)[0]
            expected_gradient = (torch.softmax(batch['native_logits'],dim=1)-onehot)/len(native_target)
            expected_gradient += 2*c['correction_penalty']*batch['correction']/(len(native_target)*21)
            torch.testing.assert_close(actual_gradient,expected_gradient,rtol=1e-12,atol=1e-14)
            np.testing.assert_allclose(float(expected_loss.detach()),loss,atol=1e-12)
'''
        text = text[:start]+replacement+text[end:]
        text = text.replace("'native_joint_nll_gradient_equivalence_verified':True","'native_delta_cross_entropy_gradient_verified':True")
        old_zero = "zeros = {m:next(row for row in selected['results'] if row['candidate'].get('member')==m and row['candidate'].get('auxiliary_weight')==0) for m in best}"
        assert old_zero in text
        text = text.replace(old_zero,"zeros = {m:next(row for row in selected['results'] if row['candidate'].get('member')==m and row['candidate'].get('auxiliary_weight')==0 and row['candidate']['correction_penalty']==best[m]['candidate']['correction_penalty']) for m in best}")
        text = text.replace("refit_ids = {row['candidate']['id'] for row in [*best.values(),*zeros.values()]}",
            "refit_ids = {c['id'] for c in study.plan()[6:]}")
        frozen_ratio = '                keep = np.arange(21)!=10\n                np.testing.assert_allclose(p[:,keep]/p[:,keep].sum(axis=1,keepdims=True),base_p[:,keep]/base_p[:,keep].sum(axis=1,keepdims=True),atol=1e-12)\n'
        assert frozen_ratio in text
        text = text.replace(frozen_ratio,'')
        text = text.replace("'nonzero_delta_ratios_frozen':True","'nonzero_delta_ratios_frozen':False")
        text = text.replace('Independent recent native-context audit','Independent full native-delta audit')
    if kind=='test':
        text = text.replace("native = torch.nn.functional.binary_cross_entropy_with_logits(z,y)",
            "native = torch.nn.functional.cross_entropy(z,y)")
        text = text.replace('expected = native+.1*source_loss+correction.square().mean()',
            "expected = native+.1*source_loss+c['correction_penalty']*correction.square().mean()")
        old = "torch.testing.assert_close(derivative,(torch.sigmoid(z)-y+2*correction)/len(y),rtol=1e-12,atol=1e-14)"
        assert old in text
        text = text.replace(old,"onehot = torch.nn.functional.one_hot(y,21).to(torch.float64)\n            expected_derivative = (torch.softmax(z,dim=1)-onehot)/len(y)+2*c['correction_penalty']*correction/(len(y)*21)\n            torch.testing.assert_close(derivative,expected_derivative,rtol=1e-12,atol=1e-14)")
        start = text.index('        torch.testing.assert_close(before[:,keep]')
        end = text.index('        self.assertEqual(joblib.hash(self.cache)',start)
        text = text[:start]+"        changed = torch.max(torch.abs(before[:,keep]/before[:,keep].sum(dim=1,keepdim=True)-after[:,keep]/after[:,keep].sum(dim=1,keepdim=True)))\n        self.assertGreater(float(changed),1e-8)\n"+text[end:]
        text = text.replace('test_frozen_native_weights_and_nonzero_ratios','test_frozen_native_weights_with_trainable_nonzero_ratios')
        text = text.replace('self.assertEqual(self.model.network.encoder[0].in_features,11)',
            'self.assertEqual(self.model.network.encoder[0].in_features,11)\n        self.assertEqual(self.model.network.corrector[-1].out_features,21)')
    name = f'{kind}_fatigue_cadence_full_delta.py'
    compile(text,name,'exec')
    target = root/name
    if target.exists():
        assert target.read_text()==text
    else:
        target.write_text(text,encoding='utf-8')
    outputs[name] = digest(target)
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_sources_sha256':sources,'derived_files_sha256':outputs,'historical_sources_modified':False,
    'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'changes':'Independent21class NLL/centered residual gradient;manual probability reconstruction;all40fold artifacts/14OOFmetrics and40network refits. Actual851source pairs/BCE/gradient,80real backward steps per refit,immutable native bases. Full qualified179case test path preserved.'}
(ROOT/'docs/fatigue-80-2026-10-25/cadence-full-delta-verifier-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
