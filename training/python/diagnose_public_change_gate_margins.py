"""Read-only fitting-participant gate adjustments and decision-boundary margins."""
import json
from pathlib import Path
import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold
import fatigue_public_change_gate as study
from public_sources import digest


def stats(values):
    values = np.asarray(values,float)
    return {'minimum':float(values.min()),'median':float(np.median(values)),
        'p90':float(np.quantile(values,.9)),'maximum':float(values.max()),'mean':float(values.mean())}


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
        if c['algorithm']!='joint_public_binary_change_gate':
            continue
        adjustments,margins,ratios,base_labels,final_labels,possible,penalty_ratios,loss_changes = [],[],[],[],[],[],[],[]
        for n,(fit,val) in enumerate(folds):
            artifact = study.DIRECTORY/'folds'/f"{c['id']}-fold-{n}.joblib"
            assert digest(artifact)==row['folds'][n]['model_sha256']
            hashes[artifact.name] = digest(artifact)
            model = joblib.load(artifact)
            validation = train.iloc[val]
            query = validation[model.input_features]
            with torch.no_grad():
                base = model.base.logits(query).exp()
                offset = study.gate_logit(base)
                correction = model.network.correction(model.history_transform(query),model.context_transform(query),offset).numpy()
            p = base.numpy()
            nonzero_order = model.base.priority[model.base.priority!=10]
            nonzero_class = nonzero_order[p[:,nonzero_order].argmax(axis=1)]
            top_nonzero_q = p[np.arange(len(p)),nonzero_class]/(1-p[:,10])
            # P(change)*q_max = 1-P(change) at logit(change)=-log(q_max).
            required = -np.log(top_nonzero_q)-offset.numpy()
            base_predicted = model.base.predict(query)
            predicted = model.predict(query)
            truth = validation.label.to_numpy()
            zero_borg = [f'Borg {int(v)}' for v in query.prior_borg]
            nonzero_borg = [f'Borg {int(v)}' for v in np.clip(query.prior_borg.to_numpy(int)+nonzero_class-10,0,10)]
            possible.extend((np.asarray(zero_borg)==truth)|(np.asarray(nonzero_borg)==truth))
            adjustments.extend(correction)
            margins.extend(required)
            ratios.extend(np.abs(correction)/np.maximum(np.abs(required),1e-15))
            base_labels.extend(base_predicted)
            final_labels.extend(predicted)
            cache = study.read_cache(inputs,c['member'],n,fit,val)
            fitting = train.iloc[fit]
            with torch.no_grad():
                fit_offset = study.gate_logit(cache['fit_logits'].exp())
                fit_correction = model.network.correction(model.history_transform(fitting),model.context_transform(fitting),fit_offset).numpy()
                corrected_change = torch.sigmoid(fit_offset+torch.tensor(fit_correction)).numpy()
            binary = fitting.label.str.removeprefix('Borg ').to_numpy(int)!=fitting.prior_borg.to_numpy(int)
            native_derivative = corrected_change-binary.astype(float)
            penalty_derivative = 2*c['correction_penalty']*fit_correction
            penalty_ratios.append(float(np.linalg.norm(penalty_derivative)/np.linalg.norm(native_derivative)))
            loss_changes.append(model.loss_endpoints[-1]['native_binary_loss']-model.loss_endpoints[0]['native_binary_loss'])
        correction,required = np.asarray(adjustments),np.asarray(margins)
        crossed = ((required>0)&(correction>=required))|((required<0)&(correction<=required))
        assert len(correction)==487
        results.append({'candidate':c,'native_cv_accuracy':row['accuracy_mean'],
            'absolute_logit_correction':stats(np.abs(correction)),'absolute_gate_boundary_margin':stats(np.abs(required)),
            'absolute_correction_over_required_margin':stats(ratios),
            'gate_boundaries_crossed':int(crossed.sum()),'final_native_borg_predictions_changed':int(np.sum(np.asarray(base_labels)!=np.asarray(final_labels))),
            'native_fitting_loss_end_minus_start_mean':float(np.mean(loss_changes)),
            'native_penalty_over_likelihood_output_derivative_norm_mean':float(np.mean(penalty_ratios)),
            'optimistic_fitting_only_correct_if_oracle_chose_zero_or_top_nonzero':int(np.sum(possible)),
            'optimistic_fitting_only_gate_choice_ceiling':float(np.mean(possible))})
    assert len(results)==6 and len(hashes)==30
    assert all(digest(study.DIRECTORY/'folds'/name)==value for name,value in hashes.items())
    report = {'diagnostic':'passed','diagnostic_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(path),'fold_model_hashes':hashes,'original_fitting_queries':487,'original_fitting_people':28,
        'results':results,'new_predictive_estimator_fits':0,'new_preprocessor_fits':0,
        'new_test_predictions_computed':0,'test_labels_inspected':False,'synthetic_rows':0,
        'new_hyperparameters_selected':0,
        'interpretation':'Gate logit adjustments are compared with the exact mathematical boundary between '
            'the original zero delta and highest-probability nonzero delta. Each source-trained model '
            'still preserves relative nonzero probabilities. Small adjustment/margin ratios can explain '
            'unchanged decisions even with verified learning and nonzero source gradients. The output '
            'derivative ratio describes the saved fitting objective,not a proof that a different penalty '
            'will improve validation. Oracle gate-choice ceilings use actual fitting-participant labels '
            'for a hypothetical bound only;they are not achieved predictions or the179case test result.'}
    (study.DOCS/'public-change-gate-margin-diagnostic.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'diagnostic':'passed','results':results,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}),flush=True)
    return report


if __name__=='__main__':
    diagnose()
