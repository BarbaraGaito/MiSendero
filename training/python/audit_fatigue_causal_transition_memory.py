"""Recompute every memory recipe independently from actual prior reports."""
from __future__ import annotations
import io
import json
import re
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

import fatigue_causal_transition_memory as study
from public_sources import digest,RAW


def independent_metadata(frame,manifest):
    sessions = json.loads((RAW/'geofatigue/session_metadata.json').read_text())
    lineage = {row['row_key']:row for row in manifest['lineage']}
    result = []
    for row in frame.itertuples():
        original = lineage[row.row_key]
        person = 'p'+re.search(r'/p(\d+)-',original['sensor_members'][0])[1]
        instant = pd.Timestamp(original['response_time'])
        actual = [s for s in sessions[person]
            if pd.Timestamp(s['start_time'])<=instant<=pd.Timestamp(s['end_time'])]
        assert len(actual)==1
        result.append({'group_key':row.group_key,'session_start':pd.Timestamp(actual[0]['start_time']),
            'task_start':pd.Timestamp(original['task_start']),'response_time':instant})
    return pd.DataFrame(result)


def independent_scaling(fitting,queries,features):
    raw = fitting[features].to_numpy(float)
    medians = np.nanmedian(raw,axis=0)
    assert np.isfinite(medians).all()
    missing = np.flatnonzero(np.isnan(raw).any(axis=0))
    def fill(frame):
        values = frame[features].to_numpy(float)
        return np.column_stack([np.where(np.isnan(values),medians,values),np.isnan(values[:,missing]).astype(float)])
    fitted = fill(fitting)
    mean,variance = fitted.mean(axis=0),fitted.var(axis=0)
    scales = np.sqrt(variance)
    scales[scales==0] = 1.
    return (fill(queries)-mean)/scales,medians,missing,mean,variance


def independent_recipe(base,c,validation,metadata,encoded):
    # Obtain raw observed-class probabilities, without calling study.logits.
    raw = base.classifier.model.predict_proba(validation[base.input_features])
    probabilities = np.full((len(validation),21),study.native.FLOOR,float)
    probabilities[:,base.class_indices] = np.maximum(raw,study.native.FLOOR)
    probabilities /= probabilities.sum(axis=1,keepdims=True)
    keys,evidence = [],[]
    for n in range(len(validation)):
        current = metadata.iloc[n]
        indices = []
        for j in range(len(validation)):
            old = metadata.iloc[j]
            if old.group_key!=current.group_key or old.session_start!=current.session_start:
                continue
            age = (current.response_time-old.response_time).total_seconds()/60
            if age<1 or (c['scope']=='task' and old.task_start!=current.task_start):
                continue
            indices.append(j)
        indices.sort(key=lambda j:metadata.iloc[j].response_time)
        keys.append(validation.iloc[indices].row_key.tolist())
        weights,targets = [],[]
        for j in indices:
            old = validation.iloc[j]
            age = (current.response_time-metadata.iloc[j].response_time).total_seconds()/60
            squared = sum((float(a)-float(b))**2 for a,b in zip(encoded[j],encoded[n]))/encoded.shape[1]
            weights.append(np.exp(-squared/(2*c['bandwidth']**2)-age/c['recency_minutes']))
            targets.append(int(old.label.removeprefix('Borg '))-int(old.prior_borg)+10)
        mass = float(sum(weights))
        mixture = c['strength']*mass/(mass+c['mass_shrinkage']) if mass else 0.
        if mixture:
            histogram = np.zeros(21)
            for target,weight in zip(targets,weights):
                assert 0<=target<=20
                histogram[target] += weight/mass
            probabilities[n] = (1-mixture)*probabilities[n]+mixture*histogram
        evidence.append({'support_count':len(indices),'weight_mass':mass,'mixture_weight':mixture})
    order = base.priority
    picked = order[probabilities[:,order].argmax(axis=1)]-10
    labels = [f'Borg {int(np.clip(prior+delta,0,10))}' for prior,delta in zip(validation.prior_borg,picked)]
    return labels,probabilities,keys,evidence


def validate():
    inputs = study.load_inputs()
    train = inputs['train']
    path = study.DIRECTORY/'selection.json'
    selection = json.loads(path.read_text())
    assert selection['status']=='complete' and selection['plan']==study.plan() and len(selection['results'])==36
    signature = study.fingerprint(inputs)
    assert all(selection.get(k)==v for k,v in signature.items())
    assert digest(study.DIRECTORY/'selection-source.py')==digest(Path(study.__file__))
    assert selection['train_row_keys']==train.row_key.tolist()
    assert selection['evaluation_denominator']==487 and selection['test_denominator']==179
    assert not selection['test_used_for_selection'] and selection['new_native_base_fits']==0
    actual = {r['candidate']['id']:r for r in selection['results']}
    independent_predictions = {c['id']:np.empty(487,object) for c in study.plan()[2:]}
    folds = list(GroupKFold(5).split(train,groups=train.group_key))
    positive = [r for r in selection['results'] if r['candidate'].get('strength',0)>0]
    best = {member:max([r for r in positive if r['candidate']['member']==member],key=lambda r:r['accuracy_mean'])
        for member in ('core','cat')}
    reload_ids = {r['candidate']['id'] for r in best.values()}|{c['id'] for c in study.plan()[2:4]}
    hashes = {p.name:digest(p) for p in (study.native.DIRECTORY/'bases').iterdir() if p.suffix in ('.json','.joblib')}
    assert len(hashes)==20
    audits,links,reloads,preprocessors = [],0,0,0
    # Any accidental predictive refitting is an error in this cache-based study.
    with patch.object(study.native.NativeBase,'fit',side_effect=AssertionError('Unexpected new base fit')):
        for member in ('core','cat'):
            for number,(fit,val) in enumerate(folds):
                fitting,validation = train.iloc[fit],train.iloc[val]
                assert set(fitting.group_key).isdisjoint(validation.group_key)
                cache = study.read_cache(inputs,member,number,fit,val)
                before = joblib.hash(cache)
                meta = independent_metadata(validation,inputs['memory_manifest'])
                pd.testing.assert_frame_equal(meta,study.temporal_metadata(validation,inputs['memory_manifest']))
                for c in (c for c in study.plan()[2:] if c['member']==member):
                    model = study.TransitionMemoryBorg(c).fit(fitting,cache)
                    preprocessors += 1
                    z,median,missing,mean,var = independent_scaling(fitting,validation,model.retrieval_features)
                    np.testing.assert_allclose(model.imputer.statistics_,median,atol=1e-12)
                    np.testing.assert_array_equal(model.imputer.indicator_.features_,missing)
                    np.testing.assert_allclose(model.scaler.mean_,mean,atol=1e-12)
                    np.testing.assert_allclose(model.scaler.var_,var,atol=1e-12)
                    np.testing.assert_allclose(model.transform(validation),z,atol=1e-11)
                    labels,p,keys,counts = independent_recipe(cache['base'],c,validation,meta,z)
                    queries = validation[model.input_features]
                    seen = []
                    packets = study.make_episodes(validation.drop(columns='label'),validation,
                        inputs['memory_manifest'],c['scope'],model.input_features,
                        observer=lambda query,support:seen.append((query,support)))
                    for n,packet in enumerate(packets):
                        assert seen[n]==(validation.iloc[n].row_key,keys[n])
                        assert packet['support_keys']==keys[n]
                        assert packet['query_metadata']=={k:str(meta.iloc[n][k]) for k in study.META_COLUMNS}
                        independent_positions = {key:j for j,key in enumerate(validation.row_key)}
                        assert packet['support_metadata']==[{k:str(meta.iloc[independent_positions[key]][k])
                            for k in study.META_COLUMNS} for key in keys[n]]
                        chosen = validation[validation.row_key.isin(keys[n])].set_index('row_key').loc[keys[n]]
                        assert packet['support_labels']==chosen.label.tolist()
                        pd.testing.assert_frame_equal(packet['support_features'].reset_index(drop=True),
                            chosen[model.input_features].reset_index(drop=True))
                        links += len(keys[n])
                    np.testing.assert_allclose(model.probabilities(queries,packets)[0],p,atol=1e-11)
                    np.testing.assert_array_equal(model.predict(queries,packets),labels)
                    saved = json.loads((study.DIRECTORY/'folds'/f"{c['id']}-fold-{number}.json").read_text())
                    assert saved==actual[c['id']]['folds'][number]
                    assert saved['candidate']==c and saved['signature']==signature
                    assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
                    assert saved['fitting_summary']==model.fitting_summary
                    np.testing.assert_array_equal(saved['predicted'],labels)
                    np.testing.assert_allclose([[e[k] for k in ('support_count','weight_mass','mixture_weight')]
                        for e in saved['causal_memory_evidence']],[[e[k] for k in ('support_count','weight_mass','mixture_weight')]
                        for e in counts],atol=1e-11)
                    independent_predictions[c['id']][val] = labels
                    if not c['strength']:
                        np.testing.assert_array_equal(labels,cache['base'].predict(queries))
                        old = inputs['parent_selection']['results'][0 if member=='core' else 1]
                        np.testing.assert_array_equal(labels,np.asarray(old['oof_predictions'])[val])
                    if c['id'] in reload_ids:
                        assert set(vars(model))=={'candidate','base','retrieval_features','input_features','imputer','scaler','fitting_summary'}
                        assert model.fitting_summary['population_artifact_stored_personal_reports']==0
                        memory = io.BytesIO()
                        joblib.dump(model,memory)
                        memory.seek(0)
                        np.testing.assert_array_equal(joblib.load(memory).predict(queries,packets),labels)
                        reloads += 1
                assert joblib.hash(cache)==before
                audits.append({'member':member,'fold':number,'recipes_independently_recomputed':17,
                    'actual_fitting_rows':len(fitting),'actual_validation_rows':len(validation),
                    'preprocessing_fitting_people_only':True,'query_labels_excluded_from_inference':True,
                    'support_times_and_actual_labels_verified':True,'base_weights_unchanged':True})
                print(f'Independent actual-memory audit:{member} fold{number+1}/5',flush=True)
    for c in study.plan():
        if c['algorithm']=='previous_real_control':
            old = next(r for r in inputs['parent_selection']['results'] if r['candidate']['id']==c['parent_candidate_id'])
            predicted = np.asarray(old['oof_predictions'])
        else:
            predicted = independent_predictions[c['id']]
        row = actual[c['id']]
        np.testing.assert_array_equal(predicted,row['oof_predictions'])
        scores = [float(np.mean(predicted[val]==train.iloc[val].label.to_numpy())) for _,val in folds]
        np.testing.assert_allclose(row['fold_accuracy'],scores,atol=1e-15)
        assert row['accuracy_mean']==float(np.mean(scores)) and row['pooled_oof_accuracy']==float(np.mean(predicted==train.label.to_numpy()))
    assert hashes=={name:digest(study.native.DIRECTORY/'bases'/name) for name in hashes}
    winner = max(selection['results'],key=lambda r:r['accuracy_mean'])
    assert selection['winner_id']==winner['candidate']['id'] and selection['best_cv_accuracy']==winner['accuracy_mean']
    gate_path = study.DOCS/'causal-transition-memory-test-gate.json'
    gate = json.loads(gate_path.read_text())
    assert gate['selection_sha256']==digest(path)
    assert gate['evaluator_code_sha256']==digest(Path(__file__).with_name('evaluate_fatigue_causal_transition_memory.py'))
    assert gate['gate_passed']==(winner['accuracy_mean']>=.65 and winner['candidate']['algorithm']=='causal_transition_memory')
    if not gate['gate_passed']:
        assert gate['new_test_evaluation'] is None and not (study.DIRECTORY/'evaluation').exists()
    else:
        # Independently verify the complete original test, not just its CV gate.
        directory = study.DIRECTORY/'evaluation'
        model_path = directory/'model.joblib'
        result = gate['new_test_evaluation']
        artifact = joblib.load(model_path)
        assert artifact.candidate==winner['candidate'] and result['model_sha256']==digest(model_path)
        assert result['frozen_artifact_reloaded_before_test'] and result['test_cases']==179
        assert result['original_test_row_keys']==inputs['test'].row_key.tolist()
        assert artifact.fitting_summary['fitting_row_keys']==train.row_key.tolist()
        assert artifact.base.fitting_summary['actual_native_rows']==487
        assert artifact.base.fitting_summary['actual_native_people']==28
        test = inputs['test']
        z,median,missing,mean,var = independent_scaling(train,test,artifact.retrieval_features)
        np.testing.assert_allclose(artifact.imputer.statistics_,median,atol=1e-12)
        np.testing.assert_array_equal(artifact.imputer.indicator_.features_,missing)
        np.testing.assert_allclose(artifact.scaler.mean_,mean,atol=1e-12)
        np.testing.assert_allclose(artifact.scaler.var_,var,atol=1e-12)
        meta = independent_metadata(test,inputs['memory_manifest'])
        labels,_,_,_ = independent_recipe(artifact.base,artifact.candidate,test,meta,z)
        packets = study.make_episodes(test.drop(columns='label'),test,inputs['memory_manifest'],
            artifact.candidate['scope'],artifact.input_features)
        np.testing.assert_array_equal(artifact.predict(test[artifact.input_features],packets),labels)
        np.testing.assert_array_equal(result['predictions'],labels)
        correct = int(np.sum(np.asarray(labels)==test.label.to_numpy()))
        assert result['test_correct']==correct and result['test_accuracy']==correct/179
        assert result['achieved']==(correct>=144)
        assert json.loads((directory/'metrics.json').read_text())==result
    compact = lambda r:{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')}
    report = {'verification':'passed','verification_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(path),'previous_verification_sha256':digest(study.PARENT_AUDIT),
        'proposal_sha256':digest(study.PROPOSAL),'test_gate_sha256':digest(gate_path),
        'native_base_cache_artifact_hashes':hashes,'all_36_oof_recipes_recomputed':True,
        'independent_preprocessor_refits':preprocessors,'independent_fold_comparisons':170,
        'actual_prior_query_links_verified_including_repeated_recipes':links,
        'memory_free_population_artifact_reloads':reloads,'fold_audits':audits,
        'best_positive_by_member':{m:compact(r) for m,r in best.items()},
        'best_positive_cv_accuracy':max(r['accuracy_mean'] for r in positive),
        'matched_zero_memory_controls':{c['member']:compact(actual[c['id']]) for c in study.plan()[2:4]},
        'best_cv_accuracy':winner['accuracy_mean'],'new_native_base_fits':0,'synthetic_rows':0,
        'preprocessing_fit_people_only':True,'current_and_future_labels_excluded':True,
        'actual_metadata_independently_resolved':True,'new_test_gate_passed':gate['gate_passed'],
        'new_test_evaluation':gate['new_test_evaluation'],'original_native_cases_preserved':True}
    assert preprocessors==170 and reloads==20 and len(audits)==10
    (study.DOCS/'causal-transition-memory-verification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('native_base_cache_artifact_hashes','fold_audits','best_positive_by_member','matched_zero_memory_controls')}),flush=True)
    return report


if __name__=='__main__':
    validate()
