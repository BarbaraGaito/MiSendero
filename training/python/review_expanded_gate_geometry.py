"""Inspect fitting-only conditional probability geometry before another model."""
import inspect
import json
from pathlib import Path
import joblib
import numpy as np
from sklearn.model_selection import GroupKFold
import fatigue_expanded_public_gate as study
from audit_fatigue_expanded_public_gate import raw_probability
from public_sources import digest

COLUMNS=['conditional_peak_probability','conditional_top_two_margin','conditional_normalized_entropy',
         'conditional_expected_delta_over_10','conditional_expected_absolute_delta_over_10','native_argmax_change_log_margin']


def geometry(probabilities):
    p=np.asarray(probabilities,float)
    assert p.ndim==2 and p.shape[1]==21 and np.isfinite(p).all() and (p>0).all()
    np.testing.assert_allclose(p.sum(axis=1),1.,atol=1e-12)
    nonzero=np.arange(21)!=10
    q=p[:,nonzero]/p[:,nonzero].sum(axis=1,keepdims=True)
    order=np.sort(q,axis=1)
    delta=(np.arange(-10,11)[nonzero])/10.
    peak=order[:,-1]
    result=np.column_stack([peak,peak-order[:,-2],-(q*np.log(q)).sum(axis=1)/np.log(20.),
        q@delta,q@np.abs(delta),np.log1p(-p[:,10])-np.log(p[:,10])+np.log(peak)])
    assert result.shape==(len(p),6) and np.isfinite(result).all()
    assert ((result[:,:3]>=-1e-12)&(result[:,:3]<=1.+1e-12)).all()
    return result


def profile(values):
    return {name:{'mean':float(values[:,n].mean()),'standard_deviation':float(values[:,n].std()),
        'quantiles_0_25_50_75_100':np.quantile(values[:,n],[0,.25,.5,.75,1]).tolist()}
        for n,name in enumerate(COLUMNS)}


def review():
    inputs=study.load_inputs()
    selected_path=study.DIRECTORY/'selection.json'
    audit_path=study.DOCS/'expanded-public-gate-verification.json'
    diagnostic_path=study.DOCS/'expanded-public-gate-diagnostic.json'
    selected,audit,diagnostic=[json.loads(p.read_text()) for p in (selected_path,audit_path,diagnostic_path)]
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selected_path)
    assert diagnostic['selection_sha256']==digest(selected_path) and diagnostic['verification_sha256']==digest(audit_path)
    correction=inspect.getsource(study.frozen.ChangeGateNetwork.correction)
    assert list(inspect.signature(study.frozen.ChangeGateNetwork.correction).parameters)==['self','history','context','offset']
    assert 'torch.sigmoid(offset)' in correction and 'self.encoder(history)' in correction
    train=inputs['train']; folds=list(GroupKFold(5).split(train,groups=train.group_key))
    profiles={}; hashes={}
    for member in ('core','cat'):
        candidate=next(c for c in study.plan()[8:] if c['member']==member and c['source_mode']=='native_only' and c['correction_penalty']==1.)
        fit_values=[]; val_values=[]; fold_profiles=[]
        oof=np.full((487,6),np.nan)
        for n,(fit,val) in enumerate(folds):
            cache=study.read_cache(inputs,member,n,fit,val)
            path=study.DIRECTORY/'folds'/f"{candidate['id']}-fold-{n}.joblib"
            assert digest(path)==audit['fold_artifact_hashes'][path.name]
            hashes[path.name]=digest(path)
            model=joblib.load(path)
            assert joblib.hash(model.base)==joblib.hash(cache['base'])
            fitting=geometry(np.exp(cache['fit_logits'].numpy()))
            validation=geometry(raw_probability(model.base,train.iloc[val][model.base.input_features]))
            fit_values.append(fitting);val_values.append(validation);oof[val]=validation
            scale=fitting.std(axis=0);scale[scale==0]=1.
            fold_profiles.append({'fold':n,'fitting_rows':len(fit),'validation_rows':len(val),
                'normalization_proposal_uses_inner_oof_fitting_only':True,
                'fitting_inner_oof_profile':profile(fitting),'outer_validation_profile':profile(validation),
                'validation_mean_in_fitting_standard_deviations':dict(zip(COLUMNS,((validation-fitting.mean(axis=0))/scale).mean(axis=0).tolist()))})
        assert np.isfinite(oof).all()
        changed=train.label.str.removeprefix('Borg ').to_numpy(int)!=train.prior_borg.to_numpy(int)
        assert int(changed.sum())==258 and int((~changed).sum())==229
        profiles[member]={'fitting_inner_oof_rows_across_folds':sum(map(len,fit_values)),
            'outer_validation_rows':487,'fitting_inner_oof_profile':profile(np.vstack(fit_values)),
            'outer_validation_profile':profile(np.vstack(val_values)),
            'actual_unchanged_oof_profile':profile(oof[~changed]),'actual_changed_oof_profile':profile(oof[changed]),
            'fold_profiles':fold_profiles}
    oracle={member:{k:v for k,v in value.items() if k not in ('cases','folds')}
            for member,value in diagnostic['frozen_nonzero_gate_oracle_upper_bounds'].items()}
    report={'review':'passed','review_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(selected_path),'verification_sha256':digest(audit_path),
        'diagnostic_sha256':digest(diagnostic_path),'native_gate_implementation_sha256':digest(Path(study.__file__)),
        'frozen_network_implementation_sha256':digest(Path(study.frozen.__file__)),
        'inspected_correction_method':correction,'current_correction_receives_only_total_nonzero_probability':True,
        'conditional_geometry_not_passed_to_current_corrector':True,'native_fitting_queries':487,
        'fitting_only':True,'test_labels_inspected':False,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
        'source_histories_physiology_or_labels_fabricated':False,'model_comparison_predeclared':False,
        'proposed_native_private_geometry':COLUMNS,'geometry_profiles':profiles,'reviewed_fold_artifact_hashes':hashes,
        'frozen_nonzero_gate_optimistic_upper_bounds_not_achieved_accuracy':oracle,
        'proposal':{'new_trainable_recipes':8,'inherited_controls':10,'total_recipes':18,
            'members':['core','cat'],'source_conditions':['native_only','expanded_sources'],
            'correction_penalties':[1.,10.],'new_joint_network_fits':40,'independent_joint_refits_required':40,
            'adapter':'zero_initialized6to8biasless_addition_to_existing_first_corrector_preactivation',
            'initialization':'Construct original network first,retain all original weights,then add zero geometry adapter. Match inactive-geometry controls before any comparison.',
            'normalization':'Fit native geometry statistics on inner-person OOF cached probabilities only. Query geometry comes from frozen native base prediction.',
            'source_inputs':'No native conditional-probability vector or native private context is invented for any source.',
            'unchanged':'3548real source fitting pairs,518reserved plus5gait people unreceived,shared3historyinputs/native20context,80epochs,seed42,AdamW.003/decay.1,original487/179,.65CVtestgate,exact Borg.'},
        'interpretation':'The perfect-choice bound exceeds80% on fitting participants but uses actual current truth and is not achieved accuracy. Source data corrected one CatBoost OOF case at penalty1;the best penalty10 stayed at baseline. Inspect conditional uncertainty/margin information currently discarded by the scalar corrector as a distinct native-private representation. Nonzero relative probabilities remain frozen;this review alone proves no predictive gain.'}
    path=study.DOCS/'expanded-public-gate-geometry-review.json'
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    status_path=study.DOCS/'current-research-status.json'
    status=json.loads(status_path.read_text())
    assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(61,1980)
    status['expanded_public_gate_geometry_review']={'document':path.name,'sha256':digest(path),'fitting_only':True,
        'model_comparison_predeclared':False,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}
    status['next_evidence_based_direction']=(
        'Study61 complete/audited24recipes(8controls/16new),80networks/refits,329distincttests;bestCV.637972 and retained108/179. '
        'Expanded source CatBoost penalty1corrected1/spoiled0vs matched legacy/native/total-mass controls but spoiled2vs global. '
        'Penalty10preserved global predictions.16fitNLL reductions/7validationNLL reductions. Fitting-only perfect-choice '
        'gate bounds are.885318MLP/.883594CatBoost;these use truth and are not achieved metrics. The scalar corrector '
        'receives only total change probability,not frozen conditional peak,margin,entropy or expected delta. '
        'Six deterministic native-private probability-geometry inputs have now been profiled using inner-OOF fitting '
        'and outer-person validation predictions with no new fits/test. Predeclare a distinct zero-initialized6to8adapter '
        'added to the existing corrector first preactivation,while matching all original initial weights and inactive '
        'adapter controls. Proposed18recipes:10inherited controls+8new(two bases*source0/expanded*penalty1/10),40networks '
        'and40independent refits. Normalize geometry only on inner-OOF fit probabilities;never invent source geometry. '
        'This comparison is reviewed but not yet predeclared or fitted. Keep real-public policy,original487/179, '
        '.65CVtestgate and144/179exact reloaded matches. Goal remains active.')
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'review':'passed','geometry_features':6,'native_fitting_queries':487,
        'reviewed_frozen_models':len(hashes),'oracle_bounds_not_achieved_metrics':{m:a['mean_fold_upper_accuracy'] for m,a in oracle.items()},
        'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,'model_comparison_predeclared':False}),flush=True)
    return report


if __name__=='__main__':
    review()
