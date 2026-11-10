"""Reproduce actual CADENCE supervision and matched native Borg comparisons."""
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

import fatigue_cadence_transfer as study
from public_sources import ROOT, digest
from validate_fatigue_release import validate as validate_incumbent

_RUNTIME = None


def require(value, reason):
    if not value:
        raise ValueError(reason)


def refit_sources(inputs, signature):
    fitting, reserved = inputs["source_fitting"], inputs["source_reserved"]
    stored = study.read_sources(signature)
    heads, checked = {}, []
    expected_weights = 1./fitting.groupby("group_key")["group_key"].transform("size").to_numpy()
    expected_weights *= len(fitting)/expected_weights.sum()
    totals = pd.DataFrame({"group":fitting.group_key,"weight":expected_weights}).groupby("group").weight.sum()
    np.testing.assert_allclose(totals,np.full(123,851/123),rtol=0,atol=1e-12)
    require(set(study.SETS) == {"absolute","relative"} and
            study.SETS["absolute"] == ["lag_hr_bpm","baseline_hr_bpm"] and
            study.SETS["relative"] == ["hr_delta_baseline","hr_ratio_baseline"],
            "Source inputs gained current-bout HR, target history or identifiers")
    for algorithm, estimator_class in (("ridge",study.Ridge),("svr",study.SVR),("random_forest",study.RandomForestRegressor)):
        for feature_set, features in study.SETS.items():
            actual_fit = estimator_class.fit
            observed_raw, observed_y = [], []
            def observe_raw(x, y, weights):
                pd.testing.assert_frame_equal(x,fitting[features])
                np.testing.assert_array_equal(y,fitting.rpe_native.to_numpy())
                np.testing.assert_array_equal(weights,expected_weights)
                observed_raw.append(len(x))
            def observe_fit(estimator, x, y, **kwargs):
                require(len(x) == 851 and x.shape[1] == 2,"Actual source fitter received extra or reserved examples")
                np.testing.assert_array_equal(y,fitting.rpe_native.to_numpy())
                np.testing.assert_array_equal(kwargs["sample_weight"],expected_weights)
                require(float(np.max(y)) > 10 and float(np.min(y)) >= 6,
                        "Original source6-20 targets were converted into native0-10 labels")
                observed_y.append(len(y))
                return actual_fit(estimator,x,y,**kwargs)
            with patch.object(estimator_class,"fit",new=observe_fit):
                model = study.fit_source(fitting,algorithm,feature_set,observe_raw)
            require(observed_raw == observed_y == [851],"Source row/label observer was bypassed")
            require(int(model[-2].n_samples_seen_) == 851,"Source scaler saw reserved people")
            for query in (fitting[features],reserved[features],study.source_query(inputs["train"],feature_set)):
                with threadpool_limits(limits=1):
                    np.testing.assert_allclose(model.predict(query),stored[algorithm,feature_set].predict(query),rtol=0,atol=1e-12)
            metadata_path = study.DIRECTORY/"teachers"/f"{algorithm}-{feature_set}.json"
            metadata = json.loads(metadata_path.read_text())
            with threadpool_limits(limits=1):
                predicted = model.predict(reserved[features])
            mae, r2 = float(mean_absolute_error(reserved.rpe_native,predicted)),float(r2_score(reserved.rpe_native,predicted))
            require(metadata["signature"] == signature and metadata["actual_source_fitting_rows"] == 851
                    and metadata["actual_source_fitting_people"] == 123 and metadata["native_labels_used_for_source_fitting"] == 0
                    and metadata["reserved_source_rows"] == 206 and not metadata["reserved_source_used_for_selection"]
                    and mae == metadata["reserved_source_mae"] and r2 == metadata["reserved_source_r2"],
                    "Source supervision boundary or independent reserved diagnostics changed")
            heads[algorithm,feature_set] = model
            checked.append({"algorithm":algorithm,"feature_set":feature_set,"actual_source_targets_observed":851,
                            "reserved_source_mae":mae,"reserved_source_r2":r2,"reserved_used_for_selection":False})
            print(f"Independent source refit {algorithm}/{feature_set}:851 original RPE targets",flush=True)
    return heads, checked


def initialize_native_audit(heads):
    global _RUNTIME
    _RUNTIME = study.load_inputs(),heads


def refit_native(task):
    row, number = task
    inputs, heads = _RUNTIME
    candidate, train = row["candidate"], inputs["train"]
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    fit,val = folds[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Independent native fitting leaked people")
    teacher = None if candidate["algorithm"] == "measured_physiology_control" else heads[candidate["source_algorithm"],candidate["source_feature_set"]]
    before = joblib.hash(teacher) if teacher is not None else None
    native_class = (study.parent.parent.parent.parent.baseline.DynamicsClassifier if candidate["member"] == "core"
                    else study.parent.parent.parent.parent.baseline.CatBoostBorg)
    estimator_class = MLPClassifier if candidate["member"] == "core" else CatBoostClassifier
    actual_native_fit, actual_estimator_fit = native_class.fit, estimator_class.fit
    target = fitting.label.str.removeprefix("Borg ").astype(int).to_numpy()
    if inputs["specifications"][candidate["member"]]["target_mode"] == "change_from_prior":
        target = target-fitting.prior_borg.to_numpy(int)
    if candidate["member"] == "core":
        target = target.astype(str)
    observed_rows, observed_targets = [], []
    def observe_native(model, data):
        pd.testing.assert_frame_equal(data[fitting.columns],fitting)
        np.testing.assert_array_equal(data.label,fitting.label)
        require(len(data) == len(fitting),"Artificial native examples entered actual fitting")
        if teacher is not None:
            require(np.isfinite(data[study.OUTPUT]).all(),"Source representation lost native cases")
        else:
            require(study.OUTPUT not in model.candidate["features"],"Measured-only control acquired a source representation")
        observed_rows.append(len(data))
        return actual_native_fit(model,data)
    def observe_estimator(estimator, x, y, **kwargs):
        np.testing.assert_array_equal(np.asarray(y),target)
        require(len(x) == len(fitting),"Native estimator saw altered rows or labels")
        if candidate["member"] == "core":
            require(estimator.max_iter == 5000 and estimator.max_fun == 100000 and estimator.alpha == 10
                    and list(estimator.hidden_layer_sizes) == [16,8] and estimator.random_state == 42
                    and not estimator.early_stopping,"Actual native MLP hyperparameters changed")
        else:
            require(estimator.get_params()["iterations"] == 900 and not estimator.get_params()["use_best_model"],
                    "Actual native CatBoost budget or stopping rule changed")
        observed_targets.append(len(y))
        return actual_estimator_fit(estimator,x,y,**kwargs)
    with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")), \
            patch.object(study,"fit_source",side_effect=AssertionError("Native fitting must not refit source heads")), \
            patch.object(native_class,"fit",new=observe_native),patch.object(estimator_class,"fit",new=observe_estimator):
        model = study.CadenceSourceBorg(candidate,teacher).fit(fitting,inputs["specifications"])
    require(observed_rows == observed_targets == [len(fitting)],"Native data/target fitter observer was bypassed")
    predicted = model.predict(validation)
    np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
    require(model.optimizer_summary == row["folds"][number]["optimizer_summary"],"Native optimizer diagnostics failed exact reproduction")
    if candidate["member"] == "core":
        require(int(model.model.model[1].n_samples_seen_) == len(fitting),"Native scaling saw validation people")
    require(not set(model.input_features)&{"label","row_key","group_key",study.OUTPUT}
            and not set(vars(model))&{"frame","pool","histories","row_keys","source_fitting","source_reserved"},
            "Current truth or a case/report pool entered runtime inputs")
    runtime = validation[model.input_features]
    np.testing.assert_array_equal(model.predict(runtime),predicted)
    require((joblib.hash(teacher) if teacher is not None else None) == before,"Native fitting mutated source weights")
    with tempfile.TemporaryDirectory() as directory:
        artifact = Path(directory)/"actual-cadence-borg.joblib"
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),predicted)
    return {"candidate_id":candidate["id"],"fold":number,"actual_native_rows_observed":len(fitting),
            "actual_estimator_targets_observed":len(target),"optimizer_summary":model.optimizer_summary,
            "source_parameters_frozen":True,"reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    train,test = inputs["train"],inputs["test"]
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
            and selection["plan"] == study.plan() and len(selection["results"]) == 16
            and selection["train_row_keys"] == train.row_key.tolist(),"Frozen CADENCE study changed or remains incomplete")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and train.group_key.nunique() == 28 and test.group_key.nunique() == 12
            and not set(train.group_key)&set(test.group_key) and not selection["test_used_for_selection"]
            and selection["minimum_cv_for_new_test_evaluation"] == .65 and selection["synthetic_training_rows"] == 0
            and selection["new_native_borg_targets"] == 0 and selection["actual_source_fitting_targets"] == 851
            and selection["source_reserved_targets_not_fitted"] == 206,
            "Original person holdout, exact targets, real-data policy or source reservation changed")
    require(len(inputs["source_fitting"]) == 851 and len(inputs["source_reserved"]) == 206
            and inputs["source_fitting"].group_key.nunique() == 123 and inputs["source_reserved"].group_key.nunique() == 32
            and not set(inputs["source_fitting"].group_key)&set(inputs["source_reserved"].group_key),"Source people reservation changed")
    original = inputs["parents"][0][0]
    pd.testing.assert_frame_equal(inputs["frame"][original.columns],original)
    require(inputs["frame"][study.NATIVE["lag_hr_bpm"]].isna().sum() == 3
            and inputs["frame"][study.NATIVE["baseline_hr_bpm"]].isna().sum() == 8,
            "Cases with naturally missing real physiology were filtered or filled before modeling")
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    previous = json.loads((study.parent.DIRECTORY/"selection.json").read_text())
    warnings_in_grid = []
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted) <= {f"Borg {i}" for i in range(11)},
                "Native OOF targets/cases changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
                and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"],"Native OOF score changed")
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,old["oof_predictions"])
            continue
        require(len(row["folds"]) == 5,"Native CADENCE folds missing")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                    and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Native fold signature/person membership changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            info = saved["optimizer_summary"]
            require(info["actual_native_fit_rows"] == len(fit) and info["synthetic_rows"] == info["artificial_history_views"] == 0
                    and info["actual_auxiliary_source_targets"] == (851 if candidate["algorithm"] == "separate_source_rpe_transfer" else 0),
                    "Native optimizer report altered real-target counts")
            if candidate["member"] == "core":
                require(info["maximum_iterations"] == 5000 and 0 < info["iterations"] <= 5000 and np.isfinite(info["fitting_loss"]),
                        "MLP solver budget/diagnostics changed")
            if info["convergence_warnings"]:
                warnings_in_grid.append([candidate["id"],number])
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"],
            "Winner differs from the frozen native CV rule")
    source_rows = [r for r in selection["results"] if r["candidate"]["algorithm"] == "separate_source_rpe_transfer"]
    controls = [r for r in selection["results"] if r["candidate"]["algorithm"] == "measured_physiology_control"]
    best_source = max(source_rows,key=lambda r:r["accuracy_mean"])
    best_control = max(controls,key=lambda r:r["accuracy_mean"])
    matched = next(r for r in controls if r["candidate"]["member"] == best_source["candidate"]["member"])
    selected = {r["candidate"]["id"]:r for r in (best_source,best_control,matched)}
    heads, source_checks = refit_sources(inputs,signature)
    checked = []
    tasks = [(row,number) for row in selected.values() for number in range(5)]
    with ProcessPoolExecutor(max_workers=2,initializer=initialize_native_audit,initargs=(heads,)) as pool:
        for future in as_completed([pool.submit(refit_native,task) for task in tasks]):
            info = future.result()
            checked.append(info)
            print(f"Independent CADENCE native refit {info['candidate_id']} fold{info['fold']+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A CADENCE model crossed its gate: freeze and evaluate the original179 artifact next")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == 108/179,"Retained original test model changed")
    policy_path = ROOT/"docs/fatigue-80-2026-10-25/public-real-data-policy.json"
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(path),"input_verification_sha256":digest(study.INPUT_AUDIT),
        "public_real_data_policy_sha256":digest(policy_path),"all_16_oof_recipes_recomputed":True,
        "actual_source_regressors_independently_refitted":source_checks,"actual_source_target_calls_observed":6,
        "source_fitting_targets":851,"source_fitting_people":123,"source_reserved_targets":206,"source_reserved_people":32,
        "source_targets_original6to20_unchanged":True,"equal_total_source_weight_per_person":True,
        "source_current_bout_hr_excluded":True,"exact_source_report_clocks_invented":False,
        "native_prior_hr_and_baseline_missing_cases_preserved":True,"source_and_native_baseline_definitions_remain_distinct":True,
        "best_source_candidate_id":best_source["candidate"]["id"],"best_source_cv_accuracy":best_source["accuracy_mean"],
        "best_measured_control_id":best_control["candidate"]["id"],"best_measured_control_cv":best_control["accuracy_mean"],
        "matching_measured_control_id":matched["candidate"]["id"],"matching_measured_control_cv":matched["accuracy_mean"],
        "native_recipes_independently_refitted":sorted(selected),"actual_native_refits":sorted(checked,key=lambda r:(r["candidate_id"],r["fold"])),
        "actual_native_target_calls_observed":len(checked),"actual_native_rows_and_delta_targets_verified":True,
        "artificial_history_fitting_disabled":True,"source_weights_frozen_during_native_fitting":True,
        "convergence_warning_folds_in_grid":warnings_in_grid,"winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],
        "new_test_gate_passed":False,"original_training_cases":487,"original_test_cases":179,
        "best_verified_test_correct":incumbent["correct"],"best_verified_test_accuracy":incumbent["accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Real public original rows only. Source6-20 targets supervise separate fixed functions of completed earlier-bout physiology; their predictions are computed inputs, never native labels. All original native487/179 cases and labels retained. Reserved source people only yield descriptive diagnostics; native CV selects. No synthetic examples, invented clocks, target conversion, changed denominator or native test tuning."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
