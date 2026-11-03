"""Reproduce source association and native exact-Borg representation tests."""
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
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from threadpoolctl import threadpool_limits

import fatigue_cadence_association as study
from public_sources import digest
from validate_fatigue_release import validate as validate_incumbent

_RUNTIME = None


def require(value, reason):
    if not value:
        raise ValueError(reason)


def independently_compute_state(frame,head,feature_set,role):
    source_names = ["hr_bpm","baseline_hr_bpm"] if feature_set == "absolute" else ["hr_delta_baseline","hr_ratio_baseline"]
    native_names = ([study.NATIVE[role+"_hr_bpm"],study.NATIVE["baseline_hr_bpm"]] if feature_set == "absolute" else
                    [study.NATIVE[role+"_hr_delta_baseline"],study.NATIVE[role+"_hr_ratio_baseline"]])
    query = frame[native_names].copy()
    query.columns = source_names
    available = np.isfinite(query.to_numpy(float)).all(axis=1)
    value = np.full(len(frame),np.nan)
    if available.any():
        with threadpool_limits(limits=1):
            value[available] = head.predict(query.loc[available])
    return value


def refit_source_functions(inputs,signature):
    source,reserved = inputs["source_fitting"],inputs["source_reserved"]
    stored = study.read_sources(signature)
    weights = 1./source.groupby("group_key")["group_key"].transform("size").to_numpy()
    weights *= len(source)/weights.sum()
    person_totals = pd.DataFrame({"person":source.group_key,"weight":weights}).groupby("person").weight.sum()
    np.testing.assert_allclose(person_totals,np.full(124,976/124),rtol=0,atol=1e-12)
    heads,checked = {},[]
    for algorithm,estimator_class in (("ridge",study.Ridge),("svr",study.SVR),("random_forest",study.RandomForestRegressor)):
        for feature_set,features in study.SETS.items():
            raw_calls,fit_calls = [],[]
            actual_fit = estimator_class.fit
            def raw_observer(x,y,weight):
                pd.testing.assert_frame_equal(x,source[features])
                np.testing.assert_array_equal(y,source.rpe_native)
                np.testing.assert_array_equal(weight,weights)
                raw_calls.append(len(x))
            def estimator_fit(estimator,x,y,**kwargs):
                require(x.shape == (976,2),"Source fitter received reserved, native or generated examples")
                np.testing.assert_array_equal(y,source.rpe_native)
                np.testing.assert_array_equal(kwargs["sample_weight"],weights)
                require(float(np.min(y)) >= 6 and float(np.max(y)) > 10,"Source6-20 targets were converted or relabeled")
                fit_calls.append(len(y))
                return actual_fit(estimator,x,y,**kwargs)
            with patch.object(estimator_class,"fit",new=estimator_fit):
                head = study.fit_source(source,algorithm,feature_set,raw_observer)
            require(raw_calls == fit_calls == [976],"Source actual-row/target observers were bypassed")
            require(int(head[-2].n_samples_seen_) == 976,"Source scaling saw reserved/native people")
            for query in (source[features],reserved[features],study.source_query(inputs["train"],feature_set,"current"),
                          study.source_query(inputs["train"],feature_set,"prior")):
                with threadpool_limits(limits=1):
                    np.testing.assert_allclose(head.predict(query),stored[algorithm,feature_set].predict(query),rtol=0,atol=1e-12)
            metadata_path = study.DIRECTORY/"teachers"/f"{algorithm}-{feature_set}.json"
            metadata = json.loads(metadata_path.read_text())
            with threadpool_limits(limits=1):
                predicted = head.predict(reserved[features])
            mae,r2 = float(mean_absolute_error(reserved.rpe_native,predicted)),float(r2_score(reserved.rpe_native,predicted))
            require(metadata["signature"] == signature and metadata["actual_source_fitting_rows"] == 976
                    and metadata["actual_source_fitting_people"] == 124 and metadata["reserved_source_rows"] == 238
                    and metadata["native_labels_used_for_source_fitting"] == 0 and not metadata["reserved_source_used_for_selection"]
                    and metadata["reserved_source_mae"] == mae and metadata["reserved_source_r2"] == r2,
                    "Source association boundary or retrospective reserved diagnostics changed")
            heads[algorithm,feature_set] = head
            checked.append({"algorithm":algorithm,"feature_set":feature_set,"actual_source_targets_observed":976,
                "source_fitting_people":124,"reserved_source_mae":mae,"reserved_source_r2":r2,
                "reserved_source_used_for_selection":False,"task":"Retrospective concurrent source association, not pre-RPE forecasting"})
            print(f"Independent retrospective source refit {algorithm}/{feature_set}:976 original6-20 targets",flush=True)
    return heads,checked


def initialize_native_audit(heads):
    global _RUNTIME
    _RUNTIME = study.load_inputs(),heads


def refit_native(task):
    row,number = task
    inputs,heads = _RUNTIME
    candidate,train = row["candidate"],inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Association refit leaked held native people")
    is_source = candidate["algorithm"] == "retrospective_source_association"
    head = heads[candidate["source_algorithm"],candidate["source_feature_set"]] if is_source else None
    before = {key:joblib.hash(model) for key,model in heads.items()}
    native_class = study.DynamicsClassifier if candidate["member"] == "core" else study.CatBoostBorg
    estimator_class = MLPClassifier if candidate["member"] == "core" else CatBoostClassifier
    actual_native_fit,actual_estimator_fit = native_class.fit,estimator_class.fit
    specification = inputs["specifications"][candidate["member"]]
    expected_features = specification["features"]+([study.STATE]+([study.CHANGE] if candidate["representation"] == "current_and_change" else [])
        if is_source else [study.NATIVE[name] for name in ("current_hr_bpm","prior_hr_bpm","baseline_hr_bpm")])
    target = fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()
    if specification["target_mode"] == "change_from_prior":
        target = target-fitting.prior_borg.to_numpy(int)
    if candidate["member"] == "core":
        target = target.astype(str)
    observed_rows,observed_targets = [],[]
    def native_fit(model,data):
        pd.testing.assert_frame_equal(data[fitting.columns],fitting)
        require(len(data) == len(fitting) and model.candidate["features"] == expected_features,
                "Native source-association fitter saw altered rows or features")
        if is_source:
            require(not set(study.NATIVE.values())&set(expected_features),"Source-proxy classifier received redundant raw inputs")
            current = independently_compute_state(fitting,head,candidate["source_feature_set"],"current")
            np.testing.assert_allclose(data[study.STATE],current,rtol=0,atol=0,equal_nan=True)
            if candidate["representation"] == "current_and_change":
                prior = independently_compute_state(fitting,head,candidate["source_feature_set"],"prior")
                np.testing.assert_allclose(data[study.CHANGE],current-prior,rtol=0,atol=0,equal_nan=True)
        else:
            require(not {study.STATE,study.CHANGE}&set(expected_features),"Measured control acquired a source representation")
        observed_rows.append(len(data))
        return actual_native_fit(model,data)
    def estimator_fit(estimator,x,y,**kwargs):
        np.testing.assert_array_equal(np.asarray(y),target)
        require(len(x) == len(fitting),"Native estimator received generated rows or converted labels")
        if candidate["member"] == "core":
            require(estimator.max_iter == 5000 and estimator.max_fun == 100000 and estimator.alpha == 10.
                    and list(estimator.hidden_layer_sizes) == [16,8] and estimator.random_state == 42
                    and estimator.solver == "lbfgs" and not estimator.early_stopping,"Native MLP fitting protocol changed")
        else:
            params = estimator.get_params()
            require(params["iterations"] == specification["iterations"] == 900 and params["depth"] == specification["depth"]
                    and params["l2_leaf_reg"] == specification["l2_leaf_reg"] and not params["use_best_model"],
                    "Native CatBoost fitting protocol changed")
        observed_targets.append(len(y))
        return actual_estimator_fit(estimator,x,y,**kwargs)
    with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")), \
            patch.object(study,"fit_source",side_effect=AssertionError("Source heads must not refit on native data")), \
            patch.object(native_class,"fit",new=native_fit),patch.object(estimator_class,"fit",new=estimator_fit):
        model = study.AssociationBorg(candidate,head).fit(fitting,inputs["specifications"])
    require(observed_rows == observed_targets == [len(fitting)],"Actual native-data/target observer was bypassed")
    predicted = model.predict(validation)
    np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
    require(model.optimizer_summary == row["folds"][number]["optimizer_summary"],"Native association optimizer diagnostics failed reproduction")
    if candidate["member"] == "core":
        pipeline = model.model.model
        require(int(pipeline[1].n_samples_seen_) == len(fitting),"Native preprocessing saw held people")
        medians = np.nanmedian(model.add_features(fitting)[model.model_features].to_numpy(float),axis=0)
        np.testing.assert_allclose(pipeline[0].statistics_,np.nan_to_num(medians,nan=0),rtol=0,atol=0)
    runtime = validation[model.input_features]
    np.testing.assert_array_equal(model.predict(runtime),predicted)
    require(not set(model.input_features)&{"label","row_key","group_key",study.STATE,study.CHANGE}
            and not set(vars(model))&{"frame","pool","histories","row_keys","source_fitting","source_reserved"},
            "Current truth, identifiers or query/report pools entered native runtime")
    require({key:joblib.hash(value) for key,value in heads.items()} == before,"Native fitting mutated source association weights")
    with tempfile.TemporaryDirectory() as directory:
        artifact = Path(directory)/"actual-source-association-native.joblib"
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),predicted)
    return {"candidate_id":candidate["id"],"fold":number,"actual_native_rows_observed":len(fitting),
        "actual_native_delta_targets_observed":len(target),"optimizer_summary":model.optimizer_summary,
        "source_functions_frozen":True,"reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    train,test = inputs["train"],inputs["test"]
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
            and selection["plan"] == study.plan() and len(selection["results"]) == 30
            and selection["train_row_keys"] == train.row_key.tolist(),"Frozen source-association selection changed or remains incomplete")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
            and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
            and selection["synthetic_training_rows"] == selection["new_native_borg_targets"] == 0
            and selection["actual_source_fitting_targets"] == 976 and selection["source_reserved_targets_not_fitted"] == 238,
            "Original exact Borg, person holdout, source reservation or public-real policy changed")
    previous_inputs = inputs["previous"]["frame"]
    pd.testing.assert_frame_equal(inputs["frame"][previous_inputs.columns],previous_inputs)
    source,held = inputs["source_fitting"],inputs["source_reserved"]
    require(len(source) == 976 and source.group_key.nunique() == 124 and len(held) == 238 and held.group_key.nunique() == 32
            and not set(source.group_key)&set(held.group_key)
            and not (set(source.group_key)|set(held.group_key))&(set(train.group_key)|set(test.group_key)),"Source/native people were mixed")
    input_audit = json.loads(study.INPUT_AUDIT.read_text())
    require(input_audit["source_original6to20_targets_unchanged"] and input_audit["source_task_is_retrospective_association"]
            and not input_audit["source_strict_pretarget_hr_forecasting_claim_approved"]
            and input_audit["native_pulse_at_query_completed_by_query"] and input_audit["native_prior_pulse_completed_by_genuine_prior"],
            "Retrospective source task was confused with operational native availability")
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    previous = json.loads((study.parent.DIRECTORY/"selection.json").read_text())
    warnings_in_grid = []
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted) <= {f"Borg {i}" for i in range(11)},
                "Native association OOF case count/scale changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
                and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"],"Native association score changed")
        if candidate["algorithm"] == "previous_real_control":
            inherited = next(r for r in previous["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,inherited["oof_predictions"])
            continue
        require(len(row["folds"]) == 5,"Association native folds missing")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Frozen native association fold changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            info = saved["optimizer_summary"]
            is_source = candidate["algorithm"] == "retrospective_source_association"
            require(info["actual_native_fit_rows"] == len(fit) and info["actual_auxiliary_source_targets"] == (976 if is_source else 0)
                    and info["synthetic_rows"] == info["artificial_history_views"] == 0 and not info["source_fitting_performed_here"],
                    "Native association fitting diagnostics changed actual-target counts")
            extra = (2 if candidate["representation"] == "current_and_change" else 1) if is_source else 3
            require(info["model_feature_count"] == len(inputs["specifications"][candidate["member"]]["features"])+extra,
                    "Source-proxy classifier acquired redundant or undisclosed features")
            if is_source:
                current = study.source_query(train.iloc[fit],candidate["source_feature_set"],"current")
                current_known = np.isfinite(current.to_numpy(float)).all(axis=1)
                expected_missing = {study.STATE:int((~current_known).sum())}
                if candidate["representation"] == "current_and_change":
                    prior = study.source_query(train.iloc[fit],candidate["source_feature_set"],"prior")
                    expected_missing[study.CHANGE] = int((~(current_known&np.isfinite(prior.to_numpy(float)).all(axis=1))).sum())
                require(info["natural_missing_representation_rows"] == expected_missing,"Natural missing physiology was masked, filled or filtered before native preprocessing")
            else:
                require(info["natural_missing_representation_rows"] == {},"Measured control acquired computed representations")
            if candidate["member"] == "core":
                require(info["maximum_iterations"] == 5000 and 0 < info["iterations"] <= 5000 and np.isfinite(info["fitting_loss"]),
                        "Native solver budget/diagnostics changed")
            if info["convergence_warnings"]:
                warnings_in_grid.append([candidate["id"],number])
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"],"Winner differs from frozen native CV selection")
    candidates = [r for r in selection["results"] if r["candidate"]["algorithm"] == "retrospective_source_association"]
    best = max(candidates,key=lambda r:r["accuracy_mean"])
    by_member = {member:max((r for r in candidates if r["candidate"]["member"] == member),key=lambda r:r["accuracy_mean"])
                 for member in ("core","cat")}
    c = best["candidate"]
    paired = {mode:next(r for r in candidates if r["candidate"]["source_algorithm"] == c["source_algorithm"]
        and r["candidate"]["source_feature_set"] == c["source_feature_set"] and r["candidate"]["member"] == c["member"]
        and r["candidate"]["representation"] == mode) for mode in ("current_state","current_and_change")}
    measured = {r["candidate"]["member"]:r for r in selection["results"] if r["candidate"]["algorithm"] == "native_measured_physiology_control"}
    selected = {r["candidate"]["id"]:r for r in [*by_member.values(),*paired.values(),*measured.values()]}
    heads,source_checks = refit_source_functions(inputs,signature)
    checked = []
    with ProcessPoolExecutor(max_workers=2,initializer=initialize_native_audit,initargs=(heads,)) as pool:
        futures = [pool.submit(refit_native,(row,number)) for row in selected.values() for number in range(5)]
        for future in as_completed(futures):
            result = future.result()
            checked.append(result)
            print(f"Independent source-association native refit {result['candidate_id']} fold{result['fold']+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A source-association model qualified: freeze/evaluate its original179 artifact before closing this audit")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == 108/179,"Retained original native test model changed")
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(path),"input_verification_sha256":digest(study.INPUT_AUDIT),"previous_verification_sha256":digest(study.PARENT_AUDIT),
        "public_real_data_policy_sha256":signature["public_real_data_policy_sha256"],"all_30_oof_recipes_recomputed":True,
        "actual_source_functions_independently_refitted":source_checks,"actual_source_target_calls_observed":6,
        "source_fitting_targets":976,"source_fitting_people":124,"source_reserved_targets":238,"source_reserved_people":32,
        "source_task_is_retrospective_association":True,"source_pre_rpe_forecast_claim_approved":False,
        "native_query_inputs_past_only_by_independent_raw_window_audit":True,"source6to20_targets_remain_separate":True,
        "native_rows_and_delta_targets_verified_at_actual_fitter":True,"source_state_and_difference_independently_verified":True,
        "all_original_native_rows_and_labels_preserved":True,"natural_missing_inputs_preserved":True,
        "native_preprocessing_fitting_people_only":True,"source_functions_frozen_during_native_fitting":True,
        "artificial_history_fitting_disabled":True,"best_source_candidate_id":best["candidate"]["id"],"best_source_cv_accuracy":best["accuracy_mean"],
        "best_source_by_member":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in by_member.items()},
        "paired_current_change_comparison":{mode:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for mode,r in paired.items()},
        "measured_physiology_controls":{member:{"candidate_id":r["candidate"]["id"],"accuracy_mean":r["accuracy_mean"]} for member,r in measured.items()},
        "native_recipes_independently_refitted":sorted(selected),"actual_native_refits":sorted(checked,key=lambda r:(r["candidate_id"],r["fold"])),
        "actual_native_target_calls_observed":len(checked),"convergence_warning_folds_in_grid":warnings_in_grid,
        "winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],"new_test_gate_passed":False,
        "original_training_cases":487,"original_test_cases":179,"best_verified_test_correct":incumbent["correct"],
        "best_verified_test_accuracy":incumbent["accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Original public concurrent source6-20 physiology/RPE association and native exact0-10 person-held targets remain distinct. All native query sensors were actually completed before the query. Source states/differences are computed inputs, not measured labels or new rows. No synthetic data, source/target scale conversion, invented source clocks, artificial histories, case filtering, changed denominator or native test tuning."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
