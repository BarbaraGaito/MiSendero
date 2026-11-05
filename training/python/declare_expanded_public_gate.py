"""Predeclare expanded source supervision and matched source-mass controls."""
import json
from pathlib import Path
import fatigue_expanded_public_gate as study
from public_sources import digest

report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'input_verification_sha256':digest(study.INPUT_AUDIT),
    'original_native_fit_cases':487,'original_native_test_cases':179,'source_fitting_pairs':3548,
    'stored_reserved_source_pairs':518,'gait_reserved_people_not_received':5,'source_counts':study.COUNTS,
    'shared_inputs':3,'native_private_inputs':20,'source_specific_heads':6,'new_joint_network_fits':80,
    'new_native_base_fits_for_cv':0,'epochs':80,'learning_rate':.003,'weight_decay':.1,'penalties':[1.,10.],
    'minimum_cv_for_new_test_evaluation':.65,'test_used_for_selection':False,'synthetic_rows':0,
    'source_weight_modes':{'native_only':[0.,0.],'legacy_sources':[.1,0.],'expanded_sources':[.1,.02],'matched_total_weight':[.12,0.]},
    'source_loss_convention':'legacy_weight/5 times sum of5person-balanced domain BCEs plus gait_weight times its original-report BCE',
    'rationale':'The audited corpus adds410actual adjacent RPE pairs/19people and combines3548source '
        'pairs without equating instruments. Share only actually measured first/second histories and '
        'availability. Private native context includes actual prior/recent HR(20features total), '
        'so source physiology is not fabricated. Six source heads/normalizers stay separate. '
        'Matched new-weight-zero and matched total auxiliary weight controls isolate data contribution '
        'from simple loss-strength increase. Frozen native nonzero delta ratios and classifiers preserve '
        'the original exact-Borg control. Independent audit refits all16new recipes/all5personfolds '
        'and verifies actual source/gait encoder gradients,80backward steps and all24OOFmetrics.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':24,'new_joint_network_fits':80,'predictive_fitting_started':False}),flush=True)
