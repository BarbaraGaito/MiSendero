"""Independent ordered-basis reconstruction and actual coefficient-chain checks."""
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
    old = root/f'{kind}_fatigue_cadence_delta_regularization.py'
    sources[old.name] = digest(old)
    text = (old.read_text().replace('fatigue_cadence_delta_regularization','fatigue_cadence_ordered_residual')
        .replace('cadence-delta-regularization','cadence-ordered-residual')
        .replace('cadence_delta_regularization','cadence_ordered_residual')
        .replace('plan()[6:]','plan()[18:]')
        .replace("len(selected['results'])==14","len(selected['results'])==26")
        .replace('all_14_oof_recipes','all_26_oof_recipes'))
    if kind=='audit':
        helper = '''def independent_basis():
    delta = np.arange(-10,11,dtype=float)
    raw = np.column_stack([delta,delta**2,delta==0])
    raw -= raw.mean(axis=0,keepdims=True)
    q,_ = np.linalg.qr(raw,mode='reduced')
    basis = q*np.sqrt(21.)
    np.testing.assert_allclose(basis.mean(axis=0),0.,atol=1e-12)
    np.testing.assert_allclose(basis.T@basis/21.,np.eye(3),atol=1e-12)
    np.testing.assert_allclose(basis@(basis.T@raw/21.),raw,atol=1e-12)
    return basis


'''
        text = text.replace('def raw_probability(base,frame):',helper+'def raw_probability(base,frame):')
        needle = '    assert model.candidate==c and model.base.specification==specification'
        assert needle in text
        text = text.replace(needle,"    assert model.network.corrector[-1].out_features==3\n    assert sum(p.numel() for p in model.network.corrector[-1].parameters())==27\n    np.testing.assert_allclose(model.network.basis.numpy(),independent_basis(),atol=1e-12)\n"+needle)
        needle = "    assert summary['native_objective']=='21_delta_cross_entropy' and summary['native_delta_probability_residuals_fitted']"
        assert needle in text
        text = text.replace(needle,needle+"\n    assert summary['native_residual_coefficients']==3 and summary['native_residual_logits']==21 and summary['native_output_parameters']==27\n    assert summary['fixed_basis_geometry']=='centered_QR_delta_delta_squared_zero'")
        prediction = '''def independent_prediction(model,query):
    base = raw_probability(model.base,query)
    offsets = np.log(base)
    with torch.no_grad():
        history = model.history_transform(query)
        context = model.context_transform(query)
        joined = torch.cat([model.network.encoder(history),context,torch.tensor(base,dtype=torch.float32)],dim=1)
        coefficients = model.network.corrector(joined).numpy().astype(float)
    raw_correction = coefficients@independent_basis().T
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
        needle = "    initial = {key:value.detach().clone() for key,value in study.FullDeltaNetwork(expected_context.shape[1]).state_dict().items()}"
        assert needle in text
        extra = '''
    torch.manual_seed(42)
    full_initial = study.full_reference.FullDeltaNetwork(expected_context.shape[1]).state_dict()
    for key,value in full_initial.items():
        if key.startswith(('encoder.','source_heads.','corrector.0.')):
            torch.testing.assert_close(initial[key],value,rtol=0,atol=0)
    np.testing.assert_allclose(initial['basis'].numpy(),independent_basis(),atol=1e-12)
'''
        text = text.replace(needle,needle+extra)
        needle = "            torch.testing.assert_close(actual_gradient,expected_gradient,rtol=1e-12,atol=1e-14)"
        assert needle in text
        extra = '''
            coefficients = batch['native_coefficients']
            assert coefficients.shape==(len(native_target),3)
            basis = torch.tensor(independent_basis(),dtype=torch.float64)
            expanded = coefficients@basis.T
            expanded = expanded-expanded.mean(dim=1,keepdim=True)
            torch.testing.assert_close(batch['correction'],expanded,rtol=1e-12,atol=1e-14)
            torch.testing.assert_close(batch['correction'].square().mean(),coefficients.square().sum(dim=1).mean(),rtol=1e-12,atol=1e-14)
            coefficient_gradient = torch.autograd.grad(batch['total'],coefficients,retain_graph=True)[0]
            expected_coefficient_gradient = (torch.softmax(batch['native_logits'],dim=1)-onehot)@basis/len(native_target)
            expected_coefficient_gradient += 2*c['correction_penalty']*coefficients/len(native_target)
            torch.testing.assert_close(coefficient_gradient,expected_coefficient_gradient,rtol=1e-12,atol=1e-14)
'''
        text = text.replace(needle,needle+extra)
        text = text.replace("'native_delta_cross_entropy_gradient_verified':True", "'native_delta_cross_entropy_gradient_verified':True,'actual_coefficient_chain_gradient_verified':True,'fixed_ordered_basis_verified':True,'shared_initialization_matched_full_residual':True")
        needle = "inputs['previous_selection']['results']"
        assert text.count(needle)==1
        text = text.replace(needle,"inputs['control_selections'][c['control_study']]['results']")
        text = text.replace('Independent stronger delta-penalty audit','Independent ordered residual audit')
    if kind=='test':
        text = text.replace('self.assertEqual(self.model.network.corrector[-1].out_features,21)',
            'self.assertEqual(self.model.network.corrector[-1].out_features,3)')
        needle = '            torch.testing.assert_close(derivative,expected_derivative,rtol=1e-12,atol=1e-14)'
        assert needle in text
        extra = '''
            coefficients = batch['native_coefficients']
            basis = cls.model_basis
            coefficient_gradient = torch.autograd.grad(batch['total'],coefficients,retain_graph=True)[0]
            expected_coefficient_gradient = (torch.softmax(z,dim=1)-onehot)@basis/len(y)+2*c['correction_penalty']*coefficients/len(y)
            torch.testing.assert_close(coefficient_gradient,expected_coefficient_gradient,rtol=1e-12,atol=1e-14)
            torch.testing.assert_close(correction.square().mean(),coefficients.square().sum(dim=1).mean(),rtol=1e-12,atol=1e-14)
'''
        text = text.replace(needle,needle+extra)
        text = text.replace('        cls.calls,cls.steps = [],[]',
            "        cls.calls,cls.steps = [],[]\n        cls.model_basis = torch.tensor(study.ordered_basis(),dtype=torch.float64)")
        marker = "\n\nif __name__=='__main__':"
        assert marker in text
        extra = '''
    def test_fixed_basis_rank_and_matching_shared_initialization(self):
        delta = np.arange(-10,11,dtype=float)
        raw = np.column_stack([delta,delta**2,delta==0])
        raw -= raw.mean(axis=0,keepdims=True)
        basis = self.model.network.basis.numpy()
        np.testing.assert_allclose(basis.mean(axis=0),0.,atol=1e-12)
        np.testing.assert_allclose(basis.T@basis/21.,np.eye(3),atol=1e-12)
        np.testing.assert_allclose(basis@(basis.T@raw/21.),raw,atol=1e-12)
        self.assertEqual(sum(p.numel() for p in self.model.network.corrector[-1].parameters()),27)
        width = self.model.network.corrector[0].in_features-29
        torch.manual_seed(42)
        small = study.FullDeltaNetwork(width).state_dict()
        torch.manual_seed(42)
        full = study.full_reference.FullDeltaNetwork(width).state_dict()
        for key,value in full.items():
            if key.startswith(('encoder.','source_heads.','corrector.0.')):
                torch.testing.assert_close(small[key],value,rtol=0,atol=0)
'''
        text = text.replace(marker,'\n'+extra+marker)
    name = f'{kind}_fatigue_cadence_ordered_residual.py'
    compile(text,name,'exec')
    path = root/name
    if path.exists():
        assert path.read_text()==text
    else:
        path.write_text(text,encoding='utf-8')
    outputs[name] = digest(path)
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_sources_sha256':sources,'derived_files_sha256':outputs,'historical_sources_modified':False,
    'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'changes':'Independent fixed-basis span/orthonormality,manual3coefficient expansion and actual coefficient-chain gradient. Shared initialization matches the full residual. All26OOFrecipes/40fold artifacts and40independent refits;80actual native/source loss/backward checks. Seven real-public-data tests and original179qualified-test path.'}
(ROOT/'docs/fatigue-80-2026-10-25/cadence-ordered-residual-verifier-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
