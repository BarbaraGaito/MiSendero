"""Freeze a distinct causal retrieval mechanism before any new selection."""
import json
from pathlib import Path
import fatigue_causal_transition_memory as study
from public_sources import digest

proof = json.loads(study.PARENT_AUDIT.read_text())
coverage = json.loads(study.COVERAGE.read_text())
assert proof['verification']=='passed' and coverage['diagnostic']=='passed'
assert coverage['scope_coverage']['session']['queries_with_any_earlier_eligible_report']==455
report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'previous_verification_sha256':digest(study.PARENT_AUDIT),'coverage_sha256':digest(study.COVERAGE),
    'original_native_fit_cases':487,'original_native_test_cases':179,'native_full_base_classifiers_reused':10,
    'new_native_base_fits_for_selection':0,'new_preprocessor_fits':170,'feature_sets':study.FEATURE_SETS,
    'synthetic_rows':0,'source_rows_fitted_in_this_study':0,'minimum_cv_for_new_test_evaluation':.65,
    'test_used_for_selection':False,'population_artifact_stored_personal_reports':0,
    'rationale':'Actual earlier same-session transition memory is available for455of487fitting queries '
        'and task memory for391. Test an observed-transition kernel histogram, distinct from old population '
        'KNN and learned ridge/SGD adaptation. Keep matched zero-memory controls, fixed native bases, '
        'whole-person population folds and original outcome/cohort. Packets include only actual reports '
        'at least1minute earlier, selected before outcome access. Fit numeric imputation/scaling to '
        'outer fitting people only. Freeze2bases*2feature sets*2bandwidths*2strengths*2scopes=32positive '
        'recipes plus2zero controls and2inherited controls; no test-directed expansion.'}
assert len(report['plan'])==36
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':36,'new_native_base_fits':0,'predictive_selection_started':False}),flush=True)
