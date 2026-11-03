"""Verify cached person-held bases and actual source/native backpropagation targets."""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch
from catboost import CatBoostClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

import fatigue_two_history_joint as study
from public_sources import digest
from validate_fatigue_release import validate as validate_release

_RUNTIME = None


def require(value,reason):
    if not value:
        raise ValueError(reason)


def original_history(frame,is_source=False):
    if is_source:
        values = {study.source.PRIOR:frame[study.source.PRIOR].to_numpy(float),study.source.SECOND:frame[study.source.SECOND].to_numpy(float)}
    else:
        values = {study.source.PRIOR:frame.prior_borg.to_numpy(float),study.source.SECOND:frame.prior2_borg.to_numpy(float)}
    return pd.DataFrame(values,index=frame.index)


def check_base(base,frame,specification):
    require(base.specification == specification and base.input_features == specification["features"],"Cached native base parameters/features changed")
    require(base.fitting_summary["actual_native_rows"] == len(frame) and base.fitting_summary["actual_native_people"] == frame.group_key.nunique(),"Cached base case/person counts changed")
    require(base.__class__.__module__ == "fatigue_two_history_joint","Native base cache lost its canonical importable module identity")
    estimator = base.classifier.model[-1] if base.member == "core" else base.classifier.model
    if base.member == "core":
        params = estimator.get_params()
        require(params["alpha"] == 10 and params["max_iter"] == 5000 and params["max_fun"] == 100000
            and list(params["hidden_layer_sizes"]) == [16,8] and params["solver"] == "lbfgs" and not params["early_stopping"],"Cached native MLP optimizer changed")
        pipeline = base.classifier.model
        medians = np.nan_to_num(np.nanmedian(frame[base.input_features].to_numpy(float),axis=0),nan=0)
        np.testing.assert_array_equal(pipeline[0].statistics_,medians)
        imputed = pipeline[0].transform(frame[base.input_features])
        np.testing.assert_allclose(pipeline[1].mean_,imputed.mean(axis=0),rtol=0,atol=1e-12)
        require(int(pipeline[1].n_samples_seen_) == len(frame),"Cached native scaling saw held-out people")
    else:
        params = estimator.get_params()
        require(params["iterations"] == 900 and params["depth"] == 3 and params["l2_leaf_reg"] == 30
            and params["random_seed"] == 42 and not params["use_best_model"],"Cached original CatBoost parameters changed")
    target = frame.label.str.removeprefix("Borg ").to_numpy(int)-frame.prior_borg.to_numpy(int)
    np.testing.assert_array_equal(np.sort(base.class_indices-10),np.unique(target))
    require(base.fitting_summary["synthetic_rows"] == base.fitting_summary["artificial_history_views"] == 0,"Cached native base used artificial inputs")


def verify_base_caches(inputs,signature):
    train = inputs["train"]
    paths,checked = {},[]
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    for member in ("core","cat"):
        for number,(fit,val) in enumerate(folds):
            fitting,validation = train.iloc[fit],train.iloc[val]
            path = study.DIRECTORY/"bases"/f"{member}-fold-{number}.joblib"
            meta_path = path.with_suffix(".json")
            meta = json.loads(meta_path.read_text())
            require(meta["signature"] == signature and meta["member"] == member and meta["fold"] == number
                and meta["fit_row_keys"] == fitting.row_key.tolist() and meta["validation_row_keys"] == validation.row_key.tolist()
                and meta["cache_sha256"] == digest(path) and meta["actual_original_native_base_fits"] == 4,"Native base cache identity or original four fits changed")
            paths[path.name],paths[meta_path.name] = digest(path),digest(meta_path)
            cache = study.read_base_cache(inputs,member,number,fit,val)
            require(cache["fit_row_keys"] == fitting.row_key.tolist() and len(cache["inner_models"]) == len(cache["inner_folds"]) == 3,"Native base cache inner membership changed")
            inner = list(GroupKFold(n_splits=3).split(fitting,groups=fitting.group_key))
            for index,(inside,held) in enumerate(inner):
                a,b = fitting.iloc[inside],fitting.iloc[held]
                evidence = cache["inner_folds"][index]
                require(not set(a.group_key)&set(b.group_key) and evidence == meta["inner_folds"][index]
                    and evidence["fit_row_keys"] == a.row_key.tolist() and evidence["validation_row_keys"] == b.row_key.tolist(),"Inner native offsets leaked participants or changed cases")
                model = cache["inner_models"][index]
                check_base(model,a,inputs["specifications"][member])
                np.testing.assert_array_equal(cache["fit_logits"][held].numpy(),model.logits(b).numpy())
                np.testing.assert_array_equal(study.predictions(cache["fit_logits"][held],model.priority,b),model.predict(b))
            check_base(cache["base"],fitting,inputs["specifications"][member])
            np.testing.assert_array_equal(study.predictions(cache["base"].logits(validation),cache["base"].priority,validation),cache["base"].predict(validation))
            checked.append({"member":member,"fold":number,"actual_native_models_checked":4,"inner_person_folds":3,
                "original_rows_and_scaling_checked":True,"initial_floor_preserves_base_predictions":True})
    # Refit all four actual native bases in outer fold zero for each member.
    fit,val = folds[0]
    fitting = train.iloc[fit]
    inner = list(GroupKFold(n_splits=3).split(fitting,groups=fitting.group_key))
    expected = [fitting.iloc[a] for a,_ in inner]+[fitting]
    refits = []
    for member in ("core","cat"):
        native_kind = study.DynamicsClassifier if member == "core" else study.CatBoostBorg
        estimator_kind = MLPClassifier if member == "core" else CatBoostClassifier
        actual_fit,actual_estimator = native_kind.fit,estimator_kind.fit
        rows,targets = [],[]
        def observe(model,data):
            pd.testing.assert_frame_equal(data,expected[len(rows)])
            rows.append(data)
            return actual_fit(model,data)
        def observe_estimator(model,x,y,**kwargs):
            data = rows[-1]
            delta = data.label.str.removeprefix("Borg ").to_numpy(int)-data.prior_borg.to_numpy(int)
            np.testing.assert_array_equal(np.asarray(y).astype(int),delta)
            require(len(x) == len(data),"Actual independent base fitter saw generated rows")
            targets.append(len(y))
            return actual_estimator(model,x,y,**kwargs)
        with patch.object(native_kind,"fit",new=observe),patch.object(estimator_kind,"fit",new=observe_estimator),\
                patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial fitting histories prohibited")):
            fresh = study.prepare_base(fitting,member,inputs["specifications"][member])
        require(len(rows) == len(targets) == 4,"Actual independent base target observer bypassed")
        stored = study.read_base_cache(inputs,member,0,fit,val)
        np.testing.assert_allclose(fresh["fit_logits"].numpy(),stored["fit_logits"].numpy(),rtol=0,atol=1e-12)
        np.testing.assert_allclose(fresh["base"].logits(inputs["frame"]).numpy(),stored["base"].logits(inputs["frame"]).numpy(),rtol=0,atol=1e-12)
        for index,data in enumerate(rows):
            refits.append({"member":member,"outer_fold":0,"base_index":index,"actual_native_rows_observed":len(data),"actual_delta_targets_observed":targets[index]})
        print(f"Independent original native base refits:{member},four actual fitting cohorts",flush=True)
    return paths,checked,refits


def initialize_joint_audit():
    global _RUNTIME
    _RUNTIME = study.load_inputs()


def observe_joint_fit(candidate,fitting,external,specification,context_features,cache):
    model = study.JointHistoryBorg(candidate)
    before = joblib.hash(cache)
    raw_native,raw_source = original_history(fitting),original_history(external,True)
    union = pd.concat([raw_native,raw_source],ignore_index=True)
    imputer = SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)
    scaler = StandardScaler().fit(imputer.fit_transform(union))
    expected_history = scaler.transform(imputer.transform(raw_native)).astype(np.float32)
    context_imputer = SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)
    context_scaler = StandardScaler().fit(context_imputer.fit_transform(fitting[context_features]))
    expected_context = context_scaler.transform(context_imputer.transform(fitting[context_features])).astype(np.float32)
    target = fitting.label.str.removeprefix("Borg ").to_numpy(int)-fitting.prior_borg.to_numpy(int)+10
    positive = candidate["auxiliary_weight"] > 0
    domains = sorted(study.SOURCE_COUNTS)
    source_values = {}
    for domain in domains:
        part = external[external.source_domain.eq(domain)]
        shared = scaler.transform(imputer.transform(original_history(part,True))).astype(np.float32)
        delta = (part[study.TARGETS[domain]].to_numpy(float)-part[study.source.PRIOR].to_numpy(float)).astype(np.float32)
        weights = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
        weights *= len(part)/weights.sum()
        source_values[domain] = shared,delta,weights.astype(np.float32)
    observations,epochs,ce_calls,smooth_calls = [],[],[],[]
    encoder_calls = Counter()
    handles = []
    native_ce,source_loss = torch.nn.functional.cross_entropy,torch.nn.functional.smooth_l1_loss
    actual_initialize = study.HistoryNetwork.__init__
    def observed_initialize(network,*args,**kwargs):
        actual_initialize(network,*args,**kwargs)
        def encoder_hook(layer,values):
            actual = values[0].detach().numpy()
            if len(actual) == len(fitting):
                np.testing.assert_array_equal(actual,expected_history)
                encoder_calls["native"] += 1
            else:
                require(positive,"Zero auxiliary weight evaluated a source encoder training batch")
                domain = next(d for d in domains if len(actual) == study.SOURCE_COUNTS[d])
                np.testing.assert_array_equal(actual,source_values[domain][0])
                encoder_calls[domain] += 1
        def corrector_hook(layer,values):
            actual = values[0].detach().numpy()
            np.testing.assert_array_equal(actual[:,:len(context_features)+len(context_imputer.indicator_.features_)],expected_context)
        handles.extend([network.encoder.register_forward_pre_hook(encoder_hook),network.corrector.register_forward_pre_hook(corrector_hook)])
    def observe(kind,domain,x,current,prior):
        if kind == "native":
            pd.testing.assert_frame_equal(x,fitting[model.input_features])
            np.testing.assert_array_equal(current,fitting.label.str.removeprefix("Borg ").to_numpy(int))
            np.testing.assert_array_equal(prior,fitting.prior_borg)
        else:
            part = external[external.source_domain.eq(domain)]
            pd.testing.assert_frame_equal(x,part[study.COMMON])
            np.testing.assert_array_equal(current,part[study.TARGETS[domain]])
            np.testing.assert_array_equal(prior,part[study.source.PRIOR])
        observations.append((kind,domain,len(current)))
    def ce(logits,y,*args,**kwargs):
        np.testing.assert_array_equal(y.numpy(),target)
        require(tuple(logits.shape) == (len(fitting),21),"Native joint loss changed actual cases or delta classes")
        ce_calls.append(len(y))
        return native_ce(logits,y,*args,**kwargs)
    def smooth(prediction,y,*args,**kwargs):
        require(positive,"Zero auxiliary weight used source current labels in the loss")
        domain = domains[len(smooth_calls)%3]
        np.testing.assert_array_equal(y.numpy(),source_values[domain][1])
        smooth_calls.append(len(y))
        return source_loss(prediction,y,*args,**kwargs)
    def batches(epoch,x,y,auxiliary):
        epochs.append(epoch)
        np.testing.assert_array_equal(x,expected_history)
        np.testing.assert_array_equal(y,target)
        require(set(auxiliary) == (set(domains) if positive else set()),"Joint source heads/loss inclusion changed")
        for domain,values in auxiliary.items():
            for actual,expected in zip(values,source_values[domain]):
                np.testing.assert_array_equal(actual,expected)
    with patch.object(study.HistoryNetwork,"__init__",new=observed_initialize),patch.object(torch.nn.functional,"cross_entropy",new=ce),\
            patch.object(torch.nn.functional,"smooth_l1_loss",new=smooth),\
            patch.object(study,"prepare_base",side_effect=AssertionError("Joint refit must reuse its frozen native base")),\
            patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial fitting histories prohibited")):
        model.fit(fitting,external,specification,context_features,cached=cache,observer=observe,batch_observer=batches)
    for handle in handles:
        handle.remove()
    require(epochs == list(range(candidate["epochs"])) and len(ce_calls) == candidate["epochs"]
        and len(smooth_calls) == (3*candidate["epochs"] if positive else 0),"Actual source/native loss steps differed from fixed epoch plan")
    require(sum(x[2] for x in observations if x[0] == "source") == (550 if positive else 0)
        and sum(x[2] for x in observations if x[0] == "native") == len(fitting),"Actual original source/native target observer bypassed")
    require(encoder_calls["native"] == candidate["epochs"]+1,"Native encoder evaluated extra/generated training examples")
    for domain in domains:
        require(encoder_calls[domain] == (candidate["epochs"] if positive else 0),"Source encoder batch coverage changed")
    require(int(model.history_scaler.n_samples_seen_) == len(union) and int(model.context_scaler.n_samples_seen_) == len(fitting),"Joint preprocessing included held rows")
    np.testing.assert_array_equal(model.history_imputer.statistics_,imputer.statistics_)
    np.testing.assert_array_equal(model.history_scaler.mean_,scaler.mean_)
    np.testing.assert_array_equal(model.context_imputer.statistics_,context_imputer.statistics_)
    np.testing.assert_array_equal(model.context_scaler.mean_,context_scaler.mean_)
    gradient = model.training_summary["initial_encoder_gradient_l2"]
    require(gradient > 0 if positive else gradient == 0,"Actual source-to-encoder gradient did not match source objective inclusion")
    require(joblib.hash(cache) == before,"Joint backpropagation changed the frozen native base/cache")
    require(not set(vars(model))&{"frame","external","cache","targets","row_keys","pool"},"Joint runtime stores fitting/query truths or IDs")
    return model,{"actual_native_target_calls":len(ce_calls),"actual_source_target_calls":len(smooth_calls),
        "actual_native_targets_per_step":len(fitting),"actual_source_targets_per_positive_step":550 if positive else 0,
        "encoder_input_batches_verified":dict(encoder_calls),"initial_encoder_gradient_l2":gradient,
        "native_base_weights_frozen":True,"source_labels_excluded_when_zero":not positive,"original_observation_targets_verified":True}


def refit_joint(job):
    row,number = job
    inputs = _RUNTIME
    candidate,train = row["candidate"],inputs["train"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Joint native refit leaked held people")
    cache = study.read_base_cache(inputs,candidate["member"],number,fit,val)
    model,evidence = observe_joint_fit(candidate,fitting,inputs["source"],inputs["specifications"][candidate["member"]],inputs["context_features"],cache)
    predicted = model.predict(validation[model.input_features])
    np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
    require(model.training_summary == row["folds"][number]["training_summary"] and model.loss_endpoints == row["folds"][number]["loss_endpoints"],"Joint losses/optimizer diagnostics failed exact reproduction")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/"actual-joint-history.joblib"
        joblib.dump(model,path)
        np.testing.assert_array_equal(joblib.load(path).predict(validation[model.input_features]),predicted)
    return {"candidate_id":candidate["id"],"fold":number,**evidence,"training_summary":model.training_summary,
        "reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    signature = study.fingerprint(inputs)
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    train,test = inputs["train"],inputs["test"]
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
        and selection["plan"] == study.plan(inputs["previous_audit"]) and len(selection["results"]) == 16
        and selection["train_row_keys"] == train.row_key.tolist(),"Frozen joint two-history selection changed or incomplete")
    require(selection["evaluation_denominator"] == len(train) == 487 and selection["test_denominator"] == len(test) == 179
        and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
        and selection["actual_source_fitting_targets_available"] == 550 and selection["actual_source_fitting_second_priors"] == 367
        and selection["reserved_source_targets_not_fitted"] == 57 and not selection["test_used_for_selection"]
        and selection["minimum_cv_for_new_test_evaluation"] == .65 and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == 0
        and not selection["source_targets_pooled_across_instruments"],"Original native/source targets, reservations or test gate changed")
    require(digest(study.DIRECTORY/"selection-source.py") == signature["code_sha256"],"Frozen fitting source snapshot differs from selected implementation")
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in selection["plan"] and len(predicted) == 487 and set(predicted)<={f"Borg {i}" for i in range(11)},"Joint OOF targets/cases changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
            and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"],"Joint native OOF metrics changed")
        if candidate["algorithm"] == "previous_real_control":
            previous = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,previous["oof_predictions"])
            continue
        require(len(row["folds"]) == 5,"Joint actual native folds missing")
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist() and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Frozen joint fold membership changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            summary = saved["training_summary"]
            positive = candidate["auxiliary_weight"] > 0
            require(summary["actual_native_targets"] == len(fit) and summary["source_input_rows_for_shared_preprocessing"] == 550
                and summary["actual_source_targets_in_objective"] == (550 if positive else 0)
                and summary["source_targets_by_separate_head"] == (study.SOURCE_COUNTS if positive else {})
                and summary["source_fitting_actual_second_priors"] == 367 and summary["native_actual_second_priors"] == int(train.iloc[fit].prior2_borg.notna().sum())
                and summary["source_reserved_targets_not_fitted"] == 57 and summary["gradient_steps"] == candidate["epochs"]
                and summary["native_base_weights_frozen"] and summary["synthetic_rows"] == summary["artificial_history_views"] == summary["invented_source_times_or_sensor_joins"] == 0,
                "Joint fitting supervision, actual priors or source/native scope changed")
            require(summary["initial_encoder_gradient_l2"] > 0 if positive else summary["initial_encoder_gradient_l2"] == 0,"Stored actual source gradient evidence changed")
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"] and selection["best_cv_accuracy"] == winner["accuracy_mean"],"Full-CV joint winner changed")
    new = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    positive = [r for r in new if r["candidate"]["auxiliary_weight"] > 0]
    best = {member:max((r for r in positive if r["candidate"]["member"] == member),key=lambda r:r["accuracy_mean"]) for member in ("core","cat")}
    all_best = {member:max((r for r in new if r["candidate"]["member"] == member),key=lambda r:r["accuracy_mean"]) for member in ("core","cat")}
    matched = {member:next(r for r in new if r["candidate"]["member"] == member and r["candidate"]["auxiliary_weight"] == 0
        and r["candidate"]["epochs"] == row["candidate"]["epochs"]) for member,row in best.items()}
    selected = {r["candidate"]["id"]:r for r in [*best.values(),*matched.values(),*all_best.values()]}
    hashes,base_checks,base_refits = verify_base_caches(inputs,signature)
    joint_refits = []
    with ProcessPoolExecutor(max_workers=2,initializer=initialize_joint_audit) as pool:
        for future in as_completed([pool.submit(refit_joint,(row,number)) for row in selected.values() for number in range(5)]):
            item = future.result()
            joint_refits.append(item)
            print(f"Independent actual joint target/gradient refit {item['candidate_id']} fold{item['fold']+1}/5",flush=True)
    evaluation = None
    if winner["accuracy_mean"] >= .65 and winner["candidate"]["algorithm"] != "previous_real_control":
        from evaluate_fatigue_two_history_joint import evaluate
        require((study.DIRECTORY/"evaluation/metrics.json").exists(),"Qualified sole joint winner needs frozen original179 evaluation first")
        evaluation = evaluate()
        model = joblib.load(study.DIRECTORY/"evaluation/model.joblib")
        cache = study.prepare_base(train,winner["candidate"]["member"],inputs["specifications"][winner["candidate"]["member"]])
        reproduced,_ = observe_joint_fit(winner["candidate"],train,inputs["source"],inputs["specifications"][winner["candidate"]["member"]],inputs["context_features"],cache)
        np.testing.assert_array_equal(reproduced.predict(inputs["frame"][reproduced.input_features]),model.predict(inputs["frame"][model.input_features]))
        require(evaluation["cases"] == 179 and evaluation["selection_sha256"] == digest(selection_path),"Frozen joint test denominator or selection changed")
    else:
        require(not (study.DIRECTORY/"evaluation/metrics.json").exists(),"A native test was opened below the fixed CVgate")
    for name,expected in hashes.items():
        require(digest(study.DIRECTORY/"bases"/name) == expected,"Verification changed frozen native base caches")
    original_release = validate_release()
    require(original_release["correct"] == 108 and original_release["accuracy"] == 108/179,"Original retained release artifact changed")
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "selection_sha256":digest(selection_path),"input_verification_sha256":digest(study.INPUT_AUDIT),"previous_verification_sha256":digest(study.PARENT_AUDIT),
        "public_real_data_policy_sha256":signature["public_real_data_policy_sha256"],"all_16_oof_recipes_recomputed":True,
        "native_base_caches_checked":10,"cached_native_base_fit_models_checked":40,"native_base_cache_checks":base_checks,
        "native_base_artifact_hashes":hashes,"independent_native_base_fits":8,"independent_native_base_refits":base_refits,
        "actual_native_joint_refits":len(joint_refits),"joint_refits":sorted(joint_refits,key=lambda r:(r["candidate_id"],r["fold"])),
        "native_recipes_independently_refitted":sorted(selected),"original_native_rows_and_targets_preserved":True,
        "actual_source_and_native_loss_targets_observed":True,"actual_source_encoder_gradients_verified":True,
        "zero_auxiliary_control_excludes_source_labels":True,"native_base_weights_frozen":True,
        "shared_preprocessing_fitting_rows_only":True,"native_context_preprocessing_fitting_people_only":True,
        "source_outcomes_pooled":False,"synthetic_rows":0,"invented_source_times_or_sensor_joins":0,
        "best_positive_by_member":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in best.items()},
        "matched_zero_auxiliary_controls":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in matched.items()},
        "best_new_by_member":{member:{"candidate":r["candidate"],"accuracy_mean":r["accuracy_mean"]} for member,r in all_best.items()},
        "best_positive_cv_accuracy":max(r["accuracy_mean"] for r in positive),"winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],
        "new_test_gate_passed":evaluation is not None,"new_test_evaluation":evaluation,
        "original_training_cases":487,"original_test_cases":179,"original_release_test_correct":108,"original_release_test_accuracy":108/179,
        "best_verified_test_correct":max(108,evaluation["correct"] if evaluation else 0),"target_accuracy":.8,"achieved":bool(evaluation and evaluation["correct"]>=144),
        "scope":"Actual public histories and unchanged native exact cases only. All40cached native bases inspected for person membership,parameters,scaling and inner offsets;8base fits independently reproduced in outer fold0,not all40refitted. Best positive/zero and overall new joint recipes reproduced across all5original person folds with actual encoder inputs,loss targets,source weights,gradient flow and reloading observed. Separate source outcomes preserve550original fitting targets and367measured second priors;57source targets reserved. No synthetic examples, invented missing histories, source clocks/phases/sensors or changed native487/179cases."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
