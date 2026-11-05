"""Check whether a distinct observed-change factorization remains untested."""
import json
from pathlib import Path
import numpy as np
from sklearn.model_selection import GroupKFold
from fatigue_dynamics import load_inputs
from public_sources import digest,ROOT


def review():
    _,train,_,_,_ = load_inputs()
    assert len(train)==487 and train.group_key.nunique()==28
    delta = train.label.str.removeprefix('Borg ').to_numpy(int)-train.prior_borg.to_numpy(int)
    references = {
        'fatigue_ordinal.py':'Continuous regression on original Borg, rounded only at prediction; no binary observed-change classifier.',
        'fatigue_dynamics_regression.py':'Continuous original-Borg/delta regressors; no conditional nonzero class estimator.',
        'fatigue_spectral_correction.py':'Multi-class residual correction around an inner-person-fitted base prediction; its zero means correct base prediction, not unchanged observed Borg.',
        'fatigue_catboost.py':'Flat original-Borg/delta multiclass CatBoost; no separately fitted observed-change gate.',
    }
    evidence = {}
    for name,interpretation in references.items():
        path = Path(__file__).with_name(name)
        code = path.read_text()
        if name=='fatigue_spectral_correction.py':
            assert 'context_fit[:, 0].astype(int)' in code and 'target = fitting[' in code
        elif name=='fatigue_dynamics_regression.py':
            assert 'target = target - frame[' in code and 'self.model.fit(frame[c[' in code
        elif name=='fatigue_ordinal.py':
            assert 'MLPRegressor' in code and 'RandomForestRegressor' in code
        else:
            assert 'MultiClass' in code
        evidence[name] = {'sha256':digest(path),'review':interpretation}
    folds = []
    for number,(fit,val) in enumerate(GroupKFold(5).split(train,groups=train.group_key)):
        assert set(train.iloc[fit].group_key).isdisjoint(train.iloc[val].group_key)
        change = delta[fit]!=0
        assert change.any() and (~change).any()
        folds.append({'fold':number,'fitting_rows':len(fit),'fitting_unchanged':int((~change).sum()),
            'fitting_nonzero_change':int(change.sum()),'actual_nonzero_delta_classes':sorted(set(delta[fit][change].tolist())),
            'validation_rows':len(val),'fit_row_keys':train.iloc[fit].row_key.tolist()})
    contexts = {}
    for value in sorted(train.prior_in_current_task.unique().tolist()):
        mask = train.prior_in_current_task.eq(value).to_numpy()
        contexts[str(value)] = {'actual_queries':int(mask.sum()),'unchanged':int((mask&(delta==0)).sum()),
            'nonzero_change':int((mask&(delta!=0)).sum())}
    report = {'review':'passed','review_code_sha256':digest(Path(__file__)),
        'native_fitting_queries':487,'native_fitting_people':28,'observed_unchanged_queries':int((delta==0).sum()),
        'observed_nonzero_queries':int((delta!=0).sum()),'observed_negative_changes':int((delta<0).sum()),
        'fitting_context_counts':contexts,'outer_fitting_folds':folds,'prior_code_review':evidence,
        'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,'test_labels_inspected':False,
        'synthetic_rows':0,'next_comparison_predeclared':False,
        'interpretation':'A separately fitted observed-change gate P(delta!=0|x) and magnitude '
            'classifier P(delta=k|delta!=0,x) would factor the exact original delta distribution. '
            'Binary labels are deterministic descriptions of two actual reports; they are not new observations '
            'or assumed-zero labels. Nonzero magnitude training would use only the actually observed nonzero '
            'subset of the outer fitting people. Preserve both negative changes and all original cases. '
            'Prior continuous regressors and residual-zero options do not implement this factorization. '
            'No accuracy improvement is demonstrated by this review; a bounded predeclared comparison '
            'with matched flat-class controls is required before fitting.'}
    docs = ROOT/'docs/fatigue-80-2026-10-25'
    (docs/'native-change-factorization-review.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='outer_fitting_folds'}),flush=True)
    return report


if __name__=='__main__':
    review()
