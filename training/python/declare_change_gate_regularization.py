"""Freeze a diagnostic-motivated penalty comparison before new fitting."""
import json
from pathlib import Path
import fatigue_change_gate_regularization as study
from public_sources import digest

proof = json.loads(study.PARENT_AUDIT.read_text())
diagnostic = json.loads(study.DIAGNOSTIC.read_text())
assert proof['verification']=='passed' and diagnostic['diagnostic']=='passed'
assert all(row['final_native_borg_predictions_changed']==0 for row in diagnostic['results'])
report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'frozen_fitting_implementation_sha256':digest(Path(study.parent.__file__)),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'margin_diagnostic_sha256':digest(study.DIAGNOSTIC),
    'original_native_fit_cases':487,'original_native_test_cases':179,'source_fitting_pairs':2287,
    'source_reserved_pairs_not_fitted':312,'excluded_single_class_sts_pairs':49,'new_joint_network_fits':60,
    'new_native_base_fits':0,'minimum_cv_for_new_test_evaluation':.65,'test_used_for_selection':False,'synthetic_rows':0,
    'independent_refit_policy':'Best positive-source recipe per member and zero-source control at its penalty,plus best native-only recipe per member if different,in all5personfolds;all60saved artifacts/all18OOFmetrics verified.',
    'rationale':'Study54verified real learning and source gradients,but none of six gate recipes changed '
        'a native OOFdecision. CatBoost source.1median logit adjustment was.00176versus median boundary '
        'distance1.00966. Test whether relaxing the existing penalty10permits useful changes without '
        'hurting participant CV. Predeclare new penalties0/.1/1,source weights0/.1and matched inherited '
        'penalty10controls. Source.1is the first CVtied positive-source control,not a test-chosen setting. '
        'Keep all80epoch implementation/initialization/optimizer/data/normalization/native weights '
        'and nonzero delta ratios fixed. This diagnosis does not prove improved CV;do not expand '
        'the grid after observing results or count hypothetical oracle bounds as achieved accuracy.'}
assert len(study.plan())==18
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':18,'new_joint_network_fits':60,'new_native_base_fits':0,'predictive_fitting_started':False}),flush=True)
