"""Prepare study55 bookkeeping from frozen study54 helpers; never refit."""
from pathlib import Path
import fatigue_change_gate_regularization as study

root = Path(__file__).parent
source_names = {
    'record_change_gate_regularization_checkpoint.py':'record_public_change_gate_checkpoint.py',
    'check_change_gate_regularization_checkpoint_integrity.py':'check_public_change_gate_checkpoint_integrity.py',
    'integrate_change_gate_regularization_checkpoint.py':'integrate_public_change_gate_checkpoint.py',
}
outputs = {}
for target,source in source_names.items():
    code = (root/source).read_text()
    code = code.replace('public_change_gate','change_gate_regularization').replace('public-change-gate','change-gate-regularization')
    code = code.replace('study54','study55')
    code = code.replace('change-gate-regularization-transfer','change-gate-regularization')
    code = code.replace('all_10_oof_recipes','all_18_oof_recipes').replace('all_30_fold_artifacts','all_60_fold_artifacts')
    code = code.replace("len(selected['results'])==10","len(selected['results'])==18")
    if target.startswith('record_'):
        code = code.replace('(53,1858,282),(54,1868,287)','(54,1868,287),(55,1886,292)')
        code = code.replace('completed_studies=54,evaluated_configurations_including_controls=1868,python_tests_passed=287',
            'completed_studies=55,evaluated_configurations_including_controls=1886,python_tests_passed=292')
        code = code.replace("'configurations':10,'new_joint_network_fits':30","'configurations':18,'new_joint_network_fits':60")
        code = code.replace("len(diagnostic['results'])==6","len(diagnostic['results'])==12")
        code = code.replace("'recipes_checked':6","'recipes_checked':12")
        code = code.replace("'configurations':10,'new_joint_network_fits':30","'configurations':18,'new_joint_network_fits':60")
        code = code.replace("'completed_studies':54,'completed_configurations':1868,'distinct_tests':287",
            "'completed_studies':55,'completed_configurations':1886,'distinct_tests':292")
        marker = "status['next_evidence_based_direction'] = ("
        start,end = code.index(marker),code.index('summary = {',code.index(marker))
        replacement = '''review_path = study.DOCS/'cadence-binary-physiology-review.json'
review = json.loads(review_path.read_text())
assert review['review']=='passed' and review['preceding_selection_sha256']==digest(selection_path)
assert review['preceding_verification_sha256']==digest(audit_path)
assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_binary_physiology.py'))
assert review['source_fitting_actual_pairs']==851 and review['source_reserved_pairs_not_used']==206
assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0
status['cadence_binary_physiology_review'] = {'document':review_path.name,'sha256':digest(review_path),
    'fitting_only':True,'source_fitting_actual_pairs':851,'source_reserved_pairs_not_used':206,
    'actual_source_second_priors_recoverable':727,'source_actual_unchanged_pairs':299,'source_actual_changed_pairs':552,
    'model_comparison_predeclared':False,'new_predictive_estimator_fits':0}
status['public_change_gate_margin_diagnostic'].update(followup_comparison_completed=True,used_in_study=study.DIRECTORY.name)
status['next_evidence_based_direction'] = (
    'Study55completed18predeclared recipes/60joint networks,all60artifacts and18OOFmetrics independently '
    'verified,20networks refitted with actual losses/gradients/backward and unchanged native base weights. '
    'New penalties0/.1/1produced6to27decision changes,but best new CatBoost.633837CV did not beat.637972 '
    'global control. Source.1did not improve the best matching native-only recipe;no new test qualified. '
    'Do not extend pure-history source-weight/penalty grids. The shared encoder still observes only '
    'two past RPEreports,without physiological state. The read-only CADENCE review independently '
    'checked851actual adjacent-stage fitting pairs/123people,299unchanged/552changed,4decreases and '
    '727genuine second priors;206source reserved pairs were not used. Source HRcomes only from a '
    'completed preceding bout;native prior HR/baseline windows were verified on all487fitting cases '
    'without discarding missing inputs. Next predeclare a distinct actual-physiology-plus-history '
    'binary auxiliary representation with matched measured native-only controls and a separately '
    'audited prepared adapter. Earlier CADENCE representations used continuous RPE;history-only '
    'binary transfer55omitted physiology. No source current-bout HR,timestamps,ages,native phases '
    'or scale equivalence may be invented. Keep original487/179and.65CVgate,real public data only. '
    '80percent still requires144of179exact matches from a frozen reloaded model;retained108. '
    'The physiological binary comparison is not yet predeclared or fitted.')
'''
        code = code[:start]+replacement+code[end:]
        summary_marker = "    'winner_id':selected['winner_id'],'best_cv_accuracy':selected['best_cv_accuracy'],"
        assert code.count(summary_marker)==1
        code = code.replace(summary_marker,summary_marker+"\n    'best_native_only_by_member':audit['best_native_only_by_member'],'cadence_binary_physiology_review_sha256':digest(review_path),")
        loop_marker = "for row in audit['native_joint_refits']:\n"
        assert code.count(loop_marker)==1
        code = code.replace(loop_marker,loop_marker+"    assert row['actual_correction_penalty']==next(r['candidate']['correction_penalty'] for r in selected['results'] if r['candidate']['id']==row['candidate_id'])\n")
    elif target.startswith('check_'):
        code = code.replace('==(54,1868,287)','==(55,1886,292)')
        code = code.replace('len(counts)==54 and sum(counts)==1868','len(counts)==55 and sum(counts)==1886')
        code = code.replace("study.DIRECTORY/'folds',60","study.DIRECTORY/'folds',120")
        code = code.replace("len(diagnostic['results'])==6","len(diagnostic['results'])==12")
        code = code.replace("'completed_studies':54,'completed_configurations':1868,'distinct_tests':287",
            "'completed_studies':55,'completed_configurations':1886,'distinct_tests':292")
        code = code.replace("'new_fold_artifact_hashes_checked':60","'new_fold_artifact_hashes_checked':120")
        marker = "    assert status['change_gate_regularization_proposal']['model_study_completed']\n"
        assert code.count(marker)==1
        code = code.replace(marker,marker+'''    review_path = study.DOCS/'cadence-binary-physiology-review.json'
    assert status['cadence_binary_physiology_review']['sha256']==summary['cadence_binary_physiology_review_sha256']==digest(review_path)
    review = json.loads(review_path.read_text())
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_binary_physiology.py'))
    assert review['preceding_selection_sha256']==digest(selected_path) and review['preceding_verification_sha256']==digest(audit_path)
    assert review['source_fitting_actual_pairs']==851 and review['source_reserved_pairs_not_used']==206
    assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0
    prepared_path = study.DOCS/'change-gate-regularization-verifier-preparation.json'
    preparation = json.loads(prepared_path.read_text())
    assert preparation['preparation_code_sha256']==digest(Path(__file__).with_name('prepare_change_gate_regularization_verifiers.py'))
    for name,value in {**preparation['frozen_sources_sha256'],**preparation['derived_files_sha256']}.items():
        assert digest(Path(__file__).with_name(name))==value
''')
    else:
        # The new registry entry is prepended to the current study54 entry.
        code = code.replace('observed-change-factorization-80-v1','public-change-gate-transfer-80-v1')
    compile(code,target,'exec')
    outputs[target] = code
for name,code in outputs.items():
    path = root/name
    if path.exists():
        existing = path.read_text()
        assert existing==code or existing.replace('change-gate-regularization-transfer','change-gate-regularization')==code,name
        if existing!=code:
            path.write_text(code,encoding='utf-8')
    else:
        path.write_text(code,encoding='utf-8')
print('Prepared study55scoped recorder,registry integration and read-only checker',flush=True)
