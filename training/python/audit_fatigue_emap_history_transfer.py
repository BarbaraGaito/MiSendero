"""Reproduce actual source supervision and paired native ordered-history recipes."""
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
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from threadpoolctl import threadpool_limits

import fatigue_emap_history_transfer as study
from public_sources import digest
from validate_fatigue_release import validate as validate_incumbent

_RUNTIME = None


def require(value,reason):
    if not value:
        raise ValueError(reason)


def independent_query(frame,domain):
    values = {"prior_borg":frame.prior_borg.to_numpy(float)}
    if domain == "emap":
        values["prior2_borg"] = frame.prior2_borg.to_numpy(float)
    return pd.DataFrame(values,index=frame.index)


def verify_sources(inputs,signature):
    paths = [study.DIRECTORY/"teachers"/f"{algorithm}{extension}" for algorithm in study.ALGORITHMS for extension in (".joblib",".json")]
    hashes = {path.name:digest(path) for path in paths}
    stored = study.read_sources(signature)
    all_heads,checked = {},[]
    for algorithm in study.ALGORITHMS:
        kind = type(study.estimator(algorithm))
        actual_fit = kind.fit
        calls = []
        def observe(estimator,x,y,**kwargs):
            domain = list(study.source.FEATURES)[len(calls)]
            part = inputs["source"]
            part = part[part.source_domain.eq(domain)&part.source_partition.eq("fitting")]
            target = part[study.source.TARGET_COLUMNS[domain]].to_numpy(float)-part.prior_borg.to_numpy(float)
            np.testing.assert_array_equal(y,target)
            require(len(x) == len(part),"Actual source fitter saw generated or reserved rows")
            weights = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
            weights *= len(part)/weights.sum()
            np.testing.assert_array_equal(kwargs["sample_weight"],weights)
            expected_params = study.estimator(algorithm).get_params()
            require(estimator.get_params() == expected_params,"Actual source hyperparameters differ from the frozen plan")
            calls.append({"domain":domain,"actual_target_count":len(y),"actual_people":part.group_key.nunique(),
                "fractional_original_targets":int((part[study.source.TARGET_COLUMNS[domain]]%1 != 0).sum()),
                "observed_zero_priors":int(part.prior_borg.eq(0).sum()),"actual_scaled_inputs":np.asarray(x).copy()})
            return actual_fit(estimator,x,y,**kwargs)
        with patch.object(kind,"fit",new=observe),patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
            fresh = study.fit_sources(inputs["source"],algorithm)
        require(len(calls) == 3,"Source fitting observer bypassed")
        for call in calls:
            domain = call["domain"]
            part = inputs["source"]
            part = part[part.source_domain.eq(domain)&part.source_partition.eq("fitting")]
            features = ["prior_borg","prior2_borg"] if domain == "emap" else ["prior_borg"]
            head = fresh[domain]
            medians = np.nanmedian(part[features].to_numpy(float),axis=0)
            np.testing.assert_array_equal(head[0].statistics_,medians)
            imputed = head[0].transform(part[features])
            np.testing.assert_allclose(head[1].mean_,imputed.mean(axis=0),rtol=0,atol=1e-12)
            require(int(head[1].n_samples_seen_) == len(part),"Source preprocessing included reserved or native people")
            np.testing.assert_allclose(call.pop("actual_scaled_inputs"),head[1].transform(imputed),rtol=0,atol=1e-12)
            query = independent_query(inputs["frame"],domain)
            with threadpool_limits(limits=1):
                np.testing.assert_allclose(head.predict(query),stored[algorithm][domain].predict(query),rtol=0,atol=1e-12)
                np.testing.assert_allclose(head.predict(part[features]),stored[algorithm][domain].predict(part[features]),rtol=0,atol=1e-12)
            checked.append({"algorithm":algorithm,**call,"actual_fitter_targets_weights_and_scaling_verified":True,
                "all_666_native_query_predictions_reproduced":True,"synthetic_rows":0})
        reserved = inputs["source"]
        reserved = reserved[reserved.source_domain.eq("emap")&reserved.source_partition.eq("reserved")]
        with threadpool_limits(limits=1):
            prediction = reserved.prior_borg.to_numpy()+fresh["emap"].predict(reserved[["prior_borg","prior2_borg"]])
        metadata = json.loads((study.DIRECTORY/"teachers"/(algorithm+".json")).read_text())
        require(not metadata["source_reserved_scores_used_for_model_selection"] and metadata["native_targets_used_for_source_fitting"] == 0,
            "Source fitting depended on native or reserved target selection")
        require(metadata["reserved_emap_mae_descriptive_only"] == float(mean_absolute_error(reserved.current_rpe,prediction))
            and metadata["reserved_emap_rmse_descriptive_only"] == float(np.sqrt(mean_squared_error(reserved.current_rpe,prediction))),
            "Descriptive source-held metrics differ from original57 actual pairs")
        all_heads[algorithm] = fresh
        print(f"Independent ordered-history source refit {algorithm}:248EMAP+253Worker+49STS",flush=True)
    require(hashes == {path.name:digest(path) for path in paths},"Verification changed frozen source artifacts")
    return all_heads,checked,hashes


def worker_initialize(heads):
    global _RUNTIME
    _RUNTIME = study.load_inputs(),heads


def refit_native(job):
    row,number = job
    inputs,all_heads = _RUNTIME
    candidate,train = row["candidate"],inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Native fitting/validation people overlap")
    heads = all_heads[candidate["source_algorithm"]]
    domains = ("emap","worker","sts") if candidate["include_worker_sts"] else ("emap",)
    before = joblib.hash(heads)
    specification = inputs["specifications"][candidate["member"]]
    expected_features = specification["features"]+[study.OUTPUTS[domain] for domain in domains]
    actual_class = study.DynamicsClassifier if candidate["member"] == "core" else study.native.CatBoostBorg
    estimator_class = MLPClassifier if candidate["member"] == "core" else CatBoostClassifier
    actual_native_fit,actual_estimator_fit = actual_class.fit,estimator_class.fit
    raw_target = fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()-fitting.prior_borg.to_numpy(int)
    target = raw_target.astype(str) if candidate["member"] == "core" else raw_target
    row_calls,target_calls = [],[]
    def native_fit(model,data):
        pd.testing.assert_frame_equal(data[fitting.columns],fitting)
        require(len(data) == len(fitting) and model.candidate["features"] == expected_features,"Native fitter changed actual rows or acquired extra inputs")
        with threadpool_limits(limits=1):
            for domain in domains:
                expected = heads[domain].predict(independent_query(fitting,domain))
                np.testing.assert_allclose(data[study.OUTPUTS[domain]],expected,rtol=0,atol=0)
        row_calls.append(len(data))
        return actual_native_fit(model,data)
    def estimator_fit(estimator,x,y,**kwargs):
        np.testing.assert_array_equal(np.asarray(y),target)
        require(len(x) == len(fitting),"Actual native estimator saw generated rows")
        if candidate["member"] == "core":
            require(estimator.alpha == 10 and list(estimator.hidden_layer_sizes) == [16,8] and estimator.solver == "lbfgs"
                and estimator.max_iter == 5000 and estimator.max_fun == 100000 and estimator.random_state == 42 and not estimator.early_stopping,
                "Actual ordered-history MLP parameters changed")
        else:
            params = estimator.get_params()
            require(params["iterations"] == 900 and params["depth"] == specification["depth"]
                and params["l2_leaf_reg"] == specification["l2_leaf_reg"] and not params["use_best_model"],"Actual ordered-history CatBoost parameters changed")
        target_calls.append(len(y))
        return actual_estimator_fit(estimator,x,y,**kwargs)
    with patch.object(actual_class,"fit",new=native_fit),patch.object(estimator_class,"fit",new=estimator_fit),\
            patch.object(study,"fit_sources",side_effect=AssertionError("Native fitting cannot update source weights")),\
            patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
        model = study.EmapHistoryBorg(candidate,heads).fit(fitting,inputs["specifications"])
    require(row_calls == target_calls == [len(fitting)],"Actual native row/target observer bypassed")
    predicted = model.predict(validation)
    np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
    require(model.optimizer_summary == row["folds"][number]["optimizer_summary"],"Ordered-history optimizer diagnostics failed reproduction")
    if candidate["member"] == "core":
        pipeline = model.model.model
        require(int(pipeline[1].n_samples_seen_) == len(fitting),"Native preprocessing saw held-out people")
        values = study.add_features(fitting,model.heads)
        np.testing.assert_array_equal(pipeline[0].statistics_,np.nan_to_num(np.nanmedian(values[model.model_features].to_numpy(float),axis=0),nan=0))
        imputed = pipeline[0].transform(values[model.model_features])
        np.testing.assert_allclose(pipeline[1].mean_,imputed.mean(axis=0),rtol=0,atol=1e-12)
    runtime = validation[model.input_features]
    require(not set(model.input_features)&{"label","row_key","group_key",*study.OUTPUTS.values()},"Actual truth/IDs/precomputed query labels entered runtime")
    np.testing.assert_array_equal(model.predict(runtime),predicted)
    require(joblib.hash(heads) == before,"Native fitting changed source weights")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/"actual-history-model.joblib"
        joblib.dump(model,path)
        np.testing.assert_array_equal(joblib.load(path).predict(runtime),predicted)
    return {"candidate_id":candidate["id"],"fold":number,"actual_native_rows_observed":len(fitting),
        "actual_native_delta_targets_observed":len(target),"optimizer_summary":model.optimizer_summary,
        "source_weights_frozen":True,"reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    train,test = inputs["train"],inputs["test"]
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
        and selection["plan"] == study.plan() and len(selection["results"]) == 16
        and selection["train_row_keys"] == train.row_key.tolist(),"Frozen ordered-history plan changed or incomplete")
    require(selection["evaluation_denominator"] == len(train) == 487 and selection["test_denominator"] == len(test) == 179
        and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
        and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
        and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == 0
        and selection["new_emap_actual_fitting_targets"] == 248 and selection["new_emap_reserved_targets_not_fitted"] == 57
        and selection["existing_worker_sts_fitting_targets"] == 302 and not selection["source_targets_pooled_across_instruments"],
        "Ordered-history native/source target scope or reservation changed")
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    warnings_in_grid = []
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted)<={f"Borg {i}" for i in range(11)},"OOF native labels or case count changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
            and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"],"Ordered-history OOF score changed")
        if candidate["algorithm"] == "previous_real_control":
            previous = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,previous["oof_predictions"])
            continue
        require(len(row["folds"]) == 5,"New native folds missing")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist() and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),
                "Frozen native fold membership/recipe changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            info = saved["optimizer_summary"]
            require(info["actual_native_fit_rows"] == len(fit) and info["actual_auxiliary_source_targets"] == (550 if candidate["include_worker_sts"] else 248)
                and info["native_feature_count"] == len(inputs["specifications"][candidate["member"]]["features"])+(3 if candidate["include_worker_sts"] else 1)
                and info["synthetic_rows"] == info["artificial_history_views"] == info["native_rows_duplicated"] == 0
                and not info["source_functions_refitted_in_native_fitting"],"Actual native fitting rows, features or frozen source weights changed")
            if info["convergence_warnings"]:
                warnings_in_grid.append([candidate["id"],number])
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"],"Winner changed from frozen native CV rule")
    new = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    by_member = {member:max((r for r in new if r["candidate"]["member"] == member),key=lambda r:r["accuracy_mean"]) for member in ("core","cat")}
    matched = {member:next(r for r in new if r["candidate"]["member"] == member
        and r["candidate"]["source_algorithm"] == best["candidate"]["source_algorithm"]
        and r["candidate"]["include_worker_sts"] != best["candidate"]["include_worker_sts"]) for member,best in by_member.items()}
    selected = {r["candidate"]["id"]:r for r in [*by_member.values(),*matched.values()]}
    heads,source_checks,source_hashes = verify_sources(inputs,signature)
    checked = []
    with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize,initargs=(heads,)) as pool:
        for future in as_completed([pool.submit(refit_native,(row,number)) for row in selected.values() for number in range(5)]):
            info = future.result()
            checked.append(info)
            print(f"Independent ordered-history native refit {info['candidate_id']} fold{info['fold']+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
        "Ordered-history winner qualified:freeze/evaluate original179 artifact before closing this audit")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == 108/179,"Retained original test model changed")
    best = max(new,key=lambda r:r["accuracy_mean"])
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(path),"input_verification_sha256":digest(study.INPUT_AUDIT),"previous_verification_sha256":digest(study.PARENT_AUDIT),
        "public_real_data_policy_sha256":signature["public_real_data_policy_sha256"],"all_16_oof_recipes_recomputed":True,
        "actual_source_functions_independently_refitted":source_checks,"source_verification_refits":9,
        "frozen_source_artifact_hashes":source_hashes,"source_artifacts_unchanged_after_verification":True,
        "actual_native_target_calls_observed":len(checked),"actual_native_refits":sorted(checked,key=lambda r:(r["candidate_id"],r["fold"])),
        "native_recipes_independently_refitted":sorted(selected),"original_native_rows_and_targets_preserved":True,
        "original_source_delta_targets_observed_at_actual_fitter":True,"source_scaling_and_weights_fitting_people_only":True,
        "native_delta_targets_observed_at_actual_fitter":True,"native_preprocessing_fitting_people_only":True,
        "computed_history_changes_independently_verified":True,"source_weights_frozen_during_native_fitting":True,
        "source_target_pooling_performed":False,"synthetic_rows":0,"invented_source_clocks_or_sensor_joins":0,
        "best_new_candidate_id":best["candidate"]["id"],"best_new_cv_accuracy":best["accuracy_mean"],
        "best_new_by_member":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in by_member.items()},
        "matched_single_or_combined_heads":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in matched.items()},
        "winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],"convergence_warning_folds_in_grid":warnings_in_grid,
        "new_test_gate_passed":False,"original_training_cases":487,"original_test_cases":179,
        "best_verified_test_correct":incumbent["correct"],"best_verified_test_accuracy":incumbent["accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Only actual public original ordered CR10 pairs, separate source outcomes and native exact labels.9source refits verify248EMAP/253Worker/49STS actual deltas and source-only preprocessing;57EMAPreserved pairs never fitted. Paired best native recipes independently refitted across original5person folds with real-row/target observers and immutable source weights. No source timestamp/phase invention, sensor join, MICE/formula targets, generated examples or changed native487/179cases."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
