"""Predeclare the smaller ordered residual,controls and penalties before fitting."""
import json
from pathlib import Path
import fatigue_cadence_ordered_residual as study
from public_sources import digest

report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'review_sha256':digest(study.REVIEW),
    'input_verification_sha256':digest(study.INPUT_AUDIT),'original_native_fit_cases':487,'original_native_test_cases':179,
    'source_actual_fit_pairs':851,'source_reserved_pairs':206,'shared_inputs':11,'native_private_inputs':16,
    'new_joint_network_fits':40,'new_native_base_fits_for_cv':0,'minimum_cv_for_new_test_evaluation':.65,
    'test_used_for_selection':False,'synthetic_rows':0,'coefficient_outputs':3,'logit_outputs':21,
    'last_layer_parameters':27,'full_residual_last_layer_parameters':189,
    'basis_convention':'column-centered reducedQR of[delta,delta squared,zero indicator],Q*sqrt21',
    'basis':study.ordered_basis().tolist(),'basis_is_mathematical_class_geometry':True,
    'penalty_convention':'lambda*mean of squared expanded centered21residual;equals mean row squared coefficient norm',
    'penalties':[.1,1.],'source_weights':[0.,.1],'epochs':80,'learning_rate':.003,'weight_decay':.1,
    'controls':{'native_global':2,'full_residual_same_penalties':8,'full_residual_stronger_penalties':4,'scalar_gates':4},
    'rationale':'Strong shrinkage largely restored baseline decisions. A fixed three-dimensional output '
        'geometry retains zero/magnitude/dispersion shifts with fewer parameters. All other inputs, '
        'source head,normalization,base weights and optimizer stay fixed. Full-residual same-penalty '
        'controls and exact shared/source initialization allow a direct comparison. No synthetic '
        'observations,source current context or transformed targets. Refit all8new recipes in5personfolds '
        'and independently verify all26OOFmetrics/40fold artifacts and coefficient-chain gradients.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':26,'new_joint_network_fits':40,'predictive_fitting_started':False}),flush=True)
