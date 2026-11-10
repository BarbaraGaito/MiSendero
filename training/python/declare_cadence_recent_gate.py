"""Predeclare the native recent-HR comparison before any predictive fit."""
import json
from pathlib import Path
import fatigue_cadence_recent_gate as study
from public_sources import digest

audit = json.loads(study.INPUT_AUDIT.read_text())
assert audit['verification']=='passed' and audit['native_cells_independently_rebuilt']==666
report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'input_verification_sha256':digest(study.INPUT_AUDIT),'previous_verification_sha256':digest(study.PARENT_AUDIT),
    'source_fitting_actual_pairs':851,'source_reserved_pairs':206,'source_actual_second_priors':727,
    'original_native_fit_cases':487,'original_native_test_cases':179,'new_joint_network_fits':20,'new_native_base_fits':0,
    'minimum_cv_for_new_test_evaluation':.65,'test_used_for_selection':False,'synthetic_rows':0,
    'new_native_private_features':study.added.COLUMNS,'total_native_private_features':16,
    'shared_encoder_and_source_features_changed':False,'source_current_hr_introduced':False,
    'independent_refit_policy':'All4new recipes in all5personfolds;20fold artifacts and10OOFmetrics.',
    'rationale':'Study56source physiology repaired2matched-control errors but no global-control errors. '
        'Its private native context still lacked recent pulse. Add actual current HR and subtraction/ratio '
        'to genuinely earlier report HR,with all666clocks verified and natural missing contrasts preserved. '
        'Keep six inherited global/old-context controls and matched new source0/.1 controls. Only native '
        'private context gains these3features. Keep source851actual pairs and shared6numeric/5availability '
        'encoder,original scales/targets,frozen native base/nonzero-delta ratios,80epochs,penalty1 and '
        'AdamW.003/decay.1. Fit preprocessing only within training people;all487/179remain required.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':10,'new_joint_network_fits':20,'source_fitting_actual_pairs':851,
    'native_private_features':16,'predictive_fitting_started':False}),flush=True)
