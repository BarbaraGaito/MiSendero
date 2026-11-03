"""Read-only integrity check of scoped evidence; no historical model refits."""
import json
from pathlib import Path

import fatigue_cadence_transfer as study
from public_sources import ROOT, digest


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status = json.loads((folder/"current-research-status.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (40,1602,228)
    assert status["goal_status"] == "active" and not status["goal_achieved"] and "running_study" not in status
    assert status["best_verified_test_correct"] == 108 and status["best_verified_test_accuracy"] == 108/179
    assert status["original_training_cases"] == 487 and status["original_test_cases"] == 179
    assert status["required_correct_for_80_percent"] == 144
    checked = 0
    for field in ("additional_scoped_verifications","additional_data_audits"):
        for name,expected in status[field].items():
            assert digest(folder/name) == expected,(field,name)
            checked += 1
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["status"] == "complete" and all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert len(selection["results"]) == len(selection["plan"]) == 16
    audit_path = folder/"cadence-transfer-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_transfer.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT)
    summary = json.loads((folder/"cadence-physiology-transfer.json").read_text())
    assert summary["verification_sha256"] == digest(audit_path) and summary["selection_sha256"] == digest(selection_path)
    candidate = json.loads((folder/"light-exercise-eligibility.json").read_text())
    assert candidate["audit_code_sha256"] == digest(Path(__file__).with_name("audit_light_exercise_eligibility.py"))
    assert candidate["actual_coded_participant_rows"] == 24 and candidate["numeric_B_cells"] == 1121
    assert not candidate["training_approved"] and not candidate["used_for_training"]
    print(json.dumps({"integrity":"passed","studies":40,"configurations":1602,"distinct_tests_cumulative":228,
        "scoped_evidence_hashes_checked":checked,"source_regressors_refitted_by_saved_audit":6,
        "native_refits_in_saved_audit":len(audit["actual_native_refits"]),"retained_test_correct":108,
        "retained_test_cases":179,"best_verified_test_accuracy":108/179,"goal":"active;80percent not achieved",
        "historical_model_refitting_performed_by_this_integrity_check":False}),flush=True)


if __name__ == "__main__":
    validate()
