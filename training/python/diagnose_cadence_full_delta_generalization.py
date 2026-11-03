"""Compare actual fit/validation NLL and paired OOF errors of full residuals."""
import json
from pathlib import Path
import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold
import fatigue_cadence_full_delta as study
from public_sources import digest


def measure(model,frame,offsets):
    target = frame.label.str.removeprefix('Borg ').to_numpy(int)-frame.prior_borg.to_numpy(int)+10
    with torch.no_grad():
        correction = model.network.correction(model.history_transform(frame),model.context_transform(frame),offsets)
        z = offsets+correction
        true = torch.tensor(target,dtype=torch.long)
        before = torch.nn.functional.cross_entropy(offsets,true)
        after = torch.nn.functional.cross_entropy(z,true)
    return {'original_delta_nll':float(before),'corrected_delta_nll':float(after),
        'residual_rms':float(correction.square().mean().sqrt()),
        'residual_row_mean_max':float(correction.mean(dim=1).abs().max()),
        'corrector_output_parameters':sum(p.numel() for p in model.network.corrector[-1].parameters())}


def diagnose():
    inputs = study.load_inputs()
    train = inputs['train']
    path = study.DIRECTORY/'selection.json'
    selected = json.loads(path.read_text())
    audit_path = study.DOCS/'cadence-full-delta-verification.json'
    audit = json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(path)
    rows = {row['candidate']['id']:row for row in selected['results']}
    truth = train.label.to_numpy()
    metrics = {}
    for c in study.plan()[6:]:
        folds = []
        for n,(fit,val) in enumerate(GroupKFold(5).split(train,groups=train.group_key)):
            fitting,validation = train.iloc[fit],train.iloc[val]
            artifact = study.DIRECTORY/'folds'/f"{c['id']}-fold-{n}.joblib"
            assert audit['fold_artifact_hashes'][artifact.name]==digest(artifact)
            model = joblib.load(artifact)
            cache = study.read_cache(inputs,c['member'],n,fit,val)
            folds.append({'fold':n,'fit_with_actual_inner_person_offsets':measure(model,fitting,cache['fit_logits']),
                'validation':measure(model,validation,model.base.logits(validation[model.input_features]))})
        metrics[c['id']] = {'member':c['member'],'source_weight':c['auxiliary_weight'],'penalty':c['correction_penalty'],
            'exact_native_cv_accuracy':rows[c['id']]['accuracy_mean'],'folds':folds,
            'mean_fit_original_nll':float(np.mean([r['fit_with_actual_inner_person_offsets']['original_delta_nll'] for r in folds])),
            'mean_fit_corrected_nll':float(np.mean([r['fit_with_actual_inner_person_offsets']['corrected_delta_nll'] for r in folds])),
            'mean_validation_original_nll':float(np.mean([r['validation']['original_delta_nll'] for r in folds])),
            'mean_validation_corrected_nll':float(np.mean([r['validation']['corrected_delta_nll'] for r in folds]))}
    paired = {}
    for member,global_key,scalar_key in [('core',0,3),('cat',1,5)]:
        best = max([r for r in selected['results'] if r['candidate'].get('member')==member and r['candidate'].get('auxiliary_weight',0)>0],key=lambda r:r['accuracy_mean'])
        c = best['candidate']
        zero = next(r for r in selected['results'] if r['candidate'].get('member')==member and r['candidate'].get('auxiliary_weight')==0 and r['candidate']['correction_penalty']==c['correction_penalty'])
        a = np.asarray(best['oof_predictions'])==truth
        paired[member] = {'best_source_candidate':c['id'],'best_source_correct':int(a.sum())}
        for name,other in [('matched_zero_source',zero),('global',rows[f'cadence-full-delta-{global_key:03d}']),
                           ('previous_scalar_source',rows[f'cadence-full-delta-{scalar_key:03d}'])]:
            b = np.asarray(other['oof_predictions'])==truth
            paired[member][name] = {'other_correct':int(b.sum()),'corrected':int((a&~b).sum()),'spoiled':int((~a&b).sum())}
    trends = []
    for member in ('core','cat'):
        for weight in (0.,.1):
            pair = {c['correction_penalty']:metrics[c['id']] for c in study.plan()[6:] if c['member']==member and c['auxiliary_weight']==weight}
            trends.append({'member':member,'source_weight':weight,
                'penalty1_outperformed_point1':pair[1.]['exact_native_cv_accuracy']>pair[.1]['exact_native_cv_accuracy']})
    report = {'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(path),'verification_sha256':digest(audit_path),'original_fitting_cases':487,
        'original_fitting_people':28,'metrics':metrics,'paired_oof_comparisons':paired,'regularization_trends':trends,
        'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,'test_labels_inspected':False,'synthetic_rows':0,
        'interpretation':'All8new recipes had the full21class native objective. Compare within-fit actual '
            'inner-person offsets with outer-person validation separately. Greater output flexibility is '
            'not itself evidence of improvement. Any stronger regularization or lower-dimensional '
            'ordered residual must be reviewed and predeclared as another comparison,not selected on test.'}
    output = study.DOCS/'cadence-full-delta-generalization-diagnostic.json'
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='metrics'}),flush=True)
    print(json.dumps({key:{k:v for k,v in value.items() if k!='folds'} for key,value in metrics.items()}),flush=True)
    return report


if __name__=='__main__':
    diagnose()
