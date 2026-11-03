"""Only the frozen, CV-qualified winner may reach the original 179 cases."""
import json
from pathlib import Path
import joblib
import numpy as np
from sklearn.metrics import accuracy_score
import fatigue_causal_transition_memory as study
from public_sources import digest


def evaluate():
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selection_path.read_text())
    assert selected['status']=='complete' and selected['plan']==study.plan()
    assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
    winner = max(selected['results'],key=lambda r:r['accuracy_mean'])
    qualified = winner['accuracy_mean']>=.65 and winner['candidate']['algorithm']=='causal_transition_memory'
    report = {'evaluator_code_sha256':digest(Path(__file__)),'selection_sha256':digest(selection_path),
        'winner_id':winner['candidate']['id'],'best_cv_accuracy':winner['accuracy_mean'],
        'minimum_cv_for_new_test_evaluation':.65,'gate_passed':qualified,'new_test_evaluation':None}
    if qualified:
        directory = study.DIRECTORY/'evaluation'
        directory.mkdir(exist_ok=True)
        model_path = directory/'model.joblib'
        candidate = winner['candidate']
        fitting,test = inputs['train'],inputs['test']
        identity = {'selection_sha256':digest(selection_path),'candidate':candidate}
        metadata_path = directory/'model.json'
        if model_path.exists():
            meta = json.loads(metadata_path.read_text())
            assert all(meta[k]==v for k,v in identity.items()) and meta['model_sha256']==digest(model_path)
        else:
            base = study.native.NativeBase(candidate['member'],inputs['specifications'][candidate['member']]).fit(fitting)
            model = study.TransitionMemoryBorg(candidate).fit(fitting,{'base':base,'fit_row_keys':fitting.row_key.tolist()})
            joblib.dump(model,model_path)
            metadata_path.write_text(json.dumps({**identity,'model_sha256':digest(model_path),
                'actual_native_base_fits':1,'artifact_stored_personal_reports':0},indent=2)+'\n',encoding='utf-8')
        restored = joblib.load(model_path)
        # Eligibility is established before these actual earlier labels are read.
        episodes = study.make_episodes(test.drop(columns='label'),test,inputs['memory_manifest'],
            candidate['scope'],restored.input_features)
        predictions = restored.predict(test[restored.input_features],episodes)
        correct = int(np.sum(predictions==test.label.to_numpy()))
        result = {'test_cases':179,'test_correct':correct,'test_accuracy':float(accuracy_score(test.label,predictions)),
            'model_sha256':digest(model_path),'frozen_artifact_reloaded_before_test':True,
            'predictions':predictions.tolist(),'original_test_row_keys':test.row_key.tolist(),
            'achieved':correct>=144,'past_self_report_feedback_required':True}
        assert result['test_accuracy']==correct/179
        metrics_path = directory/'metrics.json'
        if metrics_path.exists():
            assert json.loads(metrics_path.read_text())==result
        else:
            metrics_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        report['new_test_evaluation'] = result
    output = study.DOCS/'causal-transition-memory-test-gate.json'
    if output.exists():
        assert json.loads(output.read_text())==report
    else:
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report if not qualified else {k:v for k,v in report.items() if k!='new_test_evaluation'}),flush=True)
    return report


if __name__=='__main__':
    evaluate()
