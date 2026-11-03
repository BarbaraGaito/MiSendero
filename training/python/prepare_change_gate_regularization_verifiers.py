"""Derive scoped verification from frozen study54 without changing its files."""
import json
from pathlib import Path
import fatigue_change_gate_regularization as study
from public_sources import digest

root = Path(__file__).parent
sources = [root/name for name in ('audit_fatigue_public_change_gate.py',
    'evaluate_fatigue_public_change_gate.py','diagnose_public_change_gate_margins.py')]
audit = sources[0].read_text()
replacements = {
    'fatigue_public_change_gate':'fatigue_change_gate_regularization',
    'public-change-gate':'change-gate-regularization',
    'joint_public_binary_change_gate':'regularized_public_binary_change_gate',
    'study.PublicChangeGateBorg(c)':'study.RegularizedChangeGateBorg(c)',
    '+10*np.mean(correction**2)':"+c['correction_penalty']*np.mean(correction**2)",
    "len(selected['results'])==10":"len(selected['results'])==18",
    'study.plan()[4:]':'study.plan()[6:]',
    "inputs['previous_selection']":"inputs['parent_selection']",
    "'all_10_oof_recipes_recomputed'":"'all_18_oof_recipes_recomputed'",
    "'all_30_fold_artifacts_recomputed'":"'all_60_fold_artifacts_recomputed'",
    "'independent_joint_refits':20":"'independent_joint_refits':len(refits)",
    "'candidate_id':c['id'],'member':member,'fold':n,**details,":
        "'candidate_id':c['id'],'member':member,'fold':n,'actual_correction_penalty':c['correction_penalty'],**details,",
}
for before,after in replacements.items():
    assert before in audit,before
    audit = audit.replace(before,after)
old = """    zeros = {m:next(row for row in selected['results'] if row['candidate'].get('member')==m and row['candidate'].get('auxiliary_weight')==0) for m in best}
    refit_ids = {row['candidate']['id'] for row in [*best.values(),*zeros.values()]}"""
new = """    native_only = {m:max([row for row in selected['results'] if row['candidate'].get('member')==m
        and row['candidate'].get('auxiliary_weight')==0],key=lambda row:row['accuracy_mean']) for m in best}
    zeros = {m:next(row for row in selected['results'] if row['candidate'].get('member')==m
        and row['candidate'].get('auxiliary_weight')==0
        and row['candidate'].get('correction_penalty')==best[m]['candidate']['correction_penalty']) for m in best}
    refit_ids = {row['candidate']['id'] for row in [*best.values(),*zeros.values(),*native_only.values()]}"""
assert audit.count(old)==1
audit = audit.replace(old,new)
old = 'assert len(artifacts)==60 and len(refits)==20 and inner_models_verified==30'
new = 'assert len(artifacts)==120 and len(refits)==5*len(refit_ids) and 20<=len(refits)<=30 and inner_models_verified==30'
assert audit.count(old)==1
audit = audit.replace(old,new)
marker = "        'matched_zero_source_controls':{m:compact(row) for m,row in zeros.items()},"
assert audit.count(marker)==1
audit = audit.replace(marker,marker+"\n        'best_native_only_by_member':{m:compact(row) for m,row in native_only.items()},")
audit = audit.replace("'native_joint_refits','best_positive_by_member','matched_zero_source_controls')",
    "'native_joint_refits','best_positive_by_member','matched_zero_source_controls','best_native_only_by_member')")
evaluate = sources[1].read_text().replace('fatigue_public_change_gate','fatigue_change_gate_regularization')
evaluate = evaluate.replace('public-change-gate','change-gate-regularization')
evaluate = evaluate.replace('joint_public_binary_change_gate','regularized_public_binary_change_gate')
evaluate = evaluate.replace('PublicChangeGateBorg','RegularizedChangeGateBorg')
diagnostic = sources[2].read_text().replace('fatigue_public_change_gate','fatigue_change_gate_regularization')
diagnostic = diagnostic.replace('public-change-gate','change-gate-regularization')
diagnostic = diagnostic.replace('joint_public_binary_change_gate','regularized_public_binary_change_gate')
assert diagnostic.count('len(results)==6 and len(hashes)==30')==1
diagnostic = diagnostic.replace('len(results)==6 and len(hashes)==30','len(results)==12 and len(hashes)==60')
outputs = {'audit_fatigue_change_gate_regularization.py':audit,
    'evaluate_fatigue_change_gate_regularization.py':evaluate,
    'diagnose_change_gate_regularization_margins.py':diagnostic}
for name,code in outputs.items():
    compile(code,name,'exec')
    path = root/name
    if path.exists():
        assert path.read_text()==code,name
    else:
        path.write_text(code,encoding='utf-8')
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_sources_sha256':{path.name:digest(path) for path in sources},
    'derived_files_sha256':{name:digest(root/name) for name in outputs},
    'historical_sources_modified':False,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'change':'Verify actual candidate penalty,18recipes and60fold artifacts;refit best positive/matched zero/best native-only recipes in all5folds. Preserve full qualified179case test verification.'}
(study.DOCS/'change-gate-regularization-verifier-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
