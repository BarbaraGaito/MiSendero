"""Record completed real-source transfer and newly reviewed public candidates."""
import json
from pathlib import Path

import fatigue_walking_source_teachers as study
from public_sources import ROOT, digest


def record():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    status_path = folder/"current-research-status.json"
    status = json.loads(status_path.read_text())
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    audit_path = folder/"walking-source-teacher-verification.json"
    audit = json.loads(audit_path.read_text())
    cadence_path = folder/"cadence-eligibility.json"
    cadence = json.loads(cadence_path.read_text())
    assert selection["status"] == "complete" and len(selection["results"]) == len(selection["plan"]) == 22
    assert selection["code_sha256"] == digest(Path(study.__file__)) and audit["selection_sha256"] == digest(selection_path)
    assert audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_walking_source_teachers.py"))
    assert audit["best_verified_test_correct"] == 108 and not audit["achieved"] and not audit["new_test_gate_passed"]
    assert audit["combined_actual_source_pairs_verified"] == 458
    assert cadence["audit_code_sha256"] == digest(Path(__file__).with_name("audit_cadence_candidates.py"))
    assert cadence["cohorts"]["adult"]["original_rows"] == 1214 and cadence["cohorts"]["adult"]["identity_stage_screen_passed"]
    assert not cadence["cohorts"]["older"]["identity_stage_screen_passed"] and not cadence["model_fitting_started"]
    assert (status["completed_studies"],status["evaluated_configurations_including_controls"]) in ((37,1542),(38,1564))
    tests = (folder/"walking-source-teacher-tests.log").read_text()
    assert "Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests
    status.update(completed_studies=38,evaluated_configurations_including_controls=1564,python_tests_passed=220)
    status.pop("running_study",None)
    status["additional_scoped_verifications"][audit_path.name] = digest(audit_path)
    status["additional_data_audits"][cadence_path.name] = digest(cadence_path)
    status["latest_complete_results"].update({"walking_spe_source_teacher_best_new_cv":audit["best_new_cv_accuracy"],
        "walking_spe_combined_sources_best_cv":audit["best_combined_source_cv_accuracy"],
        "walking_spe_matching_previous_sources_cv":audit["matching_previous_source_cv_accuracy"],
        "walking_spe_best_control_cv":audit["best_cv_accuracy"]})
    status["new_public_walking_source"].update(model_fitting_started=True,used_in_study=study.DIRECTORY.name)
    status["combined_real_source_pairs"] = {"directory":study.source.DIRECTORY.name,"actual_targets":458,
        "counts":{"worker":253,"sts":49,"walking_spe":156},"native_borg_targets_added":0,
        "provenance_sha256":digest(study.source.DIRECTORY/"provenance.json"),"used_in_study":study.DIRECTORY.name}
    status["cadence_public_candidate"] = {"verification":cadence_path.name,"adult_actual_rpe_rows":1214,
        "adult_participant_ids":156,"adult_identity_screen_passed":True,"older_original_rows":550,
        "older_inconsistent_ids":len(cadence["cohorts"]["older"]["ids_with_inconsistent_static_fields"]),
        "older_cohort_excluded_from_fitting":True,"native_scale_conversion_approved":False,
        "current_bout_hr_causal_use_approved":False,"fitting_started":False}
    status["next_evidence_based_direction"] = (
        "The458-real-pair source transfer failed to beat the history control. In response to the user's request, next run a frozen MLP hyperparameter grid varying3 architectures and3L2 penalties on original13 inputs and real walking-source features, with increased L-BFGS5000/100000 budgets and explicit convergence diagnostics. Retain original487/179 participant folds and no test selection. Separately reviewed CADENCE provides1214 measured Borg6-20 rows from156 consistent adult IDs; it needs a source-only lagged-input adapter, reserved source people and independent audit before fitting. Older cohort550 rows is excluded because33 IDs have inconsistent static fields. Current-bout HR can follow an unknown RPE response time; do not use it as strictly past or invent exact report clocks. No synthetic data or native label conversion.")
    for field in ("additional_scoped_verifications","additional_data_audits"):
        assert all(digest(folder/name) == expected for name,expected in status[field].items())
    summary = {"version":1,"status":"complete","selection_sha256":digest(selection_path),"verification_sha256":digest(audit_path),
        "configurations":22,"combined_real_source_pairs":458,"new_walking_actual_pairs":156,
        "public_real_data_policy_sha256":digest(study.parent.native.POLICY),"winner_id":selection["winner_id"],
        "best_cv_accuracy":selection["best_cv_accuracy"],"best_new_id":audit["best_new_candidate_id"],
        "best_new_cv_accuracy":audit["best_new_cv_accuracy"],"best_combined_source_cv":audit["best_combined_source_cv_accuracy"],
        "matching_previous_source_cv":audit["matching_previous_source_cv_accuracy"],
        "results":[{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"],"fold_accuracy":r["fold_accuracy"]} for r in selection["results"]],
        "original_training_cases":487,"original_test_cases":179,"new_test_gate_passed":False,"test_used_for_selection":False,
        "retained_test_correct":108,"retained_test_accuracy":audit["best_verified_test_accuracy"],"target_accuracy":.8,"achieved":False,
        "optimization_note":"Training log includes MLP iteration-limit warnings. The three recipes reproduced by the scoped auditor are CatBoost; their warnings are separately recorded. Do not imply all22 recipes were refitted during the audit.",
        "scope":"Only original public observations. Separate Borg/SPE source heads and original native exact-Borg task; no invented HR joins, participant IDs, labels, examples, report clocks or test denominator changes."}
    (folder/"walking-source-teachers.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"studies":38,"configurations":1564,"best_new_cv":audit["best_new_cv_accuracy"],
        "retained_test":audit["best_verified_test_accuracy"],"goal_achieved":False}),flush=True)


if __name__ == "__main__":
    record()
