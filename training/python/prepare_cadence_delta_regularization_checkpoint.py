"""Prepare read-only evidence checks and registration for audited study59."""
from pathlib import Path

root = Path(__file__).parent


def common(text):
    return (text.replace('fatigue_cadence_full_delta','fatigue_cadence_delta_regularization')
        .replace('cadence-full-delta','cadence-delta-regularization')
        .replace('cadence_full_delta_','cadence_delta_regularization_')
        .replace('cadence-delta-regularization-residual.json','cadence-delta-regularization.json')
        .replace('cadence_delta_regularization_residual_proposal','cadence_delta_regularization_proposal'))


text = common((root/'record_cadence_full_delta_checkpoint.py').read_text())
text = text.replace('(57,1902,303),(58,1916,309)','(58,1916,309),(59,1930,315)')
text = text.replace('completed_studies=58,evaluated_configurations_including_controls=1916,python_tests_passed=309',
    'completed_studies=59,evaluated_configurations_including_controls=1930,python_tests_passed=315')
old = "status['cadence_delta_regularization_residual_review'].update(model_comparison_predeclared=True,model_study_completed=True,used_in_study=study.DIRECTORY.name)"
assert old in text
text = text.replace(old,'''review_path = study.DOCS/'cadence-ordered-residual-review.json'
review = json.loads(review_path.read_text())
assert review['review']=='passed' and review['selection_sha256']==digest(path) and review['verification_sha256']==digest(audit_path)
assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_ordered_residual.py'))
assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0 and not review['model_comparison_predeclared']
status['cadence_ordered_residual_review'] = {'document':review_path.name,'sha256':digest(review_path),
    'fitting_only':True,'model_comparison_predeclared':False,'new_predictive_estimator_fits':0}
access_path = study.DOCS/'treadmill-cr10-access-refresh.json'
access = json.loads(access_path.read_text())
assert access['inspection']=='passed' and access['inspection_code_sha256']==digest(Path(__file__).with_name('record_treadmill_cr10_access_refresh.py'))
assert access['previous_access_conditions_unchanged'] and not access['training_merge_approved']
assert access['public_file_count']==0 and not access['source_data_downloaded']
status['additional_public_candidate_inspections'][access_path.name] = digest(access_path)
status['treadmill_cr10_access_refresh'] = {'document':access_path.name,'sha256':digest(access_path),
    'access':'embargoed','until':'2027-04-07','public_file_count':0,'training_merge_approved':False}
''')
start = text.index("status['next_evidence_based_direction'] =")
end = text.index('summary = ',start)
text = text[:start]+'''status['next_evidence_based_direction'] = (
    'Study59 completed14recipes/40networks and40independent refits using only stronger10/100penalties '
    'with frozen study58fit/data/architecture. Best Cat/source penalty100 reached.636011CV,above its '
    'matched zero.632090but below global.637972. It corrected2/spoiled0vs matched zero and0/spoiled1 '
    'vs global. Core preferred10to100. Cat/source validation NLL nearly equals the original baseline; '
    'strong shrinkage mainly restores it. The fitting-only ordered-residual review verifies a fixed '
    'centered3basis spanning delta,delta-squared andzero-change with uniform orthonormality. A3output '
    'head would reduce final-layer parameters189to27while allowing magnitude andzero-change shifts. '
    'Next predeclare that distinct smaller residual with source-zero controls,penalties and global/ '
    'full/scalar controls before fitting. Basis values are mathematical class geometry,not generated '
    'observations/labels. The primary treadmill23208045metadata was revalidated;embargo remains until '
    '2027-04-07,no public files and license-description inconsistency. It was already reviewed and '
    'is not a new usable source;no retries or source merging. Existing851source pairs,original487/179, '
    '.65CVtestgate and144/179exact reloaded artifact matches remain required. Retained108/179;goal active.')
''' + text[end:]
text = text.replace("'paired_oof_comparisons':diagnostic['paired_oof_comparisons']", "'ordered_residual_review_sha256':digest(review_path),'treadmill_access_refresh_sha256':digest(access_path),\n    'paired_oof_comparisons':diagnostic['paired_oof_comparisons']")
text = text.replace("'completed_studies':58,'completed_configurations':1916,'distinct_tests':309",
    "'completed_studies':59,'completed_configurations':1930,'distinct_tests':315")
text = text.replace('Record audited study58','Record audited study59')
outputs = {'record_cadence_delta_regularization_checkpoint.py':text}

text = common((root/'check_cadence_full_delta_checkpoint_integrity.py').read_text())
for old,new in {
    '==(58,1916,309)':'==(59,1930,315)',
    'len(counts)==58 and sum(counts)==1916':'len(counts)==59 and sum(counts)==1930',
    "study.previous.previous.INPUT_AUDIT.read_text()":"(study.DOCS/'cadence-binary-gate-input-verification.json').read_text()",
    "'completed_studies':58,'completed_configurations':1916,'distinct_tests':309":"'completed_studies':59,'completed_configurations':1930,'distinct_tests':315"}.items():
    assert old in text,old
    text = text.replace(old,new)
marker = '    preparation = '
index = text.index(marker)
additional = '''    review_path = study.DOCS/'cadence-ordered-residual-review.json'
    review = json.loads(review_path.read_text())
    assert summary['ordered_residual_review_sha256']==status['cadence_ordered_residual_review']['sha256']==digest(review_path)
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_ordered_residual.py'))
    assert review['selection_sha256']==digest(path) and review['verification_sha256']==digest(audit_path)
    assert review['diagnostic_sha256']==digest(diagnostic_path) and review['basis_is_class_geometry_not_training_observations_or_targets']
    assert review['proposed_residual']['basis_rank']==3 and len(review['proposed_residual']['basis'])==21
    assert all(digest(Path(__file__).with_name(name))==value for name,value in review['reviewed_implementation_sha256'].items())
    access_path = study.DOCS/'treadmill-cr10-access-refresh.json'
    access = json.loads(access_path.read_text())
    assert summary['treadmill_access_refresh_sha256']==status['treadmill_cr10_access_refresh']['sha256']==digest(access_path)
    assert access['inspection_code_sha256']==digest(Path(__file__).with_name('record_treadmill_cr10_access_refresh.py'))
    assert access['fetch_code_sha256']==digest(Path(__file__).with_name('fetch_treadmill_cr10_metadata.py'))
    import fetch_treadmill_cr10_metadata as source_access
    assert access['primary_metadata_sha256']==digest(source_access.DIRECTORY/'metadata.json')
    assert access['access_receipt_sha256']==digest(source_access.DIRECTORY/'metadata-access-result.json')
    assert access['previous_access_conditions_unchanged'] and access['public_file_count']==0 and not access['training_merge_approved']
'''
text = text[:index]+additional+text[index:]
text = text.replace('audited study58','audited study59')
outputs['check_cadence_delta_regularization_checkpoint_integrity.py'] = text

integration = '''"""Register audited study59 without historical refitting."""
import json
from pathlib import Path
import fatigue_cadence_delta_regularization as study
from public_sources import digest

audit = json.loads((study.DOCS/'cadence-delta-regularization-verification.json').read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
assert audit['verification_code_sha256']==digest(Path(__file__).with_name('audit_fatigue_cadence_delta_regularization.py'))
path = Path(__file__).with_name('fatigue_80_checkpoint.py')
code = path.read_text()
old = f'for name in ("{study.previous.DIRECTORY.name}",'
new = f'for name in ("{study.DIRECTORY.name}", "{study.previous.DIRECTORY.name}",'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
branch = f\'''        if name == "{study.DIRECTORY.name}":
            from audit_fatigue_cadence_delta_regularization import validate as validate_delta_regularization
            gate_audit = validate_delta_regularization()
            result["cadence_delta_regularization"] = gate_audit
            if gate_audit["new_test_evaluation"] is not None:
                result["experiments"][name] = {{"status": selection["status"], "completed_candidates": len(selection["results"]),
                    "best_cv_accuracy": gate_audit["best_cv_accuracy"], "winner_id": selection["winner_id"],
                    "selection_snapshot_sha256": sha256}}
                result["best_verified_test_accuracy"] = max(result["best_verified_test_accuracy"],
                    gate_audit["new_test_evaluation"]["test_accuracy"])
                continue
\'''
marker = f'        if name == "{study.previous.DIRECTORY.name}":\\n'
if branch not in code:
    assert code.count(marker)==1
    code = code.replace(marker,branch+marker)
compile(code,str(path),'exec')
path.write_text(code,encoding='utf-8')
print('Registered audited study59without historical refits',flush=True)
'''
outputs['integrate_cadence_delta_regularization_checkpoint.py'] = integration
for name,text in outputs.items():
    compile(text,name,'exec')
    path = root/name
    if path.exists():
        assert path.read_text()==text,name
    else:
        path.write_text(text,encoding='utf-8')
print('Prepared study59record,integration and read-only evidence checker',flush=True)
