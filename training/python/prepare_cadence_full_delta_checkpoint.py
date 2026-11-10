"""Prepare study58 bookkeeping from verified study57 without changing its evidence."""
from pathlib import Path

root = Path(__file__).parent


def common(text):
    return (text.replace('fatigue_cadence_recent_gate','fatigue_cadence_full_delta')
        .replace('cadence-recent-gate','cadence-full-delta')
        .replace('cadence-recent-native-gate.json','cadence-full-delta-residual.json')
        .replace('cadence_recent_native_gate_proposal','cadence_full_delta_residual_proposal')
        .replace('cadence_recent_gate_','cadence_full_delta_')
        .replace('all_10_oof_recipes','all_14_oof_recipes')
        .replace('all_20_fold_artifacts','all_40_fold_artifacts')
        .replace('cadence-full-delta-error-diagnostic.json','cadence-full-delta-generalization-diagnostic.json')
        .replace('diagnose_cadence_full_delta_errors.py','diagnose_cadence_full_delta_generalization.py')
        .replace('diagnose_cadence_recent_gate_errors.py','diagnose_cadence_full_delta_generalization.py')
        .replace('audit_cadence_full_delta_inputs.py','audit_cadence_recent_gate_inputs.py')
        .replace('native_joint_nll_gradient_equivalence_verified','native_delta_cross_entropy_gradient_verified'))


text = common((root/'record_cadence_recent_gate_checkpoint.py').read_text())
text = text.replace('(56,1892,297),(57,1902,303)','(57,1902,303),(58,1916,309)')
text = text.replace("len(selected['results'])==10","len(selected['results'])==14")
text = text.replace("audit['independent_joint_refits']==len(audit['native_joint_refits'])==20", "audit['independent_joint_refits']==len(audit['native_joint_refits'])==40")
text = text.replace("row['base_weights_frozen'] and row['nonzero_delta_ratios_frozen']", "row['base_weights_frozen'] and not row['nonzero_delta_ratios_frozen']")
start = text.index("review_path = study.DOCS/'cadence-full-delta-residual-review.json'")
end = text.index("assert (len(inputs['train'])",start)
text = text[:start]+text[end:]
text = text.replace('completed_studies=57,evaluated_configurations_including_controls=1902,python_tests_passed=303',
    'completed_studies=58,evaluated_configurations_including_controls=1916,python_tests_passed=309')
start = text.index("status['cadence_gate_recent_native_state_review'].update(")
end = text.index("status['cadence_full_delta_residual_proposal']",start)
text = text[:start]+text[end:]
text = text.replace("'configurations':10", "'configurations':14").replace("'new_joint_network_fits':20", "'new_joint_network_fits':40")
text = text.replace("'independent_joint_refits':20", "'independent_joint_refits':40")
start = text.index("status['cadence_full_delta_residual_review'] =")
end = text.index("status['next_evidence_based_direction']",start)
text = text[:start]+"status['cadence_full_delta_residual_review'].update(model_comparison_predeclared=True,model_study_completed=True,used_in_study=study.DIRECTORY.name)\n"+text[end:]
start = text.index("status['next_evidence_based_direction'] =")
end = text.index('summary = ',start)
replacement = '''status['next_evidence_based_direction'] = (
    'Study58 completed14recipes/40networks and40independent refits. All actual native/source targets, '
    '21class cross-entropy/centered residual gradients/source BCE and80backward steps were verified. '
    'All8new full-delta residuals reduced fitting NLL but increased outer-person validation NLL. '
    'Penalty1 outperformed.1 in all4member/source comparisons. Best new Cat/source.613929CV remains '
    'below global.637972;it corrected7/spoiled19vs global and5/spoiled2vs matched zero. Source '
    'improvement within a weaker architecture is not a global improvement. Next predeclare stronger '
    'regularization10/100 with otherwise frozen full-delta fit,matched source-zero/source-positive '
    'controls and original global controls. Preserve the851source pairs,11shared inputs,16private '
    'native inputs and base weights. No synthetic examples,scale conversion or source current context. '
    'No new test qualified;retained108/179. Original487/179,.65CVtestgate and144/179exact reloaded '
    'artifact matches remain required. Stronger penalties are not yet predeclared or fitted.')
'''
text = text[:start]+replacement+text[end:]
text = text.replace("'full_delta_residual_review_sha256':digest(review_path),\n",'')
text = text.replace("'completed_studies':57,'completed_configurations':1902,'distinct_tests':303",
    "'completed_studies':58,'completed_configurations':1916,'distinct_tests':309")
text = text.replace('Record audited study57','Record audited study58')
outputs = {'record_cadence_full_delta_checkpoint.py':text}

text = common((root/'check_cadence_recent_gate_checkpoint_integrity.py').read_text())
for old,new in {
    '==(57,1902,303)':'==(58,1916,309)',
    'len(counts)==57 and sum(counts)==1902':'len(counts)==58 and sum(counts)==1916',
    "audit['independent_joint_refits']==len(audit['native_joint_refits'])==20":"audit['independent_joint_refits']==len(audit['native_joint_refits'])==40",
    "row['base_weights_frozen'] and row['nonzero_delta_ratios_frozen']":"row['base_weights_frozen'] and not row['nonzero_delta_ratios_frozen']",
    "study.DIRECTORY/'folds',40":"study.DIRECTORY/'folds',80",
    "study.previous.INPUT_AUDIT.read_text()":"study.previous.previous.INPUT_AUDIT.read_text()",
    "'completed_studies':57,'completed_configurations':1902,'distinct_tests':303":"'completed_studies':58,'completed_configurations':1916,'distinct_tests':309",
    "'new_fold_artifact_hashes_checked':40":"'new_fold_artifact_hashes_checked':80",
    "'independent_joint_refits':20":"'independent_joint_refits':40"}.items():
    assert old in text,old
    text = text.replace(old,new)
start = text.index("    review_path = study.DOCS/'cadence-full-delta-residual-review.json'")
end = text.index('    preparation = ',start)
text = text[:start]+text[end:]
text = text.replace('audited study57','audited study58')
outputs['check_cadence_full_delta_checkpoint_integrity.py'] = text

text = (root/'integrate_cadence_recent_gate_checkpoint.py').read_text()
text = text.replace('fatigue_cadence_recent_gate','fatigue_cadence_full_delta')
text = text.replace('cadence-recent-gate-verification','cadence-full-delta-verification')
text = text.replace('audit_fatigue_cadence_recent_gate','audit_fatigue_cadence_full_delta')
text = text.replace("old = 'for name in (\"cadence-binary-physiology-gate-80-v1\",'",
    "old = 'for name in (\"cadence-recent-native-gate-80-v1\",'")
text = text.replace("new = 'for name in (\"cadence-recent-native-gate-80-v1\", \"cadence-binary-physiology-gate-80-v1\",'",
    "new = 'for name in (\"cadence-full-delta-residual-80-v1\", \"cadence-recent-native-gate-80-v1\",'")
text = text.replace('if name == "cadence-recent-native-gate-80-v1":','if name == "cadence-full-delta-residual-80-v1":')
text = text.replace('validate_recent_gate','validate_full_delta').replace('cadence_recent_native_gate','cadence_full_delta_residual')
text = text.replace('marker = \'        if name == "cadence-binary-physiology-gate-80-v1":',
    'marker = \'        if name == "cadence-recent-native-gate-80-v1":')
text = text.replace('study57','study58')
outputs['integrate_cadence_full_delta_checkpoint.py'] = text
for name,text in outputs.items():
    compile(text,name,'exec')
    path = root/name
    # These bookkeeping helpers have not been executed or included in fitted signatures.
    path.write_text(text,encoding='utf-8')
print('Prepared study58record,integration and read-only integrity checker',flush=True)
