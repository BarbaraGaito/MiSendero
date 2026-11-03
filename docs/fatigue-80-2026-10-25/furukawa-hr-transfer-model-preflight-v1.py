"""Strictly pre-report public runner HR functions as separate source features."""
from __future__ import annotations

import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

import fatigue_furukawa_hr_inputs as source
import fatigue_resistance_history_joint as parent
from fatigue_catboost import CatBoostBorg
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = parent.DIRECTORY.parent/"furukawa-pre-report-hr-transfer-80-v1"
DOCS = parent.DOCS
INPUT_AUDIT = DOCS/"furukawa-pre-report-hr-input-verification.json"
PARENT_AUDIT = DOCS/"resistance-history-joint-verification.json"
PROPOSAL = DOCS/"furukawa-hr-transfer-plan.json"
CURRENT = "cadence_association_current_hr_bpm"
PRIOR = "cadence_association_prior_hr_bpm"
DIFFERENCE = "furukawa_measured_hr_current_minus_prior"
STATE = "furukawa_computed_current_source_points"
CHANGE = "furukawa_computed_source_point_change"
DELTA = CHANGE
SOURCE_FEATURES = {"state":["current_hr_bpm"],"delta":["current_hr_bpm","prior_hr_bpm","hr_change_bpm"]}
_RUNTIME = None


def representation_features(task):
    return [STATE,CHANGE] if task == "state" else [DELTA]


def plan():
    result = [{"id":f"furukawa-hr-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":f"resistance-joint-{i:03d}"} for i in range(4)]
    for member in ("core","cat"):
        result.append({"id":f"furukawa-hr-{len(result):03d}","algorithm":"native_measured_hr_control","member":member})
    for algorithm in ("ridge","svr"):
        for task in SOURCE_FEATURES:
            for member in ("core","cat"):
                result.append({"id":f"furukawa-hr-{len(result):03d}","algorithm":"furukawa_source_function",
                    "source_algorithm":algorithm,"source_task":task,"member":member})
    return result


def enrich(frame):
    output = frame.copy()
    a,b = frame[CURRENT].to_numpy(float),frame[PRIOR].to_numpy(float)
    output[DIFFERENCE] = np.where(np.isfinite(a)&np.isfinite(b),a-b,np.nan)
    return output


def load_inputs():
    old = parent.load_inputs()
    selection_path = parent.DIRECTORY/"selection.json"
    selection,proof = json.loads(selection_path.read_text()),json.loads(PARENT_AUDIT.read_text())
    if (selection["status"] != "complete" or len(selection["results"]) != 22
        or any(selection.get(k) != v for k,v in parent.fingerprint(old).items())
        or proof["selection_sha256"] != digest(selection_path)
        or proof["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_resistance_history_joint.py"))
        or not proof["original_native_rows_and_targets_preserved"] or proof["actual_native_joint_refits"] != 30):
        raise ValueError("The preceding actual-source/native comparison is not independently complete")
    runners,manifest = source.load()
    audit = json.loads(INPUT_AUDIT.read_text())
    if (audit["verification"] != "passed" or audit["audit_code_sha256"] != digest(Path(__file__).with_name("audit_furukawa_hr_inputs.py"))
        or audit["source_preparation_code_sha256"] != digest(Path(source.__file__))
        or audit["source_provenance_sha256"] != digest(source.DIRECTORY/"provenance.json")
        or not audit["all_sensor_timestamps_strictly_before_current_rpe"]
        or audit["source_target_conversion_or_pooling"] or audit["synthetic_rows"] != 0):
        raise ValueError("The independent original runner pre-report HR input audit changed")
    fitting,reserved = runners[runners.source_partition.eq("fitting")].copy(),runners[runners.source_partition.eq("reserved")].copy()
    if ((len(fitting),fitting.group_key.nunique(),len(reserved),reserved.group_key.nunique()) != (252,12,84,4)
        or set(fitting.group_key)&set(reserved.group_key) or set(runners.group_key)&set(old["frame"].group_key)
        or not {CURRENT,PRIOR}<=set(old["frame"])):
        raise ValueError("Original native HR cases or new whole-source-person reservations changed")
    declaration = json.loads(PROPOSAL.read_text())
    if declaration["implementation_code_sha256"] != digest(Path(__file__)) or declaration["plan"] != plan():
        raise ValueError("The source-task comparison differs from its frozen declaration")
    return {**old,"frame":enrich(old["frame"]),"train":enrich(old["train"]),"test":enrich(old["test"]),
        "runner_fitting":fitting,"runner_reserved":reserved,"runner_manifest":manifest,
        "previous":selection,"previous_audit":proof,"previous_inputs":old}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"previous_signature":parent.fingerprint(inputs["previous_inputs"]),
        "previous_selection_sha256":digest(parent.DIRECTORY/"selection.json"),"previous_verification_sha256":digest(PARENT_AUDIT),
        "source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),"source_input_verification_sha256":digest(INPUT_AUDIT),
        "source_dataset_sha256":inputs["runner_manifest"]["dataset_sha256"],"plan_sha256":digest(PROPOSAL),
        "native_measured_hr_columns":[CURRENT,PRIOR],"native_specifications":inputs["specifications"],
        "source_preparation_code_sha256":digest(Path(source.__file__)),
        "public_real_data_policy_sha256":digest(DOCS/"public-real-data-policy.json"),"worker_processes":2}


def source_rows(frame,task):
    if len(frame) != 252 or frame.group_key.nunique() != 12 or not frame.source_partition.eq("fitting").all():
        raise ValueError("Only the252actual runner fitting responses may supervise source functions")
    data = frame.copy() if task == "state" else frame[frame.prior_rpe_points.notna()].copy()
    if len(data) != (252 if task == "state" else 168):
        raise ValueError("Original source current/adjacent-pair case counts changed")
    data["current_hr_bpm"] = data.hr_recent_60s_mean
    data["prior_hr_bpm"] = data.prior_report_hr_recent_mean
    data["hr_change_bpm"] = data.current_hr_bpm-data.prior_hr_bpm
    return data


def fit_source(frame,algorithm,task,observer=None):
    data = source_rows(frame,task)
    target = data.original_rpe_points.to_numpy(float)
    if task == "delta":
        target = target-data.prior_rpe_points.to_numpy(float)
    weight = 1./data.groupby("group_key").group_key.transform("size").to_numpy()
    weight *= len(data)/weight.sum()
    estimator = Ridge(alpha=10.) if algorithm == "ridge" else SVR(C=10.,gamma="scale",epsilon=.1)
    model = make_pipeline(SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),StandardScaler(),estimator)
    x = data[SOURCE_FEATURES[task]]
    if not np.isfinite(x.to_numpy(float)).all() or not np.isfinite(target).all():
        raise ValueError("Source functions require the audited measured HR and original continuous targets")
    if observer is not None:
        observer(x.copy(),target.copy(),weight.copy())
    with threadpool_limits(limits=1):
        model.fit(x,target,**{model.steps[-1][0]+"__sample_weight":weight})
    return model


def make_source_query(frame,task,role="current"):
    if task == "state":
        return pd.DataFrame({"current_hr_bpm":frame[CURRENT if role == "current" else PRIOR]},index=frame.index)
    return pd.DataFrame({"current_hr_bpm":frame[CURRENT],"prior_hr_bpm":frame[PRIOR],
        "hr_change_bpm":frame[CURRENT]-frame[PRIOR]},index=frame.index)


def score(frame,teacher,task,role="current"):
    query = make_source_query(frame,task,role)
    measured = np.isfinite(query.to_numpy(float)).all(axis=1)
    values = np.full(len(frame),np.nan)
    if measured.any():
        with threadpool_limits(limits=1):
            values[measured] = teacher.predict(query.loc[measured])
        if not np.isfinite(values[measured]).all():
            raise ValueError("A measured computed source-scale score is not finite")
    return values


class RunnerHRBorg:
    def __init__(self,candidate,teacher=None):
        self.candidate,self.teacher = candidate,teacher

    def add_features(self,frame):
        data = enrich(frame)
        if self.teacher is not None:
            task = self.candidate["source_task"]
            current = score(frame,self.teacher,task)
            if task == "state":
                data[STATE] = current
                data[CHANGE] = current-score(frame,self.teacher,task,"prior")
            else:
                data[DELTA] = current
        return data

    def fit(self,frame,specifications):
        validate_calibration(frame)
        c = self.candidate
        specification = copy.deepcopy(specifications[c["member"]])
        if c["member"] == "core":
            specification["params"].update(max_iter=5000,max_fun=100000,tol=.0001)
        if c["algorithm"] == "native_measured_hr_control":
            if self.teacher is not None:
                raise ValueError("Measured control must not contain a source model")
            added = [CURRENT,PRIOR,DIFFERENCE]
        elif c["algorithm"] == "furukawa_source_function":
            if self.teacher is None:
                raise ValueError("Actual-source representation requires its frozen teacher")
            added = representation_features(c["source_task"])
        else:
            raise ValueError("Unknown predeclared original-source/native recipe")
        self.input_features = list(dict.fromkeys(specification["features"]+[CURRENT,PRIOR]))
        self.model_features = list(dict.fromkeys(specification["features"]+added))
        recipe = {**specification,"id":c["id"],"features":self.model_features}
        before = joblib.hash(self.teacher)
        kind = DynamicsClassifier if c["member"] == "core" else CatBoostBorg
        with warnings.catch_warnings(record=True) as captured,threadpool_limits(limits=1):
            warnings.simplefilter("always",ConvergenceWarning)
            self.model = kind(recipe).fit(self.add_features(frame))
        if joblib.hash(self.teacher) != before:
            raise ValueError("Native fitting changed its fixed original-source teacher")
        self.optimizer_summary = {"actual_native_fit_rows":len(frame),"actual_native_fit_people":frame.group_key.nunique(),
            "actual_source_fitting_targets":0 if self.teacher is None else (252 if c["source_task"] == "state" else 168),
            "source_reserved_targets_not_fitted":84,"source_outcomes_pooled":False,
            "source_teacher_frozen":True,"synthetic_rows":0,"artificial_history_views":0,
            "convergence_warnings":[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)]}
        return self

    def predict(self,frame):
        return self.model.predict(self.add_features(frame))


def read_sources(inputs):
    signature = fingerprint(inputs)
    result = {}
    for algorithm in ("ridge","svr"):
        for task in SOURCE_FEATURES:
            key = algorithm+"-"+task
            path = DIRECTORY/"teachers"/(key+".joblib")
            meta = json.loads(path.with_suffix(".json").read_text())
            if meta["signature"] != signature or meta["source_algorithm"] != algorithm or meta["source_task"] != task or meta["model_sha256"] != digest(path):
                raise ValueError("Frozen original-source teacher changed")
            result[key] = joblib.load(path)
    return result


def initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs),read_sources(inputs)


def fit_fold(job):
    candidate,number,fit,val = job
    inputs,signature,teachers = _RUNTIME
    fitting,validation = inputs["train"].iloc[fit],inputs["train"].iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Original native outer-fold people overlap")
    teacher = teachers[candidate["source_algorithm"]+"-"+candidate["source_task"]] if candidate["algorithm"] == "furukawa_source_function" else None
    model = RunnerHRBorg(candidate,teacher).fit(fitting,inputs["specifications"])
    saved = {"signature":signature,"candidate":candidate,"fold_number":number,"fit_row_keys":fitting.row_key.tolist(),
        "validation_row_keys":validation.row_key.tolist(),"predicted":model.predict(validation[model.input_features]).tolist(),
        "optimizer_summary":model.optimizer_summary}
    path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
    path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"Actual pre-report runner native fold:{candidate['id']} {number+1}/5",flush=True)
    return candidate["id"],number


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload,encoding="utf-8")
    path.write_text(payload,encoding="utf-8")


def select():
    inputs = load_inputs()
    signature = fingerprint(inputs)
    train,test = inputs["train"],inputs["test"]
    DIRECTORY.mkdir(exist_ok=True)
    for folder in ("teachers","folds"):
        (DIRECTORY/folder).mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":487,"test_denominator":179,
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "actual_source_fitting_responses":252,"actual_source_fitting_adjacent_pairs":168,"source_fitting_people":12,
        "reserved_source_responses_not_fitted":84,"source_reserved_people":4,"new_native_borg_targets":0,
        "synthetic_training_rows":0,"source_targets_pooled_across_instruments":False,
        "policy":"Fixed14recipes:4inherited real controls,2measured HRcontrols and8Ridge/SVR state/delta source functions paired with native MLP/Cat. Source state252actual original-point targets or168observed within-condition deltas,with12fitting people and84responses/4otherpeople reserved. Source input HRmeans strictly before each actualreport; no first-running-minute reference interpreted asrest,no scaleconversion or interval dependence assumed. Native current/priorHRare original completed1minreadings; source means5/6observed10secpoints,differences in windows/support preserved. Native classifier alone learns its unchanged487original exactdelta targets with5personfolds. Computed source point states/differences remain features rather than new labels. Actual missing nativeHRpropagates; no generated examples,guessed times/source-person mapping or changed native179testcases."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen actual runner source comparison changed")
        report = old
    else:
        (DIRECTORY/"selection-source.py").write_bytes(Path(__file__).read_bytes())
        save(report)
    if report["status"] == "complete":
        return report
    for algorithm in ("ridge","svr"):
        for task in SOURCE_FEATURES:
            key = algorithm+"-"+task
            source_path = DIRECTORY/"teachers"/(key+".joblib")
            if source_path.with_suffix(".json").exists():
                continue
            teacher = fit_source(inputs["runner_fitting"],algorithm,task)
            joblib.dump(teacher,source_path)
            metadata = {"signature":signature,"source_algorithm":algorithm,"source_task":task,"model_sha256":digest(source_path),
                "actual_fitting_targets":252 if task == "state" else 168,"source_fitting_people":12,"reserved_source_responses_not_fitted":84}
            source_path.with_suffix(".json").write_text(json.dumps(metadata,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    read_sources(inputs)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for c in plan()[4:]:
        for number,(fit,val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["signature"] != signature or saved["candidate"] != c or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist():
                    raise ValueError("Frozen runner native fold changed")
            else:
                jobs.append((c,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
            for future in as_completed([pool.submit(fit_fold,job) for job in jobs]):
                future.result()
    for candidate in plan():
        if any(row["candidate"] == candidate for row in report["results"]):
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
        print(f"Actual pre-report runner recipe:{candidate['id']} CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    import fatigue_furukawa_hr_transfer as implementation
    implementation.select()
