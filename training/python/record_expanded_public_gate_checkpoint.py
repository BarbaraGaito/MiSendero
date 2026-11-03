"""Register the completed, independently audited expanded public-history study."""
import json
from pathlib import Path
import fatigue_expanded_public_gate as study
from check_expanded_public_gate_checkpoint_integrity import evidence
from public_sources import digest

inputs,selected,audit,diagnostic=evidence()
status_path=study.DOCS/'current-research-status.json'
status=json.loads(status_path.read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'],status['python_tests_passed']) in ((60,1956,322),(61,1980,329))
status.update(completed_studies=61,evaluated_configurations_including_controls=1980,python_tests_passed=329)
status.pop('running_study',None)
audit_path=study.DOCS/'expanded-public-gate-verification.json'
status['additional_scoped_verifications'][audit_path.name]=digest(audit_path)
status['expanded_public_binary_histories'].update(model_comparison_predeclared=True,model_study_completed=True,used_in_study=study.DIRECTORY.name)
status['rpe_forecasting_candidate'].update(model_fitting_started=True,model_study_completed=True,used_in_study=study.DIRECTORY.name)
status['expanded_public_gate_proposal']={'document':study.PROPOSAL.name,'sha256':digest(study.PROPOSAL),
    'model_study_completed':True,'used_in_study':study.DIRECTORY.name,'configurations':24,'new_trainable_recipes':16,
    'new_joint_network_fits':80,'independent_joint_refits':80,'new_native_base_fits_for_cv':0,
    'source_fitting_actual_pairs':3548,'source_reserved_pairs_not_fitted':518,'gait_reserved_people_not_received':5,
    'shared_history_encoder_features':3,'native_private_features':20,'source_heads':6,
    'source_private_context_fabricated':False,'source_instrument_scales_converted_to_native_targets':False}
status['latest_complete_results'].update(expanded_public_gate_best_gait_source_cv=audit['best_positive_cv_accuracy'],
    expanded_public_gate_mlp_gait_source_cv=audit['best_positive_by_member']['core']['accuracy_mean'],
    expanded_public_gate_catboost_gait_source_cv=audit['best_positive_by_member']['cat']['accuracy_mean'],
    expanded_public_gate_best_overall_cv=audit['best_cv_accuracy'])
test=audit['new_test_evaluation']
if test and test['test_correct']>status['best_verified_test_correct']:
    status.update(best_verified_test_correct=test['test_correct'],best_verified_test_accuracy=test['test_accuracy'],
        best_verified_test_artifact=str(study.DIRECTORY/'evaluation/model.joblib'))
status['goal_achieved']=status['best_verified_test_correct']>=144
diagnostic_path=study.DOCS/'expanded-public-gate-diagnostic.json'
status['expanded_public_gate_diagnostic']={'document':diagnostic_path.name,'sha256':digest(diagnostic_path),
    'fitting_queries':487,'fitting_only':True,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}
status['next_evidence_based_direction']=(
    'Study61 completed24recipes(8inherited controls/16new),80new networks and80independent refits. '
    'Actual3548public fitting pairs across6heads include410new original gait reports;shared3history '
    'inputs and20native-private measured/history features. The comparison controls old-source weights '
    'and total auxiliary mass;no native targets/scales are merged or fabricated. '
    f"Best expanded source CV={audit['best_positive_cv_accuracy']:.12f};global CV={audit['best_cv_accuracy']:.12f}. "
    f"Fit native NLL decreased for{diagnostic['native_fit_nll_reduced_recipes']}/16recipes and validation NLL decreased "
    f"for{diagnostic['native_validation_nll_reduced_recipes']}/16. "
    'Inspect all four expanded-vs-legacy/mass/native paired comparisons rather than only the '
    'strong-penalty recipes that preserve baseline predictions. The frozen change-only correction '
    'cannot repair a wrong nonzero-delta conditional;use fitting-only evidence to identify whether '
    'remaining errors need temporal/context support or a different native learning objective before '
    'predeclaring another model. No newtest qualifies unless CV>=.65. Keep original487/179, '
    'literal native classes,real public observations and144/179exact reloaded artifact matches. '
    f"Retained{status['best_verified_test_correct']}/179;goal remains active unless independently achieved.")
summary={'version':1,'status':'complete','selection_sha256':digest(study.DIRECTORY/'selection.json'),
    'verification_sha256':digest(audit_path),'input_verification_sha256':digest(study.INPUT_AUDIT),
    'configurations':24,'new_trainable_recipes':16,'new_joint_network_fits':80,'independent_joint_refits':80,
    'new_native_base_fits_for_cv':0,'source_fitting_actual_pairs':3548,'source_reserved_pairs':518,
    'gait_reserved_people_not_received':5,'shared_encoder_features':3,'native_private_features':20,
    **{name:audit[name] for name in ('best_positive_by_member','matched_zero_source_controls','matched_legacy_source_controls','matched_total_weight_controls')},
    'winner_id':selected['winner_id'],'best_cv_accuracy':selected['best_cv_accuracy'],
    'real_tests_code_sha256':digest(Path(__file__).with_name('test_fatigue_expanded_public_gate.py')),
    'real_tests_log_sha256':digest(study.DOCS/'expanded-public-gate-tests.log'),'error_diagnostic_sha256':digest(diagnostic_path),
    'paired_oof_comparisons':diagnostic['paired_oof_comparisons'],
    'all_expanded_recipe_paired_comparisons':diagnostic['all_expanded_recipe_paired_comparisons'],
    'new_test_evaluation':test,'retained_test_correct':status['best_verified_test_correct'],
    'retained_test_accuracy':status['best_verified_test_accuracy'],'target_accuracy':.8,'achieved':status['goal_achieved'],
    'results':[{k:r[k] for k in ('candidate','accuracy_mean','fold_accuracy')} for r in selected['results']]}
(study.DOCS/'expanded-public-gate.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(study.DOCS/name)==value for name,value in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'completed_studies':61,'completed_configurations':1980,'distinct_tests':329,
    'best_cv_accuracy':audit['best_cv_accuracy'],'retained_test_correct':status['best_verified_test_correct'],
    'goal_achieved':status['goal_achieved']}),flush=True)
