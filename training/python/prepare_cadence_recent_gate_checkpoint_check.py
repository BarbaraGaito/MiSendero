"""Prepare a read-only checker for the latest57-study checkpoint."""
from pathlib import Path

root = Path(__file__).parent
text = (root/'check_cadence_binary_gate_checkpoint_integrity.py').read_text()
for old,new in {
    'fatigue_cadence_binary_gate':'fatigue_cadence_recent_gate',
    'cadence-binary-gate':'cadence-recent-gate',
    'cadence-binary-physiology-gate.json':'cadence-recent-native-gate.json',
    'cadence_binary_gate_proposal':'cadence_recent_native_gate_proposal',
    'all_6_oof_recipes':'all_10_oof_recipes',
    'prepare_cadence_binary_gate_verifiers.py':'prepare_cadence_recent_gate_verifiers.py',
    '==(56,1892,297)':'==(57,1902,303)',
    'len(counts)==56 and sum(counts)==1892':'len(counts)==57 and sum(counts)==1902',
    "'completed_studies':56,'completed_configurations':1892,'distinct_tests':297":"'completed_studies':57,'completed_configurations':1902,'distinct_tests':303",
    'Ran 5 tests':'Ran 6 tests'}.items():
    assert old in text,old
    text = text.replace(old,new)
start = text.index("    input_audit = json.loads(study.INPUT_AUDIT.read_text())")
end = text.index("    assert summary['real_tests_code_sha256']",start)
replacement = '''    input_audit = json.loads(study.INPUT_AUDIT.read_text())
    assert input_audit['verification']=='passed'
    assert input_audit['audit_code_sha256']==digest(Path(__file__).with_name('audit_cadence_recent_gate_inputs.py'))
    assert input_audit['preparation_code_sha256']==digest(Path(study.added.__file__))
    assert input_audit['provenance_sha256']==digest(study.added.DIRECTORY/'provenance.json')
    assert input_audit['native_dataset_sha256']==digest(study.added.DIRECTORY/'native.csv')
    assert input_audit['native_cells_independently_rebuilt']==input_audit['native_clocks_verified']==666
    source_audit = json.loads(study.previous.INPUT_AUDIT.read_text())
    assert source_audit['verification']=='passed' and source_audit['actual_source_pairs_independently_rebuilt']==1057
    assert source_audit['preparation_code_sha256']==digest(Path(study.prepared.__file__))
    assert source_audit['source_dataset_sha256']==digest(study.prepared.DIRECTORY/'source.csv')
    assert source_audit['native_dataset_sha256']==digest(study.prepared.DIRECTORY/'native.csv')
'''
text = text[:start]+replacement+text[end:]
start = text.index("    review_path = study.DOCS/'cadence-gate-recent-native-state-review.json'")
end = text.index('    preparation = ',start)
replacement = '''    diagnostic_path = study.DOCS/'cadence-recent-gate-error-diagnostic.json'
    assert summary['error_diagnostic_sha256']==status['cadence_recent_gate_diagnostic']['sha256']==digest(diagnostic_path)
    diagnostic = json.loads(diagnostic_path.read_text())
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_cadence_recent_gate_errors.py'))
    assert diagnostic['selection_sha256']==digest(path) and diagnostic['verification_sha256']==digest(audit_path)
    assert diagnostic['new_predictive_estimator_fits']==diagnostic['new_test_predictions_computed']==0 and not diagnostic['test_labels_inspected']
    review_path = study.DOCS/'cadence-full-delta-residual-review.json'
    assert summary['full_delta_residual_review_sha256']==status['cadence_full_delta_residual_review']['sha256']==digest(review_path)
    review = json.loads(review_path.read_text())
    assert review['review_code_sha256']==digest(Path(__file__).with_name('review_cadence_full_delta_residual.py'))
    assert review['selection_sha256']==digest(path) and review['verification_sha256']==digest(audit_path)
    assert all(digest(Path(__file__).with_name(name))==value for name,value in review['implementation_sha256'].items())
    assert review['new_predictive_estimator_fits']==review['new_test_predictions_computed']==0 and not review['model_comparison_predeclared']
'''
text = text[:start]+replacement+text[end:]
text = text.replace('audited study56','audited study57')
compile(text,'check_cadence_recent_gate_checkpoint_integrity.py','exec')
path = root/'check_cadence_recent_gate_checkpoint_integrity.py'
if path.exists():
    assert path.read_text()==text
else:
    path.write_text(text,encoding='utf-8')
print('Prepared read-only study57checkpoint checker',flush=True)
