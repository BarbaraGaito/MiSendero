"""Prepare registration and read-only evidence checks for audited study60."""
from pathlib import Path

root = Path(__file__).parent


def common(text):
    return (text.replace('fatigue_cadence_delta_regularization','fatigue_cadence_ordered_residual')
        .replace('cadence-delta-regularization','cadence-ordered-residual')
        .replace('cadence_delta_regularization','cadence_ordered_residual')
        .replace('cadence-ordered-residual-generalization-diagnostic.json','cadence-ordered-residual-diagnostic.json')
        .replace('diagnose_cadence_ordered_residual_generalization.py','diagnose_cadence_ordered_residual.py')
        .replace('all_14_oof_recipes','all_26_oof_recipes').replace('Ran 6 tests','Ran 7 tests'))


text = common((root/'record_cadence_delta_regularization_checkpoint.py').read_text())
text = text.replace('(58,1916,309),(59,1930,315)','(59,1930,315),(60,1956,322)')
text = text.replace("len(selected['results'])==14","len(selected['results'])==26")
text = text.replace('completed_studies=59,evaluated_configurations_including_controls=1930,python_tests_passed=315',
    'completed_studies=60,evaluated_configurations_including_controls=1956,python_tests_passed=322')
text = text.replace("'configurations':14","'configurations':26")
needle = "    assert row['native_delta_cross_entropy_gradient_verified'] and row['source_targets_from_original_pairs']"
assert needle in text
text = text.replace(needle,needle+"\n    assert row['actual_coefficient_chain_gradient_verified'] and row['fixed_ordered_basis_verified'] and row['shared_initialization_matched_full_residual']")
text = text.replace("assert review['review']=='passed' and review['selection_sha256']==digest(path) and review['verification_sha256']==digest(audit_path)",
    "assert review['review']=='passed' and review['selection_sha256']==digest(study.previous.DIRECTORY/'selection.json') and review['verification_sha256']==digest(study.PARENT_AUDIT)")
text = text.replace("'fitting_only':True,'model_comparison_predeclared':False,'new_predictive_estimator_fits':0}",
    "'fitting_only':True,'model_comparison_predeclared':True,'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'new_predictive_estimator_fits':0}")
start = text.index("status['next_evidence_based_direction'] =")
end = text.index('summary = ',start)
text = text[:start]+'''candidate_path = study.DOCS/'rpe-forecasting-candidate-inspection.json'
candidate = json.loads(candidate_path.read_text())
assert candidate['inspection']=='passed' and candidate['inspection_code_sha256']==digest(Path(__file__).with_name('review_rpe_forecasting_candidate.py'))
assert candidate['participant_split_frozen_before_original_target_review'] and candidate['case2_available_people']==24
assert len(candidate['case2_fitting_people'])==19 and len(candidate['case2_reserved_people'])==5
assert not candidate['case1_use_for_fitting_approved'] and not candidate['case2_training_merge_approved']
assert candidate['new_predictive_estimator_fits']==candidate['new_test_predictions_computed']==0
status['additional_public_candidate_inspections'][candidate_path.name] = digest(candidate_path)
status['rpe_forecasting_candidate'] = {'document':candidate_path.name,'sha256':digest(candidate_path),
    'revision':candidate['revision'],'fitting_people':19,'reserved_people':5,'case2_training_merge_approved':False}
status['next_evidence_based_direction'] = (
    'Study60 completed26recipes(18inherited controls/8new),40networks and40independent refits. '
    'Fixed3basis/27output parameters,shared initialization,actual coefficient-chain gradients and '
    '80native/source backward steps were verified. Best new core/source.610047CV;Cat/source.609810, '
    'below global.637972. Core/source corrected8/spoiled6vs matching free21and17/spoiled16vs global; '
    'Cat/source corrected7/spoiled9vs matching free21and7/spoiled21vs global. All8new residuals '
    'again reduced fitNLL but increased outer-person validationNLL. Smaller output geometry did '
    'not solve generalization. Pivot to raw evidence for the public RPE_ForecastingCase2candidate '
    'at pinned2e2233a6a755b05dc4dc0404d580d401ff7d520e. Its author context describes24participants '
    'with one RPE per squatting/walking trial. Freeze19fitting/5reserved people before raw target '
    'review(already recorded),retrieve only19fitting workbooks and verify Git blob identities, '
    'original report cells,scale and actual trial order. Do not count repeated strides as separate '
    'reports. Case1percentile-rescaled/median-filtered data stays excluded. Case2has no approved '
    'training merge or downloaded raw workbooks yet;do not invent clocks/HR/labels or equate scales. '
    'Original487/179,.65CVtestgate and144/179exact reloaded artifact matches remain required. '
    'No newtest qualified;retained108/179and goal active.')
''' + text[end:]
text = text.replace("'ordered_residual_review_sha256':digest(review_path)",
    "'rpe_forecasting_candidate_sha256':digest(candidate_path),'ordered_residual_review_sha256':digest(review_path)")
text = text.replace("'completed_studies':59,'completed_configurations':1930,'distinct_tests':315",
    "'completed_studies':60,'completed_configurations':1956,'distinct_tests':322")
text = text.replace('Record audited study59','Record audited study60')
outputs = {'record_cadence_ordered_residual_checkpoint.py':text}

text = common((root/'check_cadence_delta_regularization_checkpoint_integrity.py').read_text())
for old,new in {
    '==(59,1930,315)':'==(60,1956,322)',
    'len(counts)==59 and sum(counts)==1930':'len(counts)==60 and sum(counts)==1956',
    "'completed_studies':59,'completed_configurations':1930,'distinct_tests':315":"'completed_studies':60,'completed_configurations':1956,'distinct_tests':322"}.items():
    assert old in text,old
    text = text.replace(old,new)
text = text.replace(needle,needle+"\n        assert row['actual_coefficient_chain_gradient_verified'] and row['fixed_ordered_basis_verified'] and row['shared_initialization_matched_full_residual']")
text = text.replace("assert review['selection_sha256']==digest(path) and review['verification_sha256']==digest(audit_path)",
    "assert review['selection_sha256']==digest(study.previous.DIRECTORY/'selection.json') and review['verification_sha256']==digest(study.PARENT_AUDIT)")
text = text.replace("assert review['diagnostic_sha256']==digest(diagnostic_path) and review['basis_is_class_geometry_not_training_observations_or_targets']",
    "assert review['diagnostic_sha256']==digest(study.DOCS/'cadence-delta-regularization-generalization-diagnostic.json') and review['basis_is_class_geometry_not_training_observations_or_targets']")
index = text.index('    preparation = ')
additional = '''    candidate_path = study.DOCS/'rpe-forecasting-candidate-inspection.json'
    candidate = json.loads(candidate_path.read_text())
    assert summary['rpe_forecasting_candidate_sha256']==status['rpe_forecasting_candidate']['sha256']==digest(candidate_path)
    assert candidate['inspection_code_sha256']==digest(Path(__file__).with_name('review_rpe_forecasting_candidate.py'))
    import review_rpe_forecasting_candidate as source_candidate
    assert all(digest(source_candidate.DIRECTORY/name)==value for name,value in candidate['snapshot_sha256'].items())
    original_context = (source_candidate.DIRECTORY/'source-context.Rmd').read_bytes()
    assert source_candidate.git_blob(original_context)==candidate['source_context_git_blob_sha1']
    assert candidate['participant_split_frozen_before_original_target_review'] and candidate['case2_original_workbooks_downloaded']==0
    assert len(candidate['case2_fitting_people'])==19 and len(candidate['case2_reserved_people'])==5
    assert not candidate['case1_use_for_fitting_approved'] and not candidate['case2_training_merge_approved']
    assert candidate['new_predictive_estimator_fits']==candidate['new_test_predictions_computed']==0
'''
text = text[:index]+additional+text[index:]
text = text.replace('audited study59','audited study60')
outputs['check_cadence_ordered_residual_checkpoint_integrity.py'] = text

text = common((root/'integrate_cadence_delta_regularization_checkpoint.py').read_text()).replace('study59','study60')
outputs['integrate_cadence_ordered_residual_checkpoint.py'] = text
for name,text in outputs.items():
    compile(text,name,'exec')
    path = root/name
    if path.exists():
        assert path.read_text()==text,name
    else:
        path.write_text(text,encoding='utf-8')
print('Prepared study60record,integration and read-only evidence checker',flush=True)
