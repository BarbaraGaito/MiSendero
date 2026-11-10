"""Freeze the original exact-Borg factorization comparison before fitting."""
import json
from pathlib import Path
import fatigue_observed_change_factorization as study
from public_sources import digest

proof = json.loads(study.PARENT_AUDIT.read_text())
review = json.loads(study.REVIEW.read_text())
assert proof['verification']=='passed' and review['review']=='passed'
assert (review['observed_unchanged_queries'],review['observed_nonzero_queries'],review['observed_negative_changes'])==(229,258,2)
report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'factorization_review_sha256':digest(study.REVIEW),
    'original_native_fitting_cases':487,'original_native_test_cases':179,'new_candidate_fold_fits':40,
    'new_stage_estimator_fits':60,'workers':2,'synthetic_rows':0,'native_target_coarsening':False,
    'physiology_features_added_in_matched_feature_set':study.PHYSIOLOGY,
    'minimum_cv_for_new_test_evaluation':.65,'test_used_for_selection':False,
    'independent_refit_policy':'Best factorized recipe per member and its matched flat control,plus sole CVwinner if new and not already included; all40fold artifacts and10OOFmetrics independently recomputed.',
    'rationale':'The fitting-only review identified229actual unchanged transitions and258nonzero transitions, '
        'including2negative. Previous continuous regressors and residual-zero options did not separately '
        'fit observed-change probability and conditional exact nonzero magnitude. Compare that factorization '
        'with matched flat-class models,using the exact same family hyperparameters/history features, '
        'and one matched extension of3already causal HRfeatures. Both submodels see fitting people only; '
        'the conditional model sees only their actually observed nonzero transitions. Binary labels describe '
        'real pairs,not assumed zeros or extra observations. Final predictions remain exact Borg0-10 '
        'for every original case. No bandwidth,source-weight,epoch or rate/budget grid repetition.'}
assert len(study.plan())==10
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':10,'new_candidate_fold_fits':40,'new_stage_estimator_fits':60,
    'predictive_fitting_started':False}),flush=True)
