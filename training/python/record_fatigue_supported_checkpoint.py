"""Record the audited supported-physiology results and real-source review."""
import json
from pathlib import Path

import fatigue_supported_physiology as study
import walking_spe_transitions as walking
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    audit_path = folder/"supported-physiology-verification.json"
    audit = json.loads(audit_path.read_text())
    source_audit_path = folder/"walking-spe-eligibility.json"
    source_audit = json.loads(source_audit_path.read_text())
    assert selection["status"] == "complete" and len(selection["results"]) == len(selection["plan"]) == 11
    assert selection["code_sha256"] == digest(Path(study.__file__))
    assert audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_supported_physiology.py"))
    assert audit["best_verified_test_correct"] == 108 and not audit["achieved"] and not audit["new_test_gate_passed"]
    assert source_audit["verification"] == "passed" and source_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_walking_spe_eligibility.py"))
    assert source_audit["prepared_provenance_sha256"] == digest(walking.DIRECTORY/"provenance.json")
    assert source_audit["prepared_dataset_sha256"] == digest(walking.DIRECTORY/"dataset.csv")
    assert source_audit["actual_source_targets_with_genuine_prior_verified"] == 156
    assert not source_audit["model_fitting_started"] and not source_audit["hr_spe_positional_join_approved"]
    assert not source_audit["native_borg_target_merge_approved"]
    assert (status["completed_studies"], status["evaluated_configurations_including_controls"]) in ((36, 1531), (37, 1542))
    tests = (folder/"supported-physiology-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    status.update(completed_studies=37, evaluated_configurations_including_controls=1542, python_tests_passed=216)
    status.pop("running_study", None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["additional_data_audits"][source_audit_path.name] = digest(source_audit_path)
    status["latest_complete_results"].update({"supported_physiology_best_new_cv": audit["best_new_cv_accuracy"],
        "supported_physiology_best_positive_floor_cv": audit["best_positive_floor_cv_accuracy"],
        "supported_physiology_matching_zero_floor_cv": audit["matched_zero_floor_cv_accuracy"],
        "supported_physiology_best_control_cv": audit["best_cv_accuracy"]})
    status["next_evidence_based_direction"] = (
        "Bounded finite-support waveform correction remained below the history-only control, so no new test was opened. A newly retrieved public walking source (doi10.17632/mn3xyg2gh6.1) provides208 original SPE cells and156 actual within-table current/prior pairs at nominal five-minute intervals. Independent audit verified every target/prior against original archive bytes. HR tables have12 rows versus SPE13 without identity mapping; positional sensor joins are prohibited. Keep SPE-only outcomes as a separate auxiliary task with one conservative source-cohort cluster, no invented participant split, no unproven native Borg merge. Next combine these history-only auxiliary observations with compatible already verified source tasks and test source-specific representations on the original487 participant-disjoint cases. Original179 test and labels remain unchanged; no synthetic data.")
    status["new_public_walking_source"] = {"directory": walking.DIRECTORY.name, "source": walking.source.PAGE,
        "actual_current_targets_with_real_prior": 156, "anonymous_table_sequences": 52,
        "person_count_asserted": None, "single_conservative_source_cluster": True,
        "source_sensor_join_approved": False, "native_borg_target_merge_approved": False,
        "spe_only_auxiliary_eligible": True, "model_fitting_started": False,
        "verification": source_audit_path.name}
    for field in ("additional_scoped_verifications", "additional_data_audits"):
        assert all(digest(folder/name) == expected for name, expected in status[field].items())
    summary = {"version": 1, "status": "complete", "selection_sha256": digest(selection_path),
        "verification_sha256": digest(audit_path), "public_real_data_policy_sha256": digest(study.parent.source.POLICY),
        "configurations": len(selection["plan"]), "winner_id": selection["winner_id"],
        "best_cv_accuracy": selection["best_cv_accuracy"], "best_new_id": audit["best_new_candidate_id"],
        "best_new_cv_accuracy": audit["best_new_cv_accuracy"], "best_positive_floor_cv_accuracy": audit["best_positive_floor_cv_accuracy"],
        "matched_zero_floor_cv_accuracy": audit["matched_zero_floor_cv_accuracy"],
        "original_training_cases": 487, "original_test_cases": 179, "additional_actual_fitting_reports": 56,
        "results": [{"candidate": r["candidate"], "accuracy_mean": r["accuracy_mean"], "fold_accuracy": r["fold_accuracy"]} for r in selection["results"]],
        "new_test_gate_passed": False, "test_used_for_selection": False,
        "retained_test_correct": 108, "retained_test_accuracy": audit["best_verified_test_accuracy"], "target_accuracy": .8, "achieved": False,
        "scope": "Probability anchors regularized, actual integer targets unchanged. Real public observations only, original participant holdout and exact Borg metric. No synthetic data or artificial extra examples."}
    (folder/"supported-physiology.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    status_path.write_text(json.dumps(status, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"studies": status["completed_studies"], "configurations": status["evaluated_configurations_including_controls"],
        "best_new_cv": summary["best_new_cv_accuracy"], "retained_test": summary["retained_test_accuracy"],
        "new_actual_walking_source_pairs_verified": 156, "goal_achieved": False}), flush=True)


if __name__ == "__main__":
    record()
