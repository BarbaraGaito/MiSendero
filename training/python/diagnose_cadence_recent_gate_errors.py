"""Fitting-person error attribution using frozen OOF artifacts only."""
import json
from pathlib import Path
import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold
import fatigue_cadence_recent_gate as study
from public_sources import digest


def gate_metrics(model,frame,probabilities):
    p0 = probabilities[:,10]
    offset = np.log1p(-p0)-np.log(p0)
    with torch.no_grad():
        correction = model.network.correction(model.history_transform(frame),model.context_transform(frame),
            torch.tensor(offset,dtype=torch.float64)).numpy()
    z = offset+correction
    truth = frame.label.str.removeprefix('Borg ').to_numpy(int)!=frame.prior_borg.to_numpy(int)
    return {'gate_binary_accuracy':float(np.mean((z>0)==truth)),
        'gate_bce':float(np.mean(np.logaddexp(0,z)-truth*z)),
        'uncorrected_gate_bce':float(np.mean(np.logaddexp(0,offset)-truth*offset)),
        'median_absolute_logit_correction':float(np.median(np.abs(correction)))}


def diagnose():
    inputs = study.load_inputs()
    train = inputs['train']
    selected_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selected_path.read_text())
    audit_path = study.DOCS/'cadence-recent-gate-verification.json'
    audit = json.loads(audit_path.read_text())
    assert selected['status']=='complete' and audit['verification']=='passed'
    assert audit['selection_sha256']==digest(selected_path) and audit['all_20_fold_artifacts_recomputed']
    rows = {row['candidate']['id']:row for row in selected['results']}
    actual = train.label.to_numpy()
    paired = {}
    for member,global_id,old_zero,old_source,new_zero,new_source in (
            ('core',0,2,3,6,7),('cat',1,4,5,8,9)):
        correctness = {name:np.asarray(rows[f'recent-gate-{key:03d}']['oof_predictions'])==actual
            for name,key in [('global',global_id),('old_zero',old_zero),('old_source',old_source),
                             ('new_zero',new_zero),('new_source',new_source)]}
        paired[member] = {'correct_counts':{key:int(value.sum()) for key,value in correctness.items()}}
        for name,a,b in [('new_source_vs_new_zero','new_source','new_zero'),
                         ('new_zero_vs_old_zero','new_zero','old_zero'),
                         ('new_source_vs_old_source','new_source','old_source'),
                         ('new_source_vs_global','new_source','global')]:
            paired[member][name] = {'corrected':int((correctness[a]&~correctness[b]).sum()),
                'spoiled':int((~correctness[a]&correctness[b]).sum())}
    metrics = {}
    folds = list(GroupKFold(5).split(train,groups=train.group_key))
    for candidate in study.plan()[6:]:
        per_fold = []
        for n,(fit,val) in enumerate(folds):
            fitting,validation = train.iloc[fit],train.iloc[val]
            path = study.DIRECTORY/'folds'/f"{candidate['id']}-fold-{n}.joblib"
            assert audit['fold_artifact_hashes'][path.name]==digest(path)
            model = joblib.load(path)
            cache = study.read_cache(inputs,candidate['member'],n,fit,val)
            # Fit-side offsets are the genuine inner-person OOF offsets used by the objective.
            fit_probability = np.exp(cache['fit_logits'].numpy())
            validation_probability = np.exp(model.base.logits(validation[model.input_features]).numpy())
            per_fold.append({'fold':n,'fitting_inner_offset_metrics':gate_metrics(model,fitting,fit_probability),
                'validation_metrics':gate_metrics(model,validation,validation_probability)})
        metrics[candidate['id']] = {'member':candidate['member'],'source_weight':candidate['auxiliary_weight'],
            'exact_native_cv_accuracy':rows[candidate['id']]['accuracy_mean'],'folds':per_fold,
            'mean_fitting_gate_bce':float(np.mean([r['fitting_inner_offset_metrics']['gate_bce'] for r in per_fold])),
            'mean_validation_gate_bce':float(np.mean([r['validation_metrics']['gate_bce'] for r in per_fold])),
            'mean_uncorrected_validation_gate_bce':float(np.mean([r['validation_metrics']['uncorrected_gate_bce'] for r in per_fold]))}
    report = {'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(selected_path),'verification_sha256':digest(audit_path),
        'original_fitting_queries':487,'original_fitting_people':28,'paired_oof_comparisons':paired,
        'gate_metrics':metrics,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
        'test_labels_inspected':False,'synthetic_rows':0,
        'interpretation':'Recent private native physiology did not beat the global control. '
            'Exact Borg scores and change-gate component losses are separate quantities. '
            'Fit-side metrics use the actual inner-person OOF offsets used in training. '
            'A lower fitting BCE alone is not evidence of improved generalization.'}
    path = study.DOCS/'cadence-recent-gate-error-diagnostic.json'
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='gate_metrics'}),flush=True)
    print(json.dumps({key:{k:v for k,v in value.items() if k!='folds'} for key,value in metrics.items()}),flush=True)
    return report


if __name__=='__main__':
    diagnose()
