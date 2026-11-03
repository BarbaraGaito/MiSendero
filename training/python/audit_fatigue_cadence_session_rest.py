"""Reproduce baseline comparisons and independently verify frozen functions."""
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

import fatigue_cadence_session_rest as study
from audit_fatigue_cadence_association import refit_source_functions
from public_sources import digest
from validate_fatigue_release import validate as validate_incumbent

_RUNTIME = None


def require(value, reason):
    if not value:
        raise ValueError(reason)


def independent_state(frame,candidate,head,role):
    hr = frame[study.parent.NATIVE[role+"_hr_bpm"]].to_numpy(float)
    base = frame[study.REST[candidate["baseline"]]].to_numpy(float)
    if candidate["source_feature_set"] == "absolute":
        values,columns = np.column_stack([hr,base]),["hr_bpm","baseline_hr_bpm"]
    else:
        values,columns = np.column_stack([hr-base,hr/base]),["hr_delta_baseline","hr_ratio_baseline"]
    known = np.isfinite(values).all(axis=1)
    predicted = np.full(len(frame),np.nan)
    if known.any():
        query = pd.DataFrame(values[known],columns=columns)
        with threadpool_limits(limits=1):
            predicted[known] = head.predict(query)
    return predicted


def verify_frozen_source_functions(inputs):
    paths = [study.parent.DIRECTORY/"teachers"/f"{algorithm}-{feature_set}{extension}"
        for algorithm in ("ridge","svr","random_forest") for feature_set in study.parent.SETS for extension in (".joblib",".json")]
    before = {path.name:digest(path) for path in paths}
    previous = inputs["previous"]
    fresh,checked = refit_source_functions(previous,study.parent.fingerprint(previous))
    stored = study.read_sources(inputs)
    for (algorithm,feature_set),head in fresh.items():
        for baseline in study.BASELINES:
            candidate = {"baseline":baseline,"source_feature_set":feature_set}
            for role in ("current","prior"):
                query = study.source_query(inputs["frame"],candidate,role)
                known = np.isfinite(query.to_numpy(float)).all(axis=1)
                with threadpool_limits(limits=1):
                    np.testing.assert_allclose(head.predict(query.loc[known]),stored[algorithm,feature_set].predict(query.loc[known]),rtol=0,atol=1e-12)
    require({path.name:digest(path) for path in paths} == before,"Verification refits changed frozen source artifacts")
    return fresh,checked,before


def initialize_native_audit(heads):
    global _RUNTIME
    _RUNTIME = study.load_inputs(),heads


def refit_native(task):
    row,number = task
    inputs,heads = _RUNTIME
    candidate,train = row["candidate"],inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Session-rest audit leaked native people")
    proxy = candidate["algorithm"] == "session_rest_source_representation"
    head = heads[candidate["source_algorithm"],candidate["source_feature_set"]] if proxy else None
    before = {key:joblib.hash(value) for key,value in heads.items()}
    specification = inputs["specifications"][candidate["member"]]
    expected_features = specification["features"]+([study.STATE]+([study.CHANGE] if candidate["representation"] == "current_and_change" else [])
        if proxy else [study.parent.NATIVE["current_hr_bpm"],study.parent.NATIVE["prior_hr_bpm"],study.REST[candidate["baseline"]]])
    target = fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()
    if specification["target_mode"] == "change_from_prior":
        target = target-fitting.prior_borg.to_numpy(int)
    if candidate["member"] == "core":
        target = target.astype(str)
    native_class = study.DynamicsClassifier if candidate["member"] == "core" else study.CatBoostBorg
    estimator_class = MLPClassifier if candidate["member"] == "core" else CatBoostClassifier
    actual_native_fit,actual_estimator_fit = native_class.fit,estimator_class.fit
    observed_rows,observed_targets = [],[]
    def native_fit(model,data):
        pd.testing.assert_frame_equal(data[fitting.columns],fitting)
        require(len(data) == len(fitting) and model.candidate["features"] == expected_features,"Session-rest fitter altered native rows or feature order")
        if proxy:
            require(not set(study.REST.values())&set(expected_features),"Raw session baseline entered a proxy-only classifier")
            current = independent_state(fitting,candidate,head,"current")
            np.testing.assert_allclose(data[study.STATE],current,rtol=0,atol=0,equal_nan=True)
            if candidate["representation"] == "current_and_change":
                prior = independent_state(fitting,candidate,head,"prior")
                np.testing.assert_allclose(data[study.CHANGE],current-prior,rtol=0,atol=0,equal_nan=True)
        else:
            require(not {study.STATE,study.CHANGE}&set(expected_features),"Raw measured control acquired source representations")
        observed_rows.append(len(data))
        return actual_native_fit(model,data)
    def estimator_fit(estimator,x,y,**kwargs):
        np.testing.assert_array_equal(np.asarray(y),target)
        require(len(x) == len(fitting),"Actual session-rest estimator received generated examples or changed targets")
        if candidate["member"] == "core":
            require(estimator.max_iter == 5000 and estimator.max_fun == 100000 and estimator.alpha == 10
                    and list(estimator.hidden_layer_sizes) == [16,8] and estimator.random_state == 42
                    and not estimator.early_stopping and estimator.solver == "lbfgs","Actual session-rest MLP parameters changed")
        else:
            params = estimator.get_params()
            require(params["iterations"] == specification["iterations"] == 900 and params["depth"] == specification["depth"]
                    and params["l2_leaf_reg"] == specification["l2_leaf_reg"] and not params["use_best_model"],"Session-rest CatBoost parameters changed")
        observed_targets.append(len(y))
        return actual_estimator_fit(estimator,x,y,**kwargs)
    with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial fitting histories prohibited")), \
            patch.object(study.parent,"fit_source",side_effect=AssertionError("Native fitting must not update source functions")), \
            patch.object(native_class,"fit",new=native_fit),patch.object(estimator_class,"fit",new=estimator_fit):
        model = study.SessionRestBorg(candidate,head).fit(fitting,inputs["specifications"])
    require(observed_rows == observed_targets == [len(fitting)],"Session-rest native fitter observer was bypassed")
    predicted = model.predict(validation)
    np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
    require(model.optimizer_summary == row["folds"][number]["optimizer_summary"],"Session-rest optimizer diagnostics failed exact reproduction")
    if candidate["member"] == "core":
        pipeline = model.model.model
        require(int(pipeline[1].n_samples_seen_) == len(fitting),"Session-rest preprocessing saw held-out people")
        medians = np.nanmedian(model.add_features(fitting)[model.model_features].to_numpy(float),axis=0)
        np.testing.assert_allclose(pipeline[0].statistics_,np.nan_to_num(medians,nan=0),rtol=0,atol=0)
    runtime = validation[model.input_features]
    np.testing.assert_array_equal(model.predict(runtime),predicted)
    require(not set(model.input_features)&{"label","row_key","group_key",study.STATE,study.CHANGE}
            and not set(vars(model))&{"frame","pool","histories","row_keys","source_fitting","source_reserved"},"Current truth, IDs or query pools entered runtime")
    require({key:joblib.hash(value) for key,value in heads.items()} == before,"Native fitting changed frozen source weights")
    with tempfile.TemporaryDirectory() as directory:
        artifact = Path(directory)/"actual-session-rest-borg.joblib"
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),predicted)
    return {"candidate_id":candidate["id"],"fold":number,"actual_native_rows_observed":len(fitting),
        "actual_native_delta_targets_observed":len(target),"optimizer_summary":model.optimizer_summary,
        "source_functions_frozen_during_native_fitting":True,"reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    train,test = inputs["train"],inputs["test"]
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
            and selection["plan"] == study.plan() and len(selection["results"]) == 34
            and selection["train_row_keys"] == train.row_key.tolist(),"Frozen session-rest selection changed or remains incomplete")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
            and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == 0
            and selection["actual_source_fitting_targets"] == 976 and selection["source_reserved_targets_not_fitted"] == 238
            and not selection["source_functions_refitted"],"Session-rest selection changed target scope, source fitting or native holdout")
    original = inputs["previous"]["frame"]
    pd.testing.assert_frame_equal(inputs["frame"][original.columns],original)
    for column in study.REST.values():
        require(int(inputs["frame"][column].isna().sum()) == 30,"Missing session baselines were filled or cases filtered")
    previous = json.loads((study.parent.DIRECTORY/"selection.json").read_text())
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    warnings_in_grid = []
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted) <= {f"Borg {i}" for i in range(11)},"Session-rest OOF case count/scale changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
                and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"],"Session-rest OOF accuracy changed")
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,old["oof_predictions"])
            continue
        require(len(row["folds"]) == 5,"Session-rest folds missing")
        proxy = candidate["algorithm"] == "session_rest_source_representation"
        if proxy:
            require(candidate["representation"] == study.MODES[candidate["member"]],"Preceding-CV fixed representation mode changed")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Frozen session-rest fold membership changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            info = saved["optimizer_summary"]
            fitting = train.iloc[fit]
            require(info["actual_native_fit_rows"] == len(fit) and info["actual_auxiliary_source_targets"] == (976 if proxy else 0)
                    and info["synthetic_rows"] == info["artificial_history_views"] == 0 and not info["source_fitting_performed_here"]
                    and info["actual_session_baseline_missing_rows"] == int(fitting[study.REST[candidate["baseline"]]].isna().sum()),"Session-rest fitting/missing-data counts changed")
            extra = (2 if candidate["representation"] == "current_and_change" else 1) if proxy else 3
            require(info["model_feature_count"] == len(inputs["specifications"][candidate["member"]]["features"])+extra,"Native session-rest recipe acquired extra features")
            expected_missing = {}
            if proxy:
                base = fitting[study.REST[candidate["baseline"]]].notna().to_numpy()
                current = base&fitting[study.parent.NATIVE["current_hr_bpm"]].notna().to_numpy()
                expected_missing[study.STATE] = int((~current).sum())
                if candidate["representation"] == "current_and_change":
                    prior = base&fitting[study.parent.NATIVE["prior_hr_bpm"]].notna().to_numpy()
                    expected_missing[study.CHANGE] = int((~(current&prior)).sum())
            require(info["natural_missing_representation_rows"] == expected_missing,"Natural missing session physiology was altered before preprocessing")
            if candidate["member"] == "core":
                require(info["maximum_iterations"] == 5000 and 0 < info["iterations"] <= 5000 and np.isfinite(info["fitting_loss"]),"Session-rest solver budget/diagnostics changed")
            if info["convergence_warnings"]:
                warnings_in_grid.append([candidate["id"],number])
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"],"Session-rest winner differs from frozen native CV rule")
    source_rows = [r for r in selection["results"] if r["candidate"]["algorithm"] == "session_rest_source_representation"]
    best = max(source_rows,key=lambda r:r["accuracy_mean"])
    by_member = {member:max((r for r in source_rows if r["candidate"]["member"] == member),key=lambda r:r["accuracy_mean"])
                 for member in study.MODES}
    c = best["candidate"]
    paired = {baseline:next(r for r in source_rows if r["candidate"]["baseline"] == baseline and r["candidate"]["member"] == c["member"]
        and r["candidate"]["source_algorithm"] == c["source_algorithm"] and r["candidate"]["source_feature_set"] == c["source_feature_set"])
        for baseline in study.BASELINES}
    controls = [r for r in selection["results"] if r["candidate"]["algorithm"] == "session_rest_measured_control"]
    matched = {member:next(r for r in controls if r["candidate"]["member"] == member and r["candidate"]["baseline"] == source_row["candidate"]["baseline"])
               for member,source_row in by_member.items()}
    selected = {r["candidate"]["id"]:r for r in [*by_member.values(),*paired.values(),*matched.values()]}
    heads,source_checks,source_hashes = verify_frozen_source_functions(inputs)
    checked = []
    with ProcessPoolExecutor(max_workers=2,initializer=initialize_native_audit,initargs=(heads,)) as pool:
        futures = [pool.submit(refit_native,(row,number)) for row in selected.values() for number in range(5)]
        for future in as_completed(futures):
            info = future.result()
            checked.append(info)
            print(f"Independent session-rest native refit {info['candidate_id']} fold{info['fold']+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A session-rest model qualified: freeze/evaluate its original179 artifact before closing this audit")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == 108/179,"Retained original native test model changed")
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(path),"input_verification_sha256":digest(study.INPUT_AUDIT),"previous_verification_sha256":digest(study.PARENT_AUDIT),
        "source_refit_verifier_code_sha256":digest(Path(__file__).with_name("audit_fatigue_cadence_association.py")),
        "public_real_data_policy_sha256":signature["public_real_data_policy_sha256"],"all_34_oof_recipes_recomputed":True,
        "source_functions_refitted_during_selection":False,"source_functions_refitted_for_independent_verification_only":source_checks,
        "source_verification_refits":6,"frozen_source_artifact_hashes":source_hashes,"source_artifacts_unchanged_after_verification":True,
        "all_native_rows_and_labels_preserved":True,"natural_missing_session_baselines":30,
        "source_states_and_changes_independently_computed":True,"native_rows_and_delta_targets_observed_at_actual_fitter":True,
        "native_preprocessing_fitting_people_only":True,"artificial_history_fitting_disabled":True,"source_functions_frozen_during_native_fitting":True,
        "best_source_candidate_id":best["candidate"]["id"],"best_source_cv_accuracy":best["accuracy_mean"],
        "best_source_by_member":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in by_member.items()},
        "paired_session_baseline_comparison":{baseline:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for baseline,r in paired.items()},
        "matching_measured_controls":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in matched.items()},
        "native_recipes_independently_refitted":sorted(selected),"actual_native_refits":sorted(checked,key=lambda r:(r["candidate_id"],r["fold"])),
        "actual_native_target_calls_observed":len(checked),"convergence_warning_folds_in_grid":warnings_in_grid,
        "winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],"new_test_gate_passed":False,
        "original_training_cases":487,"original_test_cases":179,"best_verified_test_correct":incumbent["correct"],"best_verified_test_accuracy":incumbent["accuracy"],
        "target_accuracy":.8,"achieved":False,"scope":"Only original measured public observations. Session baselines precede first task/query; all487/179 native exact Borg and30 naturally unavailable session baselines retained. Source6-20 retrospective functions frozen in selection; verification refits reproduce their artifacts and all new native queries. No assumed seated posture, generated data, synthetic history, source/native label conversion, changed denominator or native test tuning."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
