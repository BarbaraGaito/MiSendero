"""Freeze the actual-source shoulder comparison before any model fitting."""
import json
from pathlib import Path
import fatigue_shoulder_history_joint as study
from public_sources import digest

proof = json.loads(study.INPUT_AUDIT.read_text())
assert proof['verification']=='passed' and proof['actual_source_fitting_targets']==2336
assert len(study.plan())==10
report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'source_input_verification_sha256':digest(study.INPUT_AUDIT),
    'preceding_schedule_verification_sha256':digest(study.PARENT_AUDIT),
    'original_joint_verification_sha256':digest(study.BASE_AUDIT),
    'overfit_diagnostic_sha256':digest(study.DOCS/'catboost-schedule-fit-cv-diagnostic.json'),
    'actual_source_fitting_targets':2336,'new_shoulder_fitting_targets':920,'new_shoulder_fitting_people':27,
    'source_reserved_targets':312,'new_shoulder_reserved_targets':187,'new_shoulder_reserved_people':7,
    'source_fitting_actual_second_priors':1927,'original_native_fit_cases':487,'original_native_test_cases':179,
    'new_joint_network_fits':30,'new_native_base_fits':0,'shoulder_weights':[0.,.1,1.],
    'fixed_epochs':80,'fixed_correction_penalty':10.,'minimum_cv_for_new_test_evaluation':.65,
    'test_used_for_selection':False,'synthetic_rows':0,'source_native_outcome_pooling':False,
    'rationale':'Native rate/tree grid49reproduced originalcontrols and seven fitting-better/CV-worse budget transitions. Do not extend epochs. Add920actual timed shoulder pairs/27people to1416old actualsource pairs as a fifth separate original6-20delta head. Native inputs remain original0-10reports; no point conversion,source clocks/native phases or sensor join inferred. Keep original old550source normalization and old four-head initialization; shoulderweight0must exactly reproduce old47bestpositive predictions/losses. Compare weights0/.1/1with core/Cat,80epochs,penalty10 and original frozen basecaches. Original487/179native cases and5personfolds unchanged.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':10,'new_joint_network_fits':30,'new_native_base_fits':0,'model_fitting_started':False}))
