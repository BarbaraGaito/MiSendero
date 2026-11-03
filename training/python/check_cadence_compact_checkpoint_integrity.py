"""Read-only scoped integrity and search counts after compact CADENCE research."""
import ast
import json
from pathlib import Path

import fatigue_cadence_compact as study
from public_sources import ROOT, digest


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status = json.loads((folder/"current-research-status.json").read_text())
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"],status["python_tests_passed"]) == (41,1634,232)
    assert status["goal_status"] == "active" and not status["goal_achieved"] and "running_study" not in status
    assert status["original_training_cases"] == 487 and status["original_test_cases"] == 179
    assert status["best_verified_test_correct"] == 108 and status["best_verified_test_accuracy"] == 108/179
    assert status["required_correct_for_80_percent"] == 144
    assert status["public_real_data_policy_sha256"] == digest(folder/"public-real-data-policy.json")
    hash_count = 0
    for field in ("additional_scoped_verifications","additional_data_audits"):
        for name,expected in status[field].items():
            assert digest(folder/name) == expected,(field,name)
            hash_count += 1
    tree = ast.parse(Path(__file__).with_name("fatigue_80_checkpoint.py").read_text())
    families = next(ast.literal_eval(node.iter) for node in ast.walk(tree)
        if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id == "name"
        and isinstance(node.iter,ast.Tuple) and any(isinstance(value,ast.Constant) and value.value == study.DIRECTORY.name for value in node.iter.elts))
    counts = {}
    for name in families:
        selection = json.loads((study.DIRECTORY.parent/name/"selection.json").read_text())
        assert selection["status"] == "complete",name
        counts[name] = len(selection["results"])
    assert len(counts) == 41 and sum(counts.values()) == 1634
    inputs = study.load_inputs()
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert all(selection.get(k) == v for k,v in study.fingerprint(inputs).items())
    assert selection["plan"] == study.plan() and len(selection["results"]) == 32
    audit_path = folder/"cadence-compact-verification.json"
    audit = json.loads(audit_path.read_text())
    assert audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_cadence_compact.py"))
    assert audit["previous_verification_sha256"] == digest(study.PARENT_AUDIT)
    assert audit["all_original_native_rows_and_labels_preserved"] and not audit["fresh_source_fitting_performed"]
    assert len(audit["actual_native_refits"]) == audit["actual_native_target_calls_observed"] == 20
    for source in audit["source_artifact_hashes_verified"]:
        path = study.parent.DIRECTORY/"teachers"/f"{source['algorithm']}-{source['feature_set']}.joblib"
        assert digest(path) == source["model_sha256"] and digest(path.with_suffix(".json")) == source["metadata_sha256"]
    summary = json.loads((folder/"cadence-compact-representation.json").read_text())
    assert summary["verification_sha256"] == digest(audit_path) and summary["selection_sha256"] == digest(selection_path)
    temporal = json.loads((folder/"cadence-temporal-eligibility.json").read_text())
    assert temporal["code_sha256"] == digest(Path(__file__).with_name("diagnose_cadence_temporal_eligibility.py"))
    assert temporal["source_partitions"] == {"fitting":727,"reserved":174} and not temporal["model_fitting_started"]
    association = json.loads((folder/"cadence-association-task-review.json").read_text())
    assert association["review_code_sha256"] == digest(Path(__file__).with_name("review_cadence_association_task.py"))
    assert association["source_fitting_targets"] == 976 and association["source_reserved_targets"] == 238
    assert association["all_native_used_minutes_completed_by_query"] and not association["model_fitting_started"]
    assert association["native_newer_current_minutes_recovered"] == 2
    article_receipt = ROOT/"training/data/raw/fatigue-research/light-exercise-article-v1/receipt.json"
    followup = json.loads((folder/"light-exercise-documentation-followup.json").read_text())
    assert followup["retrieval_receipt_sha256"] == digest(article_receipt) and not followup["used_for_training"]
    tests = (folder/"cadence-compact-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    print(json.dumps({"integrity":"passed","completed_studies_counted_from_saved_selections":len(counts),
        "configurations_counted_from_saved_results":sum(counts.values()),"distinct_tests_cumulative":232,
        "scoped_evidence_hashes_checked":hash_count,"frozen_source_artifacts_checked":6,
        "native_refits_in_saved_audit":20,"best_verified_test_accuracy":108/179,"retained_test_correct":108,
        "original_test_cases":179,"goal":"active;80percent not achieved","new_source_tasks_fitted":False,
        "historical_model_refitting_performed_by_this_integrity_check":False}),flush=True)


if __name__ == "__main__":
    validate()
