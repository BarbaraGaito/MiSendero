"""Freeze the14-recipe full-delta/source-binary comparison before fitting."""
import json
from pathlib import Path
import fatigue_cadence_full_delta as study
from public_sources import digest

report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'review_sha256':digest(study.REVIEW),
    'input_verification_sha256':digest(study.INPUT_AUDIT),'original_native_fit_cases':487,'original_native_test_cases':179,
    'source_actual_fit_pairs':851,'source_reserved_pairs':206,'shared_inputs':11,'native_private_inputs':16,
    'new_joint_network_fits':40,'new_native_base_fits_for_cv':0,'minimum_cv_for_new_test_evaluation':.65,
    'test_used_for_selection':False,'synthetic_rows':0,'residual_outputs':21,
    'native_objective':'cross_entropy(log_base_probability + centered21residual,actual_current_minus_prior+10)',
    'source_objective':'person-balanced BCE on actual unequal original6-20current/prior,one separate head',
    'penalty_convention':'lambda*mean of squared centered residual across actual native rows and21outputs',
    'penalties':[.1,1.],'source_weights':[0.,.1],'epochs':80,'learning_rate':.003,'weight_decay':.1,
    'architecture':'same11to8to8sharedencoder;corrector concat encoder8/context/21baseprobabilities to8to21;zero final layer',
    'rationale':'Scalar gate improvements in binary loss did not improve exact Borg.56core/57Cat fitting '
        'cases cannot be corrected by any scalar gate with the fixed nonzero delta branch. Earlier full '
        'residuals used only two histories and continuous source heads. This comparison combines real '
        'prior physiology and recent private native context with21native outputs and an unchanged separate '
        'CADENCEbinary head. Six inherited global/scalar controls and matched source-zero/positive recipes '
        'isolate effects. Base weights remain immutable;nonzero delta probabilities may now change. '
        'No source recent context,current-bout HR,scale conversion or artificial training rows. '
        'Independent audit recomputes all14OOFmetrics/all40fold artifacts and refits all8new recipes.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':14,'new_joint_network_fits':40,'predictive_fitting_started':False}),flush=True)
