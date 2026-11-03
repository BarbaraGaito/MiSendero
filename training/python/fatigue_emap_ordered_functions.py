"""Preserve separate actual source transition functions without guessing native phases.

This follow-up requires the preceding pooled-history study to be audited first.
The fixed per-member Worker/STS option is inherited from its native CV, while
T2/T3/T4 remain three alternative computed functions evaluated at every query.
"""
from __future__ import annotations

import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score,mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

import fatigue_emap_history_transfer as parent
from public_sources import digest

DIRECTORY = parent.DIRECTORY.parent/"emap-ordered-functions-80-v1"
PARENT_AUDIT = parent.source.DOCS/"emap-history-verification.json"
DIAGNOSTIC = parent.source.DOCS/"emap-ordered-history-context-diagnostic.json"
DECLARATION = parent.source.DOCS/"emap-ordered-functions-plan.json"
FEATURES = {"T2":["prior_borg"],"T3":["prior_borg","prior2_borg"],"T4":["prior_borg","prior2_borg"]}
OUTPUTS = {slot:"emap_ordered_function_"+slot+"_computed_change" for slot in FEATURES}
_RUNTIME = None


def plan(proof):
    controls = ["emap-history-000","emap-history-001"]+[proof["best_new_by_member"][m]["candidate"]["id"] for m in ("core","cat")]
    result = [{"id":f"emap-order-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":name} for i,name in enumerate(controls)]
    for algorithm in parent.ALGORITHMS:
        for member in ("core","cat"):
            result.append({"id":f"emap-order-{len(result):03d}","algorithm":"separate_recorded_order_functions",
                "source_algorithm":algorithm,"member":member,
                "include_worker_sts":proof["best_new_by_member"][member]["candidate"]["include_worker_sts"],
                "native_phase_equivalence_assumed":False,"ordered_source_functions":["T2","T3","T4"]})
    return result


def load_inputs():
    inputs = parent.load_inputs()
    selection = json.loads((parent.DIRECTORY/"selection.json").read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    diagnostic = json.loads(DIAGNOSTIC.read_text())
    declaration = json.loads(DECLARATION.read_text())
    if declaration["implementation_code_sha256"] != digest(Path(__file__)) or declaration["planned_native_recipes"] != 6:
        raise ValueError("Predeclared source-order implementation changed before selection")
    if (selection["status"] != "complete" or selection["plan"] != parent.plan() or len(selection["results"]) != 16
        or proof["selection_sha256"] != digest(parent.DIRECTORY/"selection.json")
        or proof["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_emap_history_transfer.py"))
        or proof["source_verification_refits"] != 9 or proof["actual_native_target_calls_observed"] != 20
        or not proof["original_native_rows_and_targets_preserved"]):
        raise ValueError("Preceding real-source history study is not complete and independently verified")
    if (diagnostic["code_sha256"] != digest(Path(__file__).with_name("diagnose_emap_ordered_history_context.py"))
        or diagnostic["source_provenance_sha256"] != digest(parent.source.DIRECTORY/"provenance.json")
        or diagnostic["emap_reserved_targets_used"] or diagnostic["native_test_targets_used"]):
        raise ValueError("Fitting-only source-order rationale changed")
    return {**inputs,"previous":selection,"previous_audit":proof,"parent_inputs":inputs}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"parent_signature":parent.fingerprint(inputs["parent_inputs"]),
        "previous_selection_sha256":digest(parent.DIRECTORY/"selection.json"),"previous_verification_sha256":digest(PARENT_AUDIT),
        "fitting_context_diagnostic_sha256":digest(DIAGNOSTIC),"predeclared_plan_sha256":digest(DECLARATION),
        "public_real_data_policy_sha256":digest(parent.source.DOCS/"public-real-data-policy.json"),
        "worker_processes":2}


def fit_ordered_functions(data,algorithm,observer=None):
    fitting = data[data.source_domain.eq("emap")&data.source_partition.eq("fitting")]
    models = {}
    for slot,features in FEATURES.items():
        part = fitting[fitting.current_slot.eq(int(slot[1:]))]
        expected = 82 if slot == "T4" else 83
        if len(part) != expected or part.group_key.nunique() != expected or part[features].isna().any().any():
            raise ValueError("Ordered source function lost genuine rows or acquired unavailable features")
        target = part.current_rpe.to_numpy(float)-part.prior_borg.to_numpy(float)
        model = make_pipeline(SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),StandardScaler(),parent.estimator(algorithm))
        if observer is not None:
            observer(slot,part[features].copy(),target.copy())
        with threadpool_limits(limits=1):
            model.fit(part[features],target)
        models[slot] = model
    return models


def add_features(frame,ordered,existing):
    parent.native.validate_calibration(frame)
    data = frame.copy()
    with threadpool_limits(limits=1):
        for slot,model in ordered.items():
            data[OUTPUTS[slot]] = model.predict(frame[FEATURES[slot]])
        for domain,model in existing.items():
            data[parent.OUTPUTS[domain]] = model.predict(frame[["prior_borg"]])
    if not np.isfinite(data[[OUTPUTS[s] for s in ordered]+[parent.OUTPUTS[d] for d in existing]].to_numpy()).all():
        raise ValueError("Nonfinite ordered-history computed representation")
    return data


class OrderedHistoryBorg:
    def __init__(self,candidate,ordered,existing):
        self.candidate,self.ordered = candidate,ordered
        self.existing = {domain:existing[domain] for domain in ("worker","sts")} if candidate["include_worker_sts"] else {}

    def fit(self,frame,specifications):
        c = self.candidate
        recipe = copy.deepcopy(specifications[c["member"]])
        if c["member"] == "core":
            recipe["params"] = {**recipe["params"],"max_iter":5000,"max_fun":100000,"tol":.0001}
        self.input_features = list(recipe["features"])
        self.model_features = self.input_features+[OUTPUTS[s] for s in FEATURES]+[parent.OUTPUTS[d] for d in self.existing]
        recipe.update(id=c["id"],features=self.model_features)
        kind = parent.DynamicsClassifier if c["member"] == "core" else parent.native.CatBoostBorg
        with warnings.catch_warnings(record=True) as captured,threadpool_limits(limits=1):
            warnings.simplefilter("always",ConvergenceWarning)
            self.model = kind(recipe).fit(add_features(frame,self.ordered,self.existing))
        self.optimizer_summary = {"actual_native_fit_rows":len(frame),"actual_distinct_emap_source_targets":248,
            "source_order_target_counts":{"T2":83,"T3":83,"T4":82},"additional_existing_source_targets":302 if self.existing else 0,
            "native_feature_count":len(self.model_features),"source_functions_refitted_in_native_fitting":False,
            "synthetic_rows":0,"artificial_history_views":0,"native_phase_assignment_performed":False,
            "convergence_warnings":[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)]}
        if c["member"] == "core":
            model = self.model.model[-1]
            self.optimizer_summary.update(iterations=int(model.n_iter_),fitting_loss=float(model.loss_),maximum_iterations=int(model.max_iter))
        return self

    def predict(self,frame):
        return self.model.predict(add_features(frame,self.ordered,self.existing))


def read_sources(inputs):
    signature = fingerprint(inputs)
    models = {}
    for algorithm in parent.ALGORITHMS:
        path = DIRECTORY/"teachers"/(algorithm+".joblib")
        meta = json.loads(path.with_suffix(".json").read_text())
        if meta["signature"] != signature or meta["algorithm"] != algorithm or meta["model_sha256"] != digest(path):
            raise ValueError("Frozen source ordered functions changed")
        models[algorithm] = joblib.load(path)
    previous = parent.read_sources(parent.fingerprint(inputs["parent_inputs"]))
    return models,previous


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs),read_sources(inputs)


def compute_fold(job):
    candidate,number,fit,val = job
    inputs,signature,(ordered,existing) = _RUNTIME
    train = inputs["train"]
    fitting,validation = train.iloc[fit],train.iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Native ordered-function fitting/validation people overlap")
    algorithm = candidate["source_algorithm"]
    model = OrderedHistoryBorg(candidate,ordered[algorithm],existing[algorithm]).fit(fitting,inputs["specifications"])
    return {"signature":signature,"candidate":candidate,"fold_number":number,"fit_row_keys":fitting.row_key.tolist(),
        "validation_row_keys":validation.row_key.tolist(),"predicted":model.predict(validation).tolist(),"optimizer_summary":model.optimizer_summary}


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload,encoding="utf-8")
    path.write_text(payload,encoding="utf-8")


def select():
    inputs = load_inputs()
    signature = fingerprint(inputs)
    train,test = inputs["train"],inputs["test"]
    candidates = plan(inputs["previous_audit"])
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("teachers","folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":candidates,"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "actual_distinct_emap_fitting_targets":248,"emap_reserved_targets_not_fitted":57,"new_native_borg_targets":0,
        "synthetic_training_rows":0,"source_targets_pooled_across_instruments":False,"native_phase_assignment_performed":False,
        "policy":"Fixed10recipes:4preceding real controls plus3regressors x2native classifiers. Separate sourceT2/T3/T4 functions use83/83/82 original actual targets;T2uses only its one observed prior andT3/T4two measured priors. No example is duplicated across source-order tasks. All3source functions are evaluated at every genuine native history,without assigning native phases. Worker/STS inclusion per native member fixed from preceding audited pooled-history CV; their frozen source functions are reused. Native13/29original features plus3ordered representations andoptional2existing computed changes;MLP16/8alpha10,5000iterations;CatBoost900depth3L2=30. Original487/179native exact cases,person folds and.65testgate retained. No synthetic data, invented clocks, phase equivalence, sensor joins or imputed targets."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != candidates or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen recorded-order study changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    data = inputs["source"]
    reserved = data[data.source_domain.eq("emap")&data.source_partition.eq("reserved")]
    for algorithm in parent.ALGORITHMS:
        path = DIRECTORY/"teachers"/(algorithm+".joblib")
        if path.with_suffix(".json").exists():
            meta = json.loads(path.with_suffix(".json").read_text())
            if meta["signature"] != signature or meta["model_sha256"] != digest(path):
                raise ValueError("Frozen recorded-order source function changed")
        else:
            models = fit_ordered_functions(data,algorithm)
            joblib.dump(models,path)
            held_scores = {}
            for slot,model in models.items():
                part = reserved[reserved.current_slot.eq(int(slot[1:]))]
                prediction = part.prior_borg.to_numpy()+model.predict(part[FEATURES[slot]])
                held_scores[slot] = {"reserved_actual_pairs":len(part),"mae_descriptive_only":float(mean_absolute_error(part.current_rpe,prediction))}
            meta = {"signature":signature,"algorithm":algorithm,"model_sha256":digest(path),"source_fitting_counts":{"T2":83,"T3":83,"T4":82},
                "source_reserved_scores_used_for_model_selection":False,"reserved_scores":held_scores,"native_targets_used_for_source_fitting":0,
                "synthetic_rows":0,"source_features":FEATURES}
            path.with_suffix(".json").write_text(json.dumps(meta,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print(f"Recorded-order source functions ready:{algorithm};83/83/82 distinct actual targets",flush=True)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for candidate in candidates[4:]:
        for number,(fit,val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist():
                    raise ValueError("Frozen recorded-order native fold changed")
            else:
                jobs.append((candidate,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            for future in as_completed([pool.submit(compute_fold,job) for job in jobs]):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
                print(f"Recorded-order native fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete",flush=True)
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            predicted,details = np.asarray(old["oof_predictions"]),[]
        else:
            predicted,details = np.empty(len(train),dtype=object),[]
            for number,(_,val) in enumerate(folds):
                saved = json.loads((DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
                predicted[val] = saved["predicted"]
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report["results"].append({"candidate":candidate,"accuracy_mean":float(np.mean(scores)),"fold_accuracy":scores,
            "pooled_oof_accuracy":float(accuracy_score(train.label,predicted)),"oof_predictions":predicted.tolist(),"folds":details})
        winner = max(report["results"],key=lambda r:r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"],best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Recorded-order recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
