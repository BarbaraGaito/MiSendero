"""Register independently verified public source expansion;do not increment model studies."""
import json
from pathlib import Path
import rpe_expanded_binary_history_inputs as combined
from public_sources import digest

status_path = combined.DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed'])==(60,1956,322)
assert status['goal_status']=='active' and status['best_verified_test_correct']==108 and not status['goal_achieved']
gait_audit_path = combined.AUDITS['gait_forecasting']
union_audit_path = combined.DOCS/'rpe-expanded-binary-history-input-verification.json'
gait = json.loads(gait_audit_path.read_text())
union = json.loads(union_audit_path.read_text())
assert gait['verification']==union['verification']=='passed'
assert gait['verification_code_sha256']==digest(Path(__file__).with_name('audit_rpe_forecasting_history_inputs.py'))
assert union['verification_code_sha256']==digest(Path(__file__).with_name('audit_rpe_expanded_binary_history_inputs.py'))
assert gait['independently_rebuilt_actual_adjacent_pairs']==410 and gait['reserved_people_received']==0
assert union['actual_fitting_source_pairs']==3548 and union['additional_actual_gait_pairs']==410
assert gait['new_predictive_estimator_fits']==union['new_predictive_estimator_fits']==0
assert gait['new_test_predictions_computed']==union['new_test_predictions_computed']==0
fitting,reserved,manifest = combined.load()
for path in (gait_audit_path,union_audit_path):
    status['additional_data_audits'][path.name] = digest(path)
status['rpe_forecasting_candidate'].update(original_workbooks_verified=19,original_workbook_bytes=271700,
    original_target_cells_reviewed=True,unambiguous_original_reports=432,conflicting_trials_excluded=2,
    eligible_actual_adjacent_pairs=410,actual_second_priors=388,source_binary_head_eligibility_approved=True,
    case2_training_merge_approved=True,native_target_merge_approved=False,model_fitting_started=False,
    raw_input_verification=gait_audit_path.name,raw_input_verification_sha256=digest(gait_audit_path))
status['expanded_public_binary_histories'] = {'directory':combined.DIRECTORY.name,
    'provenance_sha256':digest(combined.DIRECTORY/'provenance.json'),'verification':union_audit_path.name,
    'verification_sha256':digest(union_audit_path),'actual_fitting_pairs':3548,'stored_reserved_pairs':518,
    'additional_actual_gait_pairs':410,'additional_gait_people':19,'gait_reserved_people_not_received':5,
    'actual_second_priors':3042,'source_counts':combined.COUNTS,'source_heads_must_remain_separate':True,
    'native_target_merge_approved':False,'source_physiology_fabricated':False,'model_comparison_predeclared':False,
    'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}
status['next_evidence_based_direction'] = (
    'Public raw-data expansion completed after study60.19original fitting workbooks were verified '
    'against pinned Git blobs and parsed independently from XLSX XML.6147stride rows contain434 '
    'identified trials;432have one unambiguous observed RPE.2conflicting trials,40unassigned rows '
    'and1physical row-order inversion remain in provenance. Do not invent IDs,ages or labels; '
    'actual source order follows authors numeric trial identifiers. Gait features are excluded '
    'because their pretarget clocks/placement/units are not aligned.410real adjacent pairs/388 '
    'second priors(158equal/252different) are approved only for a separate source binary head. '
    'The common history corpus now has3548fitting pairs across6domains(2287old four-domain+851 '
    'CADENCE+410gait),3042actual second priors,518stored reserved rows and5gait reserved people '
    'whose workbooks were not received. Next predeclare a distinct model using common actual two- '
    'report histories and separate source heads/domain fitting-only normalizers. Put measured '
    'native physiology in private native context;do not fabricate missing source physiology. '
    'Include matched new-source-weight-zero controls,source-zero controls and original native '
    'controls. The frozen851pair physiology/ordered models cannot be silently given a different '
    'source corpus. No new model fitting or accuracy claim yet. Keep original487/179,.65CVgate '
    'and144/179exact reloaded artifact matches;retained108/179and goal remains active.')
summary = {'version':1,'status':'data_prepared_and_independently_audited',
    'source_raw_input_verification_sha256':digest(gait_audit_path),'combined_input_verification_sha256':digest(union_audit_path),
    'combined_provenance_sha256':digest(combined.DIRECTORY/'provenance.json'),
    'original_gait_workbooks_verified':19,'original_gait_bytes':271700,
    'identified_trial_reports':434,'unambiguous_original_reports':432,'ambiguous_trials_not_used_as_targets':2,
    'additional_actual_gait_pairs':410,'additional_gait_people':19,'actual_gait_second_priors':388,
    'total_actual_auxiliary_fitting_pairs':3548,'total_actual_second_priors':3042,
    'stored_reserved_source_pairs':518,'gait_reserved_people_not_received':5,'source_counts':combined.COUNTS,
    'source_specific_heads_required':True,'source_target_scale_conversion':False,'native_target_merge_approved':False,
    'synthetic_rows':0,'synthetic_targets':0,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'model_comparison_predeclared':False,'model_studies_completed':60,'model_configurations_including_controls':1956,
    'distinct_python_tests_passed':322,'native_fitting_cases':487,'native_test_cases':179,
    'retained_test_correct':108,'retained_test_accuracy':108/179,'required_correct_for_80_percent':144,'goal_achieved':False}
(combined.DOCS/'rpe-expanded-binary-history.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(combined.DOCS/name)==value for name,value in status[field].items())
status_path.write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary),flush=True)
