"""Assess the remaining gate restriction and distinguish prior full-delta work."""
import ast
import json
from pathlib import Path
import numpy as np
from sklearn.model_selection import GroupKFold
import fatigue_cadence_recent_gate as study
from public_sources import digest


def review():
    inputs = study.load_inputs()
    train = inputs['train']
    selected_path = study.DIRECTORY/'selection.json'
    audit_path = study.DOCS/'cadence-recent-gate-verification.json'
    audit = json.loads(audit_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(selected_path)
    parent = Path(__file__).parent
    paths = [parent/name for name in ('fatigue_two_history_joint.py','fatigue_domain_aligned_history.py',
        'fatigue_cadence_binary_gate.py','fatigue_cadence_recent_gate.py')]
    # Check actual implementations rather than infer behavior from study names.
    old_joint = ast.parse(paths[0].read_text())
    old_fit = next(node for node in ast.walk(old_joint) if isinstance(node,ast.FunctionDef) and node.name=='fit'
        and any(isinstance(n,ast.Constant) and n.value==550 for n in ast.walk(node)))
    old_fit_text = ast.get_source_segment(paths[0].read_text(),old_fit)
    assert 'cross_entropy(offsets+correction,target)' in old_fit_text
    assert 'smooth_l1_loss' in old_fit_text and 'history_query' in old_fit_text
    gate_fit = ast.parse(paths[2].read_text())
    gate_fit = next(node for node in ast.walk(gate_fit) if isinstance(node,ast.FunctionDef) and node.name=='fit')
    gate_text = ast.get_source_segment(paths[2].read_text(),gate_fit)
    assert 'binary_cross_entropy_with_logits(native_logits,target)' in gate_text
    assert 'nonzero_delta_relative_probabilities_frozen' in gate_text
    feasibility = {}
    truth = train.label.str.removeprefix('Borg ').to_numpy(int)
    prior = train.prior_borg.to_numpy(int)
    for member in ('core','cat'):
        alternative = np.empty(len(train),int)
        for n,(fit,val) in enumerate(GroupKFold(5).split(train,groups=train.group_key)):
            cache = study.read_cache(inputs,member,n,fit,val)
            base = cache['base']
            query = train.iloc[val][base.input_features]
            logp = base.logits(query).numpy()
            priority = base.priority[base.priority!=10]
            delta = priority[logp[:,priority].argmax(axis=1)]-10
            alternative[val] = np.clip(prior[val]+delta,0,10)
        zero_correct,nonzero_correct = truth==prior,truth==alternative
        possible = zero_correct|nonzero_correct
        feasibility[member] = {'native_fitting_queries':487,'zero_branch_correct':int(zero_correct.sum()),
            'fixed_nonzero_branch_correct':int(nonzero_correct.sum()),
            'unreachable_by_any_binary_gate':int((~possible).sum()),
            'optimistic_label_informed_gate_choice_count':int(possible.sum()),
            'optimistic_choice_is_not_achieved_accuracy':True,
            'interpretation':'A binary gate can only select unchanged Borg or the frozen most likely nonzero delta. These fitting-only counts use truth to describe that restriction;they are not model predictions or evidence of80percent.'}
    report = {'review':'passed','review_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(selected_path),'verification_sha256':digest(audit_path),
        'implementation_sha256':{path.name:digest(path) for path in paths},
        'native_fitting_queries':487,'native_fitting_people':28,'gate_restriction':feasibility,
        'previous_full_delta_work':{'native_objective':'21-delta cross-entropy residual on frozen native logits',
            'shared_features':'two actual Borg histories with domain normalization',
            'native_context_features':13,'external_objectives':'separate original-scale continuous delta heads',
            'recent_native_context_or_shared_prior_hr_included':False},
        'proposed_distinct_work':{'native_objective':'21-delta cross-entropy residual on frozen native logits',
            'shared_features':'six actual histories/prior-HR numerics plus five real availability flags',
            'native_context_features':16,'external_objective':'separate CADENCE851 actual-change binary head',
            'source_current_hr_or_native_private_context_added':False,'base_classifier_weights_to_remain_frozen':True,
            'nonzero_delta_residuals_may_change':True},
        'model_comparison_predeclared':False,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
        'test_labels_inspected':False,'synthetic_rows':0,
        'interpretation':'Earlier full-delta residuals existed and must not be presented as a new general method. '
            'The distinct comparison combines the now-audited measured prior physiology and native recent context '
            'with a full native residual and a separate original-scale-independent source binary head. '
            'Study57slightly improved binary validation BCE without improving exact Borg. This motivates a '
            'matched comparison against its scalar gate,not a claim of expected or guaranteed improvement. '
            'Predeclare source-zero controls and penalties before fitting;retain original487/179and.65CVtestgate.'}
    path = study.DOCS/'cadence-full-delta-residual-review.json'
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    review()
