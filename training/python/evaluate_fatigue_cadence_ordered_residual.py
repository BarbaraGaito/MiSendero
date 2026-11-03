"""Only a frozen CV-qualified full-Borg winner can reach the original test."""
import json
from pathlib import Path
import joblib
import numpy as np
from sklearn.model_selection import GroupKFold
import fatigue_cadence_ordered_residual as study
from public_sources import digest


def evaluate():
    inputs = study.load_inputs()
    selected_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selected_path.read_text())
    assert selected['status']=='complete' and selected['plan']==study.plan()
    assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
    winner = max(selected['results'],key=lambda row:row['accuracy_mean'])
    qualified = winner['accuracy_mean']>=.65 and winner['candidate']['algorithm']=='cadence_ordered_residual'
    report = {'evaluator_code_sha256':digest(Path(__file__)),'selection_sha256':digest(selected_path),
        'winner_id':winner['candidate']['id'],'best_cv_accuracy':winner['accuracy_mean'],
        'minimum_cv_for_new_test_evaluation':.65,'gate_passed':qualified,'new_test_evaluation':None,
        'pretest_verifier_code_sha256':digest(Path(__file__).with_name('audit_fatigue_cadence_ordered_residual.py')),
        'pretest_winner_fold_artifacts_verified':0}
    if qualified:
        from audit_fatigue_cadence_ordered_residual import verify_model,independent_prediction,verify_cache
        candidate = winner['candidate']
        train = inputs['train']
        scores = []
        for n,(fit,val) in enumerate(GroupKFold(5).split(train,groups=train.group_key)):
            fitting,validation = train.iloc[fit],train.iloc[val]
            cache = study.read_cache(inputs,candidate['member'],n,fit,val)
            verify_cache(cache,fitting,inputs['specifications'][candidate['member']])
            path = study.DIRECTORY/'folds'/f"{candidate['id']}-fold-{n}.json"
            saved = json.loads(path.read_text())
            assert saved['candidate']==candidate and saved['model_sha256']==digest(path.with_suffix('.joblib'))
            assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
            model = joblib.load(path.with_suffix('.joblib'))
            verify_model(model,candidate,fitting,inputs['gate_source'],inputs['specifications'][candidate['member']],inputs['context_features'],cache)
            labels,_,_ = independent_prediction(model,validation[model.input_features])
            np.testing.assert_array_equal(labels,np.asarray(winner['oof_predictions'])[val])
            scores.append(float(np.mean(labels==validation.label.to_numpy())))
            report['pretest_winner_fold_artifacts_verified'] += 1
        assert np.mean(scores)==winner['accuracy_mean'] and np.mean(scores)>=.65
        directory = study.DIRECTORY/'evaluation'
        directory.mkdir(exist_ok=True)
        model_path,cache_path = directory/'model.joblib',directory/'base-cache.joblib'
        metadata_path = directory/'model.json'
        identity = {'selection_sha256':digest(selected_path),'candidate':candidate}
        if model_path.exists():
            metadata = json.loads(metadata_path.read_text())
            assert all(metadata[k]==value for k,value in identity.items())
            assert metadata['model_sha256']==digest(model_path) and metadata['base_cache_sha256']==digest(cache_path)
        else:
            cache = study.native.prepare_base(train,candidate['member'],inputs['specifications'][candidate['member']])
            joblib.dump(cache,cache_path)
            model = study.FullDeltaCadenceBorg(candidate).fit(train,inputs['gate_source'],inputs['specifications'][candidate['member']],inputs['context_features'],cache)
            joblib.dump(model,model_path)
            metadata_path.write_text(json.dumps({**identity,'model_sha256':digest(model_path),'base_cache_sha256':digest(cache_path),
                'actual_full_native_base_fits':4,'joint_network_fits':1,'training_summary':model.training_summary},indent=2)+'\n',encoding='utf-8')
        restored = joblib.load(model_path)
        test = inputs['test']
        predicted = restored.predict(test[restored.input_features])
        correct = int(np.sum(predicted==test.label.to_numpy()))
        result = {'test_cases':179,'test_correct':correct,'test_accuracy':correct/179,
            'model_sha256':digest(model_path),'frozen_artifact_reloaded_before_test':True,
            'predictions':predicted.tolist(),'original_test_row_keys':test.row_key.tolist(),
            'achieved':correct>=144,'native_labels_coarsened':False,'synthetic_rows':0,'deployment_approved':False}
        path = directory/'metrics.json'
        if path.exists():
            assert json.loads(path.read_text())==result
        else:
            path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        report['new_test_evaluation'] = result
    path = study.DOCS/'cadence-ordered-residual-test-gate.json'
    if path.exists():
        assert json.loads(path.read_text())==report
    else:
        path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='new_test_evaluation'}),flush=True)
    return report


if __name__=='__main__':
    evaluate()
