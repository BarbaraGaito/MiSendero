"""Freeze the predictor-alignment comparison before predictive fitting."""
import json
from pathlib import Path
import fatigue_domain_aligned_history as study
from public_sources import digest

proof = json.loads(study.PARENT_AUDIT.read_text())
assert proof['verification']=='passed' and proof['actual_native_joint_refits']==20
diagnostic = json.loads(study.DIAGNOSTIC.read_text())
assert diagnostic['diagnostic']=='passed' and diagnostic['native_test_predictions_computed']==0
report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'range_diagnostic_sha256':digest(study.DIAGNOSTIC),
    'actual_source_fitting_targets':2336,'source_reserved_targets':312,'source_fitting_actual_second_priors':1927,
    'original_native_fit_cases':487,'original_native_test_cases':179,'new_joint_network_fits':30,'new_native_base_fits':0,
    'native_preprocessing_fit':'outer_fold_fitting_people_only','source_preprocessing_fit':'each_domain_fitting_people_only',
    'numeric_columns_standardized_per_domain':2,'missing_second_history_indicator':'binary_preserved',
    'source_targets_transformed':False,'source_native_outcome_pooling':False,'synthetic_rows':0,
    'shoulder_weights':[0.,.1,1.],'fixed_epochs':80,'fixed_correction_penalty':10.,'minimum_cv_for_new_test_evaluation':.65,
    'test_used_for_selection':False,
    'rationale':'Fitting-only study50diagnostic found853/920shoulder priors beyond the first native fitting-fold range and87.39percent beyond3pooled standard deviations. Test a complete predictor-preprocessing recipe: separate native/source fitting-only numerical imputation+zscore,and preserve actual missing-history bits asbinary. Keep all source target points/deltas unchanged in separate heads; this is statistical representation alignment,not physiological Borgscaleequivalence. Matched aligned weightzero controls distinguish normalization effects from added shoulder supervision. Original native487/179cases and5personfolds,oldnetworkinitialization/nativebases,80epochs andpenalty10remainfixed.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':10,'new_joint_network_fits':30,'predictive_model_fitting_started':False}),flush=True)
