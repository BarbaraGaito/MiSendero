"""Choose a small calibrated ensemble from saved participant-disjoint OOF.

No held-out prediction is read during selection. A later explicit evaluation
fits the frozen member list and verifies portable predictions on all responses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from common.calibrated_ensemble import aggregate_borg, predict_ensemble_json
from common.calibrated_forest import export_calibrated_forest, predict_calibrated_json
from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
from fatigue_experiment import estimator_for
from fatigue_features import RESEARCH
from public_sources import OUTPUT, ROOT, digest, verify_source_snapshot


DIRECTORY = RESEARCH / "calibrated-ensemble-v1"


def load_inputs():
    dataset = RESEARCH / "calibrated-v2"
    manifest = json.loads((dataset / "provenance.json").read_text(encoding="utf-8"))
    if digest(dataset / "dataset.csv") != manifest["dataset_sha256"]:
        raise ValueError("Calibrated input snapshot changed")
    frame = pd.read_csv(dataset / "dataset.csv", dtype={"label": str})
    frame = pd.concat([frame, pd.DataFrame({"row_key": [r["row_key"] for r in manifest["lineage"]],
                                           "group_key": [r["group_key"] for r in manifest["lineage"]]})], axis=1)
    protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    train = frame[frame["row_key"].isin(protocol["train_row_keys"])].copy()
    test = frame[frame["row_key"].isin(protocol["test_row_keys"])].copy()
    if len(train) != len(protocol["train_row_keys"]) or len(test) != len(protocol["test_row_keys"]) or set(train["group_key"]) & set(test["group_key"]):
        raise ValueError("Original participant holdout changed")
    return frame, train, test, manifest, protocol


def member_pool(training):
    pool, fingerprints, hashes = [], set(), {}
    for version in ("calibrated-v1", "calibrated-v2"):
        path = RESEARCH / version / "selection.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["status"] != "complete" or report["train_row_keys"] != training["row_key"].tolist():
            raise ValueError("Member selection incomplete or uses different training observations")
        hashes[version] = digest(path)
        for result in report["results"]:
            candidate = result["candidate"]
            if candidate["algorithm"] not in ("random_forest", "extra_trees"):
                continue
            fingerprint = json.dumps({key: candidate[key] for key in ("algorithm", "params", "features", "target_mode")}, sort_keys=True)
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            pool.append({"member_id": version + "/" + candidate["id"], "version": version,
                         "candidate": candidate, "cv": result["cv"]})
    return sorted(pool, key=lambda row: row["cv"]["accuracy_mean"], reverse=True), hashes


def ensemble_plan(pool):
    families = {}
    for member in pool:
        key = (member["version"], member["candidate"]["feature_set"])
        families.setdefault(key, member)
    diverse = sorted(families.values(), key=lambda row: row["cv"]["accuracy_mean"], reverse=True)
    recipes = {"best_single": pool[:1], "top3": pool[:3], "top5": pool[:5], "top7": pool[:7],
               "diverse3": diverse[:3], "diverse5": diverse[:5], "all_families": diverse}
    result = []
    seen = set()
    for name, members in recipes.items():
        for aggregation in (("majority_vote",) if len(members) == 1 else ("majority_vote", "rounded_mean", "rounded_median")):
            key = (tuple(row["member_id"] for row in members), aggregation)
            if key in seen:
                continue
            seen.add(key)
            result.append({"id": f"ensemble-{len(result):03d}", "name": name, "aggregation": aggregation,
                           "member_ids": [row["member_id"] for row in members]})
    return result


def select():
    _, training, _, manifest, _ = load_inputs()
    pool, source_hashes = member_pool(training)
    plan = ensemble_plan(pool)
    lookup = {row["member_id"]: row for row in pool}
    truth = training["label"].str.replace("Borg ", "", regex=False).astype(int)
    folds = list(GroupKFold(n_splits=5).split(training, truth, training["group_key"]))
    results = []
    for candidate in plan:
        values = [[int(label.removeprefix("Borg ")) for label in lookup[key]["cv"]["oof_predictions"]] for key in candidate["member_ids"]]
        predicted = aggregate_borg(values, candidate["aggregation"])
        scores = [float(accuracy_score(truth.iloc[validation], predicted[validation])) for _, validation in folds]
        results.append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                        "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(truth, predicted)),
                        "oof_predictions": [f"Borg {i}" for i in predicted]})
        print(f"{candidate['name']} {candidate['aggregation']}: exact CV accuracy={np.mean(scores):.4f}", flush=True)
    winner = max(results, key=lambda row: row["accuracy_mean"])
    report = {"version": 1, "objective": "exact_native_Borg_accuracy_with_observed_previous_input",
              "target_accuracy": .6, "test_used_for_selection": False, "prior_version_test_is_published": True,
              "dataset_sha256": manifest["dataset_sha256"], "code_sha256": digest(Path(__file__)), "source_selection_hashes": source_hashes,
              "train_row_keys": training["row_key"].tolist(), "plan": plan,
              "plan_sha256": hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
              "results": results, "winner_id": winner["candidate"]["id"], "best_cv_accuracy": winner["accuracy_mean"],
              "selected_members": [lookup[key] for key in winner["candidate"]["member_ids"]],
              "status": "complete", "interpretation": "These ensemble choices reuse optimized OOF predictions and have selection bias. Held-out benchmark evaluation remains necessary; no claim of new independent confirmation."}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != report:
        raise ValueError("Ensemble selection changed; preserve old evidence before replacing it")
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Frozen ensemble winner {winner['candidate']}: CV={winner['accuracy_mean']:.4f}", flush=True)
    return report


def evaluate():
    verify_source_snapshot("fatigue")
    frame, training, test, manifest, protocol = load_inputs()
    selection_path = DIRECTORY / "selection.json"
    report = json.loads(selection_path.read_text(encoding="utf-8"))
    if report["dataset_sha256"] != manifest["dataset_sha256"] or report["code_sha256"] != digest(Path(__file__)):
        raise ValueError("Ensemble evaluation inputs changed after selection")
    destination = DIRECTORY / "evaluation"
    if destination.exists():
        raise ValueError("Frozen ensemble was already evaluated; do not overwrite held-out results")
    winner = next(r for r in report["results"] if r["candidate"]["id"] == report["winner_id"])
    if winner != max(report["results"], key=lambda row: row["accuracy_mean"]):
        raise ValueError("Ensemble winner was not selected on training-only CV")
    validity = {"real_public_ground_truth": True, "native_labels": True, "synthetic_rows": 0, "deployment_approved": False,
                "status": "participant_holdout_with_observed_prior_Borg_calibration",
                "reason": "Exact current Borg with a real previous user report 1-15 minutes earlier; not sensor-only. The original held-out benchmark was previously published and is reused descriptively; no clinical/field approval."}
    members = []
    for record in report["selected_members"]:
        candidate = record["candidate"]
        target = training["label"].str.replace("Borg ", "", regex=False).astype(int)
        if candidate["target_mode"] == "change_from_prior":
            target = target - training["prior_borg"].astype(int)
        model = estimator_for(candidate)
        with threadpool_limits(limits=1):
            model.fit(training[candidate["features"]], target.astype(str))
        exported = export_calibrated_forest(model, candidate, manifest["input_contract"], validity)
        expected = model.predict(frame[candidate["features"]]).astype(int)
        if candidate["target_mode"] == "change_from_prior":
            expected = np.clip(expected + frame["prior_borg"].to_numpy(dtype=int), 0, 10)
        if predict_calibrated_json(exported, frame[candidate["features"]]).tolist() != [f"Borg {i}" for i in expected]:
            raise AssertionError("Portable calibrated member differs from fitted estimator")
        exported["member_id"] = record["member_id"]
        members.append(exported)
    features = list(dict.fromkeys(name for member in members for name in member["feature_order"]))
    payload = {"type": "calibrated_forest_ensemble_json", "version": 1, "feature_order": features,
               "input_contract": manifest["input_contract"], "aggregation": winner["candidate"]["aggregation"],
               "evaluation_validity": validity, "members": members}
    class Predictor:
        def predict(self, x):
            return predict_ensemble_json(payload, x)
    predictor = Predictor()
    labels = [f"Borg {i}" for i in range(11)]
    metrics = evaluate_training_run(clf=predictor, dataset_name="Fatiga Borg calibrada con autoevaluación previa",
        declared_source=manifest["source"]["source"], source_note=validity["reason"], feature_cols=features, labels=labels,
        full_features=frame[features], full_labels=frame["label"], x_train=training[features], x_test=test[features],
        y_train=training["label"], y_test=test["label"])
    predicted = predictor.predict(test[features])
    metrics["trained_at"] = datetime.now(timezone.utc).isoformat()
    metrics["evaluation_validity"] = validity
    cv_f1 = [float(f1_score(training.iloc[val]["label"], np.asarray(winner["oof_predictions"])[val], labels=labels, average="macro", zero_division=0)) for _, val in GroupKFold(n_splits=5).split(training, groups=training["group_key"])]
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": winner["accuracy_mean"], "accuracy_std": winner["accuracy_std"],
        "f1_macro_mean": float(np.mean(cv_f1)), "f1_macro_std": float(np.std(cv_f1))}
    metrics["hyperparameters"] = {"algorithm": "calibrated_forest_ensemble", "selection_method": "cross_validated", "cv_folds": 5,
                                  "cv_f1_macro_mean": float(np.mean(cv_f1)), "members": len(members), "aggregation": payload["aggregation"]}
    metrics["evaluation_protocol"] = {**protocol, "test_used_for_selection": False, "previous_version_test_was_published": True,
                                       "selection_sha256": digest(selection_path), "calibration_provenance_sha256": digest(RESEARCH / "calibrated-v2/provenance.json"),
                                       "observed_previous_user_reports_are_inputs": True}
    metrics["evaluation_details"] = holdout_details(training["label"], test["label"], predicted, labels, training["group_key"], test["group_key"])
    metrics["previous_borg_baseline"] = {"strategy": "repeat_previous_observed_Borg", **_summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], labels)}
    metrics["input_contract"] = manifest["input_contract"]
    metrics["guardrails"]["warnings"].insert(0, "Requiere una Borg previa observada de 1 a 15 minutos. No representa inferencia con sensores solos ni aprobación de campo.")
    destination.mkdir()
    model_path = destination / "model.calibrated-ensemble.json"
    model_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    metrics["model_artifact"] = {"path": model_path.name, "sha256": digest(model_path), "algorithm": "calibrated_forest_ensemble"}
    prediction_path = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted,
                  "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(prediction_path, index=False)
    metrics["test_predictions_sha256"] = digest(prediction_path)
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Frozen ensemble test accuracy={metrics['accuracy']:.6f} ({sum(predicted==test['label'])}/{len(test)}); prior-Borg baseline={metrics['previous_borg_baseline']['accuracy']:.6f}; >=60%: {metrics['accuracy'] >= .6}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    evaluate() if args.evaluate else select()
