"""Compare genuine pre-first-task baselines using frozen source functions."""
from __future__ import annotations

import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_cadence_association as parent
import fatigue_session_rest_inputs as rest
from fatigue_catboost import CatBoostBorg
from fatigue_dynamics_experiment import DynamicsClassifier
from public_sources import ROOT, digest

DIRECTORY = rest.DIRECTORY.parent/"cadence-session-rest-transfer-80-v1"
PARENT_AUDIT = ROOT/"docs/fatigue-80-2026-10-25/cadence-association-verification.json"
INPUT_AUDIT = ROOT/"docs/fatigue-80-2026-10-25/session-rest-input-verification.json"
BASELINES = {"session_mean":"session_rest_mean_hr_bpm","session_lowest":"session_rest_lowest_minute_hr_bpm"}
REST = {name:"cadence_session_rest_"+column for name,column in BASELINES.items()}
MODES = {"core":"current_state","cat":"current_and_change"}
STATE = "cadence_session_rest_computed_source_state6to20"
CHANGE = "cadence_session_rest_computed_source_state_difference"
_RUNTIME = None


def plan():
    controls = ("cadence-assoc-000","cadence-assoc-001","cadence-assoc-004","cadence-assoc-005","cadence-assoc-022","cadence-assoc-029")
    result = [{"id":f"cadence-rest-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":name}
              for i,name in enumerate(controls)]
    for baseline in BASELINES:
        for member in MODES:
            result.append({"id":f"cadence-rest-{len(result):03d}","algorithm":"session_rest_measured_control",
                           "baseline":baseline,"member":member})
    for baseline in BASELINES:
        for algorithm in ("ridge","svr","random_forest"):
            for features in parent.SETS:
                for member,mode in MODES.items():
                    result.append({"id":f"cadence-rest-{len(result):03d}","algorithm":"session_rest_source_representation",
                        "baseline":baseline,"source_algorithm":algorithm,"source_feature_set":features,"member":member,"representation":mode})
    return result


def enrich(frame,cache):
    matched = cache.set_index("row_key").loc[frame.row_key]
    if not np.array_equal(matched.group_key.to_numpy(),frame.group_key.to_numpy()):
        raise ValueError("Session-rest inputs belong to different actual people/cases")
    data = frame.copy()
    for name,column in REST.items():
        if column in data:
            raise ValueError("New session-rest inputs collide with frozen native features")
        data[column] = matched[BASELINES[name]].to_numpy()
    return data


def load_inputs():
    previous = parent.load_inputs()
    audit = json.loads(PARENT_AUDIT.read_text())
    if (audit["selection_sha256"] != digest(parent.DIRECTORY/"selection.json")
        or audit["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_cadence_association.py"))
        or audit["actual_source_target_calls_observed"] != 6 or not audit["all_original_native_rows_and_labels_preserved"]
        or not audit["native_query_inputs_past_only_by_independent_raw_window_audit"]):
        raise ValueError("Independent source-association/native comparison changed")
    for member,mode in MODES.items():
        if audit["best_source_by_member"][member]["candidate"]["representation"] != mode:
            raise ValueError("Fixed per-member representation was not selected by the preceding audited native CV")
    cache,manifest = rest.load()
    proof = json.loads(INPUT_AUDIT.read_text())
    if (proof["verification"] != "passed" or proof["audit_code_sha256"] != digest(Path(__file__).with_name("audit_session_rest_inputs.py"))
        or proof["raw_csv_reader_code_sha256"] != digest(Path(__file__).with_name("audit_cadence_association_inputs.py"))
        or proof["input_provenance_sha256"] != digest(rest.DIRECTORY/"provenance.json")
        or not proof["all_used_minutes_completed_before_first_task_and_query"]
        or proof["original_native_cases_independently_verified"] != 666 or proof["natural_missing_baselines_per_feature"] != 30):
        raise ValueError("Independent pre-first-task native baseline proof changed")
    return {"frame":enrich(previous["frame"],cache),"train":enrich(previous["train"],cache),"test":enrich(previous["test"],cache),
        "specifications":previous["specifications"],"rest_manifest":manifest,"previous":previous}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"parent_signature":parent.fingerprint(inputs["previous"]),
        "parent_selection_sha256":digest(parent.DIRECTORY/"selection.json"),"parent_verification_sha256":digest(PARENT_AUDIT),
        "session_rest_provenance_sha256":digest(rest.DIRECTORY/"provenance.json"),"input_verification_sha256":digest(INPUT_AUDIT),
        "public_real_data_policy_sha256":digest(ROOT/"docs/fatigue-80-2026-10-25/public-real-data-policy.json"),"worker_processes":2}


def read_sources(inputs):
    return parent.read_sources(parent.fingerprint(inputs["previous"]))


def source_query(frame,candidate,role):
    hr = frame[parent.NATIVE[role+"_hr_bpm"]]
    baseline = frame[REST[candidate["baseline"]]]
    if candidate["source_feature_set"] == "absolute":
        return pd.DataFrame({"hr_bpm":hr,"baseline_hr_bpm":baseline},index=frame.index)
    return pd.DataFrame({"hr_delta_baseline":hr-baseline,"hr_ratio_baseline":hr/baseline},index=frame.index)


def source_state(frame,candidate,teacher,role):
    query = source_query(frame,candidate,role)
    measured = np.isfinite(query.to_numpy(float)).all(axis=1)
    values = np.full(len(frame),np.nan)
    if measured.any():
        with threadpool_limits(limits=1):
            values[measured] = teacher.predict(query.loc[measured])
        if not np.isfinite(values[measured]).all():
            raise ValueError("Measured session-rest source-state computation is nonfinite")
    return values


class SessionRestBorg:
    def __init__(self,candidate,teacher=None):
        self.candidate,self.teacher = candidate,teacher

    def add_features(self,frame):
        data = frame.copy()
        if self.teacher is not None:
            current = source_state(frame,self.candidate,self.teacher,"current")
            data[STATE] = current
            if self.candidate["representation"] == "current_and_change":
                data[CHANGE] = current-source_state(frame,self.candidate,self.teacher,"prior")
        return data

    def fit(self,frame,specifications):
        c = self.candidate
        specification = copy.deepcopy(specifications[c["member"]])
        if c["member"] == "core":
            specification["params"] = {**specification["params"],"max_iter":5000,"max_fun":100000,"tol":.0001}
        required = [parent.NATIVE["current_hr_bpm"],REST[c["baseline"]]]
        if c["algorithm"] == "session_rest_measured_control":
            if self.teacher is not None:
                raise ValueError("Measured session-rest control cannot contain a source function")
            required = [parent.NATIVE["current_hr_bpm"],parent.NATIVE["prior_hr_bpm"],REST[c["baseline"]]]
            self.model_features = specification["features"]+required
        elif c["algorithm"] == "session_rest_source_representation":
            if self.teacher is None or c["representation"] != MODES[c["member"]]:
                raise ValueError("Source representation or its predeclared per-member mode changed")
            self.model_features = specification["features"]+[STATE]
            if c["representation"] == "current_and_change":
                required += [parent.NATIVE["prior_hr_bpm"]]
                self.model_features += [CHANGE]
        else:
            raise ValueError("Unknown predeclared session-rest recipe")
        self.input_features = list(dict.fromkeys(specification["features"]+required))
        data = self.add_features(frame)
        recipe = {**specification,"id":c["id"],"features":self.model_features}
        classifier = DynamicsClassifier if c["member"] == "core" else CatBoostBorg
        with warnings.catch_warnings(record=True) as captured,threadpool_limits(limits=1):
            warnings.simplefilter("always",ConvergenceWarning)
            self.model = classifier(recipe).fit(data)
        self.optimizer_summary = {"convergence_warnings":[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)],
            "actual_native_fit_rows":len(frame),"actual_auxiliary_source_targets":976 if self.teacher is not None else 0,
            "source_fitting_performed_here":False,"model_feature_count":len(self.model_features),
            "actual_session_baseline_missing_rows":int(frame[REST[c["baseline"]]].isna().sum()),
            "natural_missing_representation_rows":{name:int(data[name].isna().sum()) for name in (STATE,CHANGE) if name in self.model_features},
            "synthetic_rows":0,"artificial_history_views":0}
        if c["member"] == "core":
            estimator = self.model.model[-1]
            self.optimizer_summary.update(iterations=int(estimator.n_iter_),fitting_loss=float(estimator.loss_),maximum_iterations=int(estimator.max_iter))
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
        raise ValueError("Session-rest fitting leaked held native people")
    teacher = None if candidate["algorithm"] == "session_rest_measured_control" else heads[candidate["source_algorithm"],candidate["source_feature_set"]]
    model = SessionRestBorg(candidate,teacher).fit(fitting,inputs["specifications"])
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
        "actual_source_fitting_targets":976,"source_reserved_targets_not_fitted":238,"source_functions_refitted":False,
        "new_native_borg_targets":0,"synthetic_training_rows":0,
        "policy":"Fixed34recipes:6 inherited controls,4 actual current/prior/session-baseline controls and24 representations(2actual session baselines,3frozen source regressors,2source feature sets,2native classifiers). Native modes fixed from audited preceding native CV:core=current state,Cat=current state plus past-state difference. Source976 original6-20 targets/124 people remain a retrospective association task,238 source targets/32 people reserved. Source functions never refit here. Native session mean/lowest actual minute use only the5min window ending before the first task and original session start bound; native posture is not assumed seated. All666 original cases and487/179 exact targets retained,30 naturally missing baselines propagated. Original native columns unchanged, no synthetic data, masks, generated labels, invented clocks, case filtering or native test tuning."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen session-rest transfer plan changed")
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
                    raise ValueError("Frozen session-rest native fold changed")
            else:
                jobs.append((candidate,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            for future in as_completed([pool.submit(compute_fold,job) for job in jobs]):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
                print(f"Session-rest native fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete",flush=True)
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
        print(f"Session-rest recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
