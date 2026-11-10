"""Audit compact inputs, actual native fitting and frozen CADENCE functions."""
from __future__ import annotations

import argparse
import json
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from threadpoolctl import threadpool_limits

import fatigue_cadence_compact as study
from public_sources import digest
from validate_fatigue_release import validate as validate_incumbent

_RUNTIME = None


def require(value, reason):
    if not value:
        raise ValueError(reason)


def check_source_artifacts(inputs):
    heads = study.read_sources(inputs)
    previous = json.loads(study.PARENT_AUDIT.read_text())
    require(previous["actual_source_target_calls_observed"] == 6 and previous["source_targets_original6to20_unchanged"]
            and previous["source_current_bout_hr_excluded"] and previous["equal_total_source_weight_per_person"],
            "Previous independent actual source-supervision proof changed")
    signature = study.parent.fingerprint(inputs)
    checked = []
    for (algorithm,feature_set),head in heads.items():
        path = study.parent.DIRECTORY/"teachers"/f"{algorithm}-{feature_set}.joblib"
        metadata_path = path.with_suffix(".json")
        metadata = json.loads(metadata_path.read_text())
        evidence = next(r for r in previous["actual_source_regressors_independently_refitted"]
                        if r["algorithm"] == algorithm and r["feature_set"] == feature_set)
        require(metadata["signature"] == signature and metadata["model_sha256"] == digest(path)
                and metadata["actual_source_fitting_rows"] == 851 and metadata["actual_source_fitting_people"] == 123
                and metadata["reserved_source_rows"] == 206 and not metadata["reserved_source_used_for_selection"]
                and metadata["native_labels_used_for_source_fitting"] == 0 and int(head[-2].n_samples_seen_) == 851
                and metadata["reserved_source_mae"] == evidence["reserved_source_mae"]
                and metadata["reserved_source_r2"] == evidence["reserved_source_r2"],
                "Frozen source model, original supervision or reservation boundary changed")
        checked.append({"algorithm":algorithm,"feature_set":feature_set,"model_sha256":digest(path),
            "metadata_sha256":digest(metadata_path),"original_source_targets":851,"source_refitted_in_this_study":False})
    return heads,checked


def initialize_native_audit(heads):
    global _RUNTIME
    _RUNTIME = study.load_inputs(),heads


def refit_native(task):
    row, number = task
    inputs,heads = _RUNTIME
    candidate,train = row["candidate"],inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Compact refit leaked validation people")
    proxy = candidate["input_mode"] == "source_proxy"
    teacher = heads[candidate["source_algorithm"],candidate["source_feature_set"]] if proxy else None
    source_before = {key:joblib.hash(model) for key,model in heads.items()}
    native_class = study.DynamicsClassifier if candidate["member"] == "core" else study.CatBoostBorg
    estimator_class = MLPClassifier if candidate["member"] == "core" else CatBoostClassifier
    actual_native_fit,actual_estimator_fit = native_class.fit,estimator_class.fit
    specification = inputs["specifications"][candidate["member"]]
    source_fields = study.parent.SETS[candidate["source_feature_set"]]
    raw_fields = [study.parent.NATIVE[name] for name in source_fields]
    expected_features = specification["features"]+([study.OUTPUT] if proxy else raw_fields)
    observed_pair = np.isfinite(fitting[raw_fields].to_numpy(float)).all(axis=1)
    target = fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()
    if specification["target_mode"] == "change_from_prior":
        target = target-fitting.prior_borg.to_numpy(int)
    if candidate["member"] == "core":
        target = target.astype(str)
    observed_rows,observed_targets = [],[]
    def native_fit(model,data):
        pd.testing.assert_frame_equal(data[fitting.columns],fitting)
        require(model.candidate["features"] == expected_features and len(data) == len(fitting),
                "Compact model changed actual rows or its frozen feature recipe")
        if proxy:
            require(not set(study.parent.NATIVE.values())&set(model.candidate["features"]),
                    "Raw physiological fields entered the proxy-only native classifier")
            np.testing.assert_array_equal(data[study.OUTPUT].isna(),~observed_pair)
            query = fitting.loc[observed_pair,raw_fields].rename(columns=dict(zip(raw_fields,source_fields)))
            with threadpool_limits(limits=1):
                expected_proxy = teacher.predict(query)
            np.testing.assert_array_equal(data.loc[observed_pair,study.OUTPUT],expected_proxy)
        else:
            require(study.OUTPUT not in model.candidate["features"],"Measured control acquired a source proxy")
        observed_rows.append(len(data))
        return actual_native_fit(model,data)
    def estimator_fit(estimator,x,y,**kwargs):
        np.testing.assert_array_equal(np.asarray(y),target)
        require(len(x) == len(fitting),"Actual native estimator received generated rows or altered targets")
        if candidate["member"] == "core":
            params = candidate.get("params",{**specification["params"],"max_iter":5000,"max_fun":100000,"tol":.0001})
            require(estimator.max_iter == params["max_iter"] == 5000 and estimator.max_fun == params["max_fun"] == 100000
                    and estimator.alpha == params["alpha"] and list(estimator.hidden_layer_sizes) == params["hidden_layer_sizes"]
                    and estimator.random_state == 42 and not estimator.early_stopping and estimator.solver == "lbfgs",
                    "Actual compact MLP hyperparameters/stopping rule changed")
        else:
            params = estimator.get_params()
            require(params["iterations"] == specification["iterations"] == 900 and params["depth"] == specification["depth"]
                    and params["l2_leaf_reg"] == specification["l2_leaf_reg"] and not params["use_best_model"],
                    "Actual compact CatBoost capacity/stopping rule changed")
        observed_targets.append(len(y))
        return actual_estimator_fit(estimator,x,y,**kwargs)
    with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial fitting histories prohibited")), \
            patch.object(study.parent,"fit_source",side_effect=AssertionError("Source functions must remain frozen")), \
            patch.object(native_class,"fit",new=native_fit),patch.object(estimator_class,"fit",new=estimator_fit):
        model = study.CompactCadenceBorg(candidate,teacher).fit(fitting,inputs["specifications"])
    require(observed_rows == observed_targets == [len(fitting)],"Actual compact native-data/target observer was bypassed")
    predicted = model.predict(validation)
    np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
    require(model.optimizer_summary == row["folds"][number]["optimizer_summary"],"Compact optimizer diagnostics failed exact reproduction")
    if candidate["member"] == "core":
        require(int(model.model.model[1].n_samples_seen_) == len(fitting),"Compact scaling saw held participants")
        observed_data = model.add_features(fitting)
        with np.errstate(all="ignore"):
            medians = np.nanmedian(observed_data[model.model_features].to_numpy(float),axis=0)
        np.testing.assert_allclose(model.model.model[0].statistics_,np.nan_to_num(medians,nan=0.),rtol=0,atol=0)
    require(not set(model.input_features)&{"label","row_key","group_key",study.OUTPUT}
            and not set(vars(model))&{"frame","pool","histories","row_keys","source_fitting","source_reserved"},
            "Current truth, identifiers or a history/query pool entered compact runtime")
    runtime = validation[model.input_features]
    np.testing.assert_array_equal(model.predict(runtime),predicted)
    require({key:joblib.hash(head) for key,head in heads.items()} == source_before,"Native fitting mutated a frozen source function")
    with tempfile.TemporaryDirectory() as directory:
        artifact = Path(directory)/"compact-source-native-borg.joblib"
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),predicted)
    return {"candidate_id":candidate["id"],"fold":number,"actual_native_rows_observed":len(fitting),
        "actual_estimator_delta_targets_observed":len(target),"model_feature_count":len(model.model_features),
        "natural_missing_representation_rows":int((~observed_pair).sum()) if proxy else None,
        "optimizer_summary":model.optimizer_summary,"source_functions_frozen":True,"reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    train,test = inputs["train"],inputs["test"]
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
            and selection["plan"] == study.plan() and len(selection["results"]) == 32
            and selection["train_row_keys"] == train.row_key.tolist(),"Compact source selection changed or remains incomplete")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
            and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["synthetic_training_rows"] == selection["new_native_borg_targets"] == 0
            and selection["actual_source_fitting_targets"] == 851 and selection["source_reserved_targets_not_fitted"] == 206,
            "Original exact native target, person holdout, public-real constraint or source reservation changed")
    original = inputs["parents"][0][0]
    pd.testing.assert_frame_equal(inputs["frame"][original.columns],original)
    require(len(inputs["source_fitting"]) == 851 and len(inputs["source_reserved"]) == 206
            and not set(inputs["source_fitting"].group_key)&set(inputs["source_reserved"].group_key),"Source reserved people changed")
    relative_fields = [study.parent.NATIVE[name] for name in study.parent.SETS["relative"]]
    require(int((~np.isfinite(inputs["frame"][relative_fields].to_numpy(float)).all(axis=1)).sum()) == 11,
            "Naturally missing physiology cases changed")
    heads,source_evidence = check_source_artifacts(inputs)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    previous = json.loads((study.parent.DIRECTORY/"selection.json").read_text())
    warnings_in_grid = []
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted) <= {f"Borg {i}" for i in range(11)},
                "Compact OOF case count/scale changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
                and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"],"Compact OOF score changed")
        if candidate["algorithm"] == "previous_real_control":
            inherited = next(r for r in previous["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,inherited["oof_predictions"])
            continue
        require(len(row["folds"]) == 5,"Compact native folds missing")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Compact frozen fold inputs changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            proxy = candidate["input_mode"] == "source_proxy"
            raw = [study.parent.NATIVE[name] for name in study.parent.SETS[candidate["source_feature_set"]]]
            missing_count = int((~np.isfinite(train.iloc[fit][raw].to_numpy(float)).all(axis=1)).sum())
            info = saved["optimizer_summary"]
            require(info["actual_native_fit_rows"] == len(fit) and info["synthetic_rows"] == info["artificial_history_views"] == 0
                    and info["actual_auxiliary_source_targets"] == (851 if proxy else 0) and not info["source_fitting_performed_here"]
                    and info["natural_missing_representation_rows"] == (missing_count if proxy else None)
                    and info["model_feature_count"] == len(inputs["specifications"][candidate["member"]]["features"])+(1 if proxy else 2),
                    "Compact real fitting rows, missing representation or feature counts changed")
            if candidate["member"] == "core":
                params = candidate.get("params",{**inputs["specifications"]["core"]["params"],"max_iter":5000,"max_fun":100000})
                require(info["maximum_iterations"] == 5000 and info["maximum_function_evaluations"] == 100000
                        and info["hidden_layer_sizes"] == params["hidden_layer_sizes"] and info["alpha"] == params["alpha"]
                        and 0 < info["iterations"] <= 5000 and np.isfinite(info["fitting_loss"]),"Compact MLP capacity/L2/budget changed")
            if info["convergence_warnings"]:
                warnings_in_grid.append([candidate["id"],number])
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"],
            "Compact winner differs from the predeclared native CV rule")
    source_rows = [r for r in selection["results"] if r["candidate"].get("input_mode") == "source_proxy"]
    best = max(source_rows,key=lambda r:r["accuracy_mean"])
    by_member = {member:max((r for r in source_rows if r["candidate"]["member"] == member),key=lambda r:r["accuracy_mean"])
                 for member in ("core","cat")}
    measured = {r["candidate"]["member"]:r for r in selection["results"] if r["candidate"].get("input_mode") == "measured_relative"}
    tuned_core = by_member["core"]["candidate"]
    fixed_budget = next(r for r in source_rows if r["candidate"]["member"] == "core"
        and r["candidate"]["source_algorithm"] == tuned_core["source_algorithm"]
        and r["candidate"]["params"]["hidden_layer_sizes"] == [16,8] and r["candidate"]["params"]["alpha"] == 10.)
    selected = {r["candidate"]["id"]:r for r in [*by_member.values(),*measured.values(),fixed_budget]}
    checked = []
    with ProcessPoolExecutor(max_workers=2,initializer=initialize_native_audit,initargs=(heads,)) as pool:
        futures = [pool.submit(refit_native,(row,number)) for row in selected.values() for number in range(5)]
        for future in as_completed(futures):
            result = future.result()
            checked.append(result)
            print(f"Independent compact CADENCE refit {result['candidate_id']} fold{result['fold']+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A compact source model qualified: freeze/evaluate its original179 artifact before closing the audit")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == 108/179,"Retained original native test model changed")
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(path),"previous_verification_sha256":digest(study.PARENT_AUDIT),
        "public_real_data_policy_sha256":signature["public_real_data_policy_sha256"],"all_32_oof_recipes_recomputed":True,
        "source_artifact_hashes_verified":source_evidence,"fresh_source_fitting_performed":False,
        "source_fitting_targets":851,"source_fitting_people":123,"source_reserved_targets":206,"source_reserved_people":32,
        "source6to20_targets_remain_separate":True,"compact_native_features_exclude_redundant_raw_fields":True,
        "all_original_native_rows_and_labels_preserved":True,"natural_missing_native_pairs":11,
        "native_missing_proxy_cells_verified_at_actual_fitter":True,"native_delta_targets_verified_at_actual_estimator":True,
        "native_preprocessing_fitting_people_only":True,"artificial_history_fitting_disabled":True,
        "source_functions_frozen_during_native_fitting":True,"best_source_candidate_id":best["candidate"]["id"],
        "best_source_cv_accuracy":best["accuracy_mean"],"best_source_by_member":{member:{"candidate":r["candidate"],
            "accuracy_mean":r["accuracy_mean"]} for member,r in by_member.items()},
        "measured_relative_controls":{member:{"candidate_id":r["candidate"]["id"],"accuracy_mean":r["accuracy_mean"]} for member,r in measured.items()},
        "best_core_matching_16_8_alpha10_id":fixed_budget["candidate"]["id"],"best_core_matching_16_8_alpha10_cv":fixed_budget["accuracy_mean"],
        "native_recipes_independently_refitted":sorted(selected),"actual_native_refits":sorted(checked,key=lambda r:(r["candidate_id"],r["fold"])),
        "actual_native_target_calls_observed":len(checked),"convergence_warning_folds_in_grid":warnings_in_grid,
        "winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],"new_test_gate_passed":False,
        "original_training_cases":487,"original_test_cases":179,"best_verified_test_correct":incumbent["correct"],
        "best_verified_test_accuracy":incumbent["accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Actual public source851 targets and original native487/179 cohorts. Frozen source6-20 functions produce compact features; natural missing physiology propagates without artificial masks, generated examples or row filtering. Capacity/L2 selection uses fixed native person CV. No source target conversion, invented clocks, current truth/IDs at runtime, source-reserved fitting or native test tuning."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
