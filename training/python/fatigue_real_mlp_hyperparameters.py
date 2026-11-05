"""User-requested MLP hyperparameter search on unchanged real public cases.

Compare original13 inputs with the newly audited real walking-source features.
Change capacity, L2 and L-BFGS budgets; preserve targets and participant folds.
"""
from __future__ import annotations

import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_walking_source_teachers as parent
from public_sources import ROOT, digest

DIRECTORY = parent.DIRECTORY.parent/"real-mlp-hyperparameters-80-v1"
PARENT_AUDIT = ROOT/"docs/fatigue-80-2026-10-25/walking-source-teacher-verification.json"
_RUNTIME = None


def plan():
    controls = ("walking-teacher-000", "walking-teacher-001", "walking-teacher-010", "walking-teacher-015")
    result = [{"id":f"real-mlp-hp-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":old}
              for i,old in enumerate(controls)]
    for features in ("original_13", "real_walking_ridge"):
        for shape in ([8], [16,8], [32,16]):
            for alpha in (1.,10.,100.):
                result.append({"id":f"real-mlp-hp-{len(result):03d}","algorithm":"real_report_mlp_hyperparameters",
                    "feature_set":features,"params":{"hidden_layer_sizes":shape,"solver":"lbfgs","activation":"relu",
                        "alpha":alpha,"max_iter":5000,"max_fun":100000,"tol":.0001},
                    "random_seed":42,"early_stopping":False,"target_mode":"change_from_prior"})
    return result


def load_inputs():
    inputs = parent.load_inputs()
    audit = json.loads(PARENT_AUDIT.read_text())
    if audit["selection_sha256"] != digest(parent.DIRECTORY/"selection.json") or audit["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_walking_source_teachers.py")):
        raise ValueError("The independently verified real-source control study changed")
    if not audit["native_labels_and_rows_verified_at_actual_fitter"] or audit["original_training_cases"] != 487 or audit["original_test_cases"] != 179:
        raise ValueError("Original participant cohorts or actual native fitting evidence changed")
    return inputs


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"parent_signature":parent.fingerprint(inputs),
            "previous_verification_sha256":digest(PARENT_AUDIT),"public_real_data_policy_sha256":digest(parent.parent.native.POLICY),
            "worker_processes":2}


def read_ridge_heads(signature):
    path = parent.DIRECTORY/"teachers/ridge.joblib"
    metadata = json.loads(path.with_suffix(".json").read_text())
    if metadata["signature"] != signature["parent_signature"] or metadata["algorithm"] != "ridge" or metadata["model_sha256"] != digest(path):
        raise ValueError("Frozen real walking source heads changed")
    return joblib.load(path)


class TunedRealBorg:
    def __init__(self,candidate,walking_teachers):
        self.candidate = candidate
        self.walking_teachers = walking_teachers if candidate["feature_set"] == "real_walking_ridge" else {}

    def fit(self,frame,specifications):
        c = self.candidate
        specifications = copy.deepcopy(specifications)
        specifications["core"]["params"] = copy.deepcopy(c["params"])
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always",ConvergenceWarning)
            if c["feature_set"] == "original_13":
                recipe = {**specifications["core"],"id":c["id"]}
                self.model = parent.parent.parent.baseline.DynamicsClassifier(recipe).fit(frame)
                self.input_features = list(recipe["features"])
                estimator = self.model.model[-1]
            else:
                recipe = {"id":c["id"],"member":"core","include_existing_borg_teachers":False}
                self.model = parent.WalkingSourceBorg(recipe,self.walking_teachers,{}).fit(frame,specifications)
                self.input_features = self.model.input_features
                estimator = self.model.model.model[-1]
        if estimator.random_state != 42 or estimator.early_stopping or estimator.solver != "lbfgs":
            raise ValueError("The fixed native fitting protocol changed")
        self.optimizer_summary = {"iterations":int(estimator.n_iter_),"final_fitting_loss":float(estimator.loss_),
            "maximum_iterations":int(estimator.max_iter),"maximum_function_evaluations":int(estimator.max_fun),
            "alpha":float(estimator.alpha),"hidden_layer_sizes":list(estimator.hidden_layer_sizes),
            "convergence_warnings":[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)],
            "actual_native_fit_rows":len(frame),"actual_walking_source_targets":156 if self.walking_teachers else 0,
            "synthetic_rows":0,"artificial_history_views":0}
        return self

    def predict(self,frame):
        return self.model.predict(frame)


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    signature = fingerprint(inputs)
    _RUNTIME = inputs,signature,read_ridge_heads(signature)


def compute_fold(job):
    candidate,number,fit,val = job
    inputs,signature,teachers = _RUNTIME
    train = inputs[0][1]
    fitting,validation = train.iloc[fit],train.iloc[val]
    if set(fitting.group_key) & set(validation.group_key):
        raise ValueError("MLP hyperparameter fitting leaked held-out people")
    model = TunedRealBorg(candidate,teachers).fit(fitting,inputs[0][3]["member_specifications"])
    return {"signature":signature,"candidate":candidate,"fold_number":number,"fit_row_keys":fitting.row_key.tolist(),
            "validation_row_keys":validation.row_key.tolist(),"predicted":model.predict(validation).tolist(),
            "optimizer_summary":model.optimizer_summary}


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload,encoding="utf-8")
    path.write_text(payload,encoding="utf-8")


def select():
    inputs = load_inputs()
    train,test = inputs[0][1:3]
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY/"folds").mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "synthetic_training_rows":0,"new_native_borg_targets":0,
        "policy":"User-requested bounded hyperparameter grid:3 architectures,3L2 values,2real-input feature sets. All new fits use L-BFGS5000 iterations/100000 function evaluations with unchanged tolerance and seed42. No validation-driven early stopping. Imputer/scaler fit original native fitting people only; frozen source heads were fitted solely on156 actual public SPE pairs. No artificial histories, masks, invented labels, source scale conversion, extra native target cases or test selection. Original487/179 exact Borg participant cohorts retained."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen MLP hyperparameter plan changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for candidate in plan()[4:]:
        for number,(fit,val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist():
                    raise ValueError("Frozen hyperparameter fold changed")
            else:
                jobs.append((candidate,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            futures = [pool.submit(compute_fold,job) for job in jobs]
            for future in as_completed(futures):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
                print(f"Real MLP hyperparameters {saved['candidate']['id']} fold{saved['fold_number']+1}/5,iterations={saved['optimizer_summary']['iterations']},warnings={len(saved['optimizer_summary']['convergence_warnings'])}",flush=True)
    previous = json.loads((parent.DIRECTORY/"selection.json").read_text())
    for candidate in plan():
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
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
        print(f"Real MLP hyperparameter recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
