"""Compact CADENCE representations and regularization on actual native cases.

Source6-20 functions remain frozen. Native fitting sees a compact computed
feature, rather than all four redundant absolute/relative raw measurements.
"""
from __future__ import annotations

import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_cadence_transfer as parent
from fatigue_catboost import CatBoostBorg
from fatigue_dynamics_experiment import DynamicsClassifier
from public_sources import ROOT, digest

DIRECTORY = parent.DIRECTORY.parent/"cadence-compact-representation-80-v1"
PARENT_AUDIT = ROOT/"docs/fatigue-80-2026-10-25/cadence-transfer-verification.json"
OUTPUT = "cadence_compact_computed_source_rpe6to20"
_RUNTIME = None


def plan():
    controls = ("cadence-transfer-000","cadence-transfer-001","cadence-transfer-002",
                "cadence-transfer-003","cadence-transfer-014","cadence-transfer-015")
    result = [{"id":f"cadence-compact-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":name}
              for i,name in enumerate(controls)]
    for member in ("core","cat"):
        result.append({"id":f"cadence-compact-{len(result):03d}","algorithm":"compact_native_representation",
            "input_mode":"measured_relative","member":member,"source_feature_set":"relative"})
    for algorithm in ("ridge","svr","random_forest"):
        for shape in ([8],[16,8]):
            for alpha in (1.,10.,100.):
                result.append({"id":f"cadence-compact-{len(result):03d}","algorithm":"compact_native_representation",
                    "input_mode":"source_proxy","member":"core","source_algorithm":algorithm,"source_feature_set":"relative",
                    "params":{"hidden_layer_sizes":shape,"alpha":alpha,"solver":"lbfgs","activation":"relu",
                              "max_iter":5000,"max_fun":100000,"tol":.0001}})
    for algorithm in ("ridge","svr","random_forest"):
        for feature_set in ("absolute","relative"):
            result.append({"id":f"cadence-compact-{len(result):03d}","algorithm":"compact_native_representation",
                "input_mode":"source_proxy","member":"cat","source_algorithm":algorithm,"source_feature_set":feature_set})
    return result


def load_inputs():
    inputs = parent.load_inputs()
    audit = json.loads(PARENT_AUDIT.read_text())
    if (audit["selection_sha256"] != digest(parent.DIRECTORY/"selection.json")
        or audit["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_cadence_transfer.py"))
        or not audit["actual_native_rows_and_delta_targets_verified"] or not audit["source_targets_original6to20_unchanged"]
        or audit["source_fitting_targets"] != 851 or audit["source_reserved_targets"] != 206):
        raise ValueError("The independently audited source/native comparison changed")
    return inputs


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"parent_signature":parent.fingerprint(inputs),
        "parent_selection_sha256":digest(parent.DIRECTORY/"selection.json"),"parent_verification_sha256":digest(PARENT_AUDIT),
        "public_real_data_policy_sha256":digest(ROOT/"docs/fatigue-80-2026-10-25/public-real-data-policy.json"),
        "worker_processes":2}


def read_sources(inputs):
    return parent.read_sources(parent.fingerprint(inputs))


class CompactCadenceBorg:
    def __init__(self,candidate,teacher=None):
        self.candidate,self.teacher = candidate,teacher

    def add_features(self,frame):
        data = frame.copy()
        if self.candidate["input_mode"] == "source_proxy":
            query = parent.source_query(frame,self.candidate["source_feature_set"])
            available = np.isfinite(query.to_numpy(float)).all(axis=1)
            predicted = np.full(len(frame),np.nan)
            if available.any():
                with threadpool_limits(limits=1):
                    predicted[available] = self.teacher.predict(query.loc[available])
                if not np.isfinite(predicted[available]).all():
                    raise ValueError("Nonfinite source prediction for an actually measured input pair")
            # Propagate naturally unavailable measured inputs; do not invent a
            # completed pair or an extra fitting row. Native imputation is fold-local.
            data[OUTPUT] = predicted
        return data

    def fit(self,frame,specifications):
        candidate = self.candidate
        specification = copy.deepcopy(specifications[candidate["member"]])
        if candidate["member"] == "core":
            specification["params"] = copy.deepcopy(candidate.get("params",{
                **specification["params"],"max_iter":5000,"max_fun":100000,"tol":.0001}))
        query_features = [parent.NATIVE[name] for name in parent.SETS[candidate["source_feature_set"]]]
        self.input_features = list(dict.fromkeys(specification["features"]+query_features))
        if candidate["input_mode"] == "source_proxy":
            if self.teacher is None:
                raise ValueError("A source-only representation requires its frozen source function")
            self.model_features = specification["features"]+[OUTPUT]
        elif candidate["input_mode"] == "measured_relative":
            if self.teacher is not None:
                raise ValueError("Measured-only control must not contain a source function")
            self.model_features = specification["features"]+query_features
        else:
            raise ValueError("Unknown predeclared measured/compact representation")
        data = self.add_features(frame)
        recipe = {**specification,"id":candidate["id"],"features":self.model_features}
        classifier = DynamicsClassifier if candidate["member"] == "core" else CatBoostBorg
        with warnings.catch_warnings(record=True) as captured,threadpool_limits(limits=1):
            warnings.simplefilter("always",ConvergenceWarning)
            self.model = classifier(recipe).fit(data)
        self.optimizer_summary = {"convergence_warnings":[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)],
            "actual_native_fit_rows":len(frame),"model_feature_count":len(self.model_features),
            "natural_missing_representation_rows":int(data[OUTPUT].isna().sum()) if self.teacher is not None else None,
            "actual_auxiliary_source_targets":851 if self.teacher is not None else 0,"source_fitting_performed_here":False,
            "synthetic_rows":0,"artificial_history_views":0}
        if candidate["member"] == "core":
            estimator = self.model.model[-1]
            self.optimizer_summary.update(iterations=int(estimator.n_iter_),fitting_loss=float(estimator.loss_),
                maximum_iterations=int(estimator.max_iter),maximum_function_evaluations=int(estimator.max_fun),
                hidden_layer_sizes=list(estimator.hidden_layer_sizes),alpha=float(estimator.alpha))
        return self

    def predict(self,frame):
        return self.model.predict(self.add_features(frame))


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs),read_sources(inputs)


def compute_fold(job):
    candidate,number,fit,val = job
    inputs,signature,heads = _RUNTIME
    fitting,validation = inputs["train"].iloc[fit],inputs["train"].iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Compact native fitting leaked held participants")
    teacher = None if candidate["input_mode"] == "measured_relative" else heads[candidate["source_algorithm"],candidate["source_feature_set"]]
    model = CompactCadenceBorg(candidate,teacher).fit(fitting,inputs["specifications"])
    return {"signature":signature,"candidate":candidate,"fold_number":number,"fit_row_keys":fitting.row_key.tolist(),
        "validation_row_keys":validation.row_key.tolist(),"predicted":model.predict(validation).tolist(),"optimizer_summary":model.optimizer_summary}


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload,encoding="utf-8")
    path.write_text(payload,encoding="utf-8")


def select():
    inputs = load_inputs()
    train,test = inputs["train"],inputs["test"]
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY/"folds").mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "actual_source_fitting_targets":851,"source_reserved_targets_not_fitted":206,"new_native_borg_targets":0,"synthetic_training_rows":0,
        "policy":"Fixed32-recipe compact-representation comparison:6 inherited controls,2 measured-relative controls,18MLP recipes(3frozen relative source functions,2architectures,3L2 values),6CatBoost source-proxy recipes. Source-only6-20 targets remain unchanged and separate. Native model inputs add only the computed proxy, not four redundant raw fields. Actually unavailable measured pairs propagate natural NaNs; no artificially hidden inputs, invented pairs, interpolation or dropped native cases. All model imputation/scaling uses fitting people only. Original487/179 exact Borg cohorts, seed42, no validation early stopping, no synthetic rows, source refitting, source-reserved selection or native test tuning."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen compact-source study changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for candidate in plan()[6:]:
        for number,(fit,val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist():
                    raise ValueError("Frozen compact-source fold changed")
            else:
                jobs.append((candidate,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            for future in as_completed([pool.submit(compute_fold,job) for job in jobs]):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
                print(f"Compact CADENCE native fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete",flush=True)
    previous = json.loads((parent.DIRECTORY/"selection.json").read_text())
    for candidate in plan():
        if any(row["candidate"] == candidate for row in report["results"]):
            continue
        if candidate["algorithm"] == "previous_real_control":
            old = next(row for row in previous["results"] if row["candidate"]["id"] == candidate["parent_candidate_id"])
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
        winner = max(report["results"],key=lambda row:row["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"],best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Compact CADENCE recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
