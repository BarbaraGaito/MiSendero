"""Reproduce original runner HR supervision and native person-held predictions."""
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
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

import fatigue_furukawa_hr_transfer as study
from public_sources import digest
from validate_fatigue_release import validate as validate_release

_RUNTIME = None


def require(value,reason):
    if not value:
        raise ValueError(reason)


def original_source_values(frame,task):
    """Independent raw-column construction, not the fitting implementation."""
    part = frame if task == "state" else frame[frame.prior_rpe_points.notna()]
    values = {"current_hr_bpm":part.hr_recent_60s_mean.to_numpy(float)}
    if task == "delta":
        values.update(prior_hr_bpm=part.prior_report_hr_recent_mean.to_numpy(float),
            hr_change_bpm=part.hr_recent_60s_mean.to_numpy(float)-part.prior_report_hr_recent_mean.to_numpy(float))
    x = pd.DataFrame(values,index=part.index)
    target = part.original_rpe_points.to_numpy(float)
    if task == "delta":
        target = target-part.prior_rpe_points.to_numpy(float)
    weights = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
    weights *= len(part)/weights.sum()
    return part,x,target,weights


def independently_compute_features(frame,teacher,task):
    def score(query):
        known = np.isfinite(query.to_numpy(float)).all(axis=1)
        result = np.full(len(query),np.nan)
        if known.any():
            with threadpool_limits(limits=1):
                result[known] = teacher.predict(query.loc[known])
        return result
    current,prior = frame[study.CURRENT].to_numpy(float),frame[study.PRIOR].to_numpy(float)
    if task == "state":
        now = score(pd.DataFrame({"current_hr_bpm":current},index=frame.index))
        old = score(pd.DataFrame({"current_hr_bpm":prior},index=frame.index))
        return {study.STATE:now,study.CHANGE:now-old}
    query = pd.DataFrame({"current_hr_bpm":current,"prior_hr_bpm":prior,"hr_change_bpm":current-prior},index=frame.index)
    return {study.DELTA:score(query)}


def observed_source_fit(frame,algorithm,task):
    part,x,target,weights = original_source_values(frame,task)
    count = 252 if task == "state" else 168
    require(len(part) == count and part.group_key.nunique() == 12 and part.source_partition.eq("fitting").all(),"Unexpected original source training population")
    require(np.isfinite(x.to_numpy(float)).all() and np.isfinite(target).all(),"An imputed target/sensor entered source supervision")
    actual_class = Ridge if algorithm == "ridge" else SVR
    actual_fit = actual_class.fit
    raw_calls,actual_calls = [],[]
    def observer(actual_x,actual_y,actual_weights):
        pd.testing.assert_frame_equal(actual_x,x)
        np.testing.assert_array_equal(actual_y,target)
        np.testing.assert_array_equal(actual_weights,weights)
        raw_calls.append(len(actual_y))
    def fitting(estimator,actual_x,actual_y,**kwargs):
        require(actual_x.shape == (count,len(x.columns)),"The actual source estimator received generated/reserved/native rows")
        np.testing.assert_array_equal(actual_y,target)
        np.testing.assert_array_equal(kwargs["sample_weight"],weights)
        if algorithm == "ridge":
            require(estimator.alpha == 10.,"Original source Ridge penalty changed")
        else:
            require(estimator.C == 10. and estimator.gamma == "scale" and estimator.epsilon == .1,"Source SVR parameters changed")
        actual_calls.append(len(actual_y))
        return actual_fit(estimator,actual_x,actual_y,**kwargs)
    before = joblib.hash(frame)
    with patch.object(actual_class,"fit",new=fitting):
        model = study.fit_source(frame,algorithm,task,observer=observer)
    require(raw_calls == actual_calls == [count],"Original source target/weight observations were bypassed")
    require(joblib.hash(frame) == before,"Source fitting changed original observations")
    require(int(model[-2].n_samples_seen_) == count,"Source scaling included reserved/native examples")
    np.testing.assert_allclose(model[0].statistics_,np.median(x.to_numpy(float),axis=0),rtol=0,atol=0)
    np.testing.assert_allclose(model[-2].mean_,x.to_numpy(float).mean(axis=0),rtol=0,atol=1e-12)
    totals = pd.DataFrame({"person":part.group_key,"weight":weights}).groupby("person").weight.sum()
    np.testing.assert_allclose(totals,np.full(12,count/12),rtol=0,atol=1e-12)
    return model,{"algorithm":algorithm,"source_task":task,"actual_source_target_calls":1,"actual_source_targets_observed":count,
        "actual_source_people":12,"actual_original_target_points_or_differences_and_weights_verified":True,
        "reserved_source_targets_fitted":0,"native_source_labels_fitted":0,"fitting_only_source_statistics_verified":True}


def observed_native_fit(candidate,fitting,specifications,teacher=None):
    source = candidate["algorithm"] == "furukawa_source_function"
    base = specifications[candidate["member"]]
    task = candidate.get("source_task")
    extras = ([study.STATE,study.CHANGE] if task == "state" else [study.DELTA]) if source else [study.CURRENT,study.PRIOR,study.DIFFERENCE]
    expected_features = base["features"]+extras
    expected_representations = independently_compute_features(fitting,teacher,task) if source else {}
    before = joblib.hash(teacher) if teacher is not None else None
    original = joblib.hash(fitting)
    model_class = study.DynamicsClassifier if candidate["member"] == "core" else study.CatBoostBorg
    estimator_class = MLPClassifier if candidate["member"] == "core" else CatBoostClassifier
    actual_native,actual_estimator = model_class.fit,estimator_class.fit
    target = fitting.label.str.removeprefix("Borg ").to_numpy(int)-fitting.prior_borg.to_numpy(int)
    target = target.astype(str) if candidate["member"] == "core" else target
    observed_rows,observed_targets = [],[]
    def native_fit(model,data):
        pd.testing.assert_frame_equal(data[fitting.columns],fitting)
        require(len(data) == len(fitting) and model.candidate["features"] == expected_features,"Native fit used altered rows or features")
        for name,values in expected_representations.items():
            np.testing.assert_allclose(data[name],values,rtol=0,atol=0,equal_nan=True)
        if source:
            require(not {study.CURRENT,study.PRIOR,study.DIFFERENCE}&set(expected_features),"Source representation acquired redundant raw sensor inputs")
        else:
            current,prior = fitting[study.CURRENT].to_numpy(float),fitting[study.PRIOR].to_numpy(float)
            expected = np.where(np.isfinite(current)&np.isfinite(prior),current-prior,np.nan)
            np.testing.assert_allclose(data[study.DIFFERENCE],expected,rtol=0,atol=0,equal_nan=True)
        observed_rows.append(len(data))
        return actual_native(model,data)
    def estimator_fit(estimator,x,y,**kwargs):
        np.testing.assert_array_equal(np.asarray(y),target)
        require(len(x) == len(fitting),"Actual native estimator received generated/filtered cases")
        if candidate["member"] == "core":
            require(estimator.alpha == 10. and list(estimator.hidden_layer_sizes) == [16,8] and estimator.solver == "lbfgs"
                and estimator.max_iter == 5000 and estimator.max_fun == 100000 and estimator.random_state == 42
                and not estimator.early_stopping,"Native MLP solver/architecture/budget changed")
        else:
            params = estimator.get_params()
            require(params["iterations"] == 900 and params["depth"] == base["depth"] and params["l2_leaf_reg"] == base["l2_leaf_reg"]
                and not params["use_best_model"],"Native CatBoost protocol changed")
        observed_targets.append(len(y))
        return actual_estimator(estimator,x,y,**kwargs)
    with patch.object(model_class,"fit",new=native_fit),patch.object(estimator_class,"fit",new=estimator_fit),\
            patch.object(study,"fit_source",side_effect=AssertionError("Source functions remain frozen during native fitting")),\
            patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
        model = study.RunnerHRBorg(candidate,teacher).fit(fitting,specifications)
    require(observed_rows == observed_targets == [len(fitting)],"Actual original-native rows/targets were not observed")
    require(model.model_features == expected_features,"Native runtime/training feature lists differ")
    if candidate["member"] == "core":
        data = model.add_features(fitting)[expected_features]
        pipeline = model.model.model
        require(int(pipeline[1].n_samples_seen_) == len(fitting),"Native normalization included held cases")
        expected_medians = np.nan_to_num(np.nanmedian(data.to_numpy(float),axis=0),nan=0)
        np.testing.assert_allclose(pipeline[0].statistics_,expected_medians,rtol=0,atol=0)
        np.testing.assert_allclose(pipeline[1].mean_,pipeline[0].transform(data).mean(axis=0),rtol=0,atol=1e-12)
    require(joblib.hash(fitting) == original and (joblib.hash(teacher) if teacher is not None else None) == before,"Native fitting changed source weights or original observations")
    require(not set(model.input_features)&{"label","row_key","group_key",study.STATE,study.CHANGE,study.DELTA}
        and not set(vars(model))&{"frame","source","source_fitting","source_reserved","pool","row_keys","targets"},"Runtime stores current truths or source/query identifiers")
    return model,{"actual_native_rows_observed":len(fitting),"actual_native_delta_targets_observed":len(target),
        "native_estimator_target_calls":1,"source_functions_frozen":True,"native_fitting_only_statistics_verified":True,
        "actual_representation_values_independently_recomputed":source}


def initialize(heads):
    global _RUNTIME
    _RUNTIME = study.load_inputs(),heads


def refit_native(job):
    row,number = job
    inputs,heads = _RUNTIME
    candidate,train = row["candidate"],inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Native person overlap")
    key = candidate.get("source_algorithm","")+"-"+candidate.get("source_task","")
    before = {name:joblib.hash(head) for name,head in heads.items()}
    model,evidence = observed_native_fit(candidate,fitting,inputs["specifications"],heads.get(key))
    runtime = validation[model.input_features]
    prediction = model.predict(runtime)
    np.testing.assert_array_equal(prediction,np.asarray(row["oof_predictions"])[val])
    require(model.optimizer_summary == row["folds"][number]["optimizer_summary"],"Native optimizer diagnostics did not reproduce")
    with tempfile.TemporaryDirectory() as directory:
        artifact = Path(directory)/"original-runner-hr-native.joblib"
        joblib.dump(model,artifact)
        np.testing.assert_array_equal(joblib.load(artifact).predict(runtime),prediction)
    require({name:joblib.hash(head) for name,head in heads.items()} == before,"Native fitting changed frozen source functions")
    print(f"Independent original runnerHRnative refit:{candidate['id']} fold{number+1}/5",flush=True)
    return {"candidate_id":candidate["id"],"fold":number,**evidence,"optimizer_summary":model.optimizer_summary,
        "reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    signature = study.fingerprint(inputs)
    train,test = inputs["train"],inputs["test"]
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
        and selection["plan"] == study.plan() and len(selection["results"]) == 14
        and selection["train_row_keys"] == train.row_key.tolist(),"Frozen runnerHRnative selection changed/incomplete")
    require(len({r["candidate"]["id"] for r in selection["results"]}) == 14
        and {r["candidate"]["id"] for r in selection["results"]} == {c["id"] for c in study.plan()},"Original frozen14recipe coverage is not bijective")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
        and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
        and not selection["test_used_for_selection"] and selection["minimum_cv_for_new_test_evaluation"] == .65
        and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == 0
        and selection["actual_source_fitting_responses"] == 252 and selection["actual_source_fitting_adjacent_pairs"] == 168
        and selection["source_fitting_people"] == 12 and selection["reserved_source_responses_not_fitted"] == 84
        and selection["source_reserved_people"] == 4 and not selection["source_targets_pooled_across_instruments"],"Original native population/targets/policy changed")
    require(digest(study.DIRECTORY/"selection-source.py") == signature["code_sha256"],"Frozen selected fitting code changed")
    raw,held = inputs["runner_fitting"],inputs["runner_reserved"]
    require((len(raw),raw.group_key.nunique(),len(held),held.group_key.nunique()) == (252,12,84,4)
        and not set(raw.group_key)&set(held.group_key) and not (set(raw.group_key)|set(held.group_key))&set(inputs["frame"].group_key),"Source/native/reserved people were mixed")
    pd.testing.assert_frame_equal(inputs["frame"][inputs["previous_inputs"]["frame"].columns],inputs["previous_inputs"]["frame"])
    native_cache_path = study.native_hr.NATIVE_DIRECTORY/"dataset.csv"
    native_provenance_path = study.native_hr.NATIVE_DIRECTORY/"provenance.json"
    native_proof_path = study.DOCS/"cadence-association-input-verification.json"
    native_proof = json.loads(native_proof_path.read_text())
    require(signature["native_hr_dataset_sha256"] == digest(native_cache_path)
        and signature["native_hr_provenance_sha256"] == digest(native_provenance_path)
        and signature["native_hr_verification_sha256"] == digest(native_proof_path)
        and native_proof["native_provenance_sha256"] == digest(native_provenance_path)
        and native_proof["native_pulse_at_query_completed_by_query"]
        and native_proof["native_prior_pulse_completed_by_genuine_prior"],"Original native HR availability/identity evidence changed")
    native_cache = pd.read_csv(native_cache_path).set_index("row_key")
    require(len(native_cache) == 666 and native_cache.index.is_unique,"Original native HR cache cases changed")
    for part in (inputs["frame"],train,test):
        expected = native_cache.loc[part.row_key]
        np.testing.assert_array_equal(part.group_key.to_numpy(),expected.group_key.to_numpy())
        np.testing.assert_allclose(part[study.CURRENT],expected.current_hr_bpm,rtol=0,atol=0,equal_nan=True)
        np.testing.assert_allclose(part[study.PRIOR],expected.prior_hr_bpm,rtol=0,atol=0,equal_nan=True)
        values = np.where(np.isfinite(part[study.CURRENT])&np.isfinite(part[study.PRIOR]),part[study.CURRENT]-part[study.PRIOR],np.nan)
        np.testing.assert_allclose(part[study.DIFFERENCE],values,rtol=0,atol=0,equal_nan=True)
    proof = json.loads(study.INPUT_AUDIT.read_text())
    require(proof["verification"] == "passed" and proof["all_sensor_timestamps_strictly_before_current_rpe"]
        and proof["original_outcome_points_preserved_separately"] and not proof["source_target_conversion_or_pooling"],"Source real-target/pre-report availability review changed")
    stored = study.read_sources(inputs)
    heads,source_refits,teacher_hashes = {},[],{}
    for algorithm in ("ridge","svr"):
        for task in ("state","delta"):
            key = algorithm+"-"+task
            head,evidence = observed_source_fit(raw,algorithm,task)
            _,x,_,_ = original_source_values(raw,task)
            with threadpool_limits(limits=1):
                np.testing.assert_allclose(head.predict(x),stored[key].predict(x),rtol=0,atol=1e-12)
            for role in (("current","prior") if task == "state" else ("current",)):
                query = study.make_source_query(train,task,role)
                mask = np.isfinite(query.to_numpy(float)).all(axis=1)
                if mask.any():
                    with threadpool_limits(limits=1):
                        np.testing.assert_allclose(head.predict(query.loc[mask]),stored[key].predict(query.loc[mask]),rtol=0,atol=1e-12)
            for suffix in (".json",".joblib"):
                teacher_hashes[key+suffix] = digest(study.DIRECTORY/"teachers"/(key+suffix))
            metadata = json.loads((study.DIRECTORY/"teachers"/(key+".json")).read_text())
            require(metadata["signature"] == signature and metadata["model_sha256"] == teacher_hashes[key+".joblib"]
                and metadata["source_algorithm"] == algorithm and metadata["source_task"] == task
                and metadata["actual_fitting_targets"] == (252 if task == "state" else 168)
                and metadata["source_fitting_people"] == 12 and metadata["reserved_source_responses_not_fitted"] == 84,"Original source function artifact/identity changed")
            heads[key],source_refits = head,source_refits+[evidence]
            print(f"Independent source runnerHRrefit:{key},{evidence['actual_source_targets_observed']}original outcomes",flush=True)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in study.plan() and len(predicted) == 487 and set(predicted)<={f"Borg {i}" for i in range(11)},"Native OOF cases/classes changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(row["fold_accuracy"] == scores and row["accuracy_mean"] == float(np.mean(scores))
            and row["pooled_oof_accuracy"] == float(accuracy_score(train.label,predicted)),"Original native OOF metrics changed")
        if candidate["algorithm"] == "previous_real_control":
            inherited = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,inherited["oof_predictions"])
            continue
        require(len(row["folds"]) == 5,"New native person folds missing")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Frozen native fold membership changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            summary = saved["optimizer_summary"]
            count = (252 if candidate["source_task"] == "state" else 168) if candidate["algorithm"] == "furukawa_source_function" else 0
            require(summary["actual_native_fit_rows"] == len(fit) and summary["actual_native_fit_people"] == train.iloc[fit].group_key.nunique()
                and summary["actual_source_fitting_targets"] == count and summary["source_reserved_targets_not_fitted"] == 84
                and not summary["source_outcomes_pooled"] and summary["source_teacher_frozen"]
                and summary["synthetic_rows"] == summary["artificial_history_views"] == 0,"Saved actual-source/native fit coverage changed")
    sources = [r for r in selection["results"] if r["candidate"]["algorithm"] == "furukawa_source_function"]
    measured = {member:next(r for r in selection["results"] if r["candidate"]["algorithm"] == "native_measured_hr_control"
        and r["candidate"]["member"] == member) for member in ("core","cat")}
    best = {member:max((r for r in sources if r["candidate"]["member"] == member),key=lambda r:r["accuracy_mean"]) for member in ("core","cat")}
    task_best = {task:{member:max((r for r in sources if r["candidate"]["member"] == member and r["candidate"]["source_task"] == task),
        key=lambda r:r["accuracy_mean"]) for member in ("core","cat")} for task in ("state","delta")}
    selected = {r["candidate"]["id"]:r for r in [*measured.values(),*[r for group in task_best.values() for r in group.values()]]}
    native_refits = []
    with ProcessPoolExecutor(max_workers=2,initializer=initialize,initargs=(heads,)) as pool:
        for future in as_completed([pool.submit(refit_native,(row,number)) for row in selected.values() for number in range(5)]):
            native_refits.append(future.result())
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"] and selection["best_cv_accuracy"] == winner["accuracy_mean"],"Full original-person CVwinner changed")
    gate = winner["candidate"]["algorithm"] != "previous_real_control" and winner["accuracy_mean"] >= .65
    evaluation = None
    if gate:
        from evaluate_fatigue_furukawa_hr_transfer import evaluate
        require((study.DIRECTORY/"evaluation/metrics.json").exists(),"Qualified sole frozen winner must be evaluated before independent verification")
        evaluation = evaluate()
    else:
        require(not any((study.DIRECTORY/"evaluation"/name).exists() for name in ("metrics.json","predictions.csv","pre-test-model.json","model.joblib")),"Native test opened below the predeclared CVgate")
    for name,expected in teacher_hashes.items():
        require(digest(study.DIRECTORY/"teachers"/name) == expected,"Independent verification changed frozen source artifacts")
    retained = validate_release()
    require(retained["correct"] == 108 and retained["accuracy"] == 108/179,"Original retained release artifact changed")
    compact = lambda r:{k:r[k] for k in ("candidate","accuracy_mean","fold_accuracy","pooled_oof_accuracy")}
    return {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "verification_code_sha256":digest(Path(__file__)),"selection_sha256":digest(path),"input_verification_sha256":digest(study.INPUT_AUDIT),
        "previous_verification_sha256":digest(study.PARENT_AUDIT),"public_real_data_policy_sha256":signature["public_real_data_policy_sha256"],
        "all_14_oof_recipes_recomputed":True,"original_native_rows_and_targets_preserved":True,
        "native_hr_cache_identities_and_available_values_independently_checked":666,
        "native_hr_provenance_sha256":digest(native_provenance_path),"native_hr_verification_sha256":digest(native_proof_path),
        "actual_source_function_refits":len(source_refits),"source_function_refits":source_refits,"source_teacher_artifact_hashes":teacher_hashes,
        "source_fitting_actual_state_targets":252,"source_fitting_actual_delta_targets":168,"source_fitting_people":12,
        "source_reserved_targets_not_fitted":84,"source_reserved_people":4,"actual_native_refits":len(native_refits),
        "native_recipes_independently_refitted":sorted(selected),"native_refits":sorted(native_refits,key=lambda r:(r["candidate_id"],r["fold"])),
        "actual_source_and_native_estimator_targets_and_weights_observed":True,"source_functions_frozen_during_native_fitting":True,
        "source_and_native_preprocessing_fitting_only":True,"natural_missing_representations_preserved":True,
        "source_outcomes_pooled_or_converted_to_native":False,"synthetic_rows":0,"artificial_history_views":0,
        "invented_source_times_or_rest_baselines":0,"best_source_by_member":{m:compact(r) for m,r in best.items()},
        "best_source_by_task_and_member":{t:{m:compact(r) for m,r in group.items()} for t,group in task_best.items()},
        "matched_measured_controls":{m:compact(r) for m,r in measured.items()},
        "best_source_cv_accuracy":max(r["accuracy_mean"] for r in sources),"winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],
        "new_test_gate_passed":gate,"new_test_evaluation":evaluation,"original_release_test_correct":108,"original_release_test_accuracy":108/179,
        "achieved":bool(evaluation and evaluation["correct"] >= 144),
        "scope":"Original runner experiment2pre-report HRand source-native Borgpoints preserved separately.4source functions independently refitted with actual252state or168delta targets and source-person weights. All14native exact487-case OOFrecipes recalculated,selected state/delta functions and matched measured controls independently refitted across5original person folds with true native estimator targets,fold statistics,frozen teachers and input-only reload.84source targets remain reserved; original179native test opened only for a sole frozenCVwinner above.65. No synthetic observations,source label conversion,assumed rest,guessed clocks or removed native cases."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=study.DOCS/"furukawa-hr-transfer-verification.json")
    args = parser.parse_args()
    report = validate()
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("verification","actual_source_function_refits","actual_native_refits","best_cv_accuracy","best_source_cv_accuracy","new_test_gate_passed","achieved")}),flush=True)
