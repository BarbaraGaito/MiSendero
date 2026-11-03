"""Independently reproduce native CatBoost schedules and frozen prefixes."""
from __future__ import annotations

import argparse
import importlib.metadata
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
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_catboost_schedule as study
from fatigue_catboost import CatBoostBorg
from public_sources import digest
from validate_fatigue_release import validate as validate_release

_RUNTIME = None


def require(value,reason):
    if not value:
        raise ValueError(reason)


def independent_parameters(rate,count):
    """Explicit protocol, independent of the implementation's parameter builder."""
    require(rate in (.01,.03,.09) and count in (300,900,1800,2700),"Unexpected fixed schedule")
    return {"iterations":count,"depth":3,"l2_leaf_reg":30.,"learning_rate":rate,
        "loss_function":"MultiClass","boosting_type":"Ordered","grow_policy":"SymmetricTree",
        "random_seed":42,"thread_count":4,"task_type":"CPU","border_count":128,
        "bootstrap_type":"Bayesian","bagging_temperature":1.,"random_strength":1.,
        "nan_mode":"Min","use_best_model":False,"allow_writing_files":False,"verbose":False}


def native_labels(model,runtime,count):
    delta = np.asarray(model.predict(runtime[list(study.FEATURES)],prediction_type="Class",
        ntree_start=0,ntree_end=count,thread_count=4)).reshape(-1).astype(int)
    values = np.clip(delta+runtime.prior_borg.to_numpy(int),0,10)
    return np.asarray([f"Borg {value}" for value in values])


def raw_scores(model,runtime,count):
    return np.asarray(model.predict(runtime[list(study.FEATURES)],prediction_type="RawFormulaVal",
        ntree_start=0,ntree_end=count,thread_count=4))


def observed_native_fit(candidate,fitting,historical=False):
    """Intercept the real CatBoost estimator, not only a wrapper's callback."""
    x = fitting[list(study.FEATURES)]
    target = fitting.label.str.removeprefix("Borg ").to_numpy(int)-fitting.prior_borg.to_numpy(int)
    expected = independent_parameters(candidate["learning_rate"],candidate["iterations"])
    original_hash = joblib.hash(fitting)
    calls,callbacks = [],[]
    actual_fit = CatBoostClassifier.fit

    def observer(actual_x,actual_y,params):
        pd.testing.assert_frame_equal(actual_x,x)
        np.testing.assert_array_equal(actual_y,target)
        require(params == expected,"Wrapper callback received changed schedule parameters")
        callbacks.append(len(actual_y))

    def fitting_estimator(estimator,actual_x,actual_y,**kwargs):
        pd.testing.assert_frame_equal(actual_x,x)
        np.testing.assert_array_equal(np.asarray(actual_y),target)
        require(estimator.get_params() == expected,"Actual CatBoost estimator parameters changed")
        require(kwargs == {"cat_features":["current_terrain"]},
            "Actual CatBoost fit received weights,eval_set,early stopping or undeclared arguments")
        require(len(actual_x) == len(actual_y) == len(fitting),"Generated/filtered/source cases entered native fitting")
        calls.append(len(actual_y))
        return actual_fit(estimator,actual_x,actual_y,**kwargs)

    with patch.object(CatBoostClassifier,"fit",new=fitting_estimator),\
            patch.object(study.parent,"fit_source",side_effect=AssertionError("No source fitting in the native schedule search")),\
            patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
        model = CatBoostBorg(candidate).fit(fitting) if historical else study.ScheduledCatBoostBorg(candidate).fit(fitting,observer=observer)
    require(calls == [len(fitting)] and (historical or callbacks == calls),"Real estimator targets/parameters were not observed")
    require(joblib.hash(fitting) == original_hash,"Native fitting altered original observations")
    require(model.model.get_params() == expected and model.model.tree_count_ == candidate["iterations"],
        "Actual fitted parameters/tree count differ from the fixed schedule")
    require(model.model.feature_names_ == list(study.FEATURES)
        and model.model.get_cat_feature_indices() == [list(study.FEATURES).index("current_terrain")],
        "Actual CatBoost fitted feature names/categories changed")
    if not historical:
        require(model.input_features == list(study.FEATURES)
            and set(vars(model)) == {"candidate","input_features","model","optimizer_summary"},
            "Saved schedule runtime acquired raw rows,current truths or identifiers")
        summary = model.optimizer_summary
        require(summary["actual_native_fit_rows"] == summary["actual_native_delta_targets"] == len(fitting)
            and summary["actual_native_fit_people"] == fitting.group_key.nunique()
            and summary["actual_fit_parameters"] == expected and summary["actual_tree_count"] == candidate["iterations"]
            and summary["source_outcomes_fitted"] == summary["synthetic_rows"] == summary["artificial_history_views"] == 0
            and not summary["validation_or_test_eval_set_supplied"] and not summary["early_stopping"],
            "Actual schedule optimizer coverage/protocol differs")
    return model,{"actual_native_fit_rows":len(fitting),"actual_native_fit_people":fitting.group_key.nunique(),
        "actual_native_delta_targets_observed":len(target),"actual_catboost_fit_calls":1,
        "actual_fit_parameters":expected,"actual_tree_count":model.model.tree_count_,
        "natural_missing_input_cells_observed":int(x.isna().sum().sum()),
        "original_feature_values_and_missing_positions_verified":True,"validation_or_test_eval_set_supplied":False,
        "source_outcomes_fitted":0,"synthetic_rows":0,"artificial_history_views":0}


def read_stored_trajectory(inputs,signature,rate,number,fit,val):
    """Verify raw metadata plus both artifact formats without the study reader."""
    train = inputs["train"]
    fitting,validation = train.iloc[fit],train.iloc[val]
    path = study.DIRECTORY/"trajectories"/f"lr-{rate:.2f}-fold-{number}.json"
    saved = json.loads(path.read_text())
    candidate = next(c for c in study.plan()[4:] if c["learning_rate"] == rate and c["iterations"] == 2700)
    expected = independent_parameters(rate,2700)
    require(saved["signature"] == signature and saved["candidate"] == candidate and saved["fold_number"] == number
        and saved["fit_row_keys"] == fitting.row_key.tolist() and saved["validation_row_keys"] == validation.row_key.tolist()
        and not set(fitting.group_key)&set(validation.group_key) and saved["actual_fit_parameters"] == expected
        and set(saved["prefix_predictions"]) == {"300","900","1800","2700"},"Stored fixed trajectory identity/cases changed")
    hashes = {path.relative_to(study.DIRECTORY).as_posix():digest(path)}
    for kind,suffix in (("joblib",".joblib"),("native",".cbm")):
        artifact = path.with_suffix(suffix)
        require(saved["artifact_sha256"][kind] == digest(artifact),"Stored trajectory artifact changed")
        hashes[artifact.relative_to(study.DIRECTORY).as_posix()] = digest(artifact)
    wrapped = joblib.load(path.with_suffix(".joblib"))
    native = CatBoostClassifier()
    native.load_model(str(path.with_suffix(".cbm")),format="cbm")
    require(wrapped.candidate == candidate and wrapped.input_features == list(study.FEATURES)
        and wrapped.model.get_params() == expected and wrapped.model.tree_count_ == native.tree_count_ == 2700
        and wrapped.model.feature_names_ == native.feature_names_ == list(study.FEATURES)
        and wrapped.optimizer_summary == saved["optimizer_summary"],"Reloaded CatBoost trajectory protocol changed")
    np.testing.assert_array_equal(wrapped.model.classes_,native.classes_)
    actual = native.get_all_params()
    for name in ("depth","l2_leaf_reg","learning_rate","loss_function","boosting_type","grow_policy",
            "random_seed","task_type","border_count","bootstrap_type","bagging_temperature","random_strength","nan_mode"):
        if name == "learning_rate":
            require(np.isclose(actual[name],rate,rtol=1e-7,atol=0),"Native CBM learning rate changed")
        else:
            require(actual[name] == expected[name],"Native CBM fitting parameter changed:"+name)
    summary = saved["optimizer_summary"]
    require(summary["actual_native_fit_rows"] == summary["actual_native_delta_targets"] == len(fit)
        and summary["actual_native_fit_people"] == fitting.group_key.nunique()
        and summary["actual_fit_parameters"] == expected and summary["actual_tree_count"] == 2700
        and summary["source_outcomes_fitted"] == summary["synthetic_rows"] == summary["artificial_history_views"] == 0
        and not summary["validation_or_test_eval_set_supplied"] and not summary["early_stopping"],"Stored native trajectory coverage changed")
    runtime = validation[list(study.FEATURES)]
    require(not set(runtime.columns)&{"row_key","group_key","label"},"Current truth/identifiers entered runtime")
    for count in (300,900,1800,2700):
        expected_prediction = saved["prefix_predictions"][str(count)]
        require(len(expected_prediction) == len(val) and set(expected_prediction)<={f"Borg {i}" for i in range(11)},
            "Native prefix output cases/classes changed")
        np.testing.assert_array_equal(wrapped.predict_prefix(runtime,count),expected_prediction)
        np.testing.assert_array_equal(native_labels(wrapped.model,runtime,count),expected_prediction)
        np.testing.assert_array_equal(native_labels(native,runtime,count),expected_prediction)
        np.testing.assert_allclose(raw_scores(wrapped.model,runtime,count),raw_scores(native,runtime,count),rtol=0,atol=1e-12)
        if rate == .03 and count in (300,900):
            key = "catboost-021" if count == 300 else "catboost-023"
            np.testing.assert_array_equal(expected_prediction,np.asarray(inputs["baseline_rows"][key]["oof_predictions"])[val])
    controls = {"300":"catboost-021","900":"catboost-023"} if rate == .03 else {}
    require(saved["matched_original_prefix_controls"] == controls,"Historical native prefix evidence changed")
    return saved,hashes


def initialize():
    global _RUNTIME
    _RUNTIME = study.load_inputs()


def refit_trajectory(job):
    rate,number = job
    inputs = _RUNTIME
    train = inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    require(not set(train.iloc[fit].group_key)&set(train.iloc[val].group_key),"Independent refit leaked validation people")
    candidate = next(c for c in study.plan()[4:] if c["learning_rate"] == rate and c["iterations"] == 2700)
    model,evidence = observed_native_fit(candidate,train.iloc[fit])
    path = study.DIRECTORY/"trajectories"/f"lr-{rate:.2f}-fold-{number}.json"
    saved = json.loads(path.read_text())
    stored = joblib.load(path.with_suffix(".joblib"))
    require(model.optimizer_summary == saved["optimizer_summary"],"Independent trajectory coverage did not reproduce")
    runtime = train.iloc[val][list(study.FEATURES)]
    with tempfile.TemporaryDirectory() as directory:
        artifact = Path(directory)/"independent-native-schedule.joblib"
        joblib.dump(model,artifact)
        reloaded = joblib.load(artifact)
        for count in (300,900,1800,2700):
            prediction = model.predict_prefix(runtime,count)
            np.testing.assert_array_equal(prediction,saved["prefix_predictions"][str(count)])
            np.testing.assert_array_equal(reloaded.predict_prefix(runtime,count),prediction)
            np.testing.assert_allclose(raw_scores(model.model,runtime,count),raw_scores(stored.model,runtime,count),rtol=0,atol=1e-12)
    print(f"Independent native schedule trajectory:rate{rate:.2f},fold{number+1}/5,2700trees",flush=True)
    return {"learning_rate":rate,"fold_number":number,**evidence,"all_four_fixed_prefixes_reproduced":True,
        "raw_prefix_logits_independently_reproduced":True,"reload_without_current_truth_or_ids":True}


def shortened_control(inputs,count):
    train = inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[0]
    key = "catboost-021" if count == 300 else "catboost-023"
    candidate = inputs["baseline_rows"][key]["candidate"]
    model,evidence = observed_native_fit(candidate,train.iloc[fit],historical=True)
    trajectory = study.DIRECTORY/"trajectories"/"lr-0.03-fold-0.joblib"
    longest = joblib.load(trajectory)
    runtime = train.iloc[val][list(study.FEATURES)]
    expected = np.asarray(inputs["baseline_rows"][key]["oof_predictions"])[val]
    np.testing.assert_array_equal(model.predict(runtime),expected)
    np.testing.assert_array_equal(longest.predict_prefix(runtime,count),expected)
    np.testing.assert_allclose(raw_scores(model.model,runtime,count),raw_scores(longest.model,runtime,count),rtol=0,atol=1e-12)
    with tempfile.TemporaryDirectory() as directory:
        artifact = Path(directory)/"original-shortened-native-control.joblib"
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),expected)
    print(f"Independent actual shortened native control:{key},fold1/5,{count}trees",flush=True)
    return {"historical_candidate_id":key,"fold_number":0,**evidence,
        "genuine_shorter_fit_equals_long_trajectory_prefix":True,"raw_prefix_logits_equal":True,
        "reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    signature = study.fingerprint(inputs)
    train,test = inputs["train"],inputs["test"]
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    original_path = study.BASELINE_DIRECTORY/"selection.json"
    original = json.loads(original_path.read_text())
    versions = {name:importlib.metadata.version(name) for name in original["software_versions"]}
    require(versions == original["software_versions"],"Installed CatBoost/numpy/pandas/scikit-learn versions differ from original controls")
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
        and selection["plan"] == study.plan() and len(selection["results"]) == 16
        and [row["candidate"] for row in selection["results"]] == study.plan()
        and selection["train_row_keys"] == train.row_key.tolist(),"Native fixed schedule selection changed/incomplete")
    require((len(inputs["frame"]),len(train),len(test)) == (666,487,179)
        and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
        and selection["evaluation_denominator"] == 487 and selection["test_denominator"] == 179
        and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
        and selection["new_unique_native_schedules"] == 10 and selection["fresh_matched_historical_schedules"] == 2
        and selection["inherited_controls"] == 4 and selection["planned_native_trajectory_fits"] == selection["actual_native_trajectory_fits"] == 15
        and selection["matched_original_prefix_controls_verified"] == 10
        and selection["fixed_prefixes"] == [300,900,1800,2700] and selection["fixed_learning_rates"] == [.01,.03,.09]
        and selection["synthetic_training_rows"] == selection["source_targets_fitted"] == selection["new_native_borg_targets"] == 0,
        "Original native people/cases/scale or fixed schedule policy changed")
    require(digest(study.DIRECTORY/"selection-source.py") == signature["code_sha256"],"Frozen schedule implementation changed")
    pd.testing.assert_frame_equal(inputs["frame"],inputs["previous_inputs"]["frame"])
    require(len(study.FEATURES) == 29 and not set(study.FEATURES)&{"label","row_key","group_key"},"Native feature list contains current truth/IDs")
    for key in ("catboost-021","catboost-023"):
        require(inputs["baseline_rows"][key]["candidate"]["features"] == list(study.FEATURES),"Historical native feature order changed")
    tests_path = study.DOCS/"catboost-schedule-tests.log"
    tests = tests_path.read_text()
    require("Ran 4 tests" in tests and "OK" in tests and "FAILED" not in tests and "skipped" not in tests,
        "Four real-native schedule tests have not passed")
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    trajectories,artifact_hashes = {},{}
    for rate in (.01,.03,.09):
        for number,(fit,val) in enumerate(folds):
            saved,hashes = read_stored_trajectory(inputs,signature,rate,number,fit,val)
            trajectories[(rate,number)] = saved
            artifact_hashes.update(hashes)
    for row in selection["results"]:
        candidate = row["candidate"]
        prediction = np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(prediction) == 487 and set(prediction)<={f"Borg {i}" for i in range(11)},
            "Native OOF cases/classes changed")
        scores = [float(accuracy_score(train.iloc[val].label,prediction[val])) for _,val in folds]
        require(row["fold_accuracy"] == scores and row["accuracy_mean"] == float(np.mean(scores))
            and row["pooled_oof_accuracy"] == float(accuracy_score(train.label,prediction)),"Original person-CV metrics did not reproduce")
        if candidate["algorithm"] == "previous_real_control":
            inherited = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(prediction,inherited["oof_predictions"])
            require(row["folds"] == [],"Inherited control unexpectedly acquired new fitting folds")
            continue
        require(candidate["features"] == list(study.FEATURES) and candidate["depth"] == 3 and candidate["l2_leaf_reg"] == 30.
            and candidate["target_mode"] == "change_from_prior" and candidate["random_seed"] == 42 and len(row["folds"]) == 5,
            "Fixed native schedule parameters changed")
        for number,(fit,val) in enumerate(folds):
            stored = trajectories[(candidate["learning_rate"],number)]
            trajectory = study.DIRECTORY/"trajectories"/f"lr-{candidate['learning_rate']:.2f}-fold-{number}.json"
            values = stored["prefix_predictions"][str(candidate["iterations"])]
            expected = {"trajectory_file":trajectory.relative_to(study.DIRECTORY).as_posix(),"trajectory_sha256":digest(trajectory),
                "fold_number":number,"fit_row_keys":train.iloc[fit].row_key.tolist(),"validation_row_keys":train.iloc[val].row_key.tolist(),
                "prefix_tree_count":candidate["iterations"],"predicted":values,"optimizer_summary":stored["optimizer_summary"]}
            require(row["folds"][number] == expected,"Native OOF prefix fold references changed")
            np.testing.assert_array_equal(prediction[val],values)
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    schedules = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    best_schedule = max(schedules,key=lambda r:r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"] and selection["best_cv_accuracy"] == winner["accuracy_mean"],
        "Sole full-person CVwinner changed")
    refit_rates = sorted({.03,best_schedule["candidate"]["learning_rate"]})
    short_refits = [shortened_control(inputs,count) for count in (300,900)]
    refits = []
    with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
        for future in as_completed([pool.submit(refit_trajectory,(rate,number)) for rate in refit_rates for number in range(5)]):
            refits.append(future.result())
    gate = winner["candidate"]["algorithm"] != "previous_real_control" and winner["accuracy_mean"] >= .65
    evaluation = None
    if gate:
        require((study.DIRECTORY/"evaluation/metrics.json").exists(),"Qualified sole frozen winner must be evaluated before independent verification")
        from evaluate_fatigue_catboost_schedule import evaluate
        evaluation = evaluate()
    else:
        require(not (study.DIRECTORY/"evaluation/metrics.json").exists(),"Native test opened below the predeclared CVgate")
    for name,expected in artifact_hashes.items():
        require(digest(study.DIRECTORY/name) == expected,"Independent verification changed a frozen trajectory artifact")
    retained = validate_release()
    require(retained["correct"] == 108 and retained["accuracy"] == 108/179,"Original retained release artifact changed")
    compact = lambda r:{k:r[k] for k in ("candidate","accuracy_mean","fold_accuracy","pooled_oof_accuracy")}
    return {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "verification_code_sha256":digest(Path(__file__)),"selection_sha256":digest(selection_path),
        "previous_verification_sha256":digest(study.PARENT_AUDIT),"original_catboost_selection_sha256":digest(original_path),
        "original_catboost_code_sha256":digest(study.BASELINE_CODE),"public_real_data_policy_sha256":signature["public_real_data_policy_sha256"],
        "software_versions_independently_verified":versions,"real_native_tests_code_sha256":digest(Path(__file__).with_name("test_fatigue_catboost_schedule.py")),
        "real_native_tests_log_sha256":digest(tests_path),"all_16_oof_recipes_recomputed":True,
        "original_native_rows_and_targets_preserved":True,"stored_native_trajectories_independently_reloaded":15,
        "trajectory_artifact_hashes":artifact_hashes,"all_stored_native_cbm_and_joblib_prefix_predictions_checked":True,
        "both_historical_prefix_controls_verified_in_all_folds":10,"independently_refitted_learning_rates":refit_rates,
        "actual_native_trajectory_refits":len(refits),"trajectory_refits":sorted(refits,key=lambda r:(r["learning_rate"],r["fold_number"])),
        "actual_native_short_control_refits":len(short_refits),"shortened_control_refits":short_refits,
        "actual_native_estimator_targets_and_parameters_observed":True,"genuine_shorter_fits_equal_stored_long_prefixes":True,
        "natural_missing_inputs_preserved":True,"fitting_only_original_cases":True,"validation_or_test_eval_set_supplied":False,
        "source_outcomes_fitted":0,"synthetic_rows":0,"artificial_history_views":0,"best_schedule":compact(best_schedule),
        "best_by_learning_rate":{str(rate):compact(max((r for r in schedules if r["candidate"]["learning_rate"] == rate),key=lambda r:r["accuracy_mean"])) for rate in (.01,.03,.09)},
        "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],
        "new_test_gate_passed":gate,"new_test_evaluation":evaluation,"original_release_test_correct":108,"original_release_test_accuracy":108/179,
        "achieved":bool(evaluation and evaluation["correct"] >= 144),
        "scope":"All16fixed schedule OOFmetrics on unchanged487native cases and5person folds. All15maximum2700-tree trajectories reloaded from joblib and nativeCBM,with60prefix decisions/logits checked. Best schedule learning rate and.03baseline independently refitted in all5folds with actual29features,natural missing values,exactnative delta targets and every explicit CatBoost parameter observed at the actual estimator. Genuine300/900tree original controls refitted in one fold and matched against2700trajectory prefixes. No evalset,early stopping,source fitting,synthetic rows,current truths or identifiers in runtime. Original179test opened only for sole frozenCVwinner above.65."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=study.DOCS/"catboost-schedule-verification.json")
    args = parser.parse_args()
    report = validate()
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("verification","actual_native_trajectory_refits","actual_native_short_control_refits",
        "best_cv_accuracy","new_test_gate_passed","achieved")}),flush=True)
