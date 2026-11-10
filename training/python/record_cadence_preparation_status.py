"""Record verified real-input preparation and the live transfer study."""
import json
from pathlib import Path

import cadence_lagged_rpe as source
import fatigue_cadence_native_inputs as native
import fatigue_cadence_transfer as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    audit_path = folder/"cadence-lagged-input-verification.json"
    audit = json.loads(audit_path.read_text())
    selection = json.loads((study.DIRECTORY/"selection.json").read_text())
    assert audit["verification"] == "passed" and audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_cadence_lagged_inputs.py"))
    assert audit["source_provenance_sha256"] == digest(source.DIRECTORY/"provenance.json")
    assert audit["native_provenance_sha256"] == digest(native.DIRECTORY/"provenance.json")
    assert selection["status"] in {"running","complete"} and selection["code_sha256"] == digest(Path(study.__file__))
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) == (39,1586)
    tests = (folder/"cadence-transfer-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    status["python_tests_passed"] = 228
    status["additional_data_audits"][audit_path.name] = digest(audit_path)
    status["python_test_evidence"]["additional_actual_cadence_transfer_suite"] = {"tests":4,"log":"cadence-transfer-tests.log"}
    status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":16,
        "new_native_recipes_including_physiology_controls":14,"actual_source_fitting_targets":851,
        "actual_source_reserved_targets":206,"training_log":"cadence-transfer-training.log","counted_as_complete":False}
    status["cadence_public_candidate"].update(fitting_started=True,used_in_study=study.DIRECTORY.name)
    status["cadence_lagged_source_adapter"] = {"directory":source.DIRECTORY.name,"original_rpe_scale":"6-20",
        "actual_source_pairs":1057,"fitting_actual_targets":851,"reserved_actual_targets":206,
        "original_source_people_partitioned":{"fitting":124,"reserved":32},"eligible_source_people":{"fitting":123,"reserved":32},
        "current_bout_hr_used":False,"exact_report_clocks_invented":False,"native_target_merge_approved":False,
        "input_verification":audit_path.name,"native_cases_retained":666,"native_missing_lag_hr":3,"native_missing_baseline_hr":8,
        "real_prior_hr_recovered":2,"real_baseline_hr_recovered":10}
    status["next_evidence_based_direction"] = (
        "Prepared and independently verified1057 actual CADENCE adjacent-stage targets with original Borg6-20.851 targets/123 eligible source people fit source-only regressors;206 targets/32 source people remain reserved. Exact report clocks stay unknown; current-boutHR and all older-cohort rows excluded. Rebuilt all666 native prior-HR/pre-task-baseline inputs from original digital biomarkers, joining seven cross-midnight sessions and recovering2 prior-HR/10 baseline values from real data. Four actual-public-snapshot tests passed. A fixed16-recipe transfer study is running with source absolute/relative physiology representations, matched measured-input controls and original native487/179 target cohorts. No synthetic data, label conversion or test tuning.")
    assert all(digest(folder/name) == sha for field in ("additional_scoped_verifications","additional_data_audits") for name,sha in status[field].items())
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"completed_studies":39,"completed_configurations":1586,"running_study":study.DIRECTORY.name,
        "actual_source_fitting_targets":851,"retained_native_test_correct":108,"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
