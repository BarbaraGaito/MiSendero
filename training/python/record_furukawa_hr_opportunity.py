"""Link independently audited original runner inputs and their frozen model plan."""
import json
from pathlib import Path

import fatigue_furukawa_hr_transfer as study
from public_sources import digest

status_path = study.DOCS/"current-research-status.json"
status = json.loads(status_path.read_text())
assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (47,1762,256)
inputs = study.load_inputs()
original_path = study.DOCS/"furukawa-original-rpe-verification.json"
original = json.loads(original_path.read_text())
assert original["verification"] == "passed" and original["original_actual_responses"] == 336
assert original["audit_code_sha256"] == digest(Path(__file__).with_name("audit_furukawa_original_rpe.py"))
audit = json.loads(study.INPUT_AUDIT.read_text())
assert audit["verification"] == "passed" and audit["all_pre_report_hr_features_independently_recomputed"]
assert audit["source_fitting_targets"] == 252 and audit["source_reserved_targets"] == 84
for path in (original_path,study.INPUT_AUDIT):
    status["additional_data_audits"][path.name] = digest(path)
status["furukawa_pre_report_hr_opportunity"] = {"source_directory":study.source.DIRECTORY.name,
    "provenance_sha256":digest(study.source.DIRECTORY/"provenance.json"),"input_audit":study.INPUT_AUDIT.name,
    "original_report_audit":original_path.name,"actual_original_responses":336,"source_fitting_targets":252,
    "source_fitting_people":12,"reserved_source_targets":84,"source_reserved_people":4,
    "source_fitting_adjacent_pairs":168,"source_fitting_actual_second_priors":84,
    "source_outcome":"original_Japanese_Borg_points_separate_from_native_CR10",
    "experiment2_only_no_cross_experiment_person_mapping":True,"native_target_merge":False,
    "actual_strictly_pre_report_hr_samples":True,"synthetic_rows":0,"model_fitting_started":False}
status["next_furukawa_hr_proposal"] = {"document":study.PROPOSAL.name,"sha256":digest(study.PROPOSAL),
    "implementation_started":True,"model_fitting_started":False,"planned_configurations_including_controls":14,
    "planned_new_native_folds":50,"source_state_targets":252,"source_delta_targets":168,
    "source_algorithms":["ridge","svr"],"native_members":["core","cat"]}
status["other_new_public_candidates"]["runners"].update(status="Experiment2only original336RPEcells and strictly preceding HRpoints independently audited/prepared,252fitting/84reserved,with no invented cross-experiment person join or source target conversion;four-source-function14recipe comparison declared",model_fitting_started=False)
status["next_evidence_based_direction"] = (
    "Study47completed22recipes/30independent real-loss refits; best new positive.6299158914CVbelow inherited.6379721574. "
    "Next source336original experiment2runner Borgpoint cells has252fitting targets/12people,84held/4people,and168actual fitting adjacentpairs. "
    "Independent XLSX-XML audit verifies all targetcells,HRvalues,strict timestamps,natural missing priors and person split. New state252versus actualdelta168functions use Ridge/SVR,source outcomes separate,with14frozenrecipes/50new native folds. "
    "Keep all487/179native cases and.65CVtest gate. Native/source HRwindows and ranges differ; do not invent a resting baseline,person correspondence,source timing/scaleconversion or interval dependence. "
    "Model48has not fitted yet; implement/verify actual-public tests and run the bounded declared comparison rather than repeat completed regularization grids. Goal80needs144of179from a frozen reloaded artifact,retained108.")
for field in ("additional_scoped_verifications","additional_data_audits","additional_public_candidate_inspections"):
    assert all(digest(study.DOCS/name) == expected for name,expected in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
print(json.dumps({"completed_studies":47,"completed_configurations":1762,"audited_source_fitting_targets_available_for_next_study":252,
    "actual_source_fitting_pairs":168,"source_reserved_targets":84,"new_study_fitted":False,"goal_achieved":False}),flush=True)
