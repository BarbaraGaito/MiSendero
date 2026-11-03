"""Matched 249/302 actual public report-pair teacher comparison."""
from __future__ import annotations

import importlib.metadata
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_source_transitions as parent
import fatigue_worker_survey_priors as source
import fatigue_runner_real_observations as native
from public_sources import digest

DIRECTORY = parent.baseline.RESEARCH/"survey-prior-teachers-80-v1"
_RUNTIME = None


def plan():
    result = [{"id":f"survey-teacher-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":f"transition-{i:03d}"} for i in range(10)]
    for algorithm in ("ridge","svr","random_forest"):
        for member in ("core","cat"):
            old = next(c for c in parent.plan() if c.get("algorithm")==algorithm and c.get("member")==member)
            result.append({"id":f"survey-teacher-{len(result):03d}","algorithm":"expanded_actual_source_pairs",
                "teacher_algorithm":algorithm,"member":member,"matching_previous_candidate_id":old["id"]})
    return result


def load_inputs():
    frame, train, test, members, _, _, _, _, _ = native.load_inputs()
    expanded, provenance = source.load()
    previous_path = parent.DIRECTORY/"selection.json"
    previous = json.loads(previous_path.read_text())
    old_data, old_provenance = parent.load_sources()
    if (previous["status"] != "complete" or previous["plan"] != parent.plan()
            or previous["train_row_keys"] != train.row_key.tolist() or previous["test_used_for_selection"]
            or len(expanded) != 302 or len(old_data) != 249 or not expanded.row_key.is_unique
            or not set(old_data.row_key) <= set(expanded.row_key)):
        raise ValueError("The frozen real-source expansion or matched original participant CV changed")
    for name in ("worker","sts"):
        part = expanded[expanded.source_domain.eq(name)]
        split = provenance["external_splits"][name]
        if set(part.row_key) & set(split["test_row_keys"]) or set(part.group_key) & set(split["test_groups"]):
            raise ValueError("An external reserved source person/report entered fitting")
    return frame, train, test, members, expanded, provenance, previous, old_provenance


def fingerprint(inputs):
    members, provenance = inputs[3], inputs[5]
    return {"code_sha256":digest(Path(__file__)),"native_members":members,
        "public_real_data_policy_sha256":digest(native.POLICY),
        "source_dataset_sha256":provenance["dataset_sha256"],"source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),
        "previous_selection_sha256":digest(parent.DIRECTORY/"selection.json"),
        "dependency_code_sha256":{name:digest(Path(__file__).with_name(name)) for name in
            ("fatigue_source_transitions.py","fatigue_worker_survey_priors.py","fatigue_runner_real_observations.py",
             "fatigue_catboost.py","fatigue_dynamics_experiment.py","fatigue_probability.py","fatigue_warm_sgd.py")},
        "software_versions":{name:importlib.metadata.version(name) for name in ("numpy","pandas","scipy","scikit-learn","catboost","joblib")},"worker_processes":2}


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload,encoding="utf-8")
    path.write_text(payload,encoding="utf-8")


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    signature = fingerprint(inputs)
    teachers = {}
    for algorithm in ("ridge","svr","random_forest"):
        path = DIRECTORY/"teachers"/(algorithm+".joblib")
        metadata = json.loads(path.with_suffix(".json").read_text())
        if metadata["signature"] != signature or metadata["algorithm"] != algorithm or metadata["model_sha256"] != digest(path):
            raise ValueError("Expanded actual-source teacher changed")
        teachers[algorithm] = joblib.load(path)
    _RUNTIME = inputs, signature, teachers


def compute_fold(job):
    candidate, number, fit, val = job
    inputs, signature, teachers = _RUNTIME
    train, specifications = inputs[1], inputs[3]["member_specifications"]
    fitting, validation = train.iloc[fit], train.iloc[val]
    if set(fitting.group_key) & set(validation.group_key):
        raise ValueError("Expanded source study leaked native validation people")
    model = parent.TransitionBorg(candidate,teachers[candidate["teacher_algorithm"]]).fit(fitting,specifications)
    return {"signature":signature,"candidate":candidate,"fold_number":number,"fit_row_keys":fitting.row_key.tolist(),
        "validation_row_keys":validation.row_key.tolist(),"predicted":model.predict(validation).tolist()}


def select():
    inputs = load_inputs()
    _, train, test, _, expanded, provenance, previous, _ = inputs
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("teachers","folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "expanded_real_source_targets":302,"matching_previous_source_targets":249,"new_native_borg_targets":0,
        "synthetic_training_rows":0,"assumed_zero_priors":0,"invented_source_report_ages":0,
        "source_preparation_used_for_fitting_in_this_study":True,
        "policy":"Only original observed public Borg pairs. Ten previous real-data controls are preserved; six new recipes change only source pair eligibility from 249 to 302 using actual earlier survey cells. Source preprocessing/fitting sees no native labels. Native fitting uses only original participant-disjoint real reports; no artificial history views, generated examples, target rescaling, source clock invention or altered test denominator."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen survey-prior teacher study changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    for algorithm in ("ridge","svr","random_forest"):
        path = DIRECTORY/"teachers"/(algorithm+".joblib")
        if path.with_suffix(".json").exists():
            saved = json.loads(path.with_suffix(".json").read_text())
            if saved["signature"] != signature or saved["algorithm"] != algorithm or saved["model_sha256"] != digest(path):
                raise ValueError("Saved actual-survey-prior source model changed")
        else:
            teachers = parent.fit_teachers(expanded,algorithm)
            joblib.dump(teachers,path)
            metadata = {"signature":signature,"algorithm":algorithm,"model_sha256":digest(path),"actual_source_targets":len(expanded),
                "source_target_counts":provenance["counts"],"native_targets_used_for_teacher_fitting":0}
            path.with_suffix(".json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
        print(f"Actual survey-prior source models ready: {algorithm}, 302 observed targets",flush=True)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = []
    for c in report["plan"]:
        if c["algorithm"] == "previous_real_control":
            continue
        for number,(fit,val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if (saved["signature"] != signature or saved["candidate"] != c or saved["fold_number"] != number
                        or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist() or saved["validation_row_keys"] != train.iloc[val].row_key.tolist()):
                    raise ValueError("Expanded actual-source fold membership changed")
            else:
                jobs.append((c,number,fit,val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            futures = [pool.submit(compute_fold,job) for job in jobs]
            for future in as_completed(futures):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved,indent=2)+"\n",encoding="utf-8")
                print(f"Real survey-prior native fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete",flush=True)
    for c in report["plan"]:
        if any(r["candidate"] == c for r in report["results"]):
            continue
        if c["algorithm"] == "previous_real_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            predicted, details = np.asarray(old["oof_predictions"]), []
        else:
            predicted, details = np.empty(len(train),dtype=object), []
            for number,(_,val) in enumerate(folds):
                saved = json.loads((DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json").read_text())
                predicted[val] = saved["predicted"]
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report["results"].append({"candidate":c,"accuracy_mean":float(np.mean(scores)),"fold_accuracy":scores,
            "pooled_oof_accuracy":float(accuracy_score(train.label,predicted)),"oof_predictions":predicted.tolist(),"folds":details})
        winner = max(report["results"],key=lambda r:r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"],best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Actual survey-prior recipe {len(report['results'])}/16 {c['id']}: CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
