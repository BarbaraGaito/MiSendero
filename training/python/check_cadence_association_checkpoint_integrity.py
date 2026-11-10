"""Read-only integrity of completed association study and prepared baselines."""
import ast
import json
from pathlib import Path

import fatigue_cadence_association as study
import fatigue_session_rest_inputs as rest
from public_sources import ROOT, digest


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status = json.loads((folder/"current-research-status.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (42,1664,236)
    assert status["goal_status"] == "active" and not status["goal_achieved"] and "running_study" not in status
    assert status["best_verified_test_correct"] == 108 and status["best_verified_test_accuracy"] == 108/179
    assert status["original_training_cases"] == 487 and status["original_test_cases"] == 179 and status["required_correct_for_80_percent"] == 144
    assert status["public_real_data_policy_sha256"] == digest(folder/"public-real-data-policy.json")
    hashes = 0
    for field in ("additional_scoped_verifications","additional_data_audits"):
        for name,expected in status[field].items():
            assert digest(folder/name) == expected,(field,name)
            hashes += 1
    tree = ast.parse(Path(__file__).with_name("fatigue_80_checkpoint.py").read_text())
    families = next(ast.literal_eval(node.iter) for node in ast.walk(tree)
        if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id == "name"
        and isinstance(node.iter,ast.Tuple) and any(isinstance(v,ast.Constant) and v.value == study.DIRECTORY.name for v in node.iter.elts))
    counts = {}
    for name in families:
        selection = json.loads((study.DIRECTORY.parent/name/"selection.json").read_text())
        assert selection["status"] == "complete",name
        counts[name] = len(selection["results"])
    assert len(counts) == 42 and sum(counts.values()) == 1664
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert selection["plan"] == study.plan() and len(selection["results"]) == 30
    audit_path = folder/"cadence-association-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_association.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["actual_source_target_calls_observed"] == 6 and audit["actual_native_target_calls_observed"] == len(audit["actual_native_refits"]) == 25
    assert audit["source_task_is_retrospective_association"] and not audit["source_pre_rpe_forecast_claim_approved"]
    assert audit["native_query_inputs_past_only_by_independent_raw_window_audit"] and audit["all_original_native_rows_and_labels_preserved"]
    heads = study.read_sources(study.fingerprint(inputs))
    assert len(heads) == 6
    for head in heads.values():
        assert int(head[-2].n_samples_seen_) == 976
    summary = json.loads((folder/"cadence-association-transfer.json").read_text())
    assert summary["verification_sha256"] == digest(audit_path) and summary["selection_sha256"] == digest(selection_path)
    data,rest_manifest = rest.load()
    assert len(data) == 666 and data[rest.FEATURES].notna().sum().to_dict() == dict.fromkeys(rest.FEATURES,636)
    rest_audit = json.loads((folder/"session-rest-input-verification.json").read_text())
    assert rest_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_session_rest_inputs.py"))
    assert rest_audit["raw_csv_reader_code_sha256"] == digest(Path(__file__).with_name("audit_cadence_association_inputs.py"))
    assert rest_audit["input_provenance_sha256"] == digest(rest.DIRECTORY/"provenance.json")
    assert rest_audit["actual_complete_minutes_across_unique_sessions"] == rest_manifest["actual_complete_baseline_minutes_across_sessions"] == 199
    assert rest_audit["all_used_minutes_completed_before_first_task_and_query"] and not rest_audit["new_model_fitting_started"]
    diagnostic = json.loads(rest.DIAGNOSTIC.read_text())
    assert diagnostic["code_sha256"] == digest(Path(__file__).with_name("diagnose_cadence_baseline_context.py"))
    assert diagnostic["native_fitting_comparable_cases_task_baseline_above_session_by_more_than10bpm"] == 128
    tests = (folder/"cadence-association-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    print(json.dumps({"integrity":"passed","completed_studies_counted_from_saved_selections":len(counts),
        "configurations_counted_from_saved_results":sum(counts.values()),"distinct_tests_cumulative":236,
        "scoped_evidence_hashes_checked":hashes,"source_refits_in_saved_audit":6,"native_refits_in_saved_audit":25,
        "frozen_source_functions_checked":6,"session_rest_input_cases_audited":666,"session_rest_observed_cases":636,
        "session_rest_naturally_missing_cases":30,"new_session_rest_model_fitting_started":False,
        "best_verified_test_accuracy":108/179,"retained_test_correct":108,"original_test_cases":179,
        "goal":"active;80percent not achieved","historical_model_refitting_performed_by_this_integrity_check":False}),flush=True)


if __name__ == "__main__":
    validate()
