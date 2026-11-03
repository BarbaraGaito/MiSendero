"""Compare new real CR10 histories through separate immutable source functions."""
from __future__ import annotations

import copy
import importlib.metadata
import json
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

import fatigue_catboost as native
import fatigue_emap_history_inputs as source
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_warm_sgd import core_candidate
from public_sources import digest

DIRECTORY = source.DIRECTORY.parent/"emap-ordered-history-transfer-80-v1"
PREVIOUS = DIRECTORY.parent/"cadence-session-rest-transfer-80-v1/selection.json"
PARENT_AUDIT = source.DOCS/"cadence-session-rest-verification.json"
INPUT_AUDIT = source.DOCS/"emap-history-input-verification.json"
ALGORITHMS = ("ridge","svr","random_forest")
OUTPUTS = {domain:"emap_history_separate_"+domain+"_computed_change" for domain in source.FEATURES}
_RUNTIME = None


def plan():
    result = [{"id":f"emap-history-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":f"cadence-rest-{old:03d}"}
        for i,old in enumerate((0,1,26,33))]
    for algorithm in ALGORITHMS:
        for include_existing in (False,True):
            for member in ("core","cat"):
                result.append({"id":f"emap-history-{len(result):03d}","algorithm":"separate_actual_history_heads",
                    "source_algorithm":algorithm,"include_worker_sts":include_existing,"member":member,
                    "source_history_only":True,"source_targets_pooled":False})
    return result


def load_inputs():
    frame,train,test,manifest,_ = native.load_inputs()
    cat = json.loads((native.DIRECTORY/"selection.json").read_text())
    cat_winner = max(cat["results"],key=lambda r:r["accuracy_mean"])
    if cat["status"] != "complete" or cat_winner["candidate"]["id"] != cat["winner_id"] or cat["test_used_for_selection"]:
        raise ValueError("Frozen original real-report native classifier changed")
    if cat["dataset_sha256"] != manifest["dataset_sha256"] or cat["code_sha256"] != digest(Path(native.__file__)):
        raise ValueError("Original real-report native inputs changed")
    specifications = {"core":core_candidate(manifest),"cat":cat_winner["candidate"]}
    previous = json.loads(PREVIOUS.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    if (previous["status"] != "complete" or len(previous["results"]) != 34 or previous["train_row_keys"] != train.row_key.tolist()
        or previous["test_used_for_selection"] or proof["selection_sha256"] != digest(PREVIOUS)
        or proof["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_cadence_session_rest.py"))
        or not proof["all_native_rows_and_labels_preserved"]):
        raise ValueError("Preceding original-native CV or verification changed")
    data,provenance = source.load()
    input_proof = json.loads(INPUT_AUDIT.read_text())
    if (input_proof["verification"] != "passed" or input_proof["audit_code_sha256"] != digest(Path(__file__).with_name("audit_emap_history_inputs.py"))
        or input_proof["source_provenance_sha256"] != digest(source.DIRECTORY/"provenance.json")
        or input_proof["actual_emap_pairs_independently_rebuilt"] != 305
        or input_proof["total_fitting_pairs_across_separate_tasks"] != 550):
        raise ValueError("Independent actual CR10 history-input audit changed")
    if (len(frame),len(train),len(test)) != (666,487,179) or set(frame.group_key)&set(data.group_key) or set(train.group_key)&set(test.group_key):
        raise ValueError("Original public cases or source/native namespaces changed")
    return {"frame":frame,"train":train,"test":test,"manifest":manifest,"specifications":specifications,
        "source":data,"source_manifest":provenance,"previous":previous}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),
        "source_dataset_sha256":inputs["source_manifest"]["dataset_sha256"],"source_input_verification_sha256":digest(INPUT_AUDIT),
        "previous_selection_sha256":digest(PREVIOUS),"previous_verification_sha256":digest(PARENT_AUDIT),
        "native_dataset_sha256":inputs["manifest"]["dataset_sha256"],"native_specifications":inputs["specifications"],
        "native_catboost_selection_sha256":digest(native.DIRECTORY/"selection.json"),
        "public_real_data_policy_sha256":digest(source.DOCS/"public-real-data-policy.json"),
        "dependency_code_sha256":{name:digest(Path(__file__).with_name(name)) for name in (
            "fatigue_emap_history_inputs.py","fatigue_catboost.py","fatigue_dynamics_experiment.py","fatigue_warm_sgd.py","fatigue_probability.py")},
        "software_versions":{name:importlib.metadata.version(name) for name in ("numpy","pandas","scipy","scikit-learn","catboost","joblib")},
        "worker_processes":2}


def estimator(algorithm):
    return {"ridge":lambda:Ridge(alpha=10.),"svr":lambda:SVR(C=10.,gamma="scale",epsilon=.1),
        "random_forest":lambda:RandomForestRegressor(n_estimators=200,max_depth=4,min_samples_leaf=3,random_state=42,n_jobs=1)}[algorithm]()


def fit_sources(data,algorithm,observer=None):
    heads = {}
    for domain,features in source.FEATURES.items():
        part = data[data.source_domain.eq(domain)&data.source_partition.eq("fitting")]
        expected = {"emap":248,"worker":253,"sts":49}[domain]
        if len(part) != expected or part.row_key.duplicated().any():
            raise ValueError("Source fitting included reserved or duplicated actual targets")
        x = part[features]
        current,prior = part[source.TARGET_COLUMNS[domain]].to_numpy(float),part.prior_borg.to_numpy(float)
        if (not np.isfinite(current).all() or not np.isfinite(prior).all()
            or (current<0).any() or (current>10).any() or (prior<0).any() or (prior>10).any()):
            raise ValueError("Only actual finite original CR10 source targets may supervise this task")
        weight = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
        weight *= len(part)/weight.sum()
        model = make_pipeline(SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),StandardScaler(),estimator(algorithm))
        if observer is not None:
            observer(domain,x.copy(),(current-prior).copy(),weight.copy())
        with threadpool_limits(limits=1):
            model.fit(x,current-prior,**{model.steps[-1][0]+"__sample_weight":weight})
        heads[domain] = model
    return heads


def add_features(frame,heads):
    native.validate_calibration(frame)
    output = frame.copy()
    with threadpool_limits(limits=1):
        for domain,head in heads.items():
            values = head.predict(frame[source.FEATURES[domain]])
            if not np.isfinite(values).all():
                raise ValueError("Nonfinite real-source history representation")
            output[OUTPUTS[domain]] = values
    return output


class EmapHistoryBorg:
    def __init__(self,candidate,heads):
        self.candidate = candidate
        expected = set(source.FEATURES) if candidate["include_worker_sts"] else {"emap"}
        if not expected<=set(heads):
            raise ValueError("Missing separate public source function")
        self.heads = {domain:heads[domain] for domain in source.FEATURES if domain in expected}

    def fit(self,frame,specifications):
        c = self.candidate
        recipe = copy.deepcopy(specifications[c["member"]])
        if c["member"] == "core":
            recipe["params"] = {**recipe["params"],"max_iter":5000,"max_fun":100000,"tol":.0001}
        self.input_features = list(recipe["features"])
        if not {"prior_borg","prior2_borg"}<=set(self.input_features):
            raise ValueError("Native model lost its genuine history inputs")
        self.model_features = recipe["features"]+[OUTPUTS[domain] for domain in self.heads]
        recipe.update(id=c["id"],features=self.model_features)
        data = add_features(frame,self.heads)
        classifier = DynamicsClassifier if c["member"] == "core" else native.CatBoostBorg
        with warnings.catch_warnings(record=True) as captured,threadpool_limits(limits=1):
            warnings.simplefilter("always",ConvergenceWarning)
            self.model = classifier(recipe).fit(data)
        self.optimizer_summary = {"actual_native_fit_rows":len(frame),"actual_auxiliary_source_targets":550 if c["include_worker_sts"] else 248,
            "native_feature_count":len(self.model_features),"source_functions_refitted_in_native_fitting":False,
            "native_rows_duplicated":0,"synthetic_rows":0,"artificial_history_views":0,
            "convergence_warnings":[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)]}
        if c["member"] == "core":
            model = self.model.model[-1]
            self.optimizer_summary.update(iterations=int(model.n_iter_),fitting_loss=float(model.loss_),maximum_iterations=int(model.max_iter))
        return self

    def predict(self,frame):
        return self.model.predict(add_features(frame,self.heads))


def read_sources(signature):
    heads = {}
    for algorithm in ALGORITHMS:
        path = DIRECTORY/"teachers"/(algorithm+".joblib")
        saved = json.loads(path.with_suffix(".json").read_text())
        if saved["signature"] != signature or saved["algorithm"] != algorithm or saved["model_sha256"] != digest(path):
            raise ValueError("Frozen ordered-history source functions changed")
        heads[algorithm] = joblib.load(path)
    return heads


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    signature = fingerprint(inputs)
    _RUNTIME = inputs,signature,read_sources(signature)


def compute_fold(job):
    candidate,number,fit,val = job
    inputs,signature,heads = _RUNTIME
    train = inputs["train"]
    fitting,validation = train.iloc[fit],train.iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Original native fitting/validation people overlap")
    model = EmapHistoryBorg(candidate,heads[candidate["source_algorithm"]]).fit(fitting,inputs["specifications"])
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
    train,test,data = inputs["train"],inputs["test"],inputs["source"]
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("teachers","folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "new_emap_actual_fitting_targets":248,"new_emap_reserved_targets_not_fitted":57,"existing_worker_sts_fitting_targets":302,
        "new_native_borg_targets":0,"synthetic_training_rows":0,"source_targets_pooled_across_instruments":False,
        "policy":"Fixed16recipes:4 inherited real controls and12 new recipes(3source estimators,EMAPalone or3separate EMAP/Worker/STS heads,2native classifiers). NewEMAP248actual fitting targets/83people;57targets/19people reserved with original109person split before response eligibility. Source-only fitting and per-person weights, original unscaled current-minus-actual-prior CR10 targets. EMAPuses measured prior/second-prior order only,Worker/STS actual prior only. No pooled source outcomes, inferred clocks/phase equivalence, HRjoin, MICE/formula targets, artificial histories or generated examples. Outputs are computed features, not native observed targets; original native487/179 exact responses and person CV retained."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen ordered-history transfer study changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    held = data[data.source_domain.eq("emap")&data.source_partition.eq("reserved")]
    for algorithm in ALGORITHMS:
        path = DIRECTORY/"teachers"/(algorithm+".joblib")
        if path.with_suffix(".json").exists():
            meta = json.loads(path.with_suffix(".json").read_text())
            if meta["signature"] != signature or meta["model_sha256"] != digest(path):
                raise ValueError("Frozen actual-history source functions changed")
        else:
            heads = fit_sources(data,algorithm)
            joblib.dump(heads,path)
            predicted = held.prior_borg.to_numpy()+heads["emap"].predict(held[source.FEATURES["emap"]])
            meta = {"signature":signature,"algorithm":algorithm,"model_sha256":digest(path),"source_fitting_counts":{"emap":248,"worker":253,"sts":49},
                "emap_reserved_targets_not_fitted":57,"reserved_emap_mae_descriptive_only":float(mean_absolute_error(held.current_rpe,predicted)),
                "reserved_emap_rmse_descriptive_only":float(np.sqrt(mean_squared_error(held.current_rpe,predicted))),
                "source_reserved_scores_used_for_model_selection":False,"native_targets_used_for_source_fitting":0,"synthetic_rows":0}
            path.with_suffix(".json").write_text(json.dumps(meta,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print(f"Separate real-history sources ready:{algorithm};248EMAP+253Worker+49STS actual targets",flush=True)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for candidate in plan()[4:]:
        for number,(fit,val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist():
                    raise ValueError("Frozen ordered-history native fold changed")
            else:
                jobs.append((candidate,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            for future in as_completed([pool.submit(compute_fold,job) for job in jobs]):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
                print(f"Ordered-history native fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete",flush=True)
    for candidate in plan():
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
        print(f"Ordered-history recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
