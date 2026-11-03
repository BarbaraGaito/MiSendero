"""Independently verify recorded-order source functions and matched native recipes."""
from __future__ import annotations

import argparse
import json
import tempfile
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score,mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from threadpoolctl import threadpool_limits

import fatigue_emap_ordered_functions as study
from public_sources import digest
from validate_fatigue_release import validate as validate_incumbent

_RUNTIME = None


def require(value,reason):
    if not value:
        raise ValueError(reason)


def query(frame,key):
    values = {"prior_borg":frame.prior_borg.to_numpy(float)}
    if key in ("T3","T4","emap"):
        values["prior2_borg"] = frame.prior2_borg.to_numpy(float)
    return pd.DataFrame(values,index=frame.index)


def verify_sources(inputs):
    ordered,existing = study.read_sources(inputs)
    proof = inputs["previous_audit"]
    require(proof["source_verification_refits"] == len(proof["actual_source_functions_independently_refitted"]) == 9
        and proof["original_source_delta_targets_observed_at_actual_fitter"] and proof["source_scaling_and_weights_fitting_people_only"],
        "Preceding source supervision was not independently verified")
    inherited_hashes = proof["frozen_source_artifact_hashes"]
    for name,expected in inherited_hashes.items():
        require(digest(study.parent.DIRECTORY/"teachers"/name) == expected,"Inherited source weights/metadata changed")
    paths = [study.DIRECTORY/"teachers"/f"{algorithm}{extension}" for algorithm in study.parent.ALGORITHMS for extension in (".joblib",".json")]
    before = {path.name:digest(path) for path in paths}
    data = inputs["source"]
    emap = data[data.source_domain.eq("emap")&data.source_partition.eq("fitting")]
    reserved = data[data.source_domain.eq("emap")&data.source_partition.eq("reserved")]
    fresh_all,checked = {},[]
    for algorithm in study.parent.ALGORITHMS:
        kind = type(study.parent.estimator(algorithm))
        original = kind.fit
        calls = []
        def observe(model,x,y,**kwargs):
            slot = ("T2","T3","T4")[len(calls)]
            part = emap[emap.current_slot.eq(int(slot[1:]))]
            target = part.current_rpe.to_numpy()-part.prior_borg.to_numpy()
            np.testing.assert_array_equal(y,target)
            require(len(x) == len(part) and "sample_weight" not in kwargs,"Ordered source fitting changed distinct actual rows or unit per-person weight")
            require(model.get_params() == study.parent.estimator(algorithm).get_params(),"Ordered source estimator hyperparameters changed")
            calls.append({"slot":slot,"actual_targets":len(y),"actual_people":part.group_key.nunique(),"actual_scaled_x":np.asarray(x).copy()})
            return original(model,x,y,**kwargs)
        with patch.object(kind,"fit",new=observe),patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
            fresh = study.fit_ordered_functions(data,algorithm)
        require(len(calls) == 3,"Ordered source fitter observer bypassed")
        meta = json.loads((study.DIRECTORY/"teachers"/(algorithm+".json")).read_text())
        require(not meta["source_reserved_scores_used_for_model_selection"] and meta["native_targets_used_for_source_fitting"] == 0,"Source held/native targets entered fitting")
        seen = []
        for call in calls:
            slot = call["slot"]
            features = ["prior_borg"] if slot == "T2" else ["prior_borg","prior2_borg"]
            part = emap[emap.current_slot.eq(int(slot[1:]))]
            require(part[features].notna().all().all() and call["actual_targets"] == (82 if slot == "T4" else 83),"Unobserved source features were invented or source cases dropped")
            seen.extend(part.row_key)
            model = fresh[slot]
            np.testing.assert_array_equal(model[0].statistics_,np.median(part[features].to_numpy(),axis=0))
            require(model[0].n_features_in_ == len(features) and int(model[1].n_samples_seen_) == len(part),"Source preprocessing or T2available features changed")
            imputed = model[0].transform(part[features])
            np.testing.assert_allclose(model[1].mean_,imputed.mean(axis=0),rtol=0,atol=1e-12)
            np.testing.assert_allclose(call.pop("actual_scaled_x"),model[1].transform(imputed),rtol=0,atol=1e-12)
            with threadpool_limits(limits=1):
                np.testing.assert_allclose(model.predict(query(inputs["frame"],slot)),ordered[algorithm][slot].predict(query(inputs["frame"],slot)),rtol=0,atol=1e-12)
                held = reserved[reserved.current_slot.eq(int(slot[1:]))]
                prediction = held.prior_borg.to_numpy()+model.predict(held[features])
            require(meta["reserved_scores"][slot]["reserved_actual_pairs"] == len(held)
                and meta["reserved_scores"][slot]["mae_descriptive_only"] == float(mean_absolute_error(held.current_rpe,prediction)),"Descriptive ordered-source reserved score changed")
            checked.append({"algorithm":algorithm,**call,"actual_targets_and_source_only_scaling_verified":True,
                "all666native_query_predictions_reproduced":True,"invented_features":0,"synthetic_rows":0})
        require(len(seen) == len(set(seen)) == 248,"An EMAPtarget was replicated across ordered functions")
        fresh_all[algorithm] = fresh
        print(f"Independent source-order refits:{algorithm};83/83/82 distinct actual targets",flush=True)
    require(before == {path.name:digest(path) for path in paths},"Verification changed frozen ordered artifacts")
    for name,expected in inherited_hashes.items():
        require(digest(study.parent.DIRECTORY/"teachers"/name) == expected,"Verification changed inherited source artifacts")
    return fresh_all,existing,checked,before,inherited_hashes


def initialize_native(ordered,existing):
    global _RUNTIME
    _RUNTIME = study.load_inputs(),ordered,existing


def refit_native(task):
    row,number,is_ordered = task
    inputs,ordered_all,existing_all = _RUNTIME
    candidate,train = row["candidate"],inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Native fitting/validation people overlap")
    algorithm = candidate["source_algorithm"]
    ordered,existing = ordered_all[algorithm],existing_all[algorithm]
    before = joblib.hash((ordered,existing))
    generated = ([study.OUTPUTS[s] for s in ("T2","T3","T4")] if is_ordered else [study.parent.OUTPUTS["emap"]])
    if candidate["include_worker_sts"]:
        generated += [study.parent.OUTPUTS[d] for d in ("worker","sts")]
    specification = inputs["specifications"][candidate["member"]]
    expected_features = specification["features"]+generated
    native_class = study.parent.DynamicsClassifier if candidate["member"] == "core" else study.parent.native.CatBoostBorg
    estimator_class = MLPClassifier if candidate["member"] == "core" else CatBoostClassifier
    actual_fit,actual_estimator_fit = native_class.fit,estimator_class.fit
    row_calls,target_calls = [],[]
    raw_target = fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()-fitting.prior_borg.to_numpy(int)
    target = raw_target.astype(str) if candidate["member"] == "core" else raw_target
    def observe(model,data):
        pd.testing.assert_frame_equal(data[fitting.columns],fitting)
        require(len(data) == len(fitting) and model.candidate["features"] == expected_features,"Native real rows/features changed")
        with threadpool_limits(limits=1):
            if is_ordered:
                for slot in ("T2","T3","T4"):
                    np.testing.assert_allclose(data[study.OUTPUTS[slot]],ordered[slot].predict(query(fitting,slot)),rtol=0,atol=0)
            else:
                np.testing.assert_allclose(data[study.parent.OUTPUTS["emap"]],existing["emap"].predict(query(fitting,"emap")),rtol=0,atol=0)
            if candidate["include_worker_sts"]:
                for domain in ("worker","sts"):
                    np.testing.assert_allclose(data[study.parent.OUTPUTS[domain]],existing[domain].predict(query(fitting,domain)),rtol=0,atol=0)
        row_calls.append(len(data))
        return actual_fit(model,data)
    def observe_estimator(model,x,y,**kwargs):
        np.testing.assert_array_equal(np.asarray(y),target)
        require(len(x) == len(fitting),"Actual native estimator saw generated rows")
        if candidate["member"] == "core":
            require(model.alpha == 10 and list(model.hidden_layer_sizes) == [16,8] and model.max_iter == 5000
                and model.max_fun == 100000 and model.solver == "lbfgs" and not model.early_stopping and model.random_state == 42,"Ordered native MLP changed")
        else:
            params = model.get_params()
            require(params["iterations"] == 900 and params["depth"] == specification["depth"] and params["l2_leaf_reg"] == specification["l2_leaf_reg"]
                and not params["use_best_model"],"Ordered native CatBoost changed")
        target_calls.append(len(y))
        return actual_estimator_fit(model,x,y,**kwargs)
    with patch.object(native_class,"fit",new=observe),patch.object(estimator_class,"fit",new=observe_estimator),\
            patch.object(study,"fit_ordered_functions",side_effect=AssertionError("Native fitting cannot change source functions")),\
            patch.object(study.parent,"fit_sources",side_effect=AssertionError("Native fitting cannot change inherited source functions")),\
            patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
        model = (study.OrderedHistoryBorg(candidate,ordered,existing) if is_ordered else study.parent.EmapHistoryBorg(candidate,existing)).fit(fitting,inputs["specifications"])
    require(row_calls == target_calls == [len(fitting)],"Actual native observers bypassed")
    prediction = model.predict(validation)
    np.testing.assert_array_equal(prediction,np.asarray(row["oof_predictions"])[val])
    require(model.optimizer_summary == row["folds"][number]["optimizer_summary"],"Paired native optimizer diagnostics failed reproduction")
    if candidate["member"] == "core":
        pipeline = model.model.model
        require(int(pipeline[1].n_samples_seen_) == len(fitting),"Native preprocessing included held-out people")
        transformed = study.add_features(fitting,ordered,model.existing) if is_ordered else study.parent.add_features(fitting,model.heads)
        np.testing.assert_array_equal(pipeline[0].statistics_,np.nan_to_num(np.nanmedian(transformed[model.model_features].to_numpy(float),axis=0),nan=0))
        np.testing.assert_allclose(pipeline[1].mean_,pipeline[0].transform(transformed[model.model_features]).mean(axis=0),rtol=0,atol=1e-12)
    runtime = validation[model.input_features]
    require(not set(model.input_features)&{"label","row_key","group_key",*generated},"Current truth/IDs/precomputed response entered runtime")
    np.testing.assert_array_equal(model.predict(runtime),prediction)
    require(joblib.hash((ordered,existing)) == before,"Native fitting changed source weights")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/"actual-ordered-source-borg.joblib"
        joblib.dump(model,path)
        np.testing.assert_array_equal(joblib.load(path).predict(runtime),prediction)
    return {"candidate_id":candidate["id"],"fold":number,"recorded_order_functions":is_ordered,
        "actual_native_rows_observed":len(fitting),"actual_native_delta_targets_observed":len(target),
        "optimizer_summary":model.optimizer_summary,"source_weights_frozen":True,"reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    train,test = inputs["train"],inputs["test"]
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
        and selection["plan"] == study.plan(inputs["previous_audit"]) and len(selection["results"]) == 10
        and selection["train_row_keys"] == train.row_key.tolist(),"Frozen recorded-order study changed or incomplete")
    require(selection["evaluation_denominator"] == len(train) == 487 and selection["test_denominator"] == len(test) == 179
        and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
        and selection["actual_distinct_emap_fitting_targets"] == 248 and selection["emap_reserved_targets_not_fitted"] == 57
        and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == 0
        and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
        and not selection["source_targets_pooled_across_instruments"] and not selection["native_phase_assignment_performed"],
        "Original native/source cases, source target meaning or test gate changed")
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    warnings_in_grid = []
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in selection["plan"] and len(predicted) == 487 and set(predicted)<={f"Borg {i}" for i in range(11)},"OOF native targets/case count changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
            and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"],"Recorded-order OOF accuracy changed")
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,old["oof_predictions"])
            continue
        expected_option = inputs["previous_audit"]["best_new_by_member"][candidate["member"]]["candidate"]["include_worker_sts"]
        require(candidate["include_worker_sts"] == expected_option and len(row["folds"]) == 5,"Preceding-CV fixed source inclusion changed")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist() and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Frozen recorded-order fold membership changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            info = saved["optimizer_summary"]
            require(info["actual_native_fit_rows"] == len(fit) and info["actual_distinct_emap_source_targets"] == 248
                and info["source_order_target_counts"] == {"T2":83,"T3":83,"T4":82}
                and info["additional_existing_source_targets"] == (302 if candidate["include_worker_sts"] else 0)
                and info["native_feature_count"] == len(inputs["specifications"][candidate["member"]]["features"])+3+(2 if expected_option else 0)
                and info["synthetic_rows"] == info["artificial_history_views"] == 0
                and not info["source_functions_refitted_in_native_fitting"] and not info["native_phase_assignment_performed"],"Recorded-order native/source scope changed")
            if info["convergence_warnings"]:
                warnings_in_grid.append([candidate["id"],number])
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"] and selection["best_cv_accuracy"] == winner["accuracy_mean"],"Recorded-order winner changed")
    new = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    best = {member:max((r for r in new if r["candidate"]["member"] == member),key=lambda r:r["accuracy_mean"]) for member in ("core","cat")}
    paired = {member:next(r for r in inputs["previous"]["results"] if r["candidate"].get("member") == member
        and r["candidate"].get("source_algorithm") == row["candidate"]["source_algorithm"]
        and r["candidate"].get("include_worker_sts") == row["candidate"]["include_worker_sts"]) for member,row in best.items()}
    ordered,existing,source_checks,source_hashes,inherited_hashes = verify_sources(inputs)
    checked = []
    jobs = [(r,number,True) for r in best.values() for number in range(5)]+[(r,number,False) for r in paired.values() for number in range(5)]
    with ProcessPoolExecutor(max_workers=2,initializer=initialize_native,initargs=(ordered,existing)) as pool:
        for future in as_completed([pool.submit(refit_native,job) for job in jobs]):
            item = future.result()
            checked.append(item)
            print(f"Independent source-order paired native refit {item['candidate_id']} fold{item['fold']+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
        "Recorded-order model qualified:freeze/evaluate original179 artifact before closing audit")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == 108/179,"Retained original native test model changed")
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(path),"previous_verification_sha256":digest(study.PARENT_AUDIT),"predeclared_plan_sha256":digest(study.DECLARATION),
        "fitting_context_diagnostic_sha256":digest(study.DIAGNOSTIC),"public_real_data_policy_sha256":signature["public_real_data_policy_sha256"],
        "all_10_oof_recipes_recomputed":True,"source_verification_refits":9,"actual_source_functions_independently_refitted":source_checks,
        "frozen_source_artifact_hashes":source_hashes,"inherited_source_artifact_hashes":inherited_hashes,"source_artifacts_unchanged_after_verification":True,
        "inherited_source_functions_refitted":False,"original248targets_unique_across_each_algorithm_source_tasks":True,
        "original_source_delta_targets_observed_at_actual_fitter":True,"t2_unobserved_second_prior_excluded":True,
        "actual_native_target_calls_observed":len(checked),"actual_native_refits":sorted(checked,key=lambda r:(r["candidate_id"],r["fold"])),
        "original_native_rows_and_targets_preserved":True,"native_source_changes_independently_computed":True,
        "native_delta_targets_observed_at_actual_fitter":True,"native_preprocessing_fitting_people_only":True,"source_weights_frozen_during_native_fitting":True,
        "native_phase_assignment_performed":False,"synthetic_rows":0,"invented_source_clocks_or_sensor_joins":0,
        "best_new_by_member":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in best.items()},
        "matched_pooled_order_controls":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in paired.items()},
        "best_new_cv_accuracy":max(r["accuracy_mean"] for r in best.values()),"winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],
        "convergence_warning_folds_in_grid":warnings_in_grid,"new_test_gate_passed":False,"original_training_cases":487,"original_test_cases":179,
        "best_verified_test_correct":108,"best_verified_test_accuracy":108/179,"target_accuracy":.8,"achieved":False,
        "scope":"Only actual public ordered EMAPpairs and original native exact targets.9ordered source refits verify83/83/82distinct targets, available measured priors and source-only scaling. Existing Worker/STS functions remain frozen from audited predecessor. Best new native classifiers and exact matching pooled-order controls refitted in all5original person folds. All3source order functions queried as alternatives,without assigning native phases. No synthetic rows, imputed targets, guessed source times/sensors or changed native487/179cases."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
