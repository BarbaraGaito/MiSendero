"""Independent native gate/source BCE/gradient and original-cohort audit."""
from __future__ import annotations
import io
import json
from pathlib import Path
from unittest.mock import patch
import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_cadence_ordered_residual as study
from audit_fatigue_observed_change_factorization import independent_preprocessing
from public_sources import digest


def independent_basis():
    delta = np.arange(-10,11,dtype=float)
    raw = np.column_stack([delta,delta**2,delta==0])
    raw -= raw.mean(axis=0,keepdims=True)
    q,_ = np.linalg.qr(raw,mode='reduced')
    basis = q*np.sqrt(21.)
    np.testing.assert_allclose(basis.mean(axis=0),0.,atol=1e-12)
    np.testing.assert_allclose(basis.T@basis/21.,np.eye(3),atol=1e-12)
    np.testing.assert_allclose(basis@(basis.T@raw/21.),raw,atol=1e-12)
    return basis


def raw_probability(base,frame):
    options = {'thread_count':4} if base.member=='cat' else {}
    with threadpool_limits(limits=1):
        p = base.classifier.model.predict_proba(frame[base.input_features],**options)
    indices = base.classifier.model.classes_.astype(int)+10
    np.testing.assert_array_equal(indices,base.class_indices)
    values = np.full((len(frame),21),.0001)
    values[:,indices] = np.maximum(p,.0001)
    return values/values.sum(axis=1,keepdims=True)


def verify_cache(cache,fitting,specification):
    assert cache['fit_row_keys']==fitting.row_key.tolist() and cache['base'].specification==specification
    assert cache['base'].fitting_summary['actual_native_rows']==len(fitting)
    predicted = np.zeros((len(fitting),21))
    for n,(fit,val) in enumerate(GroupKFold(3).split(fitting,groups=fitting.group_key)):
        a,b = fitting.iloc[fit],fitting.iloc[val]
        assert set(a.group_key).isdisjoint(b.group_key)
        saved = cache['inner_folds'][n]
        assert saved['fit_row_keys']==a.row_key.tolist() and saved['validation_row_keys']==b.row_key.tolist()
        model = cache['inner_models'][n]
        assert model.specification==specification and model.fitting_summary['actual_native_rows']==len(a)
        assert model.fitting_summary['actual_native_people']==a.group_key.nunique()
        assert model.fitting_summary['synthetic_rows']==0
        expected_classes = np.unique(a.label.str.removeprefix('Borg ').to_numpy(int)-a.prior_borg.to_numpy(int))
        np.testing.assert_array_equal(np.sort(model.classifier.model.classes_.astype(int)),expected_classes)
        predicted[val] = raw_probability(model,b)
    np.testing.assert_allclose(np.exp(cache['fit_logits'].numpy()),predicted,atol=1e-12)
    return predicted


def history_array(frame):
    columns = study.prepared.FEATURES if 'prior' in frame else ['prior_borg','prior2_borg',*study.prepared.NATIVE_COLUMNS.values()]
    raw = frame[columns].to_numpy(float)
    median = np.nanmedian(raw,axis=0)
    assert np.isfinite(median).all()
    filled = np.where(np.isnan(raw),median,raw)
    mean,var = filled.mean(axis=0),filled.var(axis=0)
    scale = np.sqrt(var)
    scale[scale==0] = 1.
    return np.column_stack([(filled-mean)/scale,np.isnan(raw[:,1:]).astype(float)]),median,mean,var



def verify_model(model,c,fitting,external,specification,context_features,cache):
    assert len(context_features)==16 and context_features[-3:]==study.added.COLUMNS
    assert not set(study.added.COLUMNS)&set(external)
    assert model.network.corrector[-1].out_features==3
    assert sum(p.numel() for p in model.network.corrector[-1].parameters())==27
    np.testing.assert_allclose(model.network.basis.numpy(),independent_basis(),atol=1e-12)
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
    assert summary['gradient_steps']==80 and summary['base_weights_frozen'] and not summary['nonzero_delta_relative_probabilities_frozen']
    assert summary['native_objective']=='21_delta_cross_entropy' and summary['native_delta_probability_residuals_fitted']
    assert summary['native_residual_coefficients']==3 and summary['native_residual_logits']==21 and summary['native_output_parameters']==27
    assert summary['fixed_basis_geometry']=='centered_QR_delta_delta_squared_zero'
    assert not summary['source_current_values_or_context_used_as_predictors']
    assert summary['synthetic_rows']==summary['artificial_history_views']==summary['invented_source_times_or_sensor_joins']==0
    assert summary['initial_native_output_gradient_l2']>0
    assert (summary['initial_source_only_encoder_gradient_l2']>0)==bool(c['auxiliary_weight'])
    return True



def independent_prediction(model,query):
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




def refit_observed(c,fitting,external,specification,context_features,cache):
    model = study.FullDeltaCadenceBorg(c)
    expected_history = {'native':history_array(fitting)[0].astype(np.float32),
        **{d:history_array(p)[0].astype(np.float32) for d,p in external.groupby('source_domain')}}
    expected_context = independent_preprocessing(fitting,context_features)[0].astype(np.float32)
    raw = np.exp(cache['fit_logits'].numpy())
    offset = np.log(raw)
    native_target = fitting.label.str.removeprefix('Borg ').to_numpy(int)-fitting.prior_borg.to_numpy(int)+10
    source_target,source_weight = {},{}
    for domain,part in external.groupby('source_domain'):
        source_target[domain] = part[study.source.TARGETS[domain]].ne(part[study.source.PRIOR]).to_numpy(np.float32)
        w = 1./part.groupby('group_key').group_key.transform('size').to_numpy()
        source_weight[domain] = (w*len(part)/w.sum()).astype(np.float32)
    torch.manual_seed(42)
    initial = {key:value.detach().clone() for key,value in study.FullDeltaNetwork(expected_context.shape[1]).state_dict().items()}
    torch.manual_seed(42)
    full_initial = study.full_reference.FullDeltaNetwork(expected_context.shape[1]).state_dict()
    for key,value in full_initial.items():
        if key.startswith(('encoder.','source_heads.','corrector.0.')):
            torch.testing.assert_close(initial[key],value,rtol=0,atol=0)
    np.testing.assert_allclose(initial['basis'].numpy(),independent_basis(),atol=1e-12)

    calls,steps,backwards,source_forwards = [],[],[],[]
    first_source_gradient = [0.]
    pending_total = [None]
    old_source,old_backward = study.FullDeltaNetwork.source_logits,torch.Tensor.backward
    def observe(kind,domain,features,current,prior):
        if kind=='native':
            pd.testing.assert_frame_equal(features,fitting[model.input_features])
            np.testing.assert_array_equal(current,fitting.label.str.removeprefix('Borg ').to_numpy(int))
            np.testing.assert_array_equal(prior,fitting.prior_borg.to_numpy(int))
        else:
            part = external[external.source_domain.eq(domain)]
            pd.testing.assert_frame_equal(features,part[study.prepared.FEATURES])
            np.testing.assert_array_equal(current,part[study.source.TARGETS[domain]].to_numpy(float))
            np.testing.assert_array_equal(prior,part[study.source.PRIOR].to_numpy(float))
        calls.append((kind,domain,len(current)))
    def source_forward(network,history,domain):
        np.testing.assert_allclose(history.detach().numpy(),expected_history[domain],atol=1e-6)
        source_forwards.append(domain)
        return old_source(network,history,domain)
    def step(epoch,batch):
        assert epoch==len(steps)
        np.testing.assert_allclose(batch['history'].numpy(),expected_history['native'],atol=1e-6)
        np.testing.assert_allclose(batch['context'].numpy(),expected_context,atol=1e-6)
        np.testing.assert_allclose(batch['offset_probabilities'].numpy(),raw,atol=1e-12)
        np.testing.assert_array_equal(batch['native_target'].numpy(),native_target)
        z,y = batch['native_logits'].detach().numpy(),native_target
        correction = batch['correction'].detach().numpy()
        maximum = z.max(axis=1)
        loss = float(np.mean(maximum+np.log(np.exp(z-maximum[:,None]).sum(axis=1))-z[np.arange(len(y)),y]))
        per_source = []
        assert set(batch['source_batches'])==(set(study.COUNTS) if c['auxiliary_weight'] else set())
        for domain,(logits,actual,weights) in batch['source_batches'].items():
            np.testing.assert_array_equal(actual.numpy(),source_target[domain])
            np.testing.assert_allclose(weights.numpy(),source_weight[domain],atol=1e-6)
            s = logits.detach().numpy().astype(float)
            w = weights.numpy().astype(float)
            per_source.append(float(np.sum((np.logaddexp(0,s)-source_target[domain]*s)*w)/w.sum()))
        expected = loss+c['auxiliary_weight']*(np.mean(per_source) if per_source else 0.)+c['correction_penalty']*np.mean(correction**2)
        np.testing.assert_allclose(float(batch['total'].detach()),expected,rtol=2e-6,atol=2e-7)
        if epoch==0:
            for key,value in model.network.state_dict().items():
                torch.testing.assert_close(value,initial[key],rtol=0,atol=0)
            assert np.count_nonzero(correction)==0
            np.testing.assert_allclose(z,offset,atol=1e-12)
            assert batch['native_logits'].shape==(len(native_target),21)
            assert batch['native_target'].dtype==torch.long
            expected_loss = torch.nn.functional.cross_entropy(batch['native_logits'],batch['native_target'])
            onehot = torch.nn.functional.one_hot(batch['native_target'],21).to(torch.float64)
            actual_gradient = torch.autograd.grad(batch['total'],batch['correction'],retain_graph=True)[0]
            expected_gradient = (torch.softmax(batch['native_logits'],dim=1)-onehot)/len(native_target)
            expected_gradient += 2*c['correction_penalty']*batch['correction']/(len(native_target)*21)
            torch.testing.assert_close(actual_gradient,expected_gradient,rtol=1e-12,atol=1e-14)
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

            np.testing.assert_allclose(float(expected_loss.detach()),loss,atol=1e-12)
            if per_source:
                observed_losses = [(torch.nn.functional.binary_cross_entropy_with_logits(a,b,reduction='none')*w).sum()/w.sum()
                    for a,b,w in batch['source_batches'].values()]
                gradients = torch.autograd.grad(c['auxiliary_weight']*torch.stack(observed_losses).mean(),
                    tuple(model.network.encoder.parameters()),retain_graph=True)
                first_source_gradient[0] = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
                assert first_source_gradient[0]>0
        pending_total[0] = batch['total']
        steps.append(epoch)
    def backward(tensor,*args,**kwargs):
        assert tensor is pending_total[0] and len(steps)==len(backwards)+1
        backwards.append(len(backwards))
        return old_backward(tensor,*args,**kwargs)
    before = joblib.hash(cache)
    with patch.object(study.FullDeltaNetwork,'source_logits',source_forward),patch.object(torch.Tensor,'backward',backward),\
         patch.object(study.native.NativeBase,'fit',side_effect=AssertionError('Unexpected new base fit')):
        model.fit(fitting,external,specification,context_features,cache,observer=observe,step_observer=step)
    assert joblib.hash(cache)==before and steps==backwards==list(range(80))
    assert len(calls)==(2 if c['auxiliary_weight'] else 1)
    assert len(source_forwards)==(80 if c['auxiliary_weight'] else 0)
    np.testing.assert_allclose(first_source_gradient[0],model.training_summary['initial_source_only_encoder_gradient_l2'],atol=1e-12)
    verify_model(model,c,fitting,external,specification,context_features,cache)
    return model,{'actual_native_target_steps':80,'actual_source_target_steps':80 if c['auxiliary_weight'] else 0,
        'actual_losses_independently_checked':80,'actual_total_backward_calls':80,'initial_parameters_verified':True,
        'native_delta_cross_entropy_gradient_verified':True,'actual_coefficient_chain_gradient_verified':True,'fixed_ordered_basis_verified':True,'shared_initialization_matched_full_residual':True,'actual_source_encoder_gradient':first_source_gradient[0],
        'source_context_not_fabricated':True,'source_targets_from_original_pairs':True}


def validate():
    inputs = study.load_inputs()
    train,external = inputs['train'],inputs['gate_source']
    selected_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selected_path.read_text())
    signature = study.fingerprint(inputs)
    assert selected['status']=='complete' and selected['plan']==study.plan() and len(selected['results'])==26
    assert all(selected.get(k)==v for k,v in signature.items())
    assert digest(study.DIRECTORY/'selection-source.py')==digest(Path(study.__file__))
    assert selected['train_row_keys']==train.row_key.tolist() and not selected['test_used_for_selection']
    by_id = {row['candidate']['id']:row for row in selected['results']}
    positive = [row for row in selected['results'] if row['candidate'].get('auxiliary_weight',0)>0]
    best = {m:max([row for row in positive if row['candidate']['member']==m],key=lambda row:row['accuracy_mean']) for m in ('core','cat')}
    zeros = {m:next(row for row in selected['results'] if row['candidate'].get('member')==m and row['candidate'].get('auxiliary_weight')==0 and row['candidate']['correction_penalty']==best[m]['candidate']['correction_penalty']) for m in best}
    refit_ids = {c['id'] for c in study.plan()[18:]}
    predictions = {c['id']:np.empty(487,object) for c in study.plan()[18:]}
    folds = list(GroupKFold(5).split(train,groups=train.group_key))
    cache_hashes = {p.name:digest(p) for p in (study.native.DIRECTORY/'bases').iterdir() if p.suffix in ('.json','.joblib')}
    assert len(cache_hashes)==20
    artifacts,refits,inner_models_verified = {},[],0
    for member in ('core','cat'):
        for n,(fit,val) in enumerate(folds):
            fitting,validation = train.iloc[fit],train.iloc[val]
            assert set(fitting.group_key).isdisjoint(validation.group_key)
            cache = study.read_cache(inputs,member,n,fit,val)
            verify_cache(cache,fitting,inputs['specifications'][member])
            inner_models_verified += 3
            for c in (c for c in study.plan()[18:] if c['member']==member):
                path = study.DIRECTORY/'folds'/f"{c['id']}-fold-{n}.json"
                model_path = path.with_suffix('.joblib')
                saved = json.loads(path.read_text())
                assert saved==by_id[c['id']]['folds'][n] and saved['signature']==signature and saved['candidate']==c
                assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
                assert saved['model_sha256']==digest(model_path)
                artifacts[path.name],artifacts[model_path.name] = digest(path),digest(model_path)
                model = joblib.load(model_path)
                verify_model(model,c,fitting,external,inputs['specifications'][member],inputs['context_features'],cache)
                assert saved['training_summary']==model.training_summary and saved['normalization_summary']==model.normalization_summary
                assert saved['loss_endpoints']==model.loss_endpoints
                query = validation[model.input_features]
                labels,p,base_p = independent_prediction(model,query)
                np.testing.assert_allclose(model.probabilities(query).numpy(),p,atol=1e-12)
                np.testing.assert_array_equal(model.predict(query),labels)
                np.testing.assert_array_equal(saved['predicted'],labels)
                predictions[c['id']][val] = labels
                if c['id'] in refit_ids:
                    refitted,details = refit_observed(c,fitting,external,inputs['specifications'][member],inputs['context_features'],cache)
                    np.testing.assert_array_equal(refitted.predict(query),labels)
                    np.testing.assert_allclose(refitted.probabilities(query).numpy(),p,atol=1e-12)
                    assert refitted.loss_endpoints==model.loss_endpoints
                    stream = io.BytesIO()
                    joblib.dump(refitted,stream)
                    stream.seek(0)
                    restored = joblib.load(stream)
                    np.testing.assert_array_equal(restored.predict(query),labels)
                    assert set(vars(restored))=={'candidate','base','context_features','input_features','history_normalizers',
                        'normalization_summary','context_imputer','context_scaler','network','loss_endpoints','training_summary'}
                    refits.append({'candidate_id':c['id'],'member':member,'fold':n,**details,
                        'base_weights_frozen':True,'nonzero_delta_ratios_frozen':False,'input_only_reload_verified':True})
            print(f'Independent ordered residual audit:{member} fold{n+1}/5',flush=True)
    assert len(artifacts)==80 and len(refits)==40 and inner_models_verified==30
    for c in study.plan():
        row = by_id[c['id']]
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['control_selections'][c['control_study']]['results'] if r['candidate']['id']==c['parent_candidate_id'])
            predicted = np.asarray(old['oof_predictions'])
        else:
            predicted = predictions[c['id']]
        np.testing.assert_array_equal(row['oof_predictions'],predicted)
        scores = [float(np.mean(predicted[val]==train.iloc[val].label.to_numpy())) for _,val in folds]
        np.testing.assert_allclose(row['fold_accuracy'],scores,atol=1e-15)
        assert row['accuracy_mean']==float(np.mean(scores)) and row['pooled_oof_accuracy']==float(np.mean(predicted==train.label.to_numpy()))
    assert all(digest(study.DIRECTORY/'folds'/name)==value for name,value in artifacts.items())
    assert all(digest(study.native.DIRECTORY/'bases'/name)==value for name,value in cache_hashes.items())
    winner = max(selected['results'],key=lambda row:row['accuracy_mean'])
    assert selected['winner_id']==winner['candidate']['id'] and selected['best_cv_accuracy']==winner['accuracy_mean']
    gate_path = study.DOCS/'cadence-ordered-residual-test-gate.json'
    gate = json.loads(gate_path.read_text())
    assert gate['selection_sha256']==digest(selected_path) and gate['pretest_verifier_code_sha256']==digest(Path(__file__))
    assert gate['evaluator_code_sha256']==digest(Path(__file__).with_name('evaluate_fatigue_cadence_ordered_residual.py'))
    assert gate['gate_passed']==(winner['accuracy_mean']>=.65 and winner['candidate']['algorithm']=='cadence_ordered_residual')
    full_test_audit = None
    if gate['gate_passed']:
        assert gate['pretest_winner_fold_artifacts_verified']==5
        result = gate['new_test_evaluation']
        directory = study.DIRECTORY/'evaluation'
        meta = json.loads((directory/'model.json').read_text())
        assert meta['model_sha256']==result['model_sha256']==digest(directory/'model.joblib')
        assert meta['base_cache_sha256']==digest(directory/'base-cache.joblib')
        full_cache = joblib.load(directory/'base-cache.joblib')
        model = joblib.load(directory/'model.joblib')
        candidate = winner['candidate']
        verify_cache(full_cache,train,inputs['specifications'][candidate['member']])
        verify_model(model,candidate,train,external,inputs['specifications'][candidate['member']],inputs['context_features'],full_cache)
        test = inputs['test']
        labels,probabilities,_ = independent_prediction(model,test[model.input_features])
        np.testing.assert_array_equal(result['predictions'],labels)
        np.testing.assert_allclose(model.probabilities(test[model.input_features]).numpy(),probabilities,atol=1e-12)
        assert result['original_test_row_keys']==test.row_key.tolist() and result['test_cases']==179
        correct = int(np.sum(labels==test.label.to_numpy()))
        assert result['test_correct']==correct and result['test_accuracy']==correct/179 and result['achieved']==(correct>=144)
        assert result['frozen_artifact_reloaded_before_test']
        fresh_cache = study.native.prepare_base(train,candidate['member'],inputs['specifications'][candidate['member']])
        verify_cache(fresh_cache,train,inputs['specifications'][candidate['member']])
        np.testing.assert_allclose(fresh_cache['fit_logits'].numpy(),full_cache['fit_logits'].numpy(),atol=1e-12)
        refitted,details = refit_observed(candidate,train,external,inputs['specifications'][candidate['member']],inputs['context_features'],fresh_cache)
        np.testing.assert_array_equal(refitted.predict(test[refitted.input_features]),labels)
        assert json.loads((directory/'metrics.json').read_text())==result
        full_test_audit = {'test_cases':179,'independent_full_native_base_refits':4,'joint_network_refits':1,
            'actual_joint_fit_verification':details,'correct':correct,'accuracy':correct/179,
            'artifact_sha256':result['model_sha256']}
    else:
        assert gate['new_test_evaluation'] is None and gate['pretest_winner_fold_artifacts_verified']==0
        assert not (study.DIRECTORY/'evaluation').exists()
    compact = lambda row:{k:row[k] for k in ('candidate','accuracy_mean','fold_accuracy')}
    report = {'verification':'passed','verification_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(selected_path),'previous_verification_sha256':digest(study.PARENT_AUDIT),
        'proposal_sha256':digest(study.PROPOSAL),'test_gate_sha256':digest(gate_path),
        'fold_artifact_hashes':artifacts,'native_base_cache_artifact_hashes':cache_hashes,
        'all_26_oof_recipes_recomputed':True,'all_40_fold_artifacts_recomputed':True,
        'prior_inner_native_models_independently_verified':30,'native_joint_refits':refits,'independent_joint_refits':40,
        'best_positive_by_member':{m:compact(row) for m,row in best.items()},
        'matched_zero_source_controls':{m:compact(row) for m,row in zeros.items()},
        'best_positive_cv_accuracy':max(row['accuracy_mean'] for row in positive),'best_cv_accuracy':winner['accuracy_mean'],
        'source_fitting_actual_pairs':851,'other_source_domains_fitted':0,'source_reserved_pairs_not_fitted':206,
        'new_native_base_fits':0,'synthetic_rows':0,'source_targets_from_original_pairs':True,
        'current_and_future_native_labels_excluded_from_predictors':True,'original_native_cases_preserved':True,
        'new_test_gate_passed':gate['gate_passed'],'new_test_evaluation':gate['new_test_evaluation'],
        'independent_full_test_artifact_audit':full_test_audit}
    (study.DOCS/'cadence-ordered-residual-verification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('fold_artifact_hashes','native_base_cache_artifact_hashes',
        'native_joint_refits','best_positive_by_member','matched_zero_source_controls')}),flush=True)
    return report


if __name__=='__main__':
    validate()
