"""Check study43 evidence and original source artifacts without old refits."""
import ast
import json
from pathlib import Path

import fatigue_cadence_session_rest as study
import fatigue_emap_history_inputs as emap
from public_sources import ROOT, digest


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status = json.loads((folder/"current-research-status.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (43,1698,240)
    assert status["goal_status"] == "active" and not status["goal_achieved"] and "running_study" not in status
    assert status["best_verified_test_correct"] == 108 and status["best_verified_test_accuracy"] == 108/179
    assert (status["original_training_cases"],status["original_test_cases"],status["required_correct_for_80_percent"]) == (487,179,144)
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
    assert len(counts) == 43 and sum(counts.values()) == 1698
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert selection["plan"] == study.plan() and len(selection["results"]) == 34
    audit_path = folder/"cadence-session-rest-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_session_rest.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["source_refit_verifier_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_association.py"))
    assert audit["source_verification_refits"] == 6 and len(audit["source_functions_refitted_for_independent_verification_only"]) == 6
    assert audit["actual_native_target_calls_observed"] == len(audit["actual_native_refits"]) == 25
    assert audit["all_34_oof_recipes_recomputed"] and audit["all_native_rows_and_labels_preserved"]
    assert audit["source_states_and_changes_independently_computed"] and audit["native_rows_and_delta_targets_observed_at_actual_fitter"]
    assert not audit["source_functions_refitted_during_selection"] and audit["source_artifacts_unchanged_after_verification"]
    for name,expected in audit["frozen_source_artifact_hashes"].items():
        assert digest(study.parent.DIRECTORY/"teachers"/name) == expected
    heads = study.read_sources(inputs)
    assert len(heads) == 6 and all(int(head[-2].n_samples_seen_) == 976 for head in heads.values())
    summary = json.loads((folder/"cadence-session-rest-transfer.json").read_text())
    assert summary["verification_sha256"] == digest(audit_path) and summary["selection_sha256"] == digest(selection_path)
    assert not summary["new_test_gate_passed"] and summary["retained_test_correct"] == 108
    original_review = json.loads(emap.REVIEW.read_text())
    assert original_review["audit_code_sha256"] == digest(Path(__file__).with_name("audit_exercise_rpe_originals.py"))
    assert original_review["actual_published_cohort_rpe_cells"] == 407 and original_review["actual_adjacent_rpe_pairs"] == 305
    data,manifest = emap.load()
    assert len(data) == 607 and len(data[data.source_partition.eq("fitting")]) == 550
    input_audit = json.loads((folder/"emap-history-input-verification.json").read_text())
    assert input_audit["audit_code_sha256"] == digest(Path(__file__).with_name("audit_emap_history_inputs.py"))
    assert input_audit["source_provenance_sha256"] == digest(emap.DIRECTORY/"provenance.json")
    assert input_audit["actual_emap_pairs_independently_rebuilt"] == 305
    tests = (folder/"cadence-session-rest-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    print(json.dumps({"integrity":"passed","completed_studies_counted_from_saved_selections":len(counts),
        "configurations_counted_from_saved_results":sum(counts.values()),"cumulative_distinct_tests":240,
        "scoped_evidence_hashes_checked":hashes,"source_refits_in_saved_audit":6,"native_refits_in_saved_audit":25,
        "frozen_source_artifact_hashes_checked":len(audit["frozen_source_artifact_hashes"]),
        "emap_original_responses":407,"emap_actual_pairs":305,"combined_source_fitting_pairs":550,
        "retained_test_correct":108,"retained_test_accuracy":108/179,"goal_achieved":False,
        "historical_model_refitting_performed":False}),flush=True)


if __name__ == "__main__":
    validate()
