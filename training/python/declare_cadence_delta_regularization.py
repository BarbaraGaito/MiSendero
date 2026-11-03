"""Predeclare10/100penalties before further predictive fitting."""
import json
from pathlib import Path
import fatigue_cadence_delta_regularization as study
from public_sources import digest

report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'diagnostic_sha256':digest(study.DIAGNOSTIC),
    'frozen_full_delta_implementation_sha256':digest(Path(study.previous.__file__)),
    'input_verification_sha256':digest(study.INPUT_AUDIT),'original_native_fit_cases':487,'original_native_test_cases':179,
    'source_actual_fit_pairs':851,'source_reserved_pairs':206,'shared_inputs':11,'native_private_inputs':16,
    'new_joint_network_fits':40,'new_native_base_fits_for_cv':0,'minimum_cv_for_new_test_evaluation':.65,
    'test_used_for_selection':False,'synthetic_rows':0,'residual_outputs':21,
    'penalty_convention':'lambda*mean of squared centered residual across actual native rows and21outputs',
    'penalties':[10.,100.],'source_weights':[0.,.1],'epochs':80,'learning_rate':.003,'weight_decay':.1,
    'architecture_changed':False,'native_or_source_objective_changed':False,
    'rationale':'All8study58recipes reduced fit NLL but increased validation NLL. Penalty1 beat.1 '
        'in all4member/source comparisons. Freeze all other data/normalization/architecture/optimizer '
        'choices and test10/100. Six inherited controls contain global MLP/Cat and all4matching '
        'penalty1variants. Native labels remain exact original Borg0-10;the851source pairs keep '
        'their original6-20change predicate and separate head. No synthetic or transformed targets. '
        'Independently refit all8new recipes in all5personfolds and recompute all14OOFmetrics.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':14,'new_joint_network_fits':40,'predictive_fitting_started':False}),flush=True)
