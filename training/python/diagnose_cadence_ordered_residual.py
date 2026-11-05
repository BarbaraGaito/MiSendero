"""Fitting-only ordered residual NLL and matched-control OOF attribution."""
import json
from pathlib import Path
import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold
import fatigue_cadence_ordered_residual as study
from public_sources import digest


def measure(model,frame,offsets):
    target = frame.label.str.removeprefix('Borg ').to_numpy(int)-frame.prior_borg.to_numpy(int)+10
    with torch.no_grad():
        coefficients = model.network.coefficients(model.history_transform(frame),model.context_transform(frame),offsets)
        correction = model.network.expand(coefficients)
        target = torch.tensor(target,dtype=torch.long)
        before = torch.nn.functional.cross_entropy(offsets,target)
        after = torch.nn.functional.cross_entropy(offsets+correction,target)
    return {'original_delta_nll':float(before),'corrected_delta_nll':float(after),
        'coefficient_mean':coefficients.mean(dim=0).tolist(),'coefficient_std':coefficients.std(dim=0,unbiased=False).tolist(),
        'expanded_residual_rms':float(correction.square().mean().sqrt()),'output_layer_parameters':27}


def diagnose():
    inputs = study.load_inputs()
    train = inputs['train']
    selected_path = study.DIRECTORY/'selection.json'
    selected = json.loads(selected_path.read_text())
    audit_path = study.DOCS/'cadence-ordered-residual-verification.json'
    audit = json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selected_path)
    rows = {row['candidate']['id']:row for row in selected['results']}
    truth = train.label.to_numpy()
    metrics = {}
    full_rows = inputs['control_selections']['full']['results']
    for c in study.plan()[18:]:
        folds = []
        for n,(fit,val) in enumerate(GroupKFold(5).split(train,groups=train.group_key)):
            fitting,validation = train.iloc[fit],train.iloc[val]
            artifact = study.DIRECTORY/'folds'/f"{c['id']}-fold-{n}.joblib"
            assert audit['fold_artifact_hashes'][artifact.name]==digest(artifact)
            model = joblib.load(artifact)
            cache = study.read_cache(inputs,c['member'],n,fit,val)
            folds.append({'fold':n,'fit_with_inner_person_offsets':measure(model,fitting,cache['fit_logits']),
                'validation':measure(model,validation,model.base.logits(validation[model.input_features]))})
        full = next(row for row in full_rows if all(row['candidate'].get(k)==c[k] for k in ('member','auxiliary_weight','correction_penalty')))
        a,b = np.asarray(rows[c['id']]['oof_predictions'])==truth,np.asarray(full['oof_predictions'])==truth
        metrics[c['id']] = {'member':c['member'],'source_weight':c['auxiliary_weight'],'penalty':c['correction_penalty'],
            'exact_native_cv_accuracy':rows[c['id']]['accuracy_mean'],'same_penalty_full_residual_cv':full['accuracy_mean'],
            'same_penalty_full_residual_corrected':int((a&~b).sum()),'same_penalty_full_residual_spoiled':int((~a&b).sum()),
            'folds':folds,
            'mean_fit_original_nll':float(np.mean([r['fit_with_inner_person_offsets']['original_delta_nll'] for r in folds])),
            'mean_fit_corrected_nll':float(np.mean([r['fit_with_inner_person_offsets']['corrected_delta_nll'] for r in folds])),
            'mean_validation_original_nll':float(np.mean([r['validation']['original_delta_nll'] for r in folds])),
            'mean_validation_corrected_nll':float(np.mean([r['validation']['corrected_delta_nll'] for r in folds]))}
    paired = {}
    for member,global_key,strong_key,scalar_key in [('core',0,3,15),('cat',1,5,17)]:
        best = max([row for row in selected['results'] if row['candidate'].get('member')==member and row['candidate'].get('auxiliary_weight',0)>0],key=lambda row:row['accuracy_mean'])
        c = best['candidate']
        zero = next(row for row in selected['results'] if row['candidate'].get('member')==member and row['candidate'].get('auxiliary_weight')==0 and row['candidate']['correction_penalty']==c['correction_penalty'])
        full = next(row for row in full_rows if all(row['candidate'].get(k)==c[k] for k in ('member','auxiliary_weight','correction_penalty')))
        a = np.asarray(best['oof_predictions'])==truth
        paired[member] = {'best_source_candidate':c['id'],'best_source_correct':int(a.sum())}
        comparisons = [('matched_zero_source',zero),('same_penalty_full_source',full),
            ('global',rows[f'ordered-residual-{global_key:03d}']),
            ('previous_strong_source',rows[f'ordered-residual-{strong_key:03d}']),
            ('previous_scalar_source',rows[f'ordered-residual-{scalar_key:03d}'])]
        for name,other in comparisons:
            b = np.asarray(other['oof_predictions'])==truth
            paired[member][name] = {'other_correct':int(b.sum()),'corrected':int((a&~b).sum()),'spoiled':int((~a&b).sum())}
    report = {'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(selected_path),'verification_sha256':digest(audit_path),
        'original_fitting_cases':487,'original_fitting_people':28,'metrics':metrics,'paired_oof_comparisons':paired,
        'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,'test_labels_inspected':False,'synthetic_rows':0,
        'interpretation':'The smaller output basis and exact matching shared initialization were verified. '
            'A reduction in parameter count does not establish better generalization. All comparisons '
            'use original fitting-person OOF predictions;no native test observations are used to choose '
            'a model. Keep paired source effects separate from performance against the global control.'}
    path = study.DOCS/'cadence-ordered-residual-diagnostic.json'
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='metrics'}),flush=True)
    print(json.dumps({key:{k:v for k,v in value.items() if k!='folds'} for key,value in metrics.items()}),flush=True)
    return report


if __name__=='__main__':
    diagnose()
