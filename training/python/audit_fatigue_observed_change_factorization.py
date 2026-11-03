"""Independent observed-target/stage/probability and full-cohort verification."""
from __future__ import annotations
import io
import json
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from threadpoolctl import threadpool_limits

import fatigue_observed_change_factorization as study
from public_sources import digest


def targets(frame):
    original = np.asarray([int(x[5:]) for x in frame.label])
    prior = frame.prior_borg.to_numpy(float)
    assert np.isin(original,np.arange(11)).all() and np.isin(prior,np.arange(11)).all()
    return original-prior.astype(int)


def stage_rows(frame,structure):
    delta = targets(frame)
    if structure=='flat':
        return [('flat',frame,delta)]
    return [('change',frame,(delta!=0).astype(int)),('magnitude',frame.loc[delta!=0],delta[delta!=0])]


def independent_preprocessing(frame,features):
    raw = frame[features].to_numpy(float)
    medians = np.nanmedian(raw,axis=0)
    assert np.isfinite(medians).all()
    missing = np.flatnonzero(np.isnan(raw).any(axis=0))
    filled = np.column_stack([np.where(np.isnan(raw),medians,raw),np.isnan(raw[:,missing]).astype(float)])
    mean,var = filled.mean(axis=0),filled.var(axis=0)
    scale = np.sqrt(var)
    scale[scale==0] = 1.
    return (filled-mean)/scale,medians,missing,mean,var


def verify_model(model,c,fitting,specification):
    expected_features = list(specification['features'])
    if c['feature_set']=='history_physiology':
        expected_features += [x for x in ('hr_last','hr_change_after_prior','hr_recent_slope') if x not in expected_features]
    assert model.candidate==c and model.specification==specification and model.input_features==expected_features
    expected_stages = stage_rows(fitting,c['structure'])
    assert list(model.models)==[name for name,_,_ in expected_stages]
    summary = {}
    for stage,frame,y in expected_stages:
        classes = model.models[stage].classes_.astype(int)
        np.testing.assert_array_equal(np.sort(classes),np.unique(y))
        summary[stage] = {'actual_fitting_rows':len(frame),'actual_fitting_people':frame.group_key.nunique(),
            'fit_row_keys':frame.row_key.tolist(),'observed_target_classes':sorted(set(y.tolist())),
            'observed_target_counts':{str(int(k)):int(v) for k,v in zip(*np.unique(y,return_counts=True))}}
        if c['member']=='core':
            pipeline = model.models[stage]
            transformed,median,missing,mean,var = independent_preprocessing(frame,expected_features)
            imputer,scaler,mlp = [item[1] for item in pipeline.steps]
            np.testing.assert_allclose(imputer.statistics_,median,atol=1e-11)
            np.testing.assert_array_equal(imputer.indicator_.features_,missing)
            np.testing.assert_allclose(scaler.mean_,mean,atol=1e-11)
            np.testing.assert_allclose(scaler.var_,var,atol=1e-11)
            np.testing.assert_allclose(scaler.transform(imputer.transform(frame[expected_features])),transformed,atol=1e-10)
            params = mlp.get_params()
            assert all(params[k]==v for k,v in specification['params'].items())
            assert params['random_state']==42 and not params['early_stopping']
        else:
            params = model.models[stage].get_params()
            expected = {'iterations':specification['iterations'],'depth':specification['depth'],
                'l2_leaf_reg':specification['l2_leaf_reg'],'learning_rate':.03,
                'loss_function':'Logloss' if stage=='change' else 'MultiClass','boosting_type':'Ordered',
                'grow_policy':'SymmetricTree','random_seed':42,'thread_count':4,'task_type':'CPU',
                'border_count':128,'bootstrap_type':'Bayesian','bagging_temperature':1.,
                'random_strength':1.,'nan_mode':'Min','use_best_model':False,'allow_writing_files':False,'verbose':False}
            assert params==expected,(stage,params)
    assert model.stage_summary==summary
    delta = targets(fitting)
    expected = {'actual_native_rows':len(fitting),'actual_native_people':fitting.group_key.nunique(),
        'actual_zero_changes':int((delta==0).sum()),'actual_nonzero_changes':int((delta!=0).sum()),
        'actual_negative_changes':int((delta<0).sum()),'estimator_fits':len(expected_stages),
        'synthetic_rows':0,'artificial_history_views':0,'test_outcomes_used':False,'separate_source_targets_fitted':0}
    assert model.fitting_summary==expected
    if c['structure']=='flat':
        known = model.models['flat'].classes_.astype(int)+10
    else:
        known = np.sort(np.r_[0,model.models['magnitude'].classes_.astype(int)])+10
    priority = known.tolist()+[i for i in range(21) if i not in known]
    np.testing.assert_array_equal(model.priority,priority)


def independent_prediction(model,query):
    p = {}
    with threadpool_limits(limits=1):
        for name,estimator in model.models.items():
            options = {'thread_count':4} if model.candidate['member']=='cat' else {}
            p[name] = estimator.predict_proba(query[model.input_features],**options)
    if model.candidate['structure']=='flat':
        distribution = np.ones((len(query),21))*.0001
        distribution[:,model.models['flat'].classes_.astype(int)+10] = np.clip(p['flat'],.0001,None)
        distribution /= distribution.sum(axis=1)[:,None]
    else:
        nonzero = np.ones((len(query),21))*.0001
        nonzero[:,10] = 0.
        nonzero[:,model.models['magnitude'].classes_.astype(int)+10] = np.clip(p['magnitude'],.0001,None)
        nonzero /= nonzero.sum(axis=1)[:,None]
        gate_classes = model.models['change'].classes_.astype(int).tolist()
        distribution = nonzero*p['change'][:,gate_classes.index(1),None]
        distribution[:,10] = p['change'][:,gate_classes.index(0)]
    classes = model.priority
    delta = classes[np.argmax(distribution[:,classes],axis=1)]-10
    borg = np.minimum(10,np.maximum(0,query.prior_borg.to_numpy(int)+delta))
    return np.asarray([f'Borg {int(value)}' for value in borg]),distribution


def refit_observing_actual_targets(candidate,fitting,specification):
    stages = stage_rows(fitting,candidate['structure'])
    features = study.features_for(candidate,specification)
    calls = []
    old_mlp,old_cat = MLPClassifier.fit,CatBoostClassifier.fit
    def check(estimator,x,y,is_cat):
        assert len(calls)<len(stages)
        name,frame,expected = stages[len(calls)]
        np.testing.assert_array_equal(np.asarray(y).astype(int),expected)
        if is_cat:
            pd.testing.assert_frame_equal(x,frame[features])
            assert estimator.get_params()['loss_function']==('Logloss' if name=='change' else 'MultiClass')
        else:
            np.testing.assert_allclose(x,independent_preprocessing(frame,features)[0],atol=1e-10)
        calls.append({'stage':name,'actual_target_rows':len(y),'actual_target_classes':sorted(set(expected.tolist())),
            'original_row_keys':frame.row_key.tolist()})
    def mlp(estimator,x,y,*args,**kwargs):
        check(estimator,x,y,False)
        return old_mlp(estimator,x,y,*args,**kwargs)
    def cat(estimator,x,y=None,*args,**kwargs):
        check(estimator,x,y,True)
        assert kwargs.get('cat_features')==[x for x in features if x=='current_terrain']
        assert 'eval_set' not in kwargs and 'sample_weight' not in kwargs
        return old_cat(estimator,x,y,*args,**kwargs)
    with patch.object(MLPClassifier,'fit',mlp),patch.object(CatBoostClassifier,'fit',cat):
        model = study.ObservedChangeBorg(candidate).fit(fitting,specification)
    assert len(calls)==len(stages)
    verify_model(model,candidate,fitting,specification)
    return model,calls


def validate():
    inputs = study.load_inputs()
    train = inputs['train']
    selection_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selection_path.read_text())
    assert selected['status']=='complete' and selected['plan']==study.plan() and len(selected['results'])==10
    signature = study.fingerprint(inputs)
    assert all(selected.get(k)==v for k,v in signature.items())
    assert digest(study.DIRECTORY/'selection-source.py')==digest(Path(study.__file__))
    assert selected['train_row_keys']==train.row_key.tolist() and not selected['test_used_for_selection']
    folds = list(GroupKFold(5).split(train,groups=train.group_key))
    by_id = {r['candidate']['id']:r for r in selected['results']}
    factorized = [r for r in selected['results'] if r['candidate'].get('structure')=='factorized']
    best = {m:max([r for r in factorized if r['candidate']['member']==m],key=lambda r:r['accuracy_mean']) for m in ('core','cat')}
    matched = {m:next(r for r in selected['results'] if r['candidate'].get('member')==m
        and r['candidate'].get('feature_set')==best[m]['candidate']['feature_set'] and r['candidate'].get('structure')=='flat') for m in best}
    winner = max(selected['results'],key=lambda r:r['accuracy_mean'])
    refit_ids = {r['candidate']['id'] for r in [*best.values(),*matched.values()]}
    if winner['candidate']['algorithm']=='observed_change_distribution':
        refit_ids.add(winner['candidate']['id'])
    hashes,refits,stage_fits,reloads,artifact_count = {},[],0,0,0
    for c in study.plan():
        row = by_id[c['id']]
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['predecessor_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])
            predicted = np.asarray(old['oof_predictions'])
        else:
            predicted = np.empty(487,object)
            for number,(fit,val) in enumerate(folds):
                fitting,validation = train.iloc[fit],train.iloc[val]
                assert set(fitting.group_key).isdisjoint(validation.group_key)
                fold_path = study.DIRECTORY/'folds'/f"{c['id']}-fold-{number}.json"
                path = fold_path.with_suffix('.joblib')
                stored = json.loads(fold_path.read_text())
                assert stored==row['folds'][number]
                assert stored['signature']==signature and stored['candidate']==c
                assert stored['fit_row_keys']==fitting.row_key.tolist() and stored['validation_row_keys']==validation.row_key.tolist()
                assert stored['model_sha256']==digest(path)
                hashes[path.name],hashes[fold_path.name] = digest(path),digest(fold_path)
                artifact_count += 1
                model = joblib.load(path)
                verify_model(model,c,fitting,inputs['specifications'][c['member']])
                assert stored['stage_summary']==model.stage_summary and stored['fitting_summary']==model.fitting_summary
                assert stored['convergence_warnings']==model.convergence_warnings
                query = validation[model.input_features]
                expected,distribution = independent_prediction(model,query)
                np.testing.assert_allclose(model.probabilities(query),distribution,atol=1e-12)
                np.testing.assert_array_equal(model.predict(query),expected)
                np.testing.assert_array_equal(stored['predicted'],expected)
                predicted[val] = expected
                if c['feature_set']=='history' and c['structure']=='flat':
                    old = inputs['predecessor_selection']['results'][0 if c['member']=='core' else 1]
                    np.testing.assert_array_equal(expected,np.asarray(old['oof_predictions'])[val])
                if c['id'] in refit_ids:
                    refitted,calls = refit_observing_actual_targets(c,fitting,inputs['specifications'][c['member']])
                    np.testing.assert_array_equal(refitted.predict(query),expected)
                    np.testing.assert_allclose(refitted.probabilities(query),distribution,atol=1e-12)
                    assert refitted.convergence_warnings==model.convergence_warnings
                    stream = io.BytesIO()
                    joblib.dump(refitted,stream)
                    stream.seek(0)
                    restored = joblib.load(stream)
                    np.testing.assert_array_equal(restored.predict(query),expected)
                    assert set(vars(restored))=={'candidate','specification','input_features','models','stage_summary',
                        'convergence_warnings','priority','fitting_summary'}
                    reloads += 1
                    stage_fits += len(calls)
                    refits.append({'candidate_id':c['id'],'fold':number,'actual_stage_target_calls':calls,
                        'actual_input_rows_and_targets_independently_observed':True,'fitting_people_only':True,
                        'reload_without_current_truth_or_ids':True})
                print(f"Independent observed-change audit:{c['id']} fold{number+1}/5",flush=True)
        np.testing.assert_array_equal(row['oof_predictions'],predicted)
        scores = [float(np.mean(predicted[val]==train.iloc[val].label.to_numpy())) for _,val in folds]
        np.testing.assert_allclose(row['fold_accuracy'],scores,atol=1e-15)
        assert row['accuracy_mean']==float(np.mean(scores))
        assert row['pooled_oof_accuracy']==float(np.mean(predicted==train.label.to_numpy()))
    assert artifact_count==40 and len(hashes)==80 and len(refits)==5*len(refit_ids) and reloads==len(refits)
    assert all(digest(study.DIRECTORY/'folds'/name)==value for name,value in hashes.items())
    assert selected['winner_id']==winner['candidate']['id'] and selected['best_cv_accuracy']==winner['accuracy_mean']
    gate_path = study.DOCS/'observed-change-factorization-test-gate.json'
    gate = json.loads(gate_path.read_text())
    assert gate['selection_sha256']==digest(selection_path)
    assert gate['evaluator_code_sha256']==digest(Path(__file__).with_name('evaluate_fatigue_observed_change_factorization.py'))
    assert gate['pretest_verifier_code_sha256']==digest(Path(__file__))
    assert gate['gate_passed']==(winner['accuracy_mean']>=.65 and winner['candidate']['algorithm']=='observed_change_distribution')
    full_test_refit_calls = []
    if gate['gate_passed']:
        assert gate['pretest_winner_fold_artifacts_verified']==5
        path = study.DIRECTORY/'evaluation/model.joblib'
        result = gate['new_test_evaluation']
        assert digest(path)==result['model_sha256'] and result['frozen_artifact_reloaded_before_test']
        model = joblib.load(path)
        verify_model(model,winner['candidate'],train,inputs['specifications'][winner['candidate']['member']])
        test = inputs['test']
        expected,distribution = independent_prediction(model,test[model.input_features])
        np.testing.assert_allclose(model.probabilities(test[model.input_features]),distribution,atol=1e-12)
        np.testing.assert_array_equal(result['predictions'],expected)
        assert result['original_test_row_keys']==test.row_key.tolist() and result['test_cases']==179
        correct = int(np.sum(expected==test.label.to_numpy()))
        assert result['test_correct']==correct and result['test_accuracy']==correct/179 and result['achieved']==(correct>=144)
        refitted,calls = refit_observing_actual_targets(winner['candidate'],train,inputs['specifications'][winner['candidate']['member']])
        full_test_refit_calls = calls
        np.testing.assert_array_equal(refitted.predict(test[refitted.input_features]),expected)
        assert json.loads((path.parent/'metrics.json').read_text())==result
    else:
        assert gate['pretest_winner_fold_artifacts_verified']==0
        assert gate['new_test_evaluation'] is None and not (study.DIRECTORY/'evaluation').exists()
    compact = lambda r:{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')}
    report = {'verification':'passed','verification_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(selection_path),'previous_verification_sha256':digest(study.PARENT_AUDIT),
        'proposal_sha256':digest(study.PROPOSAL),'test_gate_sha256':digest(gate_path),
        'fold_artifact_hashes':hashes,'all_10_oof_recipes_recomputed':True,'all_40_fold_artifacts_recomputed':True,
        'best_factorized_by_member':{m:compact(r) for m,r in best.items()},
        'matched_flat_controls':{m:compact(r) for m,r in matched.items()},
        'best_factorized_cv_accuracy':max(r['accuracy_mean'] for r in factorized),
        'best_cv_accuracy':winner['accuracy_mean'],'independent_candidate_fold_refits':len(refits),
        'independent_stage_estimator_refits':stage_fits,'actual_refit_calls':refits,'input_only_artifact_reloads':reloads,
        'independent_full_test_refit_stage_calls':full_test_refit_calls,
        'actual_original_targets_and_subset_preprocessing_verified':True,'original_negative_changes_preserved':True,
        'original_native_cases_preserved':True,'synthetic_rows':0,'current_and_future_labels_excluded':True,
        'new_test_gate_passed':gate['gate_passed'],'new_test_evaluation':gate['new_test_evaluation']}
    (study.DOCS/'observed-change-factorization-verification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('fold_artifact_hashes','actual_refit_calls','best_factorized_by_member','matched_flat_controls')}),flush=True)
    return report


if __name__=='__main__':
    validate()
