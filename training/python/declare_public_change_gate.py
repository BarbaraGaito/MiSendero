"""Freeze four-source observed-change gate transfer before predictive fitting."""
import json
from pathlib import Path
import fatigue_public_change_gate as study
from public_sources import digest

proof = json.loads(study.PARENT_AUDIT.read_text())
review = json.loads(study.REVIEW.read_text())
assert proof['verification']=='passed' and review['review']=='passed'
assert review['source_domains']['sts']['observed_change_classes']==[1]
report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'source_change_review_sha256':digest(study.REVIEW),
    'native_stage_diagnostic_sha256':digest(study.DIAGNOSTIC),'source_fitting_pairs':2287,'source_counts':study.COUNTS,
    'excluded_single_class_sts_pairs':49,'source_reserved_pairs_not_fitted':312,'original_native_fit_cases':487,
    'original_native_test_cases':179,'new_joint_network_fits':30,'new_native_base_fits_for_selection':0,
    'minimum_cv_for_new_test_evaluation':.65,'test_used_for_selection':False,'synthetic_rows':0,
    'independent_refit_policy':'Best positive-source recipe per member plus its matching zero-source control in all5personfolds;verify all30saved fold artifacts and all10OOFmetrics.',
    'rationale':'Study53factorization did not beat the flat native controls. Its fitting-only diagnostic '
        'identified native change detection around72percent CV versus conditional magnitude around79percent. '
        'Investigate binary auxiliary supervision distinct from previous continuous source-delta heads. '
        'Preserve the stronger original flat native base distributions and freeze their relative nonzero '
        'delta probabilities. Correct only logitP(change),using inner-person OOF fitting offsets and '
        'a shared actual-two-prior encoder plus genuine native13feature context. Four separate source '
        'heads learn actual equality/inequality on each original instrument; rates/scales/protocols '
        'remain distinct. No source native-context rows,times,phases,scale conversion or missing classes '
        'are invented. Source-only gradients must reach the shared encoder; weights0/.1/1 use identical '
        'initialization,80epochs,penalty10and matched zero-source controls. Final scoring remains '
        'exact native Borg0-10on original487/179cases; binary component accuracy cannot satisfy80percent.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':10,'new_joint_network_fits':30,'new_native_base_fits':0,
    'source_actual_pairs':2287,'predictive_fitting_started':False}),flush=True)
