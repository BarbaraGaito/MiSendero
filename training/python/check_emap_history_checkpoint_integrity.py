"""Read-only aggregate integrity for the completed original CR10 history study."""
import ast
import json
from pathlib import Path

import fatigue_emap_history_transfer as study
from public_sources import digest


def validate():
    folder = study.source.DOCS
    status = json.loads((folder/"current-research-status.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (44,1714,244)
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
    assert len(counts) == 44 and sum(counts.values()) == 1714
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert selection["plan"] == study.plan() and len(selection["results"]) == 16
    audit_path = folder/"emap-history-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_emap_history_transfer.py"))
    assert audit["input_verification_sha256"] == digest(study.INPUT_AUDIT) and audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["source_verification_refits"] == len(audit["actual_source_functions_independently_refitted"]) == 9
    assert audit["actual_native_target_calls_observed"] == len(audit["actual_native_refits"]) == 20
    assert audit["all_16_oof_recipes_recomputed"] and audit["original_native_rows_and_targets_preserved"]
    assert audit["original_source_delta_targets_observed_at_actual_fitter"] and audit["source_scaling_and_weights_fitting_people_only"]
    assert audit["computed_history_changes_independently_verified"] and audit["native_delta_targets_observed_at_actual_fitter"]
    assert audit["source_weights_frozen_during_native_fitting"] and audit["native_preprocessing_fitting_people_only"]
    assert audit["source_artifacts_unchanged_after_verification"] and not audit["source_target_pooling_performed"]
    for name,expected in audit["frozen_source_artifact_hashes"].items():
        assert digest(study.DIRECTORY/"teachers"/name) == expected
    sources = study.read_sources(study.fingerprint(inputs))
    expected = {"emap":248,"worker":253,"sts":49}
    for heads in sources.values():
        assert set(heads) == set(expected)
        for domain,head in heads.items():
            assert int(head[-2].n_samples_seen_) == expected[domain]
    summary = json.loads((folder/"emap-history-transfer.json").read_text())
    assert summary["verification_sha256"] == digest(audit_path) and summary["selection_sha256"] == digest(selection_path)
    assert not summary["new_test_gate_passed"] and summary["retained_test_correct"] == 108
    assert summary["new_emap_fitting_targets"] == 248 and summary["new_emap_reserved_targets"] == 57
    diagnostic = json.loads((folder/"emap-ordered-history-context-diagnostic.json").read_text())
    assert diagnostic["code_sha256"] == digest(Path(__file__).with_name("diagnose_emap_ordered_history_context.py"))
    assert diagnostic["source_provenance_sha256"] == digest(study.source.DIRECTORY/"provenance.json")
    assert not diagnostic["native_test_targets_used"] and not diagnostic["emap_reserved_targets_used"]
    tests = (folder/"emap-history-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    print(json.dumps({"integrity":"passed","completed_studies_counted_from_saved_selections":len(counts),
        "configurations_counted_from_saved_results":sum(counts.values()),"cumulative_distinct_tests":244,
        "scoped_evidence_hashes_checked":hashes,"source_refits_in_saved_audit":9,"native_refits_in_saved_audit":20,
        "frozen_source_artifact_hashes_checked":len(audit["frozen_source_artifact_hashes"]),
        "new_emap_fitting_pairs":248,"new_emap_reserved_pairs":57,"combined_source_fitting_pairs":550,
        "retained_test_correct":108,"retained_test_accuracy":108/179,"goal_achieved":False,
        "historical_model_refitting_performed":False}),flush=True)


if __name__ == "__main__":
    validate()
