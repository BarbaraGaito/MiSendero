"""Fixed-rate CatBoost schedules on unchanged actual native Borg histories.

Fit one 2700-tree trajectory per rate and person fold, then read four fixed
prefixes. Historical 300/900-tree predictions must be reproduced exactly.
"""
from __future__ import annotations

import copy
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_furukawa_hr_transfer as parent
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = parent.DIRECTORY.parent/"catboost-schedule-80-v1"
DOCS = parent.DOCS
PROPOSAL = DOCS/"catboost-schedule-plan.json"
PARENT_AUDIT = DOCS/"furukawa-hr-transfer-verification.json"
BASELINE_DIRECTORY = DIRECTORY.parent/"catboost-80-v1"
BASELINE_CODE = Path(__file__).with_name("fatigue_catboost.py")
RATES = (.01,.03,.09)
PREFIXES = (300,900,1800,2700)
MAX_TREES = max(PREFIXES)
FEATURES = (
    "prior_borg","prior_age_minutes","prior2_borg","prior2_age_minutes",
    "prior_borg_slope","prior_in_current_task","prior_count_current_task",
    "elapsed_minutes","cumulative_active_minutes","task_order",
    "task_feedback_first","task_feedback_total_rise","task_feedback_count",
    "task_feedback_rate_mean","task_feedback_rate_median",
    "task_feedback_since_last_increase","task_feedback_zero_fraction",
    "task_feedback_linear_extrapolation","task_feedback_delta_1",
    "task_feedback_interval_1","task_feedback_delta_2","task_feedback_interval_2",
    "all_feedback_rate_mean","all_feedback_positive_fraction",
    "completed_task_rise_mean","completed_task_rate_mean",
    "previous_task_at_similar_elapsed_mean","previous_task_at_similar_elapsed_last",
    "current_terrain")
_RUNTIME = None


def plan():
    result = [{"id":f"catboost-schedule-{i:03d}","algorithm":"previous_real_control",
        "parent_candidate_id":f"furukawa-hr-{i:03d}"} for i in range(4)]
    for rate in RATES:
        for count in PREFIXES:
            historical = ("catboost-021" if count == 300 else "catboost-023") if rate == .03 and count in (300,900) else None
            result.append({"id":f"catboost-schedule-{len(result):03d}",
                "algorithm":"native_catboost_fixed_rate_prefix","features":list(FEATURES),
                "learning_rate":rate,"iterations":count,"depth":3,"l2_leaf_reg":30.,
                "target_mode":"change_from_prior","random_seed":42,
                "matched_historical_candidate_id":historical})
    return result


def parameters(candidate,iterations=None):
    if candidate not in plan()[4:]:
        raise ValueError("Only a predeclared actual-native CatBoost schedule is permitted")
    count = candidate["iterations"] if iterations is None else iterations
    if count not in PREFIXES:
        raise ValueError("The tree count is outside the fixed schedule")
    return {"iterations":count,"depth":3,"l2_leaf_reg":30.,
        "learning_rate":candidate["learning_rate"],"loss_function":"MultiClass",
        "boosting_type":"Ordered","grow_policy":"SymmetricTree","random_seed":42,
        "thread_count":4,"task_type":"CPU","border_count":128,"bootstrap_type":"Bayesian",
        "bagging_temperature":1.,"random_strength":1.,"nan_mode":"Min",
        "use_best_model":False,"allow_writing_files":False,"verbose":False}


def load_inputs():
    inputs = parent.load_inputs()
    path = parent.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    if (selection["status"] != "complete" or len(selection["results"]) != 14
        or any(selection.get(k) != v for k,v in parent.fingerprint(inputs).items())
        or proof["verification"] != "passed" or proof["selection_sha256"] != digest(path)
        or proof["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_furukawa_hr_transfer.py"))
        or not proof["original_native_rows_and_targets_preserved"]
        or proof["actual_source_function_refits"] != 4 or proof["actual_native_refits"] != 30):
        raise ValueError("The preceding original-public-data comparison is not independently complete")
    original_path = BASELINE_DIRECTORY/"selection.json"
    original = json.loads(original_path.read_text())
    if (original["status"] != "complete" or original["code_sha256"] != digest(BASELINE_CODE)
        or original["train_row_keys"] != inputs["train"].row_key.tolist()):
        raise ValueError("The frozen original CatBoost code or participant cases changed")
    baseline = {key:next(r for r in original["results"] if r["candidate"]["id"] == key)
        for key in ("catboost-021","catboost-023")}
    for key,row in baseline.items():
        c = row["candidate"]
        if (c["features"] != list(FEATURES) or c["depth"] != 3 or c["l2_leaf_reg"] != 30.
            or c["learning_rate"] != .03 or c["random_seed"] != 42
            or c["target_mode"] != "change_from_prior"
            or c["iterations"] != (300 if key == "catboost-021" else 900)):
            raise ValueError("The exact native historical control recipe changed")
    train,test = inputs["train"],inputs["test"]
    if ((len(inputs["frame"]),len(train),len(test)) != (666,487,179)
        or train.group_key.nunique() != 28 or test.group_key.nunique() != 12
        or set(train.group_key)&set(test.group_key)
        or any(name not in train for name in FEATURES)):
        raise ValueError("Original native cases or historical inputs changed")
    declaration = json.loads(PROPOSAL.read_text())
    if declaration["implementation_code_sha256"] != digest(Path(__file__)) or declaration["plan"] != plan():
        raise ValueError("The CatBoost schedule differs from its pre-fitting declaration")
    return {**inputs,"previous_inputs":inputs,"previous":selection,"previous_audit":proof,
        "baseline_rows":baseline}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"previous_signature":parent.fingerprint(inputs["previous_inputs"]),
        "previous_selection_sha256":digest(parent.DIRECTORY/"selection.json"),
        "previous_verification_sha256":digest(PARENT_AUDIT),
        "original_catboost_code_sha256":digest(BASELINE_CODE),
        "original_catboost_selection_sha256":digest(BASELINE_DIRECTORY/"selection.json"),
        "original_history_features":list(FEATURES),"native_schedule_parameters":[parameters(c) for c in plan()[4:]],
        "plan_sha256":digest(PROPOSAL),"public_real_data_policy_sha256":digest(DOCS/"public-real-data-policy.json"),
        "worker_processes":2,"maximum_native_trajectory_trees":MAX_TREES}


class ScheduledCatBoostBorg:
    def __init__(self,candidate):
        self.candidate = copy.deepcopy(candidate)
        self.input_features = list(FEATURES)

    def fit(self,frame,observer=None):
        validate_calibration(frame)
        c = self.candidate
        params = parameters(c)
        current = frame.label.str.removeprefix("Borg ").to_numpy(int)
        previous = frame.prior_borg.to_numpy(int)
        if np.any((current<0)|(current>10)) or not frame.label.eq([f"Borg {v}" for v in current]).all():
            raise ValueError("Unchanged original exact integer Borg outcomes are required")
        x,target = frame[self.input_features],current-previous
        self.model = CatBoostClassifier(**params)
        if observer is not None:
            observer(x.copy(),target.copy(),copy.deepcopy(params))
        self.model.fit(x,target,cat_features=["current_terrain"])
        if self.model.get_params() != params or self.model.tree_count_ != c["iterations"]:
            raise ValueError("Actual CatBoost fitting parameters or fixed tree count changed")
        self.optimizer_summary = {"actual_native_fit_rows":len(frame),
            "actual_native_fit_people":frame.group_key.nunique(),"actual_native_delta_targets":len(target),
            "actual_fit_parameters":self.model.get_params(),"actual_tree_count":self.model.tree_count_,
            "source_outcomes_fitted":0,"synthetic_rows":0,"artificial_history_views":0,
            "validation_or_test_eval_set_supplied":False,"early_stopping":False,
            "native_target_mode":"original_integer_change_from_genuine_prior"}
        return self

    def predict_prefix(self,frame,iterations):
        validate_calibration(frame)
        if iterations not in PREFIXES or iterations > self.model.tree_count_:
            raise ValueError("Only a fitted predeclared fixed tree prefix may be read")
        delta = np.asarray(self.model.predict(frame[self.input_features],ntree_start=0,ntree_end=iterations)).reshape(-1).astype(int)
        values = np.clip(delta+frame.prior_borg.to_numpy(int),0,10)
        return np.asarray([f"Borg {value}" for value in values])

    def predict(self,frame,ntree_end=None):
        return self.predict_prefix(frame,self.candidate["iterations"] if ntree_end is None else ntree_end)


def rate_key(rate):
    if rate not in RATES:
        raise ValueError("Unknown fixed native learning rate")
    return f"lr-{rate:.2f}"


def trajectory_path(rate,number):
    return DIRECTORY/"trajectories"/f"{rate_key(rate)}-fold-{number}.json"


def initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def read_trajectory(inputs,rate,number,fit,val):
    path = trajectory_path(rate,number)
    saved = json.loads(path.read_text())
    train = inputs["train"]
    c = next(c for c in plan()[4:] if c["learning_rate"] == rate and c["iterations"] == MAX_TREES)
    if (saved["signature"] != fingerprint(inputs) or saved["candidate"] != c
        or saved["fold_number"] != number or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist()
        or saved["validation_row_keys"] != train.iloc[val].row_key.tolist()
        or saved["actual_fit_parameters"] != parameters(c)
        or set(saved["prefix_predictions"]) != {str(n) for n in PREFIXES}):
        raise ValueError("A frozen native tree trajectory changed its plan or fitting cases")
    for kind,suffix in (("joblib",".joblib"),("native",".cbm")):
        if saved["artifact_sha256"][kind] != digest(path.with_suffix(suffix)):
            raise ValueError("A frozen native CatBoost trajectory artifact changed")
    model = joblib.load(path.with_suffix(".joblib"))
    if (model.candidate != c or model.input_features != list(FEATURES)
        or model.model.get_params() != parameters(c) or model.model.tree_count_ != MAX_TREES
        or model.optimizer_summary != saved["optimizer_summary"]):
        raise ValueError("Reloaded native CatBoost trajectory metadata changed")
    if (saved["optimizer_summary"]["actual_native_fit_rows"] != len(fit)
        or saved["optimizer_summary"]["actual_native_fit_people"] != train.iloc[fit].group_key.nunique()
        or saved["optimizer_summary"]["actual_native_delta_targets"] != len(fit)
        or saved["optimizer_summary"]["source_outcomes_fitted"] != 0):
        raise ValueError("Saved trajectory native fitting coverage changed")
    runtime = train.iloc[val][model.input_features]
    for count in PREFIXES:
        actual = model.predict_prefix(runtime,count)
        np.testing.assert_array_equal(actual,saved["prefix_predictions"][str(count)])
        if rate == .03 and count in (300,900):
            key = "catboost-021" if count == 300 else "catboost-023"
            expected = np.asarray(inputs["baseline_rows"][key]["oof_predictions"])[val]
            np.testing.assert_array_equal(actual,expected)
    expected_controls = {str(n):"catboost-021" if n == 300 else "catboost-023" for n in (300,900)} if rate == .03 else {}
    if saved["matched_original_prefix_controls"] != expected_controls:
        raise ValueError("Exact original native prefix reproduction evidence changed")
    return saved


def fit_fold(job):
    rate,number,fit,val = job
    inputs,signature = _RUNTIME
    train = inputs["train"]
    fitting,validation = train.iloc[fit],train.iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Native CatBoost trajectory leaked validation people")
    candidate = next(c for c in plan()[4:] if c["learning_rate"] == rate and c["iterations"] == MAX_TREES)
    model = ScheduledCatBoostBorg(candidate).fit(fitting)
    runtime = validation[model.input_features]
    predicted = {str(n):model.predict_prefix(runtime,n).tolist() for n in PREFIXES}
    controls = {}
    if rate == .03:
        for n,key in ((300,"catboost-021"),(900,"catboost-023")):
            expected = np.asarray(inputs["baseline_rows"][key]["oof_predictions"])[val]
            np.testing.assert_array_equal(predicted[str(n)],expected)
            controls[str(n)] = key
    path = trajectory_path(rate,number)
    joblib.dump(model,path.with_suffix(".joblib"))
    model.model.save_model(str(path.with_suffix(".cbm")),format="cbm")
    saved = {"signature":signature,"candidate":candidate,"fold_number":number,
        "fit_row_keys":fitting.row_key.tolist(),"validation_row_keys":validation.row_key.tolist(),
        "actual_fit_parameters":model.model.get_params(),"optimizer_summary":model.optimizer_summary,
        "prefix_predictions":predicted,"matched_original_prefix_controls":controls,
        "artifact_sha256":{"joblib":digest(path.with_suffix(".joblib")),"native":digest(path.with_suffix(".cbm"))}}
    path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    read_trajectory(inputs,rate,number,fit,val)
    print(f"Actual native CatBoost trajectory:{rate_key(rate)} fold{number+1}/5,2700trees,four fixed prefixes",flush=True)
    return rate,number


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload,encoding="utf-8")
    path.write_text(payload,encoding="utf-8")


def select():
    inputs = load_inputs()
    signature = fingerprint(inputs)
    train = inputs["train"]
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY/"trajectories").mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":487,"test_denominator":179,
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,
        "minimum_cv_for_new_test_evaluation":.65,"new_unique_native_schedules":10,
        "inherited_controls":4,"fresh_matched_historical_schedules":2,"planned_native_trajectory_fits":15,
        "fixed_prefixes":list(PREFIXES),"fixed_learning_rates":list(RATES),
        "synthetic_training_rows":0,"source_targets_fitted":0,"new_native_borg_targets":0,
        "policy":"Fixed16recipes:4inherited actual-public controls and12CatBoost schedules with original29history variables,depth3,L2=30,Ordered MultiClass,seed42,and all other historical parameters unchanged. Three fixed learning rates.01/.03/.09cross300/900/1800/2700trees.15maximum2700-tree native trajectories across5unchanged person folds yield predeclared prefix predictions with no eval_set,early stopping or adaptive scheduler. Original.03prefixes300/900must reproduce historicalcatboost-021/023OOFexactly in all5folds before acceptance. Computation uses only original actual487native fitting cases; source outcomes remain outside this search. Natural missing features preserved; no synthetic examples,extra target rows,source label conversions or current/future predictors. Original179native test opened only for a frozen unique CVwinner above.65."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("The frozen native CatBoost schedule comparison changed")
        report = old
    else:
        (DIRECTORY/"selection-source.py").write_bytes(Path(__file__).read_bytes())
        save(report)
    if report["status"] == "complete":
        return report
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for rate in RATES:
        for number,(fit,val) in enumerate(folds):
            if trajectory_path(rate,number).exists():
                read_trajectory(inputs,rate,number,fit,val)
            else:
                jobs.append((rate,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=initialize) as pool:
            for future in as_completed([pool.submit(fit_fold,job) for job in jobs]):
                future.result()
    trajectories = {(rate,number):read_trajectory(inputs,rate,number,fit,val)
        for rate in RATES for number,(fit,val) in enumerate(folds)}
    for candidate in plan():
        if any(row["candidate"] == candidate for row in report["results"]):
            continue
        details = []
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            predicted = np.asarray(old["oof_predictions"])
        else:
            predicted = np.empty(len(train),dtype=object)
            for number,(fit,val) in enumerate(folds):
                saved = trajectories[(candidate["learning_rate"],number)]
                values = saved["prefix_predictions"][str(candidate["iterations"])]
                predicted[val] = values
                trajectory = trajectory_path(candidate["learning_rate"],number)
                details.append({"trajectory_file":trajectory.relative_to(DIRECTORY).as_posix(),
                    "trajectory_sha256":digest(trajectory),"fold_number":number,
                    "fit_row_keys":saved["fit_row_keys"],"validation_row_keys":saved["validation_row_keys"],
                    "prefix_tree_count":candidate["iterations"],"predicted":values,
                    "optimizer_summary":saved["optimizer_summary"]})
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report["results"].append({"candidate":candidate,"accuracy_mean":float(np.mean(scores)),"fold_accuracy":scores,
            "pooled_oof_accuracy":float(accuracy_score(train.label,predicted)),"oof_predictions":predicted.tolist(),"folds":details})
        winner = max(report["results"],key=lambda r:r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"],best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Actual native CatBoost schedule:{candidate['id']} CV={np.mean(scores):.6f}",flush=True)
    report.update(status="complete",actual_native_trajectory_fits=15,matched_original_prefix_controls_verified=10)
    save(report)
    return report


if __name__ == "__main__":
    import fatigue_catboost_schedule as implementation
    implementation.select()
