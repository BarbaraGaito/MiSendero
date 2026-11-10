"""Record the fixed live native baseline comparison without claiming success."""
import json
from pathlib import Path

import fatigue_cadence_session_rest as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection = json.loads((study.DIRECTORY/"selection.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) == (42,1664)
    assert selection["status"] == "running" and selection["plan"] == study.plan() and len(study.plan()) == 34
    assert selection["code_sha256"] == digest(Path(study.__file__)) and not selection["source_functions_refitted"]
    tests = (folder/"cadence-session-rest-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    assert status["python_tests_passed"] in (236,240)
    status["python_tests_passed"] = 240
    status["python_test_evidence"]["additional_actual_session_rest_suite"] = {"tests":4,"log":"cadence-session-rest-tests.log"}
    data_audit = json.loads(study.INPUT_AUDIT.read_text())
    assert data_audit["verification"] == "passed" and data_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_session_rest_inputs.py"))
    assert data_audit["input_provenance_sha256"] == digest(study.rest.DIRECTORY/"provenance.json")
    assert data_audit["original_native_cases_independently_verified"] == 666 and data_audit["natural_missing_baselines_per_feature"] == 30
    status["native_session_rest_input_opportunity"].update(new_model_fitting_started=True,used_in_study=study.DIRECTORY.name)
    status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":34,
        "new_native_recipes_including_measured_controls":28,"predeclared_native_folds":140,
        "actual_source_fitting_targets_in_frozen_functions":976,"source_functions_refitted":False,
        "baseline_definitions":["Measured pre-first-task mean","Lowest measured complete pre-first-task minute"],
        "native_baseline_available_cases":636,"native_baseline_missing_cases_retained":30,
        "training_log":"cadence-session-rest-training.log","counted_as_complete":False}
    status["next_evidence_based_direction"] = (
        "Previous turn completed and audited source association30recipes,6source refits/25native refits and636/666 observed native pre-first-task baselines: concrete progress. "
        "Current34recipe study is running with six inherited controls, four measured controls and24 representations over two real session baselines, six frozen source functions and two native classifiers. "
        "Modes fixed from preceding native CV:MLP current state,CatBoost current state plus calculated change. Source functions still reflect976 actual6-20 targets/124 people, with238 source targets/32 people reserved; no source fitting occurs here. "
        "All native487/179 exact Borg cases and original columns retained, including30 natural missing session baselines. Four real-public-data tests passed. Wait on/revalidate the specific running process before resuming, then independently reproduce completed scores/fitting before any qualified frozen179 test evaluation. No synthetic data, label conversion, invented source clocks, assumed rest posture or test tuning.")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"completed_studies":42,"completed_configurations":1664,"running_configurations":34,
        "distinct_tests_cumulative":240,"source_functions_refitted":False,"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
