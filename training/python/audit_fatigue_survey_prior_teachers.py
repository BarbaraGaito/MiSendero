"""Verify 302 actual public source pairs and reproduce matched native fits."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

import fatigue_survey_prior_teachers as study
from public_sources import ROOT,digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition,reason):
    if not condition:
        raise ValueError(reason)


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    last_path = folder/"runner-real-verification.json"
    last = json.loads(last_path.read_text())
    require(last["selection_sha256"] == digest(study.native.DIRECTORY/"selection.json")
            and last["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_runner_real_observations.py")),"Previous real-source model evidence changed")
    data_audit_path = folder/"worker-survey-prior-verification.json"
    data_audit = json.loads(data_audit_path.read_text())
    inputs = study.load_inputs()
    _,train,test,members,expanded,provenance,previous,_ = inputs
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(all(selection.get(k) == v for k,v in signature.items()) and selection["status"] == "complete"
            and selection["plan"] == study.plan() and len(selection["results"]) == 16
            and selection["train_row_keys"] == train.row_key.tolist(),"Frozen 302-pair teacher study changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train.group_key) & set(test.group_key) and not selection["test_used_for_selection"]
            and selection["expanded_real_source_targets"] == 302 and selection["matching_previous_source_targets"] == 249
            and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == selection["assumed_zero_priors"] == selection["invented_source_report_ages"] == 0
            and selection["minimum_cv_for_new_test_evaluation"] == .65,"Original task, real-data policy or participant holdout changed")
    require(data_audit["source_dataset_sha256"] == provenance["dataset_sha256"]
            and data_audit["source_provenance_sha256"] == digest(study.source.DIRECTORY/"provenance.json")
            and data_audit["verification_code_sha256"] == digest(Path(__file__).with_name("audit_worker_survey_priors.py")),"Verified actual public survey expansion changed")
    originals,manifests,splits = study.parent.source_inputs()
    original = originals["worker"].set_index("row_key",drop=False)
    survey = pd.read_excel(study.source.SURVEY)
    lineage = {r["row_key"]:r for r in manifests["worker"]["lineage"]}
    baseline_values = []
    for row in expanded[expanded.source_domain.eq("worker")].itertuples():
        record = lineage[row.row_key]
        current = original.loc[row.row_key]
        sheet = survey.iloc[record["questionnaire_worksheet_row"]-2]
        rep = int(re.search(r"\[REP ([1-5])\]",record["questionnaire_column"])[1])
        previous_column = study.source.BASELINE_COLUMN if rep == 1 else f"What is your physical fatigue level currently [REP {rep-1}] ?"
        require(row.borg_native == current.borg_native == sheet[record["questionnaire_column"]]
                and row.prior_borg == sheet[previous_column] and 0 <= row.prior_borg <= 10
                and row.group_key == current.group_key,"An expanded source target or genuine previous survey changed")
        if rep == 1:
            baseline_values.append(row.prior_borg)
    require(len(baseline_values) == 51 and sum(v > 0 for v in baseline_values) == 39,"Real nonzero baseline surveys were replaced")
    old_sources,_ = study.parent.load_sources()
    pd.testing.assert_frame_equal(expanded[expanded.source_domain.eq("sts")].reset_index(drop=True),old_sources[old_sources.source_domain.eq("sts")].reset_index(drop=True))
    require(len(expanded) == 302 and expanded.row_key.is_unique and len(set(expanded.row_key)-set(old_sources.row_key)) == 53,"Source reports were fabricated or duplicated")
    for name in ("worker","sts"):
        part = expanded[expanded.source_domain.eq(name)]
        require(not set(part.row_key) & set(splits[name]["test_row_keys"])
                and not set(part.group_key) & set(splits[name]["test_groups"]),"Reserved external source cases entered fitting")
    teachers,source_fit_counts = {},{}
    for algorithm in ("ridge","svr","random_forest"):
        model_path = study.DIRECTORY/"teachers"/(algorithm+".joblib")
        metadata = json.loads(model_path.with_suffix(".json").read_text())
        require(metadata["signature"] == signature and metadata["model_sha256"] == digest(model_path)
                and metadata["native_targets_used_for_teacher_fitting"] == 0,"Saved source-only teachers changed")
        saved = joblib.load(model_path)
        seen = []
        original_fit = Pipeline.fit
        def actual_source_only(model,x,y,**kwargs):
            domain = ("worker","sts")[len(seen)]
            real = expanded[expanded.source_domain.eq(domain)]
            pd.testing.assert_frame_equal(x,real[study.parent.FEATURES])
            np.testing.assert_array_equal(y,real.borg_native.to_numpy()-real.prior_borg.to_numpy())
            weight = kwargs[model.steps[-1][0]+"__sample_weight"]
            require(len(x) == len(real) and abs(weight.sum()-len(real)) < 1e-9,"Source fitting changed actual report count/weight")
            seen.append({"domain":domain,"actual_reports":len(x)})
            return original_fit(model,x,y,**kwargs)
        with patch.object(Pipeline,"fit",actual_source_only):
            fresh = study.parent.fit_teachers(expanded,algorithm)
        for domain in ("worker","sts"):
            require(list(saved[domain].feature_names_in_) == study.parent.FEATURES,"Source teacher includes unavailable current labels or IDs")
            np.testing.assert_allclose(fresh[domain].predict(train[study.parent.FEATURES]),saved[domain].predict(train[study.parent.FEATURES]),rtol=0,atol=1e-10)
        old_path = study.parent.DIRECTORY/"teachers"/(algorithm+".joblib")
        require(previous["teacher_artifact_sha256"][algorithm] == digest(old_path),"Matched 249-pair source teachers changed")
        np.testing.assert_allclose(fresh["sts"].predict(train[study.parent.FEATURES]),joblib.load(old_path)["sts"].predict(train[study.parent.FEATURES]),rtol=0,atol=1e-9)
        teachers[algorithm],source_fit_counts[algorithm] = fresh,seen
        print(f"Fresh observed-survey source fits verified: {algorithm}, 253 Worker + 49 STS",flush=True)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    for row in selection["results"]:
        c,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(predicted.shape == (487,) and set(predicted) <= {f"Borg {i}" for i in range(11)},"Native label scale or denominator changed")
        scores = [accuracy_score(train.iloc[val].label,predicted[val]) for _,val in folds]
        np.testing.assert_allclose(scores,row["fold_accuracy"],rtol=0,atol=1e-12)
        require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train.label,predicted)-row["pooled_oof_accuracy"]) < 1e-12,"Saved 302-pair native metrics disagree with actual native labels")
        if c["algorithm"] == "previous_real_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,old["oof_predictions"])
            continue
        for number,(fit,val) in enumerate(folds):
            saved = json.loads((study.DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json").read_text())
            require(saved == row["folds"][number] and saved["signature"] == signature and saved["candidate"] == c
                    and saved["fold_number"] == number and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Concurrent source-expansion native fold membership changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"],"Winner differs from original participant CV rule")
    best = max((r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"),key=lambda r:r["accuracy_mean"])
    c = best["candidate"]
    matched = next(r for r in previous["results"] if r["candidate"]["id"] == c["matching_previous_candidate_id"])
    older = study.parent.fit_teachers(old_sources,c["teacher_algorithm"])
    for selected,models,tag in ((best,teachers[c["teacher_algorithm"]],"302"),(matched,older,"249")):
        candidate = selected["candidate"]
        before = joblib.hash(models)
        for number,(fit,val) in enumerate(folds):
            fitting,validation = train.iloc[fit],train.iloc[val]
            require(not set(fitting.group_key) & set(validation.group_key),"Native fitting leaked validation people")
            native_class = study.parent.baseline.DynamicsClassifier if candidate["member"] == "core" else study.parent.baseline.CatBoostBorg
            original_fit = native_class.fit
            def actual_native_only(model,data):
                np.testing.assert_array_equal(data.row_key,fitting.row_key)
                np.testing.assert_array_equal(data.label,fitting.label)
                np.testing.assert_array_equal(data.group_key,fitting.group_key)
                pd.testing.assert_frame_equal(data[study.parent.FEATURES],fitting[study.parent.FEATURES])
                return original_fit(model,data)
            with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial history examples prohibited")),patch.object(native_class,"fit",actual_native_only):
                model = study.parent.TransitionBorg(candidate,models).fit(fitting,members["member_specifications"])
            predicted = model.predict(validation)
            np.testing.assert_array_equal(predicted,np.asarray(selected["oof_predictions"])[val])
            np.testing.assert_array_equal(model.predict(validation[model.input_features]),predicted)
            without_truth = validation.drop(columns=["label","row_key","group_key"])
            np.testing.assert_array_equal(model.predict(without_truth),predicted)
            require(set(vars(model)) == {"candidate","teachers","input_features","model"} and joblib.hash(models) == before,"Native fit changed source weights or stored a query lookup")
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/"actual-survey.joblib"
                joblib.dump(model,output)
                np.testing.assert_array_equal(joblib.load(output).predict(without_truth),predicted)
            print(f"Independent {tag}-pair native refit {candidate['id']}: fold {number+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A survey-prior model crossed its gate: freeze, evaluate and independently verify the full original-179 artifact")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == last["best_verified_test_accuracy"],"Retained original real-report native test model changed")
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "previous_model_verification_sha256":digest(last_path),"source_expansion_verification_sha256":digest(data_audit_path),
        "selection_sha256":digest(path),"public_real_data_policy_sha256":digest(study.native.POLICY),
        "actual_source_pairs_used_for_fitting":302,"additional_existing_targets_with_real_prior":53,
        "nonzero_pre_experiment_priors_preserved":39,"source_fits_verified_against_actual_rows":source_fit_counts,
        "expanded_source_teachers_independently_refitted":6,"all_16_oof_recipes_recomputed":True,"inherited_real_controls_reproduced":10,
        "best_new_302_pair_candidate_id":c["id"],"best_new_302_pair_cv_accuracy":best["accuracy_mean"],
        "matched_previous_249_pair_candidate_id":matched["candidate"]["id"],"matched_previous_249_pair_cv_accuracy":matched["accuracy_mean"],
        "matched_cv_difference":best["accuracy_mean"]-matched["accuracy_mean"],"matched_native_recipes_independently_refitted":2,"grouped_folds_per_refit":5,
        "original_native_fitting_reports_and_labels_checked":True,"artificial_history_fitting_disabled_during_native_refits":True,
        "winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],"new_test_gate_passed":False,
        "original_training_cases":487,"original_test_cases":179,"best_verified_test_correct":incumbent["correct"],
        "best_verified_test_accuracy":incumbent["accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Actual public source responses and original native participant holdout only. The earlier data-preparation receipt describes its historical unfitted state; this study fits the verified 302-pair source table. No synthetic observations or source ages, source label conversion, native target additions or test tuning."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
