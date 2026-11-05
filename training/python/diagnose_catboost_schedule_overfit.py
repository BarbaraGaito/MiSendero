"""Read-only fitting-versus-person-CV gaps from all frozen CatBoost prefixes.

No estimator is fitted. All predictions use the original 487 fitting cases;
the original 179 native test cases and reserved public-source outcomes are
outside this diagnostic. The complete predeclared grid must exist first.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_catboost_schedule as study
import fatigue_prior_views as artificial_views
from public_sources import digest


def require(condition,reason):
    if not condition:
        raise ValueError(reason)


def diagnose():
    calls = {"estimator_fit_attempts":0,"artificial_view_builder_attempts":0}

    def reject_fitting(*args,**kwargs):
        calls["estimator_fit_attempts"] += 1
        raise AssertionError("Read-only schedule diagnostic must never fit an estimator")

    def reject_artificial_views(*args,**kwargs):
        calls["artificial_view_builder_attempts"] += 1
        raise AssertionError("Read-only actual-public diagnostic must never construct artificial histories")

    with patch.object(CatBoostClassifier,"fit",reject_fitting), \
         patch.object(study.ScheduledCatBoostBorg,"fit",reject_fitting), \
         patch.object(study,"select",reject_fitting), \
         patch.object(artificial_views,"build",reject_artificial_views), \
         patch.object(artificial_views,"alternative_histories",reject_artificial_views):
        inputs = study.load_inputs()
        signature = study.fingerprint(inputs)
        path = study.DIRECTORY/"selection.json"
        selection = json.loads(path.read_text())
        require(selection["status"] == "complete" and len(selection["results"]) == 16
            and selection["plan"] == study.plan() and not selection["test_used_for_selection"]
            and selection["actual_native_trajectory_fits"] == 15
            and selection["matched_original_prefix_controls_verified"] == 10
            and all(selection.get(k) == v for k,v in signature.items()),
            "Wait for the full frozen 16-recipe/15-trajectory selection before diagnostics")
        train = inputs["train"]
        require(len(train) == 487 and train.group_key.nunique() == 28
            and train.row_key.tolist() == selection["train_row_keys"],
            "Original native fitting people/cases changed")
        native = [r for r in selection["results"]
            if r["candidate"]["algorithm"] == "native_catboost_fixed_rate_prefix"]
        require(len(native) == 12,"All twelve fixed native schedules are required")
        rows = {(r["candidate"]["learning_rate"],r["candidate"]["iterations"]):r for r in native}
        require(set(rows) == {(rate,n) for rate in study.RATES for n in study.PREFIXES},
            "A declared rate/tree combination is missing")
        folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
        pinned_paths = [path,Path(study.__file__),study.DIRECTORY/"selection-source.py",
            study.PROPOSAL,study.PARENT_AUDIT,study.BASELINE_CODE,
            study.BASELINE_DIRECTORY/"selection.json",study.DOCS/"public-real-data-policy.json",
            Path(__file__)]
        for rate in study.RATES:
            for number in range(5):
                p = study.trajectory_path(rate,number)
                pinned_paths.extend(p.with_suffix(suffix) for suffix in (".json",".joblib",".cbm"))
        before = {str(p):digest(p) for p in pinned_paths}
        train_before = joblib.hash(train)
        comparisons,trajectories = [],[]
        for rate in study.RATES:
            for number,(fit,val) in enumerate(folds):
                saved = study.read_trajectory(inputs,rate,number,fit,val)
                trajectory = study.trajectory_path(rate,number)
                require(not set(train.iloc[fit].group_key)&set(train.iloc[val].group_key),
                    "Fitting and validation people overlap")
                model = joblib.load(trajectory.with_suffix(".joblib"))
                require(model.input_features == list(study.FEATURES)
                    and not {"label","row_key","group_key"}&set(model.input_features),
                    "Runtime inputs contain truth or participant/case identifiers")
                model_before = joblib.hash(model)
                fitting,validation = train.iloc[fit],train.iloc[val]
                runtime = fitting[model.input_features]
                for count in study.PREFIXES:
                    row = rows[(rate,count)]
                    values = model.predict_prefix(runtime,count)
                    require(len(values) == len(fitting)
                        and set(values)<={f"Borg {n}" for n in range(11)},
                        "Native fitting prediction count or exact Borg classes changed")
                    held_values = np.asarray(saved["prefix_predictions"][str(count)])
                    np.testing.assert_array_equal(held_values,np.asarray(row["oof_predictions"])[val])
                    detail = row["folds"][number]
                    require(detail["trajectory_file"] == trajectory.relative_to(study.DIRECTORY).as_posix()
                        and detail["trajectory_sha256"] == digest(trajectory)
                        and detail["prefix_tree_count"] == count
                        and detail["fit_row_keys"] == fitting.row_key.tolist()
                        and detail["validation_row_keys"] == validation.row_key.tolist(),
                        "Saved selection references a different frozen fitting trajectory")
                    fitting_correct = int(np.count_nonzero(values == fitting.label.to_numpy()))
                    validation_correct = int(np.count_nonzero(held_values == validation.label.to_numpy()))
                    fitting_accuracy = float(accuracy_score(fitting.label,values))
                    validation_accuracy = float(accuracy_score(validation.label,held_values))
                    require(validation_accuracy == row["fold_accuracy"][number],
                        "Saved held-person accuracy changed")
                    comparisons.append({"candidate_id":row["candidate"]["id"],"learning_rate":rate,
                        "prefix_trees":count,"fold":number,"native_fitting_cases":len(fitting),
                        "native_fitting_people":fitting.group_key.nunique(),
                        "native_validation_cases":len(validation),
                        "native_validation_people":validation.group_key.nunique(),
                        "fitting_row_keys":fitting.row_key.tolist(),"validation_row_keys":validation.row_key.tolist(),
                        "fitting_correct":fitting_correct,"validation_correct":validation_correct,
                        "fitting_exact_accuracy":fitting_accuracy,"validation_exact_accuracy":validation_accuracy,
                        "fitting_minus_validation_accuracy":fitting_accuracy-validation_accuracy,
                        "runtime_only_declared_features":True,"trajectory_file":detail["trajectory_file"],
                        "trajectory_sha256":digest(trajectory)})
                require(joblib.hash(model) == model_before,"Forward diagnostic mutated a loaded fitted model")
                trajectories.append({"learning_rate":rate,"fold":number,"maximum_trees":2700,
                    "trajectory_file":trajectory.relative_to(study.DIRECTORY).as_posix(),
                    "artifact_sha256":saved["artifact_sha256"],"model_hash_before_and_after":model_before,
                    "four_native_fitting_prefix_predictions_completed":True})
                print(f"Read-only original-native fitting/CV comparison:{study.rate_key(rate)} fold{number+1}/5,4prefixes",flush=True)
        require(len(comparisons) == 60 and len(trajectories) == 15,"Incomplete full-grid fitting diagnostic")
        aggregates = []
        for rate in study.RATES:
            for count in study.PREFIXES:
                part = [r for r in comparisons if r["learning_rate"] == rate and r["prefix_trees"] == count]
                row = rows[(rate,count)]
                mean_fit = float(np.mean([r["fitting_exact_accuracy"] for r in part]))
                mean_val = float(np.mean([r["validation_exact_accuracy"] for r in part]))
                require(len(part) == 5 and mean_val == row["accuracy_mean"],
                    "Full-grid grouped-CV mean changed")
                aggregates.append({"candidate_id":row["candidate"]["id"],"learning_rate":rate,
                    "prefix_trees":count,"folds":5,"fitting_exact_accuracy_mean":mean_fit,
                    "cv_exact_accuracy_mean":mean_val,"fitting_minus_cv_accuracy_mean":mean_fit-mean_val,
                    "pooled_oof_exact_accuracy":row["pooled_oof_accuracy"],
                    "fitting_fold_accuracy":[r["fitting_exact_accuracy"] for r in part],
                    "validation_fold_accuracy":[r["validation_exact_accuracy"] for r in part]})
        aggregate_map = {(r["learning_rate"],r["prefix_trees"]):r for r in aggregates}
        transitions = []
        for rate in study.RATES:
            for first,last in ((300,900),(900,1800),(1800,2700),(300,2700)):
                a,b = aggregate_map[(rate,first)],aggregate_map[(rate,last)]
                fit_change = b["fitting_exact_accuracy_mean"]-a["fitting_exact_accuracy_mean"]
                cv_change = b["cv_exact_accuracy_mean"]-a["cv_exact_accuracy_mean"]
                transitions.append({"learning_rate":rate,"from_trees":first,"to_trees":last,
                    "fitting_accuracy_change":fit_change,"cv_accuracy_change":cv_change,
                    "fitting_improves_while_cv_worsens":bool(fit_change>1e-12 and cv_change < -1e-12),
                    "fitting_nondecreases_while_cv_worsens":bool(fit_change>=-1e-12 and cv_change < -1e-12)})
        require(joblib.hash(train) == train_before,"Diagnostic changed original native fitting values")
        require(all(digest(Path(p)) == expected for p,expected in before.items()),
            "Diagnostic changed a frozen selection/model/proposal/artifact")
        require(calls == {"estimator_fit_attempts":0,"artificial_view_builder_attempts":0},
            "Read-only diagnostic attempted model fitting or artificial histories")
        best = max(aggregates,key=lambda r:r["cv_exact_accuracy_mean"])
        overfit = [r for r in transitions if r["fitting_improves_while_cv_worsens"]]
        return {"version":1,"diagnostic":"passed","generated_at":datetime.now(timezone.utc).isoformat(),
            "diagnostic_code_sha256":digest(Path(__file__)),"study_code_sha256":digest(Path(study.__file__)),
            "selection_sha256":digest(path),"plan_sha256":digest(study.PROPOSAL),
            "public_real_data_policy_sha256":digest(study.DOCS/"public-real-data-policy.json"),
            "original_native_fitting_cases":487,"original_native_fitting_people":28,
            "person_folds":5,"native_test_predictions_computed":0,"native_test_labels_inspected":False,
            "reserved_source_outcomes_used":0,"new_estimator_fits":0,"synthetic_rows":0,
            "actual_fit_and_artificial_builder_calls":calls,"original_fitting_frame_hash_before_and_after":train_before,
            "frozen_artifact_hashes_before_and_after":before,"all_frozen_models_immutable":True,
            "native_trajectories_read":15,"fixed_prefix_fit_cv_comparisons":60,
            "comparisons":comparisons,"by_rate_and_budget":aggregates,"trajectories":trajectories,
            "budget_transitions":transitions,"transitions_with_better_fit_and_worse_cv":len(overfit),
            "larger_budgets_can_improve_fit_while_cv_worsens":bool(overfit),
            "best_cv_schedule":best,
            "equal_rate_times_trees_27_comparison":[aggregate_map[p] for p in ((.01,2700),(.03,900),(.09,300))],
            "interpretation":"A fitting/CV gap describes memorization/generalization on the completed predeclared grid. It does not prove an independent accuracy gain or select additional hyperparameters. Fitting folds reuse original fitting cases; their accuracy is not a held-out metric. All validation scores remain the stored five-person-fold results on the original487cases. The179native test and all reserved-source outcomes are outside this read-only diagnostic."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=study.DOCS/"catboost-schedule-fit-cv-diagnostic.json")
    args = parser.parse_args()
    report = diagnose()
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("diagnostic","native_trajectories_read","fixed_prefix_fit_cv_comparisons",
        "new_estimator_fits","transitions_with_better_fit_and_worse_cv","best_cv_schedule")}),flush=True)
