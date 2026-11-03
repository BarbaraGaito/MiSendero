"""Fitting-only paired errors and gate generalization for frozen study61."""
import json
from pathlib import Path
import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold
import fatigue_expanded_public_gate as study
from audit_fatigue_expanded_public_gate import independent_prediction
from public_sources import digest


def compact(row):
    return {k:row[k] for k in ('candidate','accuracy_mean','fold_accuracy','pooled_oof_accuracy')}


def paired(a,b,truth):
    pa,pb=np.asarray(a['oof_predictions']),np.asarray(b['oof_predictions'])
    return {'candidate':a['candidate']['id'],'comparison':b['candidate']['id'],
        'candidate_cv':a['accuracy_mean'],'comparison_cv':b['accuracy_mean'],
        'corrected':int(np.sum((pa==truth)&(pb!=truth))),
        'spoiled':int(np.sum((pa!=truth)&(pb==truth))),
        'prediction_disagreements':int(np.sum(pa!=pb))}


def losses(probabilities,prior,truth):
    delta=truth-prior+10
    exact=-np.log(probabilities[np.arange(len(delta)),delta]).mean()
    changed=(truth!=prior)
    p=np.where(changed,1-probabilities[:,10],probabilities[:,10])
    return {'native_exact_delta_nll':float(exact),'native_change_binary_nll':float(-np.log(p).mean())}


def validate():
    inputs=study.load_inputs()
    selected_path=study.DIRECTORY/'selection.json'
    audit_path=study.DOCS/'expanded-public-gate-verification.json'
    selected=json.loads(selected_path.read_text())
    audit=json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selected_path)
    assert selected['status']=='complete' and len(selected['results'])==24
    train=inputs['train']; truth=train.label.to_numpy()
    global_control=max((r for r in selected['results'] if r['candidate']['algorithm']=='previous_real_control'),key=lambda r:r['accuracy_mean'])
    comparisons={}; all_comparisons={}; rows={}; endpoints=[]; oracle={}
    folds=list(GroupKFold(5).split(train,groups=train.group_key))
    for member in ('core','cat'):
        candidates=[r for r in selected['results'] if r['candidate'].get('member')==member]
        best=max((r for r in candidates if r['candidate']['source_mode']=='expanded_sources'),key=lambda r:r['accuracy_mean'])
        penalty=best['candidate']['correction_penalty']
        controls={mode:next(r for r in candidates if r['candidate']['source_mode']==mode and r['candidate']['correction_penalty']==penalty)
                  for mode in ('native_only','legacy_sources','matched_total_weight')}
        rows[member]={'best_expanded':compact(best),'matched_controls':{m:compact(r) for m,r in controls.items()}}
        oracle[member]={'folds':[],'cases':[],'uses_current_truth_only_to_bound_model_family':True,
                       'oracle_predictions_not_used_for_selection_or_test':True}
        comparisons[member]={mode:paired(best,row,truth) for mode,row in {**controls,'global':global_control}.items()}
        for expanded in (r for r in candidates if r['candidate']['source_mode']=='expanded_sources'):
            matching={mode:next(r for r in candidates if r['candidate']['source_mode']==mode
                and r['candidate']['correction_penalty']==expanded['candidate']['correction_penalty'])
                for mode in ('native_only','legacy_sources','matched_total_weight')}
            all_comparisons[expanded['candidate']['id']]={mode:paired(expanded,r,truth)
                for mode,r in {**matching,'global':global_control}.items()}
        for row in candidates:
            c=row['candidate']
            for n,(fit,val) in enumerate(folds):
                fitting,validation=train.iloc[fit],train.iloc[val]
                model=joblib.load(study.DIRECTORY/'folds'/f"{c['id']}-fold-{n}.joblib")
                cache=study.read_cache(inputs,member,n,fit,val)
                base=np.exp(cache['fit_logits'].numpy())
                with torch.no_grad():
                    correction=model.network.correction(model.history_transform(fitting),model.context_transform(fitting),study.gate_logit(torch.tensor(base))).numpy()
                z=np.log(1-base[:,10])-np.log(base[:,10])+correction
                changed=1/(1+np.exp(-z))
                conditional=base.copy();conditional[:,10]=0;conditional/=conditional.sum(axis=1,keepdims=True)
                corrected=changed[:,None]*conditional;corrected[:,10]=1-changed
                _,val_prob,val_base=independent_prediction(model,validation[model.input_features])
                fit_prior=fitting.prior_borg.to_numpy(int);fit_truth=fitting.label.str.removeprefix('Borg ').to_numpy(int)
                val_prior=validation.prior_borg.to_numpy(int);val_truth=validation.label.str.removeprefix('Borg ').to_numpy(int)
                if row is candidates[0]:
                    priority=model.base.priority[model.base.priority!=10]
                    nonzero=priority[val_base[:,priority].argmax(axis=1)]-10
                    other=np.clip(val_prior+nonzero,0,10)
                    feasible=(val_truth==val_prior)|(val_truth==other)
                    oracle[member]['folds'].append({'fold':n,'cases':len(val),'feasible':int(feasible.sum()),'upper_accuracy':float(feasible.mean())})
                    oracle[member]['cases'].extend({'row_key':key,'actual':int(target),'prior_prediction':int(prior),
                        'frozen_nonzero_prediction':int(changed),'any_scalar_gate_can_predict_actual':bool(possible)}
                        for key,target,prior,changed,possible in zip(validation.row_key,val_truth,val_prior,other,feasible))
                fit0,fit1=losses(base,fit_prior,fit_truth),losses(corrected,fit_prior,fit_truth)
                val0,val1=losses(val_base,val_prior,val_truth),losses(val_prob,val_prior,val_truth)
                endpoints.append({'candidate_id':c['id'],'member':member,'mode':c['source_mode'],'penalty':c['correction_penalty'],'fold':n,
                    'fitting_before':fit0,'fitting_after':fit1,'validation_before':val0,'validation_after':val1,
                    'actual_new_gait_gradient':model.training_summary['initial_new_gait_only_encoder_gradient_l2']})
    aggregate=[]
    for c in study.plan()[8:]:
        part=[r for r in endpoints if r['candidate_id']==c['id']]
        means={split:{key:float(np.mean([r[split][key] for r in part])) for key in part[0][split]}
               for split in ('fitting_before','fitting_after','validation_before','validation_after')}
        aggregate.append({'candidate':c,**means,
            'fit_nll_decreased':means['fitting_after']['native_exact_delta_nll']<means['fitting_before']['native_exact_delta_nll'],
            'validation_nll_decreased':means['validation_after']['native_exact_delta_nll']<means['validation_before']['native_exact_delta_nll']})
    for member,part in oracle.items():
        assert len(part['cases'])==487 and len({r['row_key'] for r in part['cases']})==487
        part['pooled_upper_accuracy']=sum(r['any_scalar_gate_can_predict_actual'] for r in part['cases'])/487
        part['mean_fold_upper_accuracy']=float(np.mean([r['upper_accuracy'] for r in part['folds']]))
        part['unreachable_cases']=sum(not r['any_scalar_gate_can_predict_actual'] for r in part['cases'])
    report={'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(selected_path),'verification_sha256':digest(audit_path),
        'fitting_queries':487,'test_labels_inspected':False,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
        'global_control':compact(global_control),'best_expanded_and_matched_controls':rows,
        'paired_oof_comparisons':comparisons,'all_expanded_recipe_paired_comparisons':all_comparisons,
        'all_16_gate_loss_comparisons':aggregate,'all_80_fold_loss_comparisons':endpoints,
        'frozen_nonzero_gate_oracle_upper_bounds':oracle,
        'native_fit_nll_reduced_recipes':sum(r['fit_nll_decreased'] for r in aggregate),
        'native_validation_nll_reduced_recipes':sum(r['validation_nll_decreased'] for r in aggregate),
        'source_current_values_used_only_as_targets':True,'source_instruments_not_converted_to_native_targets':True}
    (study.DOCS/'expanded-public-gate-diagnostic.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('diagnostic','paired_oof_comparisons','native_fit_nll_reduced_recipes','native_validation_nll_reduced_recipes')}),flush=True)
    return report


if __name__=='__main__':
    validate()
