"""Reproduce nested real-report offsets and prior-conditioned joint learning."""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

import fatigue_prior_joint_transfer as study
from public_sources import ROOT,digest
from validate_fatigue_release import validate as validate_incumbent


def require(condition,reason):
    if not condition:
        raise ValueError(reason)


def validate():
    folder = ROOT/"docs/fatigue-80-2026-10-25"
    previous_path = folder/"survey-prior-teacher-verification.json"
    previous = json.loads(previous_path.read_text())
    require(previous["selection_sha256"] == digest(study.parent.DIRECTORY/"selection.json")
            and previous["verification_code_sha256"] == digest(Path(__file__).with_name("audit_fatigue_survey_prior_teachers.py")),"Previous real-pair model evidence changed")
    inputs = study.load_inputs()
    _,train,test,external,evidence = inputs
    signature = study.fingerprint(inputs)
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    require(all(selection.get(k) == v for k,v in signature.items()) and selection["status"] == "complete"
            and selection["plan"] == study.plan() and len(selection["results"]) == 14
            and selection["train_row_keys"] == train.row_key.tolist(),"Frozen prior-conditioned joint experiment changed")
    require(len(train) == selection["evaluation_denominator"] == 487 and len(test) == selection["test_denominator"] == 179
            and not set(train.group_key) & set(test.group_key) and not selection["test_used_for_selection"]
            and selection["new_native_borg_targets"] == selection["synthetic_training_rows"] == selection["invented_source_report_ages"] == 0
            and selection["minimum_cv_for_new_test_evaluation"] == .65,"Native task, real-data constraint or original holdout changed")
    originals,_,splits = study.parent.parent.source_inputs()
    pairs,provenance = study.parent.source.load()
    require(len(external) == selection["actual_public_source_targets"] == 302
            and study.digest_frame(external) == evidence["source_row_feature_hash"],"Actual source row/context snapshot changed")
    pd.testing.assert_frame_equal(external[pairs.columns],pairs)
    for name in ("worker","sts"):
        rows = external[external.source_domain.eq(name)]
        original = originals[name].set_index("row_key").loc[rows.row_key]
        np.testing.assert_array_equal(rows.elapsed_minutes.to_numpy(),original.elapsed_minutes.to_numpy())
        np.testing.assert_array_equal(rows.borg_native.to_numpy(),original.borg_native.to_numpy())
        require(not set(rows.row_key) & set(splits[name]["test_row_keys"])
                and not set(rows.group_key) & set(splits[name]["test_groups"]),"Reserved source people entered joint fitting")
    require("prior_age_minutes" not in external.columns and provenance["invented_survey_timestamps"] == 0,
            "Unknown Worker survey ages were invented")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    fresh_bases,core_control = [],np.empty(len(train),dtype=object)
    for number,(fit,val) in enumerate(folds):
        fitting,validation = train.iloc[fit],train.iloc[val]
        cache_path = study.DIRECTORY/"bases"/f"fold-{number}.joblib"
        metadata = json.loads(cache_path.with_suffix(".json").read_text())
        require(metadata["signature"] == signature and metadata["cache_sha256"] == digest(cache_path)
                and metadata["fit_row_keys"] == fitting.row_key.tolist()
                and metadata["validation_row_keys"] == validation.row_key.tolist(),"Nested original-report baseline cache changed")
        saved = joblib.load(cache_path)
        groups = fitting.set_index("row_key").group_key.to_dict()
        seen = []
        for inner in metadata["inner_folds"]:
            require(set(inner["fit_row_keys"]) <= set(groups) and set(inner["validation_row_keys"]) <= set(groups)
                    and not {groups[k] for k in inner["fit_row_keys"]} & {groups[k] for k in inner["validation_row_keys"]},"Inner baseline fit leaked held-out native people")
            seen.extend(inner["validation_row_keys"])
        require(sorted(seen) == sorted(fitting.row_key),"Inner offsets did not cover each original fitting report exactly once")
        with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial histories prohibited")):
            fresh = study.prepare_base(fitting,evidence["native_members"]["member_specifications"]["core"])
        require(fresh["inner_folds"] == metadata["inner_folds"] == saved["inner_folds"]
                and fresh["fit_row_keys"] == saved["fit_row_keys"] == fitting.row_key.tolist(),"Fresh nested person memberships disagree")
        np.testing.assert_allclose(fresh["fit_logits"].numpy(),saved["fit_logits"].numpy(),rtol=0,atol=1e-10)
        np.testing.assert_array_equal(fresh["base"].global_predict(validation),saved["base"].global_predict(validation))
        core_control[val] = fresh["base"].global_predict(validation)
        fresh_bases.append(fresh)
        print(f"Independent real-report nested baseline {number+1}/5: three inner fits plus original full fit",flush=True)
    parent = json.loads((study.parent.DIRECTORY/"selection.json").read_text())
    for row in selection["results"]:
        c,predicted = row["candidate"],np.asarray(row["oof_predictions"])
        require(predicted.shape == (487,) and set(predicted) <= {f"Borg {i}" for i in range(11)},"Native labels or original evaluation cases changed")
        scores = [accuracy_score(train.iloc[val].label,predicted[val]) for _,val in folds]
        np.testing.assert_allclose(scores,row["fold_accuracy"],rtol=0,atol=1e-12)
        require(abs(np.mean(scores)-row["accuracy_mean"]) < 1e-12
                and abs(accuracy_score(train.label,predicted)-row["pooled_oof_accuracy"]) < 1e-12,"Saved joint scores disagree with original native labels")
        if c["algorithm"] == "previous_real_control":
            old = next(r for r in parent["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            np.testing.assert_array_equal(predicted,old["oof_predictions"])
            if c["id"] == "prior-joint-000":
                np.testing.assert_array_equal(predicted,core_control)
            continue
        for number,(fit,val) in enumerate(folds):
            saved = json.loads((study.DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json").read_text())
            require(saved == row["folds"][number] and saved["signature"] == signature and saved["candidate"] == c
                    and saved["fold_number"] == number and saved["fit_row_keys"] == train.iloc[fit].row_key.tolist()
                    and saved["validation_row_keys"] == train.iloc[val].row_key.tolist(),"Concurrent native joint fold membership changed")
            np.testing.assert_array_equal(saved["predicted"],predicted[val])
            require(saved["training_summary"]["actual_native_targets"] == len(fit)
                    and saved["training_summary"]["actual_source_targets"] == 302
                    and saved["training_summary"]["source_report_counts"] == {"worker":253,"sts":49}
                    and saved["training_summary"]["synthetic_training_rows"] == 0,"Joint training report count or real-data policy changed")
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    require(winner["candidate"]["id"] == selection["winner_id"] and winner["accuracy_mean"] == selection["best_cv_accuracy"],"Joint winner differs from declared participant CV rule")
    new = [r for r in selection["results"] if r["candidate"]["algorithm"] != "previous_real_control"]
    best = max(new,key=lambda r:r["accuracy_mean"])
    auxiliary = max((r for r in new if r["candidate"]["auxiliary_weight"] > 0),key=lambda r:r["accuracy_mean"])
    matched = next(r for r in new if r["candidate"]["auxiliary_weight"] == 0
        and r["candidate"]["common_features"] == auxiliary["candidate"]["common_features"]
        and r["candidate"]["epochs"] == auxiliary["candidate"]["epochs"])
    selected = {r["candidate"]["id"]:r for r in (best,auxiliary,matched)}
    source_observations_checked = 0
    for row in selected.values():
        c = row["candidate"]
        for number,(fit,val) in enumerate(folds):
            fitting,validation = train.iloc[fit],train.iloc[val]
            cache = fresh_bases[number]
            before = {k:v.clone() for k,v in cache["base"].model.state_dict().items()}
            seen = []
            def observe(kind,domain,features,current,prior):
                if kind == "source":
                    real = external[external.source_domain.eq(domain)]
                    pd.testing.assert_frame_equal(features,real[c["common_features"]])
                    np.testing.assert_array_equal(current,real.borg_native.to_numpy())
                    np.testing.assert_array_equal(prior,real.prior_borg.to_numpy())
                else:
                    columns = list(dict.fromkeys(evidence["context_features"]+c["common_features"]))
                    pd.testing.assert_frame_equal(features,fitting[columns])
                    np.testing.assert_array_equal(current,fitting.label.str.removeprefix("Borg ").to_numpy(int))
                    np.testing.assert_array_equal(prior,fitting.prior_borg.to_numpy(int))
                seen.append((kind,domain))
            with patch("fatigue_prior_view_training.fitting_views",side_effect=AssertionError("Artificial history fitting prohibited")),patch("torch.rand",side_effect=AssertionError("Artificial input masking prohibited")):
                model = study.PriorJointBorg(c).fit(fitting,external,evidence["native_members"]["member_specifications"]["core"],evidence["context_features"],cache,observe)
            require(set(seen) == {("source","worker"),("source","sts"),("native","native")},"Actual source/native supervision observer was bypassed")
            source_observations_checked += 302
            predicted = model.predict(validation)
            np.testing.assert_array_equal(predicted,np.asarray(row["oof_predictions"])[val])
            require(model.loss_endpoints == row["folds"][number]["loss_endpoints"],"Joint training loss endpoints failed exact reproduction")
            np.testing.assert_array_equal(model.predict(validation[model.input_features]),predicted)
            without_truth = validation.drop(columns=["label","row_key","group_key"])
            np.testing.assert_array_equal(model.predict(without_truth),predicted)
            require(int(model.shared_scaler.n_samples_seen_) == len(fitting)+302
                    and int(model.context_scaler.n_samples_seen_) == len(fitting)
                    and not set(vars(model)) & {"fit_logits","inner_folds","fit_row_keys","pool","histories","external"}
                    and all(torch.equal(value,model.base.model.state_dict()[key]) for key,value in before.items()),"Validation data entered preprocessing, baseline changed or query pool was stored")
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/"prior-conditioned-joint.joblib"
                joblib.dump(model,output)
                np.testing.assert_array_equal(joblib.load(output).predict(without_truth),predicted)
            print(f"Independent actual-public joint refit {c['id']}: fold {number+1}/5",flush=True)
    require(winner["accuracy_mean"] < .65 and not (study.DIRECTORY/"evaluation/metrics.json").exists(),
            "A joint model crossed its gate: freeze, evaluate and independently verify its full original-179 artifact")
    incumbent = validate_incumbent()
    require(incumbent["correct"] == 108 and incumbent["accuracy"] == previous["best_verified_test_accuracy"],"Retained original test model changed")
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "previous_verification_sha256":digest(previous_path),"selection_sha256":digest(path),"public_real_data_policy_sha256":digest(study.parent.native.POLICY),
        "actual_source_pairs_checked":302,"source_elapsed_context_checked_against_original_features":True,
        "unknown_worker_survey_age_not_invented":True,"independent_nested_native_baselines":5,"inner_person_folds_per_baseline":3,
        "all_14_oof_recipes_recomputed":True,"inherited_real_controls_reproduced":2,
        "best_new_candidate_id":best["candidate"]["id"],"best_new_cv_accuracy":best["accuracy_mean"],
        "best_positive_auxiliary_candidate_id":auxiliary["candidate"]["id"],"best_positive_auxiliary_cv_accuracy":auxiliary["accuracy_mean"],
        "matched_zero_auxiliary_candidate_id":matched["candidate"]["id"],"matched_zero_auxiliary_cv_accuracy":matched["accuracy_mean"],
        "native_recipes_independently_refitted":sorted(selected),"grouped_folds_per_refit":5,"actual_source_report_visits_checked":source_observations_checked,
        "actual_native_and_source_targets_observed_during_refits":True,"artificial_history_and_input_masking_disabled":True,
        "winner_id":selection["winner_id"],"best_cv_accuracy":winner["accuracy_mean"],"new_test_gate_passed":False,
        "original_training_cases":487,"original_test_cases":179,"best_verified_test_correct":incumbent["correct"],
        "best_verified_test_accuracy":incumbent["accuracy"],"target_accuracy":.8,"achieved":False,
        "scope":"Original exact native Borg and all participant-held cases. Source continuous current/prior differences retain their original observed values and study context. Nested offsets are independently reproduced; source elapsed recording context is not relabeled as an unknown Borg age. No synthetic observations, source class conversion or test tuning."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = validate()
    if args.output:
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
