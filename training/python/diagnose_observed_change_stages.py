"""Fitting-participant component diagnostics, without new fits or native test."""
import json
from pathlib import Path
import joblib
import numpy as np
from sklearn.model_selection import GroupKFold
import fatigue_observed_change_factorization as study
from public_sources import digest


def component_scores(model,frame):
    query = frame[model.input_features]
    actual = study.actual_delta(frame)
    changed = actual!=0
    gate = model.raw_probabilities('change',query)
    gate_classes = model.models['change'].classes_.astype(int)
    gate_prediction = gate_classes[gate.argmax(axis=1)]
    conditional = model.raw_probabilities('magnitude',query.loc[changed])
    magnitude = model.models['magnitude'].classes_.astype(int)[conditional.argmax(axis=1)]
    return {'actual_rows':len(frame),'actual_nonzero_rows':int(changed.sum()),
        'native_exact_accuracy':float(np.mean(model.predict(query)==frame.label.to_numpy())),
        'binary_change_accuracy':float(np.mean(gate_prediction==changed.astype(int))),
        'conditional_nonzero_delta_accuracy':float(np.mean(magnitude==actual[changed]))}


def diagnose():
    inputs = study.load_inputs()
    path = study.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    assert selected['status']=='complete' and selected['plan']==study.plan()
    assert all(selected.get(k)==v for k,v in study.fingerprint(inputs).items())
    train = inputs['train']
    folds = list(GroupKFold(5).split(train,groups=train.group_key))
    results,hashes = [],{}
    for row in selected['results']:
        c = row['candidate']
        if c.get('structure')!='factorized':
            continue
        scores = []
        for n,(fit,val) in enumerate(folds):
            model_path = study.DIRECTORY/'folds'/f"{c['id']}-fold-{n}.joblib"
            assert digest(model_path)==row['folds'][n]['model_sha256']
            hashes[model_path.name] = digest(model_path)
            model = joblib.load(model_path)
            assert model.candidate==c
            fitting,validation = train.iloc[fit],train.iloc[val]
            assert set(fitting.group_key).isdisjoint(validation.group_key)
            fitting_scores = component_scores(model,fitting)
            validation_scores = component_scores(model,validation)
            assert validation_scores['native_exact_accuracy']==row['fold_accuracy'][n]
            scores.append({'fold':n,'fitting':fitting_scores,'validation':validation_scores,
                'convergence_warnings':model.convergence_warnings})
        mean = lambda partition,key:float(np.mean([r[partition][key] for r in scores]))
        results.append({'candidate':c,'native_fitting_accuracy_mean':mean('fitting','native_exact_accuracy'),
            'native_cv_accuracy_mean':mean('validation','native_exact_accuracy'),
            'binary_change_fitting_accuracy_mean':mean('fitting','binary_change_accuracy'),
            'binary_change_cv_accuracy_mean':mean('validation','binary_change_accuracy'),
            'conditional_delta_fitting_accuracy_mean':mean('fitting','conditional_nonzero_delta_accuracy'),
            'conditional_delta_cv_accuracy_mean':mean('validation','conditional_nonzero_delta_accuracy'),
            'folds':scores})
    assert len(results)==4 and len(hashes)==20
    assert all(digest(study.DIRECTORY/'folds'/name)==expected for name,expected in hashes.items())
    report = {'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(path),'fold_model_hashes':hashes,'original_fitting_queries':487,
        'original_fitting_people':28,'results':results,'new_predictive_estimator_fits':0,
        'new_preprocessor_fits':0,'new_test_predictions_computed':0,'test_labels_inspected':False,
        'synthetic_rows':0,'hyperparameters_selected_for_another_study':0,
        'interpretation':'Only native exact Borg accuracy on all original179test cases can satisfy the goal. '
            'Binary change and conditional magnitude metrics here describe separate internal tasks on fitting '
            'participants; neither is an80percent result for the full native target. Training accuracies are '
            'optimistic diagnostics,not independent validation. Current labels select/score the actual '
            'nonzero evaluation subset only;they do not enter either stage as prediction features.'}
    (study.DOCS/'observed-change-stage-diagnostic.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'diagnostic':'passed','results':[{k:v for k,v in r.items() if k!='folds'} for r in results],
        'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}),flush=True)
    return report


if __name__=='__main__':
    diagnose()
