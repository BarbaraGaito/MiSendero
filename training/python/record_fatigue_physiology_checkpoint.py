"""Record completed, independently audited physiology study without refitting."""
import json
from pathlib import Path

import numpy as np

import fatigue_physiology_pair_learning as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    audit_path = folder/"physiology-learning-verification.json"
    audit = json.loads(audit_path.read_text())
    diagnostic_path = folder/"physiology-offset-diagnostic.json"
    diagnostic = json.loads(diagnostic_path.read_text())
    assert selection["status"] == "complete" and len(selection["results"]) == len(selection["plan"]) == 10
    assert selection["code_sha256"] == digest(Path(study.__file__))
    assert audit["selection_sha256"] == diagnostic["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_physiology_pair_learning.py"))
    assert diagnostic["diagnostic_code_sha256"] == digest(Path(__file__).with_name("diagnose_fatigue_physiology_offsets.py"))
    assert audit["best_verified_test_correct"] == 108 and not audit["achieved"]
    assert (status["completed_studies"], status["evaluated_configurations_including_controls"]) in ((35, 1521), (36, 1531))
    assert diagnostic["all_longer_fits_lower_training_nll_and_lower_cv"]
    for name in ("physiology-pair-tests.log", "physiology-learning-tests.log"):
        log = (folder/name).read_text(encoding="utf-8")
        assert "Ran 4 tests" in log and "OK" in log and "FAILED" not in log and "skipped" not in log
    arrays, input_manifest = study.source.load()
    extra_indexes = [i for i, row in enumerate(input_manifest["lineage"]) if row["cohort"] == "extra_fitting_only"]
    extra_empty_current = sum(arrays["fast_current"][extra_indexes, 2:].sum(axis=(1, 2)) == 0)
    assert len(extra_indexes) == 56 and extra_empty_current == 52
    assert sum(input_manifest["lineage"][i]["current_time_us"] == input_manifest["lineage"][i]["current_lower_bound_us"] for i in extra_indexes) == 52
    status.update(completed_studies=36, evaluated_configurations_including_controls=1531, python_tests_passed=212)
    status.pop("running_study", None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["additional_data_audits"][diagnostic_path.name] = digest(diagnostic_path)
    status["latest_complete_results"].update({"raw_physiology_pair_best_new_cv": audit["best_new_cv_accuracy"],
        "raw_physiology_pair_matching_without_extra_cv": audit["matching_without_extra_reports_cv"],
        "raw_physiology_pair_best_control_cv": audit["best_cv_accuracy"]})
    status["next_evidence_based_direction"] = (
        "Two-rate raw physiological Conv1D recipes failed to beat the original history control. All four matched 200-epoch fits lower fitting NLL but worsen held-person CV versus 80 epochs. Independent fitting-only diagnostics found 45 of 56 real extra reports expose delta classes absent in at least one inner original-only baseline fit (180/224 fitting visits); those classes receive fixed -30 baseline logits. Of the 56 extra reports, 52 have naturally empty current windows at task start and four occur later in the task. Next investigate a bounded finite-probability residual anchor and stronger regularization, accounting for this context difference, with unchanged labels, exact case scope and matched controls; predeclare the plan and validate only on original participant folds. No synthetic rows, artificial masks, target conversion or test tuning.")
    for field in ("additional_scoped_verifications", "additional_data_audits"):
        assert all(digest(folder/name) == expected for name, expected in status[field].items())
    summary = {"version": 1, "status": "complete", "selection_sha256": digest(selection_path),
        "verification_sha256": digest(audit_path), "input_verification_sha256": digest(study.INPUT_AUDIT),
        "offset_diagnostic_sha256": digest(diagnostic_path), "public_real_data_policy_sha256": digest(study.source.POLICY),
        "configurations": len(selection["plan"]), "winner_id": selection["winner_id"],
        "best_cv_accuracy": selection["best_cv_accuracy"], "best_new_id": audit["best_new_candidate_id"],
        "best_new_cv_accuracy": audit["best_new_cv_accuracy"], "matching_without_extra_cv": audit["matching_without_extra_reports_cv"],
        "original_training_cases": 487, "original_test_cases": 179, "additional_actual_fitting_reports": 56,
        "additional_reports_with_naturally_empty_current_window": int(extra_empty_current),
        "results": [{"candidate": r["candidate"], "accuracy_mean": r["accuracy_mean"], "fold_accuracy": r["fold_accuracy"]} for r in selection["results"]],
        "new_test_gate_passed": False, "test_used_for_selection": False,
        "retained_test_correct": 108, "retained_test_accuracy": audit["best_verified_test_accuracy"], "target_accuracy": .8, "achieved": False,
        "scope": "Actual public observations only. Exact original native Borg and all original participant-held cases; no synthetic examples, invented report timings, artificial masks, changed labels or new evaluation denominator."}
    (folder/"physiology-pair-learning.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    status_path.write_text(json.dumps(status, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"studies": status["completed_studies"], "configurations": status["evaluated_configurations_including_controls"],
        "best_new_cv": summary["best_new_cv_accuracy"], "retained_test": summary["retained_test_accuracy"],
        "new_scoped_verification_sha256": digest(audit_path), "goal_achieved": False}), flush=True)


if __name__ == "__main__":
    record()
