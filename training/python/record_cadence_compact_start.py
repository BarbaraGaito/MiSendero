"""Record a live frozen compact comparison without counting it completed."""
import json
from pathlib import Path

import fatigue_cadence_compact as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection = json.loads((study.DIRECTORY/"selection.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) == (40,1602)
    assert selection["status"] == "running" and selection["plan"] == study.plan() and len(study.plan()) == 32
    assert selection["code_sha256"] == digest(Path(study.__file__))
    tests = (folder/"cadence-compact-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    assert status["python_tests_passed"] in (228,232)
    status["python_tests_passed"] = 232
    status["python_test_evidence"]["additional_actual_compact_cadence_suite"] = {"tests":4,"log":"cadence-compact-tests.log"}
    status["running_study"] = {"directory":study.DIRECTORY.name,"planned_configurations_including_controls":32,
        "new_native_recipes_including_measured_relative_controls":26,"actual_source_fitting_targets":851,
        "actual_source_reserved_targets":206,"source_functions_refitted":False,"training_log":"cadence-compact-training.log",
        "counted_as_complete":False}
    status["next_evidence_based_direction"] = (
        "The previous turn completed and independently audited CADENCE transfer: concrete progress, though no improvement over the retained native model. "
        "Current fixed compact comparison is running32 configurations:6 inherited controls,2 measured-relative controls,18MLP proxy recipes(3relative source functions,2architectures,3L2 values) and6CatBoost proxy recipes. "
        "A source proxy enters the native classifier instead of four redundant raw absolute/relative fields. Eleven naturally unavailable measured pairs propagate missing representation values, with fold-local native imputation and no added/removed cases. "
        "Four real-public-data tests passed. Source851 actual targets/123 people and206 reserved/32 people remain unchanged; source functions frozen. Original487/179 exact Borg and public-real-only policy remain fixed. Read actual process/log state before any resume, and audit completed CV before evaluating a newly qualified original179 test artifact.")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"completed_studies":40,"completed_configurations":1602,"running_configurations":32,
        "distinct_tests_cumulative":232,"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
