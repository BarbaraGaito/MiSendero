"""Observe actual manual targets, gradients, normalization, and held-person OOFs."""
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
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

import fatigue_resistance_history_joint as study
from public_sources import digest
from validate_fatigue_release import validate as validate_release

_RUNTIME = None


def require(value,reason):
    if not value:
        raise ValueError(reason)


def raw_history(frame,external=False):
    return pd.DataFrame({study.source.PRIOR:frame[study.source.PRIOR].to_numpy(float) if external else frame.prior_borg.to_numpy(float),
        study.source.SECOND:frame[study.source.SECOND].to_numpy(float) if external else frame.prior2_borg.to_numpy(float)},index=frame.index)


def observe_actual_fit(candidate,fitting,external,specification,context_features,cache):
    """Intercept real torch inputs/loss/backward, independently rebuild statistics."""
    model = study.ResistanceHistoryBorg(candidate)
    before,native_before,external_before = joblib.hash(cache),joblib.hash(fitting),joblib.hash(external)
    old = external[external.source_domain.ne("resistance")]
    union = pd.concat([raw_history(fitting),raw_history(old,True)],ignore_index=True)
    imputer = SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)
    scaler = StandardScaler().fit(imputer.fit_transform(union))
    expected_history = scaler.transform(imputer.transform(raw_history(fitting))).astype(np.float32)
    context_imputer = SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)
    context_scaler = StandardScaler().fit(context_imputer.fit_transform(fitting[context_features]))
    expected_context = context_scaler.transform(context_imputer.transform(fitting[context_features])).astype(np.float32)
    target = fitting.label.str.removeprefix("Borg ").to_numpy(int)-fitting.prior_borg.to_numpy(int)+10
    positive = candidate["resistance_weight"] > 0
    domains = sorted(study.previous.SOURCE_COUNTS)+(["resistance"] if positive else [])
    source_values = {}
    for domain in domains:
        part = external[external.source_domain.eq(domain)]
        shared = scaler.transform(imputer.transform(raw_history(part,True))).astype(np.float32)
        delta = (part[study.TARGETS[domain]].to_numpy(float)-part[study.source.PRIOR].to_numpy(float)).astype(np.float32)
        weights = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
        weights *= len(part)/weights.sum()
        source_values[domain] = shared,delta,weights.astype(np.float32)
    calls,encoder_calls = Counter(),Counter()
    observed,epochs,handles = [],[],[]
    live = {}
    independent_new_gradient = 0.
    ce,smooth,backward = torch.nn.functional.cross_entropy,torch.nn.functional.smooth_l1_loss,torch.Tensor.backward
    initialize = study.ResistanceHistoryNetwork.__init__
    def observed_initialize(network,*args,**kwargs):
        initialize(network,*args,**kwargs)
        with torch.random.fork_rng():
            torch.manual_seed(candidate["random_seed"])
            original = study.previous.HistoryNetwork(args[0],args[1],sorted(study.previous.SOURCE_COUNTS))
        for name,values in original.state_dict().items():
            np.testing.assert_array_equal(network.state_dict()[name].numpy(),values.numpy())
        def encoder_hook(layer,values):
            actual = values[0].detach().numpy()
            if len(actual) == len(fitting):
                np.testing.assert_array_equal(actual,expected_history)
                encoder_calls["native"] += 1
            else:
                domain = next((d for d in domains if len(actual) == study.SOURCE_COUNTS[d]),None)
                require(domain is not None,"A reserved/generated source batch entered the encoder")
                np.testing.assert_array_equal(actual,source_values[domain][0])
                encoder_calls[domain] += 1
        def context_hook(layer,values):
            np.testing.assert_array_equal(values[0].detach().numpy()[:,:expected_context.shape[1]],expected_context)
        def correction_hook(layer,values,output):
            live["correction"] = output.to(torch.float64)
        handles.extend([network.encoder.register_forward_pre_hook(encoder_hook),network.corrector.register_forward_pre_hook(context_hook),
            network.corrector.register_forward_hook(correction_hook)])
    def observe(kind,domain,x,current,prior):
        if kind == "native":
            pd.testing.assert_frame_equal(x,fitting[model.input_features])
            np.testing.assert_array_equal(current,fitting.label.str.removeprefix("Borg ").to_numpy(int))
            np.testing.assert_array_equal(prior,fitting.prior_borg)
        else:
            part = external[external.source_domain.eq(domain)]
            pd.testing.assert_frame_equal(x,raw_history(part,True))
            np.testing.assert_array_equal(current,part[study.TARGETS[domain]])
            np.testing.assert_array_equal(prior,part[study.source.PRIOR])
        observed.append((kind,domain,len(current)))
    def observe_ce(logits,y,*args,**kwargs):
        np.testing.assert_array_equal(y.numpy(),target)
        require(tuple(logits.shape) == (len(fitting),21),"Native training targets/classes changed")
        calls["native_loss"] += 1
        output = ce(logits,y,*args,**kwargs)
        live["ce"] = output
        return output
    def observe_source(prediction,y,*args,**kwargs):
        domain = domains[calls["source_loss"]%len(domains)]
        np.testing.assert_array_equal(y.numpy(),source_values[domain][1])
        require(kwargs == {"beta":1.,"reduction":"none"},"Actual continuous source loss changed")
        calls["source_loss"] += 1
        output = smooth(prediction,y,*args,**kwargs)
        w = torch.as_tensor(source_values[domain][2])
        live[domain] = (output*w).sum()/w.sum()
        return output
    def batches(epoch,x,y,auxiliary):
        epochs.append(epoch)
        np.testing.assert_array_equal(x,expected_history)
        np.testing.assert_array_equal(y,target)
        require(list(auxiliary) == domains,"A zero-weight or reserved source target entered the objective")
        for domain,values in auxiliary.items():
            for actual,expected in zip(values,source_values[domain]):
                np.testing.assert_array_equal(actual,expected)
    def observe_backward(total,*args,**kwargs):
        nonlocal independent_new_gradient
        old_mean = torch.stack([live[d] for d in sorted(study.previous.SOURCE_COUNTS)]).mean()
        mixed = old_mean if not positive else (3*old_mean+candidate["resistance_weight"]*live["resistance"])/(3+candidate["resistance_weight"])
        expected = live["ce"]+candidate["auxiliary_weight"]*mixed+candidate["correction_penalty"]*live["correction"].square().mean()
        np.testing.assert_array_equal(total.detach().numpy(),expected.detach().numpy())
        if positive and calls["backward"] == 0:
            gradients = torch.autograd.grad(candidate["auxiliary_weight"]*candidate["resistance_weight"]*live["resistance"]/(3+candidate["resistance_weight"]),
                tuple(model.network.encoder.parameters()),retain_graph=True)
            independent_new_gradient = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
        result = backward(total,*args,**kwargs)
        new_head = model.network.source_heads["resistance"]
        if positive:
            require(all(p.grad is not None and torch.isfinite(p.grad).all() for p in new_head.parameters()),"Manual resistance head did not receive actual gradients")
        else:
            require(all(p.grad is None and not p.requires_grad for p in new_head.parameters()),"Zero-weight resistance head was trained")
        calls["backward"] += 1
        live.clear()
        return result
    with patch.object(study.ResistanceHistoryNetwork,"__init__",new=observed_initialize),\
            patch.object(torch.nn.functional,"cross_entropy",new=observe_ce),patch.object(torch.nn.functional,"smooth_l1_loss",new=observe_source),\
            patch.object(torch.Tensor,"backward",new=observe_backward),\
            patch.object(study.previous,"prepare_base",side_effect=AssertionError("Reuse the frozen original-native bases")),\
            patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial fitting histories prohibited")):
        model.fit(fitting,external,specification,context_features,cached=cache,observer=observe,batch_observer=batches)
    for handle in handles:
        handle.remove()
    require(epochs == list(range(80)) and calls["native_loss"] == calls["backward"] == 80
        and calls["source_loss"] == 80*len(domains),"Actual full-batch gradient steps differ from the frozen plan")
    require(encoder_calls["native"] == 81,"Native encoder used extra/generated cases")
    for domain in domains:
        require(encoder_calls[domain] == 80,"Source encoder training coverage changed")
    require(sum(v[2] for v in observed if v[0] == "source") == (1416 if positive else 550)
        and sum(v[2] for v in observed if v[0] == "native") == len(fitting),"Original target observation bypassed")
    require(int(model.history_scaler.n_samples_seen_) == len(union) and int(model.context_scaler.n_samples_seen_) == len(fitting),"Held/new-source cases changed matched normalization")
    np.testing.assert_array_equal(model.history_imputer.statistics_,imputer.statistics_)
    np.testing.assert_array_equal(model.history_scaler.mean_,scaler.mean_)
    np.testing.assert_array_equal(model.context_imputer.statistics_,context_imputer.statistics_)
    np.testing.assert_array_equal(model.context_scaler.mean_,context_scaler.mean_)
    require(model.training_summary["initial_resistance_only_encoder_gradient_l2"] == independent_new_gradient
        and (independent_new_gradient > 0 if positive else independent_new_gradient == 0),"Independent resistance-to-encoder gradient disagreed")
    require(model.training_summary["initial_encoder_gradient_l2"] > 0,"Old real sources stopped supervising the encoder")
    require(joblib.hash(cache) == before and joblib.hash(fitting) == native_before and joblib.hash(external) == external_before,"Training changed frozen bases or original source/native cases")
    require(not set(vars(model))&{"frame","external","cache","targets","row_keys","pool"},"Runtime retained fitting truth/identifiers")
    return model,{"actual_native_target_calls":calls["native_loss"],"actual_source_target_calls":calls["source_loss"],
        "actual_total_losses_independently_checked":calls["backward"],"actual_native_targets_per_step":len(fitting),
        "actual_source_targets_per_step":1416 if positive else 550,"actual_resistance_targets_per_step":866 if positive else 0,
        "encoder_input_batches_verified":dict(encoder_calls),"initial_resistance_only_encoder_gradient_l2":independent_new_gradient,
        "old_initial_parameters_preserved":True,"new_source_labels_excluded_when_zero":not positive,
        "all_original_outcomes_and_person_weights_verified":True,"native_base_weights_frozen":True}


def initialize():
    global _RUNTIME
    _RUNTIME = study.load_inputs()


def refit(job):
    row,number = job
    inputs,train = _RUNTIME,_RUNTIME["train"]
    candidate = row["candidate"]
    fit,val = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))[number]
    fitting,validation = train.iloc[fit],train.iloc[val]
    require(not set(fitting.group_key)&set(validation.group_key),"Outer native person overlap")
    cache = study.previous.read_base_cache(inputs["previous_inputs"],candidate["member"],number,fit,val)
    model,evidence = observe_actual_fit(candidate,fitting,inputs["source"],inputs["specifications"][candidate["member"]],inputs["context_features"],cache)
    runtime = validation[model.input_features]
    predicted = model.predict(runtime)
    np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
    require(model.training_summary == row["folds"][number]["training_summary"] and model.loss_endpoints == row["folds"][number]["loss_endpoints"],"Independent real-target refit differed from saved training")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/"original-resistance-history.joblib"
        joblib.dump(model,path)
        np.testing.assert_array_equal(joblib.load(path).predict(runtime),predicted)
    print(f"Independent original resistance joint refit:{candidate['id']} fold{number+1}/5",flush=True)
    return {"candidate_id":candidate["id"],"fold":number,**evidence,"training_summary":model.training_summary,"reload_without_current_truth_or_ids":True}


def validate():
    inputs = study.load_inputs()
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    train,test = inputs["train"],inputs["test"]
    require(selection["status"] == "complete" and all(selection.get(k) == v for k,v in signature.items())
        and selection["plan"] == study.plan(inputs["previous_audit"]) and len(selection["results"]) == 22
        and selection["train_row_keys"] == train.row_key.tolist(),"Frozen original-resistance selection changed/incomplete")
    require(selection["evaluation_denominator"] == 487 and selection["test_denominator"] == 179
        and train.group_key.nunique() == 28 and test.group_key.nunique() == 12 and not set(train.group_key)&set(test.group_key)
        and selection["actual_source_fitting_targets_available"] == 1416 and selection["actual_source_fitting_second_priors"] == 1169
        and selection["reserved_source_targets_not_fitted"] == 125 and not selection["test_used_for_selection"]
        and selection["minimum_cv_for_new_test_evaluation"] == .65
        and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == selection["new_native_base_fits"] == 0
        and selection["native_base_caches_reused"] == 10 and not selection["source_targets_pooled_across_instruments"],"Original cases/source reservations/policy changed")
    require(digest(study.DIRECTORY/"selection-source.py") == signature["code_sha256"],"Frozen source snapshot changed")
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    matched = []
    for row in selection["results"]:
        candidate,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(candidate in selection["plan"] and len(predicted) == 487 and set(predicted)<={f"Borg {i}" for i in range(11)},"Original native OOF cases/classes changed")
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        require(scores == row["fold_accuracy"] and float(np.mean(scores)) == row["accuracy_mean"]
            and float(accuracy_score(train.label,predicted)) == row["pooled_oof_accuracy"],"Actual native OOF metrics changed")
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,old["oof_predictions"])
            continue
        require(len(row["folds"]) == 5,"New actual-person folds missing")
        positive = candidate["resistance_weight"] > 0
        for number,(fit,val) in enumerate(folds):
            saved = row["folds"][number]
            disk = json.loads((study.DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
            require(saved == disk and saved["signature"] == signature and saved["candidate"] == candidate
                and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist() and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Frozen training/validation memberships changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            s = saved["training_summary"]
            require(s["actual_native_targets"] == len(fit) and s["source_input_rows_for_shared_preprocessing"] == 550
                and s["source_fitting_targets_available"] == 1416 and s["actual_source_targets_in_objective"] == (1416 if positive else 550)
                and s["resistance_source_targets_in_objective"] == (866 if positive else 0)
                and s["source_targets_by_separate_head"] == (study.SOURCE_COUNTS if positive else study.previous.SOURCE_COUNTS)
                and s["source_fitting_actual_second_priors"] == 1169 and s["native_actual_second_priors"] == int(train.iloc[fit].prior2_borg.notna().sum())
                and s["source_reserved_targets_not_fitted"] == 125 and s["gradient_steps"] == 80 and s["native_base_weights_frozen"]
                and s["initial_encoder_gradient_l2"] > 0
                and (s["initial_resistance_only_encoder_gradient_l2"] > 0 if positive else s["initial_resistance_only_encoder_gradient_l2"] == 0)
                and s["synthetic_rows"] == s["artificial_history_views"] == s["invented_source_times_or_sensor_joins"] == 0,"Actual source counts/gradients/policy changed")
        if not positive and candidate["correction_penalty"] == .1:
            old = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["previous_candidate_id"])
            np.testing.assert_array_equal(predicted,old["oof_predictions"])
            require(all(a["loss_endpoints"] == b["loss_endpoints"] for a,b in zip(row["folds"],old["folds"])),"Old matched control loss endpoints changed")
            matched.append(candidate["id"])
    require(len(matched) == 2,"Matched original-source controls missing")
    new = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    positive_by_member,zero_by_member,best_by_member,selected = {},{},{},{}
    for member in ("core","cat"):
        member_rows = [r for r in new if r["candidate"]["member"] == member]
        best_by_member[member] = max(member_rows,key=lambda r:r["accuracy_mean"])
        positive_by_member[member] = max((r for r in member_rows if r["candidate"]["resistance_weight"] > 0),key=lambda r:r["accuracy_mean"])
        positive = positive_by_member[member]
        zero_by_member[member] = next(r for r in member_rows if r["candidate"]["resistance_weight"] == 0
            and r["candidate"]["correction_penalty"] == positive["candidate"]["correction_penalty"])
        baseline = next(r for r in member_rows if r["candidate"]["resistance_weight"] == 0 and r["candidate"]["correction_penalty"] == .1)
        for row in (best_by_member[member],positive,zero_by_member[member],baseline):
            selected[row["candidate"]["id"]] = row
    global _RUNTIME
    _RUNTIME = inputs
    refits = []
    with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
        for future in as_completed([pool.submit(refit,(row,number)) for row in selected.values() for number in range(5)]):
            refits.append(future.result())
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(selection["winner_id"] == winner["candidate"]["id"] and selection["best_cv_accuracy"] == winner["accuracy_mean"],"Saved selection winner changed")
    gate = winner["candidate"]["algorithm"] != "previous_real_control" and winner["accuracy_mean"] >= .65
    test_metrics = None
    if gate:
        from evaluate_fatigue_resistance_history_joint import verify_frozen_evaluation
        test_metrics = verify_frozen_evaluation(inputs,selection)
    else:
        require(not (study.DIRECTORY/"evaluation/metrics.json").exists(),"A new original test was opened below the predeclared CV gate")
    retained = validate_release()
    require(retained["correct"] == 108 and retained["accuracy"] == 108/179,"The retained exact179artifact changed")
    compact = lambda r:{k:r[k] for k in ("candidate","accuracy_mean","fold_accuracy","pooled_oof_accuracy")}
    return {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "verification_code_sha256":digest(Path(__file__)),"selection_sha256":digest(path),
        "input_verification_sha256":digest(study.INPUT_AUDIT),"previous_verification_sha256":digest(study.PARENT_AUDIT),
        "public_real_data_policy_sha256":digest(study.DOCS/"public-real-data-policy.json"),
        "all_22_oof_recipes_recomputed":True,"original_native_rows_and_targets_preserved":True,
        "source_fitting_targets_available":1416,"additional_actual_resistance_fitting_targets":866,
        "source_fitting_actual_second_priors":1169,"reserved_source_targets_not_fitted":125,
        "native_base_cache_artifact_hashes":signature["native_base_artifact_hashes"],"native_base_caches_reused":10,
        "cached_native_base_models_previously_verified":40,"new_native_base_fits":0,
        "actual_native_joint_refits":len(refits),"native_recipes_independently_refitted":list(selected),
        "joint_refits":sorted(refits,key=lambda r:(r["candidate_id"],r["fold"])),
        "actual_source_and_native_losses_and_weights_observed":True,"actual_resistance_to_encoder_gradients_verified":True,
        "zero_new_weight_excludes_resistance_labels":True,"old_initial_parameters_and_matched_control_predictions_preserved":True,
        "matched_control_ids_reproduced":matched,"native_base_weights_frozen":True,
        "matched_preprocessing_fitting_rows_only":True,"source_outcomes_pooled":False,"synthetic_rows":0,
        "invented_source_times_or_sensor_joins":0,"winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],
        "best_positive_by_member":{m:compact(r) for m,r in positive_by_member.items()},
        "matched_zero_new_source_controls":{m:compact(r) for m,r in zero_by_member.items()},
        "best_new_by_member":{m:compact(r) for m,r in best_by_member.items()},
        "best_positive_cv_accuracy":max(r["accuracy_mean"] for r in positive_by_member.values()),
        "new_test_gate_passed":gate,"new_test_evaluation":test_metrics,"retained_test_verification":retained,
        "achieved":bool(test_metrics and test_metrics["correct"] >= 144),
        "scope":"Actual source/native targets observed in real torch CE,SmoothL1 and backward calls with independently rebuilt normalization,person weights,mixed loss and resistance-only encoder gradient. All22native OOF recipes recomputed; selected networks refitted for every original person fold and reloaded without truths/IDs. Ten preceding native-base caches/40models retained and hash-checked rather than refitted. Source1-10resistance outcomes remain separate; original487/179native cases retained,125source held targets excluded. No generated examples,EMG learned labels,SMOTE/jitter,invented clocks/sensors or label conversion."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=study.DOCS/"resistance-history-joint-verification.json")
    args = parser.parse_args()
    report = validate()
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("verification","actual_native_joint_refits","best_cv_accuracy","best_positive_cv_accuracy","new_test_gate_passed","achieved")}),flush=True)
