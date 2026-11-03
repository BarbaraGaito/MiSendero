"""Gate the sole frozen CVwinner before any original-test prediction."""
import json
from pathlib import Path
import joblib
import numpy as np
from sklearn.model_selection import GroupKFold
import fatigue_observed_change_factorization as study
from public_sources import digest


def evaluate():
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/'selection.json'
    selection = json.loads(selection_path.read_text())
    assert selection['status']=='complete' and selection['plan']==study.plan()
    assert all(selection.get(k)==v for k,v in study.fingerprint(inputs).items())
    winner = max(selection['results'],key=lambda r:r['accuracy_mean'])
    qualified = winner['accuracy_mean']>=.65 and winner['candidate']['algorithm']=='observed_change_distribution'
    report = {'evaluator_code_sha256':digest(Path(__file__)),'selection_sha256':digest(selection_path),
        'winner_id':winner['candidate']['id'],'best_cv_accuracy':winner['accuracy_mean'],
        'minimum_cv_for_new_test_evaluation':.65,'gate_passed':qualified,'new_test_evaluation':None,
        'pretest_verifier_code_sha256':digest(Path(__file__).with_name('audit_fatigue_observed_change_factorization.py')),
        'pretest_winner_fold_artifacts_verified':0}
    if qualified:
        candidate = winner['candidate']
        # Recompute the sole winner's CV from reloaded artifacts before test.
        from audit_fatigue_observed_change_factorization import verify_model,independent_prediction
        training = inputs['train']
        scores = []
        for number,(fit,val) in enumerate(GroupKFold(5).split(training,groups=training.group_key)):
            fitting,validation = training.iloc[fit],training.iloc[val]
            assert set(fitting.group_key).isdisjoint(validation.group_key)
            fold_path = study.DIRECTORY/'folds'/f"{candidate['id']}-fold-{number}.json"
            saved = json.loads(fold_path.read_text())
            model_path = fold_path.with_suffix('.joblib')
            assert saved['model_sha256']==digest(model_path) and saved['candidate']==candidate
            assert saved['fit_row_keys']==fitting.row_key.tolist() and saved['validation_row_keys']==validation.row_key.tolist()
            restored = joblib.load(model_path)
            verify_model(restored,candidate,fitting,inputs['specifications'][candidate['member']])
            predicted,_ = independent_prediction(restored,validation[restored.input_features])
            np.testing.assert_array_equal(predicted,np.asarray(winner['oof_predictions'])[val])
            np.testing.assert_array_equal(predicted,restored.predict(validation[restored.input_features]))
            scores.append(float(np.mean(predicted==validation.label.to_numpy())))
            report['pretest_winner_fold_artifacts_verified'] += 1
        assert float(np.mean(scores))==winner['accuracy_mean'] and np.mean(scores)>=.65
        directory = study.DIRECTORY/'evaluation'
        directory.mkdir(exist_ok=True)
        model_path = directory/'model.joblib'
        metadata_path = directory/'model.json'
        identity = {'selection_sha256':digest(selection_path),'candidate':candidate}
        if model_path.exists():
            meta = json.loads(metadata_path.read_text())
            assert all(meta[k]==v for k,v in identity.items()) and meta['model_sha256']==digest(model_path)
        else:
            model = study.ObservedChangeBorg(candidate).fit(inputs['train'],inputs['specifications'][candidate['member']])
            joblib.dump(model,model_path)
            metadata_path.write_text(json.dumps({**identity,'model_sha256':digest(model_path),
                'fitting_summary':model.fitting_summary,'stage_summary':model.stage_summary},indent=2)+'\n',encoding='utf-8')
        restored = joblib.load(model_path)
        test = inputs['test']
        predicted = restored.predict(test[restored.input_features])
        correct = int(np.sum(predicted==test.label.to_numpy()))
        result = {'test_cases':179,'test_correct':correct,'test_accuracy':correct/179,
            'model_sha256':digest(model_path),'frozen_artifact_reloaded_before_test':True,
            'predictions':predicted.tolist(),'original_test_row_keys':test.row_key.tolist(),
            'achieved':correct>=144,'current_or_future_truth_used_as_predictor':False,
            'synthetic_rows':0,'deployment_approved':False}
        output = directory/'metrics.json'
        if output.exists():
            assert json.loads(output.read_text())==result
        else:
            output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        report['new_test_evaluation'] = result
    output = study.DOCS/'observed-change-factorization-test-gate.json'
    if output.exists():
        assert json.loads(output.read_text())==report
    else:
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='new_test_evaluation'}),flush=True)
    return report


if __name__=='__main__':
    evaluate()
