"""Reproduce hyperparameter winners, solver-budget controls and a warning."""
from __future__ import annotations

import argparse
import copy
import json
import tempfile
import warnings
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from threadpoolctl import threadpool_limits

import fatigue_real_mlp_hyperparameters as study
from public_sources import digest
from validate_fatigue_release import validate as validate_incumbent


def require(value, reason):
    if not value:
        raise ValueError(reason)


def optimizer_pipeline(model, new, feature_set):
    if new:
        return model.model.model if feature_set == "original_13" else model.model.model.model
    return model.model if feature_set == "original_13" else model.model.model


def validate():
    inputs = study.load_inputs()
    parents = inputs[0]
    _, train, test, members, _, _, _, _ = parents
    specifications = members["member_specifications"]
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
            and selection["plan"] == study.plan() and len(selection["results"]) == 22
            and selection["train_row_keys"] == train.row_key.tolist(), "Frozen real-input hyperparameter study changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train.group_key) & set(test.group_key) and not selection["test_used_for_selection"]
            and selection["minimum_cv_for_new_test_evaluation"] == .65 and selection["synthetic_training_rows"] == 0
            and selection["new_native_borg_targets"] == 0, "Original exact target, real-data constraint or person holdout changed")
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    previous = json.loads((study.parent.DIRECTORY/"selection.json").read_text())
    previous_audit = json.loads(study.PARENT_AUDIT.read_text())
    teachers = study.read_ridge_heads(signature)
    source_before = {condition:copy.deepcopy(model[-1].coef_) for condition,model in teachers.items()}
    warned_folds = []
    for row in selection["results"]:
        candidate, predicted = row["candidate"], np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted) <= {f"Borg {i}" for i in range(11)}, "Native OOF case count or scale changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
                and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"], "Native hyperparameter accuracy changed")
        if candidate["algorithm"] == "previous_real_control":
            control = next(r for r in previous["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,control["oof_predictions"])
            continue
        require(len(row["folds"]) == 5 and candidate["random_seed"] == 42 and not candidate["early_stopping"], "Native hyperparameter fold or seed/stopping rule changed")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(), "Frozen hyperparameter/native fitting rows changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            info = saved["optimizer_summary"]
            require(info["maximum_iterations"] == 5000 and info["maximum_function_evaluations"] == 100000
                    and info["alpha"] == candidate["params"]["alpha"] and info["hidden_layer_sizes"] == candidate["params"]["hidden_layer_sizes"]
                    and 0 < info["iterations"] <= 5000 and np.isfinite(info["final_fitting_loss"])
                    and info["actual_native_fit_rows"] == len(fit) and info["synthetic_rows"] == info["artificial_history_views"] == 0
                    and info["actual_walking_source_targets"] == (156 if candidate["feature_set"] == "real_walking_ridge" else 0), "Solver, source use or real-target count changed")
            if info["convergence_warnings"]:
                warned_folds.append((candidate["id"],number))
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"], "Winner differs from the predeclared CV rule")
    new = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    best = max(new,key=lambda r:r["accuracy_mean"])
    best_by_feature = {feature:max((r for r in new if r["candidate"]["feature_set"] == feature),key=lambda r:r["accuracy_mean"])
                       for feature in ("original_13","real_walking_ridge")}
    budget_matches = {feature:next(r for r in new if r["candidate"]["feature_set"] == feature
        and r["candidate"]["params"]["hidden_layer_sizes"] == [16,8] and r["candidate"]["params"]["alpha"] == 10.)
        for feature in best_by_feature}
    selected = {r["candidate"]["id"]:r for r in [best,*best_by_feature.values(),*budget_matches.values()]}
    tasks = [(row,True,number) for row in selected.values() for number in range(5)]
    controls = {}
    for feature,control_id in (("original_13","walking-teacher-000"),("real_walking_ridge","walking-teacher-010")):
        controls[feature] = next(r for r in previous["results"] if r["candidate"]["id"] == control_id)
        tasks.extend((controls[feature],False,number) for number in range(5))
    warning_witness = warned_folds[0] if warned_folds else None
    if warning_witness and warning_witness[0] not in selected:
        row = next(r for r in new if r["candidate"]["id"] == warning_witness[0])
        tasks.append((row,True,warning_witness[1]))
    checked = []
    for row,is_new,number in tasks:
        candidate = row["candidate"]
        fit,val = folds[number]
        fitting,validation = train.iloc[fit],train.iloc[val]
        feature = candidate["feature_set"] if is_new else ("original_13" if candidate["id"] == "walking-teacher-000" else "real_walking_ridge")
        expected_target = (fitting.label.str.removeprefix("Borg ").astype(int)-fitting.prior_borg.astype(int)).astype(str).to_numpy()
        expected_params = candidate["params"] if is_new else specifications["core"]["params"]
        native_class = study.parent.parent.parent.baseline.DynamicsClassifier
        actual_native_fit,actual_mlp_fit = native_class.fit,MLPClassifier.fit
        observed_rows,observed_targets = [],[]
        def observe_native(model,data):
            pd.testing.assert_frame_equal(data[fitting.columns],fitting)
            np.testing.assert_array_equal(data.row_key,fitting.row_key)
            observed_rows.append(len(data))
            return actual_native_fit(model,data)
        def observe_mlp(estimator,x,y,**kwargs):
            np.testing.assert_array_equal(y,expected_target)
            require(len(x) == len(fitting) and estimator.max_iter == expected_params["max_iter"]
                    and estimator.alpha == expected_params["alpha"] and list(estimator.hidden_layer_sizes) == expected_params["hidden_layer_sizes"]
                    and estimator.random_state == 42 and not estimator.early_stopping, "Actual native MLP saw altered targets, rows or hyperparameters")
            observed_targets.append(len(y))
            return actual_mlp_fit(estimator,x,y,**kwargs)
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial history examples prohibited")),patch.object(native_class,"fit",new=observe_native),patch.object(MLPClassifier,"fit",new=observe_mlp),warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always",ConvergenceWarning)
            if is_new:
                model = study.TunedRealBorg(candidate,teachers).fit(fitting,specifications)
            else:
                with threadpool_limits(limits=1):
                    if feature == "original_13":
                        model = native_class(specifications["core"]).fit(fitting)
                        model.input_features = list(specifications["core"]["features"])
                    else:
                        model = study.parent.WalkingSourceBorg(candidate,teachers,{}).fit(fitting,specifications)
        require(observed_rows == observed_targets == [len(fitting)], "Actual native-data/target observer was bypassed")
        predicted = model.predict(validation)
        np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
        pipeline = optimizer_pipeline(model,is_new,feature)
        require(int(pipeline[1].n_samples_seen_) == len(fitting), "Native preprocessing saw held-out cases")
        if is_new:
            expected_info = row["folds"][number]["optimizer_summary"]
            require(model.optimizer_summary == expected_info, "MLP optimizer diagnostics failed exact reproduction")
            info = model.optimizer_summary
        else:
            estimator = pipeline[-1]
            info = {"iterations":int(estimator.n_iter_),"final_fitting_loss":float(estimator.loss_),
                    "convergence_warnings":[str(w.message) for w in caught if issubclass(w.category,ConvergenceWarning)]}
        runtime = validation[model.input_features]
        np.testing.assert_array_equal(model.predict(runtime),predicted)
        require(not set(model.input_features)&{"label","row_key","group_key"} and not set(vars(model))&{"frame","histories","pool","row_keys"}, "Current truth/IDs or a query report pool entered inference")
        for condition,value in source_before.items():
            np.testing.assert_array_equal(teachers[condition][-1].coef_,value)
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory)/"actual-hyperparameter-model.joblib"
            joblib.dump(model,artifact)
            np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),predicted)
        checked.append({"candidate_id":candidate["id"],"new_hyperparameter_recipe":is_new,"fold":number,"feature_set":feature,
                        "iterations":info["iterations"],"final_fitting_loss":info["final_fitting_loss"],"warnings":info["convergence_warnings"]})
        print(f"Independent real MLP hyperparameter refit {candidate['id']} fold{number+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A real MLP hyperparameter model crossed its gate: freeze and evaluate its original179 artifact next")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous_audit["best_verified_test_accuracy"], "Retained original test model changed")
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(path),"previous_verification_sha256":digest(study.PARENT_AUDIT),
        "public_real_data_policy_sha256":digest(study.parent.parent.native.POLICY),"all_22_oof_recipes_recomputed":True,
        "new_configurations":18,"architectures":3,"l2_penalties":3,"real_feature_sets":2,
        "best_new_candidate_id":best["candidate"]["id"],"best_new_cv_accuracy":best["accuracy_mean"],
        "best_by_feature":{feature:{"candidate_id":r["candidate"]["id"],"accuracy_mean":r["accuracy_mean"]} for feature,r in best_by_feature.items()},
        "budget_comparisons":{feature:{"new5000_candidate_id":budget_matches[feature]["candidate"]["id"],
            "new5000_cv":budget_matches[feature]["accuracy_mean"],"previous1000_candidate_id":controls[feature]["candidate"]["id"],
            "previous1000_cv":controls[feature]["accuracy_mean"]} for feature in best_by_feature},
        "new_native_recipes_independently_refitted":sorted(selected),"original1000_iteration_controls_refitted":2,
        "convergence_warning_folds_in_grid":len(warned_folds),"warning_witness_refitted":list(warning_witness) if warning_witness else None,
        "actual_native_refits":checked,"actual_target_calls_observed":len(checked),"actual_rows_and_delta_targets_verified":True,
        "native_preprocessing_fitting_people_only":True,"source_coefficients_frozen":True,"artificial_history_fitting_disabled":True,
        "winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],"new_test_gate_passed":False,
        "original_training_cases":487,"original_test_cases":179,"best_verified_test_correct":incumbent["correct"],
        "best_verified_test_accuracy":incumbent["accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Exact original native Borg, all original person-held cases and real public inputs. Frozen capacity/L2/budget tuning with current targets used only as fitting labels. No synthetic examples, artificial histories, target conversion, source refitting on native data, changed denominator or test tuning."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
