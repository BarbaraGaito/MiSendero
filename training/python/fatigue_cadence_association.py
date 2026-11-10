"""Retrospective source physiology representations for causal native queries."""
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

import cadence_association_inputs as prepared
import fatigue_cadence_compact as parent
from fatigue_catboost import CatBoostBorg
from fatigue_dynamics_experiment import DynamicsClassifier
from public_sources import ROOT, digest

DIRECTORY = prepared.SOURCE_DIRECTORY.parent/"cadence-association-transfer-80-v1"
INPUT_AUDIT = ROOT/"docs/fatigue-80-2026-10-25/cadence-association-input-verification.json"
PARENT_AUDIT = ROOT/"docs/fatigue-80-2026-10-25/cadence-compact-verification.json"
SETS = {"absolute":["hr_bpm","baseline_hr_bpm"],"relative":["hr_delta_baseline","hr_ratio_baseline"]}
NATIVE = {name:"cadence_association_"+name for name in prepared.NATIVE_FEATURES}
STATE = "cadence_association_computed_source_state6to20"
CHANGE = "cadence_association_computed_source_state_difference"
_RUNTIME = None


def plan():
    controls = ("cadence-compact-000","cadence-compact-001","cadence-compact-012","cadence-compact-029")
    result = [{"id":f"cadence-assoc-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":name}
              for i,name in enumerate(controls)]
    for member in ("core","cat"):
        result.append({"id":f"cadence-assoc-{len(result):03d}","algorithm":"native_measured_physiology_control","member":member})
    for algorithm in ("ridge","svr","random_forest"):
        for feature_set in SETS:
            for mode in ("current_state","current_and_change"):
                for member in ("core","cat"):
                    result.append({"id":f"cadence-assoc-{len(result):03d}","algorithm":"retrospective_source_association",
                        "source_algorithm":algorithm,"source_feature_set":feature_set,"representation":mode,"member":member})
    return result


def enrich(frame,cache):
    matched = cache.set_index("row_key").loc[frame.row_key]
    if not np.array_equal(matched.group_key.to_numpy(),frame.group_key.to_numpy()):
        raise ValueError("Native physiological inputs belong to other people/cases")
    result = frame.copy()
    for name,column in NATIVE.items():
        if column in result:
            raise ValueError("Association input names collide with frozen native features")
        result[column] = matched[name].to_numpy()
    return result


def load_inputs():
    previous = parent.load_inputs()
    audit = json.loads(PARENT_AUDIT.read_text())
    if (audit["selection_sha256"] != digest(parent.DIRECTORY/"selection.json")
        or audit["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_cadence_compact.py"))
        or not audit["all_original_native_rows_and_labels_preserved"] or not audit["native_delta_targets_verified_at_actual_estimator"]):
        raise ValueError("Audited preceding native comparison changed")
    fitting,reserved,cache,manifests = prepared.load()
    inputs = json.loads(INPUT_AUDIT.read_text())
    if (inputs["verification"] != "passed" or inputs["audit_code_sha256"] != digest(Path(__file__).with_name("audit_cadence_association_inputs.py"))
        or inputs["source_provenance_sha256"] != digest(prepared.SOURCE_DIRECTORY/"provenance.json")
        or inputs["native_provenance_sha256"] != digest(prepared.NATIVE_DIRECTORY/"provenance.json")
        or not inputs["native_pulse_at_query_completed_by_query"] or not inputs["source_task_is_retrospective_association"]
        or inputs["source_strict_pretarget_hr_forecasting_claim_approved"]):
        raise ValueError("Independent source-task/native-clock verification changed")
    if len(fitting) != 976 or len(reserved) != 238 or set(fitting.group_key)&set(reserved.group_key):
        raise ValueError("Whole-person source reservation changed")
    return {"frame":enrich(previous["frame"],cache),"train":enrich(previous["train"],cache),"test":enrich(previous["test"],cache),
        "specifications":previous["specifications"],"source_fitting":fitting,"source_reserved":reserved,
        "association_manifests":manifests,"previous":previous}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"parent_signature":parent.fingerprint(inputs["previous"]),
        "parent_selection_sha256":digest(parent.DIRECTORY/"selection.json"),"parent_verification_sha256":digest(PARENT_AUDIT),
        "source_provenance_sha256":digest(prepared.SOURCE_DIRECTORY/"provenance.json"),
        "native_provenance_sha256":digest(prepared.NATIVE_DIRECTORY/"provenance.json"),"input_verification_sha256":digest(INPUT_AUDIT),
        "public_real_data_policy_sha256":digest(ROOT/"docs/fatigue-80-2026-10-25/public-real-data-policy.json"),"worker_processes":2}


def fit_source(frame,algorithm,feature_set,observer=None):
    if len(frame) != 976 or frame.group_key.nunique() != 124 or set(frame.source_partition) != {"fitting"}:
        raise ValueError("Only actual fixed source-fitting976 targets/124 people may supervise source association")
    target = frame.rpe_native.to_numpy(float)
    if not np.isfinite(target).all() or np.any((target<6)|(target>20)):
        raise ValueError("Original source Borg6-20 must remain unchanged")
    features = SETS[feature_set]
    weight = 1./frame.groupby("group_key")["group_key"].transform("size").to_numpy()
    weight *= len(frame)/weight.sum()
    regressor = {"ridge":lambda:Ridge(alpha=10.),"svr":lambda:SVR(C=10.,gamma="scale",epsilon=.1),
        "random_forest":lambda:RandomForestRegressor(n_estimators=200,max_depth=4,min_samples_leaf=3,random_state=42,n_jobs=1)}[algorithm]()
    model = make_pipeline(SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),StandardScaler(),regressor)
    if observer is not None:
        observer(frame[features].copy(),target.copy(),weight.copy())
    with threadpool_limits(limits=1):
        model.fit(frame[features],target,**{model.steps[-1][0]+"__sample_weight":weight})
    return model


def query_mapping(feature_set,role):
    return {"hr_bpm":NATIVE[role+"_hr_bpm"],"baseline_hr_bpm":NATIVE["baseline_hr_bpm"]} if feature_set == "absolute" else {
        "hr_delta_baseline":NATIVE[role+"_hr_delta_baseline"],"hr_ratio_baseline":NATIVE[role+"_hr_ratio_baseline"]}


def source_query(frame,feature_set,role):
    mapping = query_mapping(feature_set,role)
    return frame[list(mapping.values())].rename(columns={value:key for key,value in mapping.items()})


def representation(frame,teacher,feature_set,role):
    query = source_query(frame,feature_set,role)
    measured = np.isfinite(query.to_numpy(float)).all(axis=1)
    values = np.full(len(frame),np.nan)
    if measured.any():
        with threadpool_limits(limits=1):
            values[measured] = teacher.predict(query.loc[measured])
        if not np.isfinite(values[measured]).all():
            raise ValueError("A measured source-scale representation is nonfinite")
    return values


class AssociationBorg:
    def __init__(self,candidate,teacher=None):
        self.candidate,self.teacher = candidate,teacher

    def add_features(self,frame):
        data = frame.copy()
        if self.teacher is not None:
            c = self.candidate
            current = representation(frame,self.teacher,c["source_feature_set"],"current")
            data[STATE] = current
            if c["representation"] == "current_and_change":
                prior = representation(frame,self.teacher,c["source_feature_set"],"prior")
                data[CHANGE] = current-prior
        return data

    def fit(self,frame,specifications):
        c = self.candidate
        specification = copy.deepcopy(specifications[c["member"]])
        if c["member"] == "core":
            specification["params"] = {**specification["params"],"max_iter":5000,"max_fun":100000,"tol":.0001}
        if c["algorithm"] == "native_measured_physiology_control":
            if self.teacher is not None:
                raise ValueError("Measured control cannot receive a source function")
            required = [NATIVE[name] for name in ("current_hr_bpm","prior_hr_bpm","baseline_hr_bpm")]
            self.model_features = specification["features"]+required
        elif c["algorithm"] == "retrospective_source_association":
            if self.teacher is None:
                raise ValueError("Source representation requires its independently fitted source function")
            required = list(query_mapping(c["source_feature_set"],"current").values())
            self.model_features = specification["features"]+[STATE]
            if c["representation"] == "current_and_change":
                required += list(query_mapping(c["source_feature_set"],"prior").values())
                self.model_features += [CHANGE]
        else:
            raise ValueError("Unknown predeclared source/native recipe")
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
            "natural_missing_representation_rows":{name:int(data[name].isna().sum()) for name in (STATE,CHANGE) if name in self.model_features},
            "synthetic_rows":0,"artificial_history_views":0}
        if c["member"] == "core":
            estimator = self.model.model[-1]
            self.optimizer_summary.update(iterations=int(estimator.n_iter_),fitting_loss=float(estimator.loss_),maximum_iterations=int(estimator.max_iter))
        return self

    def predict(self,frame):
        return self.model.predict(self.add_features(frame))


def read_sources(signature):
    result = {}
    for algorithm in ("ridge","svr","random_forest"):
        for feature_set in SETS:
            path = DIRECTORY/"teachers"/f"{algorithm}-{feature_set}.joblib"
            metadata = json.loads(path.with_suffix(".json").read_text())
            if metadata["signature"] != signature or metadata["model_sha256"] != digest(path):
                raise ValueError("Frozen source-association function changed")
            result[algorithm,feature_set] = joblib.load(path)
    return result


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    signature = fingerprint(inputs)
    _RUNTIME = inputs,signature,read_sources(signature)


def compute_fold(job):
    candidate,number,fit,val = job
    inputs,signature,heads = _RUNTIME
    fitting,validation = inputs["train"].iloc[fit],inputs["train"].iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Source/native association leaked validation people")
    teacher = None if candidate["algorithm"] == "native_measured_physiology_control" else heads[candidate["source_algorithm"],candidate["source_feature_set"]]
    model = AssociationBorg(candidate,teacher).fit(fitting,inputs["specifications"])
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
    for name in ("teachers","folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "actual_source_fitting_targets":976,"source_reserved_targets_not_fitted":238,"new_native_borg_targets":0,"synthetic_training_rows":0,
        "source_task":"Retrospective concurrent source HR/RPE association; not source pre-RPE forecasting",
        "policy":"Fixed30recipes:4 inherited controls,2 actual-current/prior/baseline controls and24 source representations(3regressors,2feature sets,2current/change modes,2native classifiers). Source functions fit only976 actual6-20 responses/124 source people;238 responses/32 source people reserved and not used for selection. Native queries use only actually completed pre-query/current-task HR, pre-prior-report HR and pre-task baseline. Computed source states/differences are not labels or new observations. Natural missing inputs propagate without interpolation, artificial masks or removed cases. Original487/179 exact native Borg, seed42,MLP16/8alpha10budget5000/100000 and fixedCatBoost900depth3L230 retained. No synthetic data, target conversion, invented source clocks, native test tuning or source refitting on native labels."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen source-association plan changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    for algorithm in ("ridge","svr","random_forest"):
        for feature_set in SETS:
            path = DIRECTORY/"teachers"/f"{algorithm}-{feature_set}.joblib"
            if path.with_suffix(".json").exists():
                metadata = json.loads(path.with_suffix(".json").read_text())
                if metadata["signature"] != signature or metadata["model_sha256"] != digest(path):
                    raise ValueError("Saved association source function changed")
            else:
                model = fit_source(inputs["source_fitting"],algorithm,feature_set)
                with threadpool_limits(limits=1):
                    predicted = model.predict(inputs["source_reserved"][SETS[feature_set]])
                metadata = {"signature":signature,"algorithm":algorithm,"feature_set":feature_set,
                    "actual_source_fitting_rows":976,"actual_source_fitting_people":124,"native_labels_used_for_source_fitting":0,
                    "reserved_source_rows":238,"reserved_source_mae":float(mean_absolute_error(inputs["source_reserved"].rpe_native,predicted)),
                    "reserved_source_r2":float(r2_score(inputs["source_reserved"].rpe_native,predicted)),"reserved_source_used_for_selection":False,
                    "task":"Retrospective concurrent source association; no source pre-RPE forecasting claim"}
                joblib.dump(model,path)
                path.with_suffix(".json").write_text(json.dumps({**metadata,"model_sha256":digest(path)},indent=2,allow_nan=False)+"\n",encoding="utf-8")
            print(f"Retrospective source function ready:{algorithm}/{feature_set},976 actual6-20 targets",flush=True)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for candidate in plan()[4:]:
        for number,(fit,val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist():
                    raise ValueError("Frozen native association fold changed")
            else:
                jobs.append((candidate,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            for future in as_completed([pool.submit(compute_fold,job) for job in jobs]):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
                print(f"Native association fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete",flush=True)
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
        print(f"Association recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
