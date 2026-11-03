"""Record the verified real-response expansion without claiming a fitted model."""
import json
from pathlib import Path

import fatigue_resistance_history_inputs as source
import fatigue_two_history_joint as joint
from public_sources import digest


def record():
    path = source.DOCS/"current-research-status.json"
    status = json.loads(path.read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (46,1740,252)
    assert status["goal_status"] == "active" and not status["goal_achieved"] and status["best_verified_test_correct"] == 108
    original_path = source.AUDIT
    original = json.loads(original_path.read_text())
    assert original["verification"] == "passed" and original["audit_code_sha256"] == digest(Path(__file__).with_name("audit_resistance_reported_rpe.py"))
    assert original["all1003reports_match_original_cells_bijectively"] and not original["smote_or_jitter_samples_used"]
    input_path = source.DOCS/"resistance-history-input-verification.json"
    inputs = json.loads(input_path.read_text())
    assert inputs["verification"] == "passed" and inputs["audit_code_sha256"] == digest(Path(__file__).with_name("audit_resistance_history_inputs.py"))
    assert inputs["source_preparation_code_sha256"] == digest(Path(source.__file__)) and inputs["source_provenance_sha256"] == digest(source.DIRECTORY/"provenance.json")
    assert inputs["combined_source_fitting_targets"] == 1416 and inputs["combined_source_fitting_actual_second_priors"] == 1169
    assert not inputs["model_fitting_started"] and inputs["resistance_fitting_pairs"] == 866 and inputs["resistance_reserved_pairs"] == 68
    diagnostic_path = source.DOCS/"two-history-joint-regularization-diagnostic.json"
    diagnostic = json.loads(diagnostic_path.read_text())
    assert diagnostic["code_sha256"] == digest(Path(__file__).with_name("diagnose_two_history_joint_regularization.py"))
    assert diagnostic["selection_sha256"] == digest(joint.DIRECTORY/"selection.json")
    assert diagnostic["pairs_with_lower_fitting_loss_and_lower_cv_at200"] == 5 and not diagnostic["native_test_targets_used"]
    for evidence in (original_path,input_path,diagnostic_path):
        status["additional_data_audits"][evidence.name] = digest(evidence)
    status["resistance_history_expansion_opportunity"] = {"source_directory":source.DIRECTORY.name,
        "source_provenance_sha256":inputs["source_provenance_sha256"],"original_response_verification":original_path.name,
        "input_verification":input_path.name,"original_manual_reports":1003,"original_sets":69,"original_people":5,
        "actual_adjacent_source_pairs":934,"additional_fitting_targets":866,"additional_fitting_people":4,
        "additional_reserved_targets":68,"additional_reserved_people":1,"existing_fitting_targets_preserved":550,
        "combined_fitting_targets":1416,"combined_stored_reserved_targets":125,"combined_fitting_actual_second_priors":1169,
        "published_resistance_scale":"1-10 as authored;separate source outcome","native_target_merge_approved":False,
        "model_fitting_started":False,"synthetic_rows":0,"imputed_targets":0,"source_clock_or_phase_mapping_invented":False}
    proposal_path = source.DOCS/"resistance-history-expansion-proposal.md"
    status["next_resistance_history_proposal"] = {"document":proposal_path.name,"sha256":digest(proposal_path),
        "implementation_started":False,"model_fitting_started":False,"planned_configurations_including_controls":22,
        "planned_new_network_folds":90,"new_source_head_weights":[0,.1,1],"correction_penalties":[.1,1,10],
        "epochs":80,"native_base_caches_to_reuse_from_previous_study":10,"new_native_base_fits_planned":0}
    inspections = {}
    for name,code in (("new-rpe-workbook-inspection.json","inspect_more_public_rpe_workbooks.py"),
        ("resistance-original-archive-inspection.json","inspect_resistance_original_archive.py")):
        report = json.loads((source.DOCS/name).read_text())
        assert report["inspection_code_sha256"] == digest(Path(__file__).with_name(code)) and not report["model_fitting_started"]
        inspections[name] = digest(source.DOCS/name)
    status["additional_public_candidate_inspections"] = inspections
    status["other_new_public_candidates"] = {
        "hift":{"public_record":"https://doi.org/10.6084/m9.figshare.25858906","original_workbook_checksum_verified":True,
            "status":"Original RPE/HR workbook inspected; instrument,cohort and temporal compatibility still need review","model_fitting_started":False},
        "runners":{"public_record":"https://doi.org/10.6084/m9.figshare.21779501","original_workbook_checksums_verified":True,
            "status":"Original RPE/time andHR sheets inspected;source instrument/person mapping and causal windows require a separate adapter","model_fitting_started":False},
        "motor_exercise":{"public_record":"https://doi.org/10.26180/24319813","original_workbook_checksum_verified":True,
            "status":"No original RPE column in the public supporting workbook;not eligible as a measured Borg target source","model_fitting_started":False}}
    status["next_evidence_based_direction"] = (
        "Study46joint actual-history backpropagation remains below original.6379721574CV control:best positive Cat.6222534311 vs matched zero.6163710782;original test retained108/179. "
        "Fiveof6paired epoch profiles lowered native fitting loss and worsenedCV at200epochs,supporting a different correction-regularization axis. "
        "A genuinely new original manual source is now independently verified:1003human resistance RPEreports/69sets/5people,allmatchingoriginal CSVcells andcanonical RPEcolumns;count-metadata undercounts2preserved,not labels changed. "
        "New source934adjacent pairs are866fitting/4people and68reserved/1person with split before pair eligibility. A versioned independently rebuilt union preserves550previous fitting targets and adds866,for1416source fitting targets and1169genuine second priors. No new native labels or times invented;no study SMOTE/jitter/learned EMG labels or supplied weights used. "
        "Next implement resistance-history-expansion-proposal.md:22recipes,4inherited controls plus18new(2native bases x3correction penalties.1/1/10 x3new-source weights0/.1/1),fixed80epochs and preceding best positive source weights per member. Reuse the10verified native base caches,fit no new native bases. Keep old550+native-fold normalization andinitialize the new head after the old3so zero-new-weight/penalty.1 reproduces the preceding matched predictions. "
        "Only actual source/native rows;new1-10resistance outcome stays a separate head. Preserve original487/179exact labels,person CV and.65new-test gate.80percent goal remains active and unachieved;new expanded source cache has not entered model fitting.")
    for field in ("additional_scoped_verifications","additional_data_audits","additional_public_candidate_inspections"):
        assert all(digest(source.DOCS/name) == expected for name,expected in status[field].items())
    path.write_text(json.dumps(status,indent=2,ensure_ascii=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"completed_studies":46,"completed_configurations":1740,"cumulative_distinct_tests":252,
        "source_input_audit":"passed","additional_actual_source_fitting_targets":866,"combined_actual_source_fitting_targets":1416,
        "actual_source_fitting_second_priors":1169,"new_source_models_fitted":False,"best_verified_test_accuracy":108/179,
        "goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
