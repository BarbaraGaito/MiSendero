"""Record live association study and completed input/test evidence."""
import json
from pathlib import Path

import fatigue_cadence_association as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection = json.loads((study.DIRECTORY/"selection.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) == (41,1634)
    assert selection["status"] == "running" and selection["plan"] == study.plan() and len(study.plan()) == 30
    assert selection["code_sha256"] == digest(Path(study.__file__))
    tests = (folder/"cadence-association-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    assert status["python_tests_passed"] in (232,236)
    status["python_tests_passed"] = 236
    status["python_test_evidence"]["additional_actual_source_association_suite"] = {"tests":4,"log":"cadence-association-tests.log"}
    data_audit = json.loads(study.INPUT_AUDIT.read_text())
    assert data_audit["verification"] == "passed" and data_audit["actual_native_cases_independently_rebuilt"] == 666
    assert data_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_cadence_association_inputs.py"))
    assert data_audit["source_provenance_sha256"] == digest(study.prepared.SOURCE_DIRECTORY/"provenance.json")
    assert data_audit["native_provenance_sha256"] == digest(study.prepared.NATIVE_DIRECTORY/"provenance.json")
    status["additional_data_audits"][study.INPUT_AUDIT.name] = digest(study.INPUT_AUDIT)
    status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":30,
        "new_native_recipes_including_measured_controls":26,"actual_source_fitting_targets":976,"actual_source_reserved_targets":238,
        "source_task":"Retrospective concurrent association, not source pre-RPE forecasting","native_queries_past_only":True,
        "training_log":"cadence-association-training.log","counted_as_complete":False}
    status["cadence_retrospective_association_opportunity"].update(model_fitting_started=True,used_in_study=study.DIRECTORY.name,
        independent_input_verification=study.INPUT_AUDIT.name,independent_adapter_audit_required=False)
    status["cadence_association_frozen_inputs"] = {"source_directory":study.prepared.SOURCE_DIRECTORY.name,
        "native_directory":study.prepared.NATIVE_DIRECTORY.name,"source_provenance_sha256":data_audit["source_provenance_sha256"],
        "native_provenance_sha256":data_audit["native_provenance_sha256"],"source_fitting_targets":976,"source_reserved_targets":238,
        "source_fitting_people":124,"source_reserved_people":32,"native_original_cases":666,
        "native_missing_counts":data_audit["native_missing_counts"],"newer_real_current_minutes_recovered":2,
        "source_target_scale":"6-20, unchanged and separate","native_target_scale":"0-10, unchanged",
        "native_current_borg_in_inputs":False,"synthetic_rows":0}
    status["next_evidence_based_direction"] = (
        "Previous turn completed and audited compact CADENCE selection: concrete progress without native test improvement. "
        "Current source-association study is running30 fixed recipes after independent raw-cell/window audit and4 real-public-data tests. "
        "Source1214 actual concurrent physiology/RPE6-20 rows preserve the original124/32-person split:976 fit,238 reserved. This is retrospective association and does not claim pre-RPE availability of source same-bout HR. "
        "Every native query uses actual completed pre-query pulse and genuine prior-report pulse, plus measured pre-task baseline. Source states/differences are computed features only. All original666 cases and487/179 exact targets remain unchanged; natural missing inputs retained,2 newer actual cross-midnight current minutes recovered. "
        "Revalidate the live process before any resume. Once complete, reproduce source/native fitting and select only by native person CV before opening any newly qualified frozen original179 test artifact. No synthetic data, native label conversion or test tuning.")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"completed_studies":41,"completed_configurations":1634,"running_configurations":30,
        "distinct_tests_cumulative":236,"input_audit":"passed","goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
