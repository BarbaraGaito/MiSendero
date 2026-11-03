"""Source-only physiology representations from actual CADENCE Borg6-20.

Source outcomes never become native0-10 labels. Only earlier measured HR and
baseline summaries enter the source functions; original native cases retained.
"""
from __future__ import annotations

import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

import cadence_lagged_rpe as source
import fatigue_cadence_native_inputs as physiology
import fatigue_real_mlp_hyperparameters as parent
from public_sources import ROOT, digest

DIRECTORY = source.DIRECTORY.parent/"cadence-physiology-transfer-80-v1"
INPUT_AUDIT = ROOT/"docs/fatigue-80-2026-10-25/cadence-lagged-input-verification.json"
SETS = {"absolute":["lag_hr_bpm","baseline_hr_bpm"],"relative":["hr_delta_baseline","hr_ratio_baseline"]}
NATIVE = {name:"cadence_input_"+name for name in source.FEATURES}
OUTPUT = "cadence_predicted_source_rpe6to20"
_RUNTIME = None


def plan():
    result = [{"id":f"cadence-transfer-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":f"real-mlp-hp-{i:03d}"} for i in range(2)]
    for member in ("core","cat"):
        result.append({"id":f"cadence-transfer-{len(result):03d}","algorithm":"measured_physiology_control","member":member})
    for algorithm in ("ridge","svr","random_forest"):
        for features in SETS:
            for member in ("core","cat"):
                result.append({"id":f"cadence-transfer-{len(result):03d}","algorithm":"separate_source_rpe_transfer",
                    "source_algorithm":algorithm,"source_feature_set":features,"member":member})
    return result


def enrich(frame,cache):
    matched = cache.set_index("row_key").loc[frame.row_key]
    if not np.array_equal(matched.group_key.to_numpy(),frame.group_key.to_numpy()):
        raise ValueError("Native physiology belongs to different actual cases/people")
    result = frame.copy()
    for source_name,target_name in NATIVE.items():
        if target_name in frame:
            raise ValueError("New native physiology names collide with existing predictors")
        result[target_name] = matched[source_name].to_numpy()
    return result


def load_inputs():
    parents = parent.load_inputs()
    frame,train,test,members = parents[0][:4]
    cache,native_manifest = physiology.load()
    fitting,reserved,source_manifest = source.load()
    audit = json.loads(INPUT_AUDIT.read_text())
    if (audit["verification"] != "passed" or audit["audit_code_sha256"] != digest(Path(__file__).with_name("audit_cadence_lagged_inputs.py"))
        or audit["source_provenance_sha256"] != digest(source.DIRECTORY/"provenance.json")
        or audit["native_provenance_sha256"] != digest(physiology.DIRECTORY/"provenance.json")):
        raise ValueError("Independent actual source/native input evidence changed")
    if len(fitting) != 851 or len(reserved) != 206 or set(fitting.group_key)&set(reserved.group_key):
        raise ValueError("Reserved source people entered source fitting")
    if set(fitting.group_key)&(set(train.group_key)|set(test.group_key)):
        raise ValueError("Native/source participant namespaces collide")
    return {"frame":enrich(frame,cache),"train":enrich(train,cache),"test":enrich(test,cache),
        "specifications":members["member_specifications"],"source_fitting":fitting,"source_reserved":reserved,
        "source_provenance":source_manifest,"native_provenance":native_manifest,"parents":parents}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"parent_signature":parent.fingerprint(inputs["parents"]),
        "source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),
        "native_provenance_sha256":digest(physiology.DIRECTORY/"provenance.json"),"input_verification_sha256":digest(INPUT_AUDIT),
        "dependency_code_sha256":{name:digest(Path(__file__).with_name(name)) for name in
            ("cadence_lagged_rpe.py","fatigue_cadence_native_inputs.py")},"worker_processes":2}


def fit_source(frame,algorithm,feature_set,observer=None):
    if len(frame) != 851 or set(frame.source_partition) != {"fitting"} or frame.group_key.nunique() != 123:
        raise ValueError("Only the fixed eligible source-fitting people may supervise this representation")
    features = SETS[feature_set]
    targets = frame.rpe_native.to_numpy(float)
    if not np.isfinite(targets).all() or np.any((targets<6)|(targets>20)):
        raise ValueError("Original source Borg6-20 targets must remain unchanged")
    weights = 1./frame.groupby("group_key")["group_key"].transform("size").to_numpy()
    weights *= len(frame)/weights.sum()
    estimator = {"ridge":lambda:Ridge(alpha=10.),"svr":lambda:SVR(C=10.,gamma="scale",epsilon=.1),
        "random_forest":lambda:RandomForestRegressor(n_estimators=200,max_depth=4,min_samples_leaf=3,random_state=42,n_jobs=1)}[algorithm]()
    model = make_pipeline(SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),StandardScaler(),estimator)
    if observer is not None:
        observer(frame[features].copy(),targets.copy(),weights.copy())
    with threadpool_limits(limits=1):
        model.fit(frame[features],targets,**{model.steps[-1][0]+"__sample_weight":weights})
    return model


def source_query(frame,feature_set):
    return frame[[NATIVE[name] for name in SETS[feature_set]]].rename(columns={value:key for key,value in NATIVE.items()})


def add_features(frame,candidate,teacher):
    data = frame.copy()
    if teacher is not None:
        with threadpool_limits(limits=1):
            predicted = teacher.predict(source_query(frame,candidate["source_feature_set"]))
        if not np.isfinite(predicted).all():
            raise ValueError("Nonfinite source-scale physiology representation")
        data[OUTPUT] = predicted
    return data


class CadenceSourceBorg:
    def __init__(self,candidate,teacher=None):
        self.candidate,self.teacher = candidate,teacher

    def fit(self,frame,specifications):
        c = self.candidate
        specification = copy.deepcopy(specifications[c["member"]])
        if c["member"] == "core":
            specification["params"] = {**specification["params"],"max_iter":5000,"max_fun":100000,"tol":.0001}
        self.input_features = list(dict.fromkeys(specification["features"]+list(NATIVE.values())))
        recipe = {**specification,"id":c["id"],"features":self.input_features+([OUTPUT] if self.teacher is not None else [])}
        data = add_features(frame,c,self.teacher)
        classifier = parent.parent.parent.parent.baseline.DynamicsClassifier if c["member"] == "core" else parent.parent.parent.parent.baseline.CatBoostBorg
        with warnings.catch_warnings(record=True) as captured,threadpool_limits(limits=1):
            warnings.simplefilter("always",ConvergenceWarning)
            self.model = classifier(recipe).fit(data)
        self.optimizer_summary = {"convergence_warnings":[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)],
            "actual_native_fit_rows":len(frame),"actual_auxiliary_source_targets":851 if self.teacher is not None else 0,
            "synthetic_rows":0,"artificial_history_views":0}
        if c["member"] == "core":
            self.optimizer_summary.update(iterations=int(self.model.model[-1].n_iter_),fitting_loss=float(self.model.model[-1].loss_),maximum_iterations=5000)
        return self

    def predict(self,frame):
        return self.model.predict(add_features(frame,self.candidate,self.teacher))


def read_sources(signature):
    models = {}
    for algorithm in ("ridge","svr","random_forest"):
        for feature_set in SETS:
            path = DIRECTORY/"teachers"/f"{algorithm}-{feature_set}.joblib"
            metadata = json.loads(path.with_suffix(".json").read_text())
            if metadata["signature"] != signature or metadata["model_sha256"] != digest(path):
                raise ValueError("Frozen source-only physiology representation changed")
            models[algorithm,feature_set] = joblib.load(path)
    return models


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    signature = fingerprint(inputs)
    _RUNTIME = inputs,signature,read_sources(signature)


def compute_fold(job):
    candidate,number,fit,val = job
    inputs,signature,sources = _RUNTIME
    fitting,validation = inputs["train"].iloc[fit],inputs["train"].iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Native physiology fitting leaked held people")
    teacher = None if candidate["algorithm"] == "measured_physiology_control" else sources[candidate["source_algorithm"],candidate["source_feature_set"]]
    model = CadenceSourceBorg(candidate,teacher).fit(fitting,inputs["specifications"])
    return {"signature":signature,"candidate":candidate,"fold_number":number,"fit_row_keys":fitting.row_key.tolist(),
        "validation_row_keys":validation.row_key.tolist(),"predicted":model.predict(validation).tolist(),"optimizer_summary":model.optimizer_summary}


def save(report):
    path = DIRECTORY/"selection.json"
    text = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(text,encoding="utf-8")
    path.write_text(text,encoding="utf-8")


def select():
    inputs = load_inputs()
    train,test = inputs["train"],inputs["test"]
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("teachers","folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "actual_source_fitting_targets":851,"source_reserved_targets_not_fitted":206,"new_native_borg_targets":0,"synthetic_training_rows":0,
        "source_target_scale":"Original Borg6-20, kept separate from native0-10",
        "policy":"Fixed source-only physiology regressors see123 eligible fitting people, with32 source people reserved. Only completed earlier-bout HR and measured baseline enter source functions; source current-bout physiology, current RPE and person IDs are excluded from predictors. Native functions receive measured prior-report HR and pre-task baseline summaries, preserving their different window/baseline definitions. Source predictions remain computed source-scale features. All native487/179 exact Borg cases and missing values retained; no label conversion, artificial data/history, clock fabrication, native holdout selection or validation stopping. New MLP fits use the user-tested16/8,alpha10 and5000/100000 budgets."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen CADENCE transfer plan changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    for algorithm in ("ridge","svr","random_forest"):
        for feature_set in SETS:
            path = DIRECTORY/"teachers"/f"{algorithm}-{feature_set}.joblib"
            if path.with_suffix(".json").exists():
                saved = json.loads(path.with_suffix(".json").read_text())
                if saved["signature"] != signature or saved["model_sha256"] != digest(path):
                    raise ValueError("Saved CADENCE source model changed")
            else:
                teacher = fit_source(inputs["source_fitting"],algorithm,feature_set)
                with threadpool_limits(limits=1):
                    held_prediction = teacher.predict(inputs["source_reserved"][SETS[feature_set]])
                held_target = inputs["source_reserved"].rpe_native
                metadata = {"signature":signature,"algorithm":algorithm,"feature_set":feature_set,
                    "actual_source_fitting_rows":851,"actual_source_fitting_people":123,"native_labels_used_for_source_fitting":0,
                    "reserved_source_rows":206,"reserved_source_mae":float(mean_absolute_error(held_target,held_prediction)),
                    "reserved_source_r2":float(r2_score(held_target,held_prediction)),"reserved_source_used_for_selection":False}
                joblib.dump(teacher,path)
                path.with_suffix(".json").write_text(json.dumps({**metadata,"model_sha256":digest(path)},indent=2,allow_nan=False)+"\n",encoding="utf-8")
            print(f"CADENCE source model ready:{algorithm}/{feature_set},851 actual targets",flush=True)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for candidate in plan()[2:]:
        for number,(fit,val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist():
                    raise ValueError("Frozen CADENCE native fold changed")
            else:
                jobs.append((candidate,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            futures = [pool.submit(compute_fold,job) for job in jobs]
            for future in as_completed(futures):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
                print(f"CADENCE native fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete",flush=True)
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
        print(f"CADENCE transfer recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
