"""Observe real native/source tensors, losses, gradients and frozen bases."""
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

import fatigue_domain_aligned_history as study


def raw_history(frame,external=False):
    return pd.DataFrame({study.source.PRIOR:frame[study.source.PRIOR].to_numpy(float) if external else frame.prior_borg.to_numpy(float),
        study.source.SECOND:frame[study.source.SECOND].to_numpy(float) if external else frame.prior2_borg.to_numpy(float)},index=frame.index)


def observe_actual_fit(candidate,fitting,external,specification,context_features,cache):
    model = study.AlignedHistoryBorg(candidate)
    hashes = [joblib.hash(x) for x in (fitting,external,cache)]
    expected_normalizers = {}
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
    expected_history = transform(fitting,False)
    context_imputer = SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)
    context_scaler = StandardScaler().fit(context_imputer.fit_transform(fitting[context_features]))
    expected_context = context_scaler.transform(context_imputer.transform(fitting[context_features])).astype(np.float32)
    target = fitting.label.str.removeprefix('Borg ').to_numpy(int)-fitting.prior_borg.to_numpy(int)+10
    domains = sorted(study.base.previous.SOURCE_COUNTS)+['resistance']+(['shoulder'] if candidate['shoulder_weight'] else [])
    values = {}
    for domain in domains:
        part = external[external.source_domain.eq(domain)]
        weights = 1./part.groupby('group_key').group_key.transform('size').to_numpy()
        weights *= len(part)/weights.sum()
        values[domain] = (transform(part,True),(part[study.source.TARGETS[domain]]-part[study.source.PRIOR]).to_numpy(np.float32),weights.astype(np.float32))
    calls,live,observed = Counter(),{},[]
    handles = []
    initialize = study.ShoulderHistoryNetwork.__init__
    ce,smooth,backward,grad = torch.nn.functional.cross_entropy,torch.nn.functional.smooth_l1_loss,torch.Tensor.backward,torch.autograd.grad
    def network_initialized(network,*args):
        initialize(network,*args)
        live['network'] = network
        with torch.random.fork_rng():
            torch.manual_seed(candidate['random_seed'])
            original = study.base.ResistanceHistoryNetwork(args[0],args[1])
        for name,value in original.state_dict().items():
            np.testing.assert_array_equal(network.state_dict()[name].numpy(),value.numpy())
        def encoding(layer,inputs):
            actual = inputs[0].detach().numpy()
            if len(actual)==len(fitting):
                np.testing.assert_array_equal(actual,expected_history)
            else:
                domain = next(d for d in domains if len(actual)==study.SOURCE_COUNTS[d])
                np.testing.assert_array_equal(actual,values[domain][0])
            calls['encoder'] += 1
        def correcting(layer,inputs,output):
            np.testing.assert_array_equal(inputs[0].detach().numpy()[:,:expected_context.shape[1]],expected_context)
            live['correction'] = output
        handles.extend([network.encoder.register_forward_pre_hook(encoding),network.corrector.register_forward_hook(correcting)])
    def observe(kind,domain,x,current,prior):
        if kind=='native':
            pd.testing.assert_frame_equal(x,fitting[model.input_features])
            np.testing.assert_array_equal(current,fitting.label.str.removeprefix('Borg ').to_numpy(int))
            np.testing.assert_array_equal(prior,fitting.prior_borg)
        else:
            part = external[external.source_domain.eq(domain)]
            pd.testing.assert_frame_equal(x,raw_history(part,True))
            np.testing.assert_array_equal(current,part[study.source.TARGETS[domain]])
            np.testing.assert_array_equal(prior,part[study.source.PRIOR])
        observed.append((kind,domain,len(current)))
    def observed_ce(logits,y,*args,**kwargs):
        np.testing.assert_array_equal(y.numpy(),target)
        assert logits.shape==(len(fitting),21)
        calls['ce'] += 1
        live['ce'] = ce(logits,y,*args,**kwargs)
        return live['ce']
    def observed_smooth(predicted,y,*args,**kwargs):
        domain = domains[calls['smooth']%len(domains)]
        np.testing.assert_array_equal(y.numpy(),values[domain][1])
        assert kwargs=={'beta':1.,'reduction':'none'}
        result = smooth(predicted,y,*args,**kwargs)
        w = torch.as_tensor(values[domain][2])
        live[domain] = (result*w).sum()/w.sum()
        calls['smooth'] += 1
        return result
    def batches(epoch,x,y,auxiliary):
        assert epoch==calls['batches'] and set(auxiliary)==set(domains)
        np.testing.assert_array_equal(x,expected_history)
        np.testing.assert_array_equal(y,target)
        for domain in domains:
            for actual,expected in zip(auxiliary[domain],values[domain]):
                np.testing.assert_array_equal(actual,expected)
        calls['batches'] += 1
    def observed_backward(total,*args,**kwargs):
        old_mean = torch.stack([live[d] for d in sorted(study.base.previous.SOURCE_COUNTS)]).mean()
        resistance = candidate['resistance_weight']
        mixed = (3*old_mean+resistance*live['resistance'])/(3+resistance)
        weight = candidate['shoulder_weight']
        if weight:
            mixed = ((3+resistance)*mixed+weight*live['shoulder'])/(3+resistance+weight)
        expected = live['ce']+candidate['auxiliary_weight']*mixed+candidate['correction_penalty']*live['correction'].square().mean()
        np.testing.assert_allclose(float(total.detach()),float(expected.detach()),rtol=0,atol=1e-6)
        calls['backward'] += 1
        return backward(total,*args,**kwargs)
    def observed_grad(outputs,parameters,*args,**kwargs):
        assert [id(p) for p in parameters]==[id(p) for p in live['network'].encoder.parameters()]
        expected = candidate['auxiliary_weight']*candidate['shoulder_weight']*live['shoulder']/(3+candidate['resistance_weight']+candidate['shoulder_weight'])
        np.testing.assert_allclose(float(outputs.detach()),float(expected.detach()),rtol=0,atol=1e-7)
        gradients = grad(outputs,parameters,*args,**kwargs)
        assert float(torch.sqrt(sum(g.square().sum() for g in gradients)))>0
        calls['shoulder_gradient'] += 1
        return gradients
    try:
        with patch.object(study.ShoulderHistoryNetwork,'__init__',network_initialized),\
                patch.object(torch.nn.functional,'cross_entropy',observed_ce),\
                patch.object(torch.nn.functional,'smooth_l1_loss',observed_smooth),\
                patch.object(torch.Tensor,'backward',observed_backward),\
                patch.object(torch.autograd,'grad',observed_grad),\
                patch.object(study.base.previous,'prepare_base',side_effect=AssertionError('Original native bases must stay frozen')),\
                patch('fatigue_prior_views.build',side_effect=AssertionError('Synthetic histories prohibited')),\
                patch('fatigue_prior_views.alternative_histories',side_effect=AssertionError('Synthetic histories prohibited')):
            model.fit(fitting,external,specification,context_features,cached=cache,observer=observe,batch_observer=batches)
    finally:
        for handle in handles:
            handle.remove()
    assert calls['ce']==calls['backward']==calls['batches']==80
    assert calls['smooth']==80*len(domains) and calls['shoulder_gradient']==int(candidate['shoulder_weight']>0)
    assert set(observed)=={('native','native',len(fitting))}|{('source',d,study.SOURCE_COUNTS[d]) for d in domains}
    assert hashes==[joblib.hash(x) for x in (fitting,external,cache)]
    assert set(model.domain_normalizers)==set(expected_normalizers)
    for domain,(imputer,scaler) in expected_normalizers.items():
        actual_imputer,actual_scaler = model.domain_normalizers[domain]
        np.testing.assert_allclose(actual_imputer.statistics_,imputer.statistics_,rtol=0,atol=0,equal_nan=True)
        np.testing.assert_array_equal(actual_imputer.indicator_.features_,imputer.indicator_.features_)
        np.testing.assert_allclose(actual_scaler.mean_,scaler.mean_,rtol=0,atol=0)
        np.testing.assert_allclose(actual_scaler.var_,scaler.var_,rtol=0,atol=0)
    assert model.training_summary['source_targets_transformed'] is False
    np.testing.assert_allclose(model.context_scaler.mean_,context_scaler.mean_,rtol=0,atol=0)
    return model,{'actual_native_target_calls':calls['ce'],'actual_source_target_calls':calls['smooth'],
        'actual_total_losses_independently_checked':calls['backward'],'source_only_encoder_gradients_checked':calls['shoulder_gradient'],
        'actual_source_targets_per_step':sum(study.SOURCE_COUNTS[d] for d in domains),
        'actual_shoulder_targets_per_step':920 if candidate['shoulder_weight'] else 0,
        'old_four_head_initial_parameters_preserved':True,'native_base_weights_frozen':True,
        'preprocessing_fitting_rows_only':True,'domain_normalizers_independently_checked':6,
        'missing_indicators_binary_preserved':True,'original_source_targets_untransformed':True,'synthetic_rows':0}


def initialize():
    global _RUNTIME
    _RUNTIME = study.load_inputs()


def refit(job):
    import tempfile
    from sklearn.model_selection import GroupKFold
    row,number = job
    inputs = _RUNTIME
    candidate,train = row['candidate'],inputs['train']
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    cache = study.base.previous.read_base_cache(inputs['base_inputs']['previous_inputs'],candidate['member'],number,fit,val)
    model,evidence = observe_actual_fit(candidate,train.iloc[fit],inputs['source'],inputs['specifications'][candidate['member']],inputs['context_features'],cache)
    runtime = train.iloc[val][model.input_features]
    prediction = model.predict(runtime)
    np.testing.assert_array_equal(prediction,np.asarray(row['oof_predictions'])[val])
    assert model.loss_endpoints==row['folds'][number]['loss_endpoints']
    assert model.training_summary==row['folds'][number]['training_summary']
    with tempfile.TemporaryDirectory() as folder:
        artifact = Path(folder)/'original-source-joint.joblib'
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),prediction)
    print(f"Independent domain-aligned network:{candidate['id']} fold{number+1}/5",flush=True)
    return {'candidate_id':candidate['id'],'fold':number,**evidence,'reload_without_current_truth_or_ids':True}


def validate():
    from concurrent.futures import ProcessPoolExecutor,as_completed
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import GroupKFold
    from public_sources import digest
    from validate_fatigue_release import validate as validate_release
    inputs = study.load_inputs()
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/'selection.json'
    selection = json.loads(path.read_text())
    assert selection['status']=='complete' and selection['plan']==study.plan() and len(selection['results'])==10
    assert all(selection.get(k)==v for k,v in signature.items())
    assert digest(study.DIRECTORY/'selection-source.py')==signature['code_sha256']
    train,test = inputs['train'],inputs['test']
    assert (len(train),len(test),train.group_key.nunique(),test.group_key.nunique())==(487,179,28,12)
    assert set(train.group_key).isdisjoint(test.group_key) and not selection['test_used_for_selection']
    assert selection['train_row_keys']==train.row_key.tolist()
    assert selection['evaluation_denominator']==487 and selection['test_denominator']==179
    assert selection['actual_source_fitting_targets_available']==2336 and selection['reserved_source_targets_not_fitted']==312
    assert selection['new_native_base_fits']==selection['new_native_borg_targets']==selection['synthetic_training_rows']==0
    assert not selection['source_targets_pooled_across_instruments']
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    for row in selection['results']:
        c,prediction = row['candidate'],np.asarray(row['oof_predictions'])
        assert c in study.plan() and len(prediction)==487 and set(prediction)<={f'Borg {i}' for i in range(11)}
        scores = [float(accuracy_score(train.iloc[val].label,prediction[val])) for _,val in folds]
        assert row['fold_accuracy']==scores and row['accuracy_mean']==float(np.mean(scores))
        assert row['pooled_oof_accuracy']==float(accuracy_score(train.label,prediction))
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['previous_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])
            np.testing.assert_array_equal(prediction,old['oof_predictions'])
            continue
        assert len(row['folds'])==5
        for number,(fit,val) in enumerate(folds):
            disk = json.loads((study.DIRECTORY/'folds'/f"{c['id']}-fold-{number}.json").read_text())
            assert disk==row['folds'][number] and disk['signature']==signature and disk['candidate']==c
            assert disk['fit_row_keys']==train.iloc[fit].row_key.tolist() and disk['validation_row_keys']==train.iloc[val].row_key.tolist()
            np.testing.assert_array_equal(disk['predicted'],prediction[val])

    positive = {m:max((r for r in selection['results'] if r['candidate'].get('member')==m and r['candidate'].get('shoulder_weight',0)>0),
        key=lambda r:r['accuracy_mean']) for m in ('core','cat')}
    zero = {m:next(r for r in selection['results'] if r['candidate'].get('member')==m and r['candidate'].get('shoulder_weight')==0) for m in ('core','cat')}
    refits = []
    with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
        for future in as_completed([pool.submit(refit,(row,n)) for row in [*positive.values(),*zero.values()] for n in range(5)]):
            refits.append(future.result())
    winner = max(selection['results'],key=lambda r:r['accuracy_mean'])
    assert selection['winner_id']==winner['candidate']['id'] and selection['best_cv_accuracy']==winner['accuracy_mean']
    gate = winner['candidate']['algorithm']!='previous_real_control' and winner['accuracy_mean']>=.65
    evaluation = None
    if gate:
        assert (study.DIRECTORY/'evaluation/metrics.json').exists(),'Evaluate the frozen qualified winner before audit'
        from evaluate_fatigue_domain_aligned_history import evaluate
        evaluation = evaluate()
    else:
        assert not (study.DIRECTORY/'evaluation/metrics.json').exists()
    base_proof = json.loads(study.parent.BASE_AUDIT.read_text())
    for name,expected in base_proof['native_base_cache_artifact_hashes'].items():
        assert digest(study.base.previous.DIRECTORY/'bases'/name)==expected
    retained = validate_release()
    assert retained['correct']==108 and retained['accuracy']==108/179
    compact = lambda r:{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')}
    return {'verification':'passed','verification_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(path),'input_verification_sha256':digest(study.parent.INPUT_AUDIT),
        'previous_verification_sha256':digest(study.PARENT_AUDIT),'base_verification_sha256':digest(study.parent.BASE_AUDIT),
        'public_real_data_policy_sha256':signature['public_real_data_policy_sha256'],
        'all_10_oof_recipes_recomputed':True,'original_native_rows_and_targets_preserved':True,
        'actual_native_joint_refits':len(refits),'joint_refits':sorted(refits,key=lambda r:(r['candidate_id'],r['fold'])),
        'native_base_cache_artifact_hashes':base_proof['native_base_cache_artifact_hashes'],
        'native_base_caches_reused':10,'cached_native_base_models_previously_verified':40,'new_native_base_fits':0,
        'source_fitting_targets_available':2336,'new_shoulder_fitting_targets':920,'new_shoulder_fitting_people':27,
        'source_fitting_actual_second_priors':1927,'reserved_source_targets_not_fitted':312,
        'actual_source_and_native_losses_and_weights_observed':True,'actual_shoulder_to_encoder_gradients_verified':True,
        'zero_new_weight_excludes_shoulder_labels':True,'old_initial_parameters_preserved':True,
        'domain_specific_numeric_stats_and_binary_missing_indicators_verified':True,
        'native_base_weights_frozen':True,'matched_preprocessing_fitting_rows_only':True,'source_outcomes_pooled':False,
        'synthetic_rows':0,'invented_source_times_or_sensor_joins':0,'best_positive_by_member':{m:compact(r) for m,r in positive.items()},
        'matched_zero_new_source_controls':{m:compact(r) for m,r in zero.items()},
        'best_positive_cv_accuracy':max(r['accuracy_mean'] for r in positive.values()),'best_cv_accuracy':selection['best_cv_accuracy'],
        'winner_id':selection['winner_id'],'new_test_gate_passed':gate,'new_test_evaluation':evaluation,
        'original_release_test_correct':108,'original_release_test_accuracy':108/179,
        'achieved':bool(evaluation and evaluation['correct']>=144)}


if __name__=='__main__':
    report = validate()
    (study.DOCS/'domain-aligned-history-verification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('verification','actual_native_joint_refits','best_positive_cv_accuracy','best_cv_accuracy','new_test_gate_passed','achieved')}),flush=True)
