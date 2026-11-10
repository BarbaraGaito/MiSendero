"""Record audited user-requested hyperparameter results without refitting."""
import json
from pathlib import Path

import fatigue_real_mlp_hyperparameters as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    audit_path = folder/"real-mlp-hyperparameter-verification.json"
    audit = json.loads(audit_path.read_text())
    assert selection["status"] == "complete" and len(selection["plan"]) == len(selection["results"]) == 22
    assert selection["code_sha256"] == digest(Path(study.__file__)) and audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_real_mlp_hyperparameters.py"))
    assert audit["actual_rows_and_delta_targets_verified"] and not audit["achieved"] and not audit["new_test_gate_passed"]
    assert audit["best_verified_test_correct"] == 108
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((38,1564),(39,1586))
    tests = (folder/"real-mlp-hyperparameter-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    status.update(completed_studies=39,evaluated_configurations_including_controls=1586,python_tests_passed=224)
    status.pop("running_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["latest_complete_results"].update({"real_mlp_hyperparameters_best_new_cv":audit["best_new_cv_accuracy"],
        "real_mlp_hyperparameters_original13_best_cv":audit["best_by_feature"]["original_13"]["accuracy_mean"],
        "real_mlp_hyperparameters_walking_features_best_cv":audit["best_by_feature"]["real_walking_ridge"]["accuracy_mean"],
        "real_mlp_hyperparameters_best_control_cv":audit["best_cv_accuracy"]})
    status["next_evidence_based_direction"] = (
        "User-requested capacity/L2/L-BFGS tuning completed18 new recipes plus4controls. Best real-input MLP remains16/8,alpha10; raising the solver budget5000/100000 left both matched best-feature CV scores unchanged from1000-iteration controls. No new test gate passed. Next prioritize genuinely additional physiological information: prepare a source-only CADENCE adult lagged-input adapter from1214 measured Borg6-20 rows/156 consistent IDs, predeclare whole-person source reservation and independently verify actual adjacent stages, laggedHR and temporal bounds. Do not use ambiguous current-boutHR, invent exact response clocks or convert6-20 into native0-10 labels. Exclude the entire older cohort with33 inconsistent IDs. Original487/179 exact Borg person holdout and real-public-only policy remain fixed.")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "configurations":22,"new_hyperparameter_recipes":18,"architectures":[[8],[16,8],[32,16]],"l2_penalties":[1,10,100],
        "max_iter":5000,"max_fun":100000,"seed":42,"early_stopping":False,
        "public_real_data_policy_sha256":digest(study.parent.parent.native.POLICY),"winner_id":selection["winner_id"],
        "best_cv_accuracy":selection["best_cv_accuracy"],"best_new_id":audit["best_new_candidate_id"],
        "best_new_cv_accuracy":audit["best_new_cv_accuracy"],"best_by_feature":audit["best_by_feature"],
        "budget_comparisons":audit["budget_comparisons"],"convergence_warning_folds":audit["convergence_warning_folds_in_grid"],
        "results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"new_test_gate_passed":False,"test_used_for_selection":False,
        "retained_test_correct":108,"retained_test_accuracy":audit["best_verified_test_accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Only unchanged actual public cases. Capacity,L2 and optimizer budgets tuned on original participant CV. Source heads frozen, all native targets unchanged; no synthetic data, altered denominator or test tuning."}
    (folder/"real-mlp-hyperparameters.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"studies":39,"configurations":1586,"best_new_cv":audit["best_new_cv_accuracy"],
        "best_original13_cv":audit["best_by_feature"]["original_13"]["accuracy_mean"],
        "retained_test":audit["best_verified_test_accuracy"],"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
