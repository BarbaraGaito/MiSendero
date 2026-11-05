"""Freeze/reload the sole CV-qualified shoulder-transfer model before test."""
import json
from datetime import datetime,timezone
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import fatigue_shoulder_history_joint as study
from public_sources import digest


def evaluate():
    inputs = study.load_inputs()
    path = study.DIRECTORY/'selection.json'
    selection = json.loads(path.read_text())
    winner = max(selection['results'],key=lambda r:r['accuracy_mean'])
    assert selection['status']=='complete' and selection['plan']==study.plan()
    assert all(selection.get(k)==v for k,v in study.fingerprint(inputs).items())
    assert selection['winner_id']==winner['candidate']['id'] and selection['best_cv_accuracy']==winner['accuracy_mean']
    assert not selection['test_used_for_selection']
    directory = study.DIRECTORY/'evaluation'
    qualified = winner['candidate']['algorithm']!='previous_real_control' and winner['accuracy_mean']>=.65
    if not qualified:
        assert not (directory/'metrics.json').exists()
        return {'evaluation_performed':False,'reason':'No new winner reached the predeclared.65CVgate',
            'winner_id':selection['winner_id'],'best_cv_accuracy':selection['best_cv_accuracy'],'original_test_cases':179}
    identity = {'signature':study.fingerprint(inputs),'selection_sha256':digest(path),'candidate':winner['candidate'],
        'evaluation_code_sha256':digest(Path(__file__)),'original_train_row_keys':inputs['train'].row_key.tolist(),
        'original_test_row_keys':inputs['test'].row_key.tolist(),'training_cases':487,'test_cases':179,
        'test_used_for_selection':False,'artifact_frozen_before_test_prediction':True,'deployment_approved':False}
    directory.mkdir(exist_ok=True)
    artifact,descriptor_path = directory/'model.joblib',directory/'pre-test-model.json'
    if not descriptor_path.exists():
        candidate = winner['candidate']
        cache = study.base.previous.prepare_base(inputs['train'],candidate['member'],inputs['specifications'][candidate['member']])
        model = study.ShoulderHistoryBorg(candidate).fit(inputs['train'],inputs['source'],inputs['specifications'][candidate['member']],inputs['context_features'],cached=cache)
        joblib.dump(model,artifact)
        descriptor = {**identity,'frozen_at':datetime.now(timezone.utc).isoformat(),'model_sha256':digest(artifact),
            'training_summary':model.training_summary,'loss_endpoints':model.loss_endpoints,'runtime_input_features':model.input_features}
        descriptor_path.write_text(json.dumps(descriptor,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    descriptor = json.loads(descriptor_path.read_text())
    assert all(descriptor.get(k)==v for k,v in identity.items()) and descriptor['model_sha256']==digest(artifact)
    model = joblib.load(artifact)
    test = inputs['test']
    predicted = model.predict(test[model.input_features])
    assert len(predicted)==179 and set(predicted)<={f'Borg {i}' for i in range(11)}
    correct = int((predicted==test.label.to_numpy()).sum())
    metrics = {'version':1,'evaluation_performed':True,'descriptor_sha256':digest(descriptor_path),
        'model_sha256':digest(artifact),'selection_sha256':digest(path),'winner_id':selection['winner_id'],
        'selected_cv_accuracy':winner['accuracy_mean'],'test_accuracy':correct/179,'correct':correct,'cases':179,
        'original_training_cases':487,'test_used_for_selection':False,'required_correct_for_80_percent':144,
        'target_accuracy':.8,'achieved':correct>=144,
        'scope':'Unchanged179native exactBorgcases after frozen original-person CVselection. Source2336actualfitting pairs and312reserved pairs kept separate. Model/descriptor serialized before original test predictions and reloaded. No synthetic observations,source-native scaleconversion or changed denominator.'}
    output = test[['row_key','group_key','label']].copy().reset_index(drop=True)
    output['predicted'] = predicted
    predictions_path,metrics_path = directory/'predictions.csv',directory/'metrics.json'
    if predictions_path.exists():
        pd.testing.assert_frame_equal(pd.read_csv(predictions_path),output,check_dtype=False)
    else:
        output.to_csv(predictions_path,index=False)
    if metrics_path.exists():
        assert json.loads(metrics_path.read_text())==metrics
    metrics_path.write_text(json.dumps(metrics,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    np.testing.assert_array_equal(joblib.load(artifact).predict(test[model.input_features]),predicted)
    return metrics


if __name__=='__main__':
    print(json.dumps(evaluate(),indent=2,allow_nan=False),flush=True)
