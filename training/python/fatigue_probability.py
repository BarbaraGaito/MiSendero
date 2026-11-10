"""Native Borg score fusion with grouped, training-only OOF selection.

Forest probability distributions are combined with independently fitted task
experts. SVMs without probability calibration contribute an explicit point vote,
not a claimed calibrated confidence. Exact current Borg remains the target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
from fatigue_calibrated_ensemble import load_inputs, member_pool
from fatigue_calibrated_experts import INITIAL_FEATURES, LATER_FEATURES, categorical_features, model as expert_model
from fatigue_experiment import estimator_for
from fatigue_features import RESEARCH
from public_sources import ROOT, digest, verify_source_snapshot

DIRECTORY = RESEARCH / "calibrated-probability-v1"


def validate_calibration(frame):
    previous, age = frame["prior_borg"].to_numpy(float), frame["prior_age_minutes"].to_numpy(float)
    if (not np.isfinite(previous).all() or not np.isfinite(age).all()
            or np.any(previous != np.rint(previous)) or np.any((previous < 0) | (previous > 10))
            or np.any((age < 1) | (age > 15))):
        raise ValueError("An actual previous Borg aged 1-15 minutes is required")


def native_scores(classifier, x, previous=None):
    if hasattr(classifier, "predict_proba"):
        head = classifier.predict_proba(x)
        classes = np.asarray(classifier.classes_, dtype=int)
    else:
        predictions = classifier.predict(x).astype(int)
        classes = np.unique(predictions)
        head = (predictions[:, None] == classes[None, :]).astype(float)
    result = np.zeros((len(x), 11))
    for column, label in enumerate(classes):
        native = np.full(len(x), label, dtype=int) if previous is None else np.clip(previous.astype(int) + label, 0, 10)
        result[np.arange(len(x)), native] += head[:, column]
    return result


class ForestMember:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame):
        y = frame["label"].str.removeprefix("Borg ").astype(int)
        if self.candidate["target_mode"] == "change_from_prior":
            y = y - frame["prior_borg"].astype(int)
        self.model = estimator_for(self.candidate)
        self.model.fit(frame[self.candidate["features"]], y.astype(str))
        return self

    def scores(self, frame):
        previous = frame["prior_borg"].to_numpy(float) if self.candidate["target_mode"] == "change_from_prior" else None
        return native_scores(self.model, frame[self.candidate["features"]], previous)


class ExpertMember:
    def __init__(self, candidate):
        self.candidate = candidate

    @staticmethod
    def x(frame, config, features):
        if config["algorithm"] == "majority":
            return np.zeros((len(frame), 1))
        return categorical_features(frame) if config["algorithm"] == "categorical_nb" else frame[features]

    def fit(self, frame):
        initial = frame["prior_age_minutes"].ge(frame["elapsed_minutes"])
        y = frame["label"].str.removeprefix("Borg ").astype(int)
        self.initial = expert_model(self.candidate["initial"])
        self.later = expert_model(self.candidate["later"])
        self.initial.fit(self.x(frame[initial], self.candidate["initial"], INITIAL_FEATURES), y[initial])
        delta = y[~initial] - frame.loc[~initial, "prior_borg"].astype(int)
        self.later.fit(self.x(frame[~initial], self.candidate["later"], LATER_FEATURES), delta)
        return self

    def scores(self, frame):
        initial = frame["prior_age_minutes"].ge(frame["elapsed_minutes"])
        result = np.zeros((len(frame), 11))
        if initial.any():
            result[initial] = native_scores(self.initial, self.x(frame[initial], self.candidate["initial"], INITIAL_FEATURES))
        if (~initial).any():
            result[~initial] = native_scores(self.later, self.x(frame[~initial], self.candidate["later"], LATER_FEATURES), frame.loc[~initial, "prior_borg"].to_numpy(float))
        return result


def build_member(record):
    return ForestMember(record["candidate"]) if record["kind"] == "forest" else ExpertMember(record["candidate"])


def sharpen(scores, temperature):
    result = np.power(scores, 1 / temperature)
    return result / result.sum(axis=1, keepdims=True)


class ScoredEnsemble:
    def __init__(self, members, recipe):
        self.members, self.recipe = members, recipe

    def predict_scores(self, frame):
        validate_calibration(frame)
        scores = {key: member.scores(frame) for key, member in self.members.items()}
        return recipe_scores(scores, self.recipe)

    def predict(self, frame):
        return np.asarray([f"Borg {i}" for i in self.predict_scores(frame).argmax(axis=1)])


def recipe_scores(scores, recipe):
    temperature = recipe["temperature"]
    if recipe["kind"] == "single":
        return sharpen(scores[recipe["member_id"]], temperature)
    forest = np.mean([sharpen(scores[key], temperature) for key in recipe["forest_ids"]], axis=0)
    expert = np.mean([sharpen(scores[key], temperature) for key in recipe["expert_ids"]], axis=0)
    return (1 - recipe["expert_weight"]) * forest + recipe["expert_weight"] * expert


def pool_and_plan(training):
    forest_pool, hashes = member_pool(training)
    families = {}
    for row in forest_pool:
        families.setdefault((row["version"], row["candidate"]["feature_set"]), row)
    forests = list(families.values())
    expert_path = RESEARCH / "calibrated-experts-v1/selection.json"
    experts_report = json.loads(expert_path.read_text(encoding="utf-8"))
    if experts_report["status"] != "complete" or experts_report["train_row_keys"] != training["row_key"].tolist():
        raise ValueError("Expert OOF cohort differs from forest cohort")
    experts = sorted(experts_report["results"], key=lambda row: row["accuracy_mean"], reverse=True)[:5]
    records = [{"member_id": row["member_id"], "kind": "forest", "candidate": row["candidate"]} for row in forests]
    records += [{"member_id": "expert/" + row["candidate"]["id"], "kind": "expert", "candidate": row["candidate"]} for row in experts]
    forest_ids = [row["member_id"] for row in records if row["kind"] == "forest"]
    expert_ids = [row["member_id"] for row in records if row["kind"] == "expert"]
    recipes = [{"id": f"scores-{i:03d}", "kind": "single", "member_id": row["member_id"], "temperature": 1.}
               for i, row in enumerate(records)]
    seen = set()
    for n_forest in (1, 3, len(forest_ids)):
        for n_expert in (1, 3, len(expert_ids)):
            for weight in (.25, .5, .75):
                for temperature in (.5, 1., 2.):
                    key = (tuple(forest_ids[:n_forest]), tuple(expert_ids[:n_expert]), weight, temperature)
                    if key in seen:
                        continue
                    seen.add(key)
                    recipes.append({"id": f"scores-{len(recipes):03d}", "kind": "blend", "forest_ids": list(key[0]),
                                    "expert_ids": list(key[1]), "expert_weight": weight, "temperature": temperature})
    return records, recipes, {**hashes, "experts": digest(expert_path)}


def select():
    _, train, _, manifest, _ = load_inputs()
    validate_calibration(train)
    records, recipes, hashes = pool_and_plan(train)
    DIRECTORY.mkdir(exist_ok=True)
    descriptor = {"dataset_sha256": manifest["dataset_sha256"], "code_sha256": digest(Path(__file__)),
                  "source_selection_hashes": hashes, "records": records, "recipes": recipes,
                  "train_row_keys": train["row_key"].tolist()}
    inputs = DIRECTORY / "inputs.json"
    if inputs.exists() and json.loads(inputs.read_text(encoding="utf-8")) != descriptor:
        raise ValueError("Score-fusion experiment inputs changed; preserve previous run first")
    inputs.write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
    truth = train["label"].str.removeprefix("Borg ").astype(int)
    folds = list(GroupKFold(n_splits=5).split(train, truth, train["group_key"]))
    scores = {}
    for member_index, record in enumerate(records):
        values = np.zeros((len(train), 11))
        for fit_idx, validation_idx in folds:
            if set(train.iloc[fit_idx]["group_key"]) & set(train.iloc[validation_idx]["group_key"]):
                raise AssertionError("OOF score fitting leaked participants")
            member = build_member(record)
            with threadpool_limits(limits=1):
                member.fit(train.iloc[fit_idx])
                values[validation_idx] = member.scores(train.iloc[validation_idx])
        if not np.isfinite(values).all() or not np.allclose(values.sum(axis=1), 1.):
            raise AssertionError("Invalid native Borg voting distribution")
        scores[record["member_id"]] = values
        print(f"OOF score member {member_index+1}/{len(records)} {record['member_id']}: accuracy={accuracy_score(truth, values.argmax(axis=1)):.4f}", flush=True)
    results = []
    for recipe in recipes:
        predicted = recipe_scores(scores, recipe).argmax(axis=1)
        accuracy = [float(accuracy_score(truth.iloc[val], predicted[val])) for _, val in folds]
        results.append({"candidate": recipe, "accuracy_mean": float(np.mean(accuracy)), "accuracy_std": float(np.std(accuracy)),
                        "fold_accuracy": accuracy, "pooled_oof_accuracy": float(accuracy_score(truth, predicted)),
                        "oof_predictions": [f"Borg {i}" for i in predicted]})
    best = max(results, key=lambda row: row["accuracy_mean"])
    np.savez_compressed(DIRECTORY / "oof_scores.npz", **{f"member_{i}": scores[row["member_id"]] for i, row in enumerate(records)})
    report = {**descriptor, "version": 1, "status": "complete", "objective": "exact_native_Borg_accuracy",
              "target_accuracy": .6, "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "winner_id": best["candidate"]["id"], "best_cv_accuracy": best["accuracy_mean"], "results": results,
              "score_semantics": "Uncalibrated native-class voting scores; SVM experts without predict_proba contribute a point vote. These are not clinical confidence estimates.",
              "oof_scores_sha256": digest(DIRECTORY / "oof_scores.npz")}
    (DIRECTORY / "selection.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Frozen score-fusion winner: {best['candidate']}; CV accuracy={best['accuracy_mean']:.6f}", flush=True)


def evaluate():
    verify_source_snapshot("fatigue")
    frame, train, test, manifest, protocol = load_inputs()
    path = DIRECTORY / "selection.json"
    selection = json.loads(path.read_text(encoding="utf-8"))
    if selection["code_sha256"] != digest(Path(__file__)) or selection["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("Score-fusion selection inputs changed")
    destination = DIRECTORY / "evaluation"
    if destination.exists():
        raise ValueError("This frozen score-fusion model already has a held-out evaluation")
    best = max(selection["results"], key=lambda row: row["accuracy_mean"])
    if selection["winner_id"] != best["candidate"]["id"]:
        raise ValueError("Winner differs from training-only CV objective")
    recipe = best["candidate"]
    needed = [recipe["member_id"]] if recipe["kind"] == "single" else recipe["forest_ids"] + recipe["expert_ids"]
    models = {}
    for record in selection["records"]:
        if record["member_id"] in needed:
            member = build_member(record)
            with threadpool_limits(limits=1):
                member.fit(train)
            models[record["member_id"]] = member
    predictor = ScoredEnsemble(models, recipe)
    labels = [f"Borg {i}" for i in range(11)]
    validity = {"real_public_ground_truth": True, "deployment_approved": False, "native_labels": True, "synthetic_rows": 0,
                "status": "observed_Borg_calibration_with_participant_disjoint_fit",
                "reason": "Requires a real previous Borg from 1-15 minutes earlier and observed causal history/sensors. Exact native ratings on the complete original published benchmark; descriptive reuse, not fresh external or clinical field validation."}
    features = list(manifest["features"])
    metrics = evaluate_training_run(clf=predictor, dataset_name="Fatiga Borg calibrada — fusión de modelos",
        declared_source=manifest["source"]["source"], source_note=validity["reason"], feature_cols=features, labels=labels,
        full_features=frame[features], full_labels=frame["label"], x_train=train[features], x_test=test[features], y_train=train["label"], y_test=test["label"])
    predicted = predictor.predict(test)
    metrics.update(trained_at=datetime.now(timezone.utc).isoformat(), evaluation_validity=validity,
                   input_contract=manifest["input_contract"], model_selection={"winner_id": selection["winner_id"], "candidate_count": len(selection["results"]), "test_used_for_selection": False})
    cv_f1 = [float(f1_score(train.iloc[val]["label"], np.asarray(best["oof_predictions"])[val], labels=labels, average="macro", zero_division=0)) for _, val in GroupKFold(n_splits=5).split(train, groups=train["group_key"])]
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": best["accuracy_mean"], "accuracy_std": best["accuracy_std"], "f1_macro_mean": float(np.mean(cv_f1)), "f1_macro_std": float(np.std(cv_f1))}
    metrics["hyperparameters"] = {"algorithm": "calibrated_score_fusion", "selection_method": "cross_validated", "cv_folds": 5, "cv_f1_macro_mean": float(np.mean(cv_f1)), "recipe": recipe}
    metrics["evaluation_protocol"] = {**protocol, "calibration_provenance_sha256": digest(RESEARCH / "calibrated-v2/provenance.json"), "selection_sha256": digest(path), "test_used_for_selection": False, "previous_benchmark_evaluations_are_published": True, "observed_prior_user_feedback_is_an_input": True}
    metrics["evaluation_details"] = holdout_details(train["label"], test["label"], predicted, labels, train["group_key"], test["group_key"])
    metrics["previous_borg_baseline"] = {"strategy": "repeat_previous_observed_Borg", **_summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], labels)}
    metrics["guardrails"]["warnings"].insert(0, "Requiere Borg previa real; no es inferencia con sensores solos. Benchmark ya publicado, sin aprobación para campo.")
    destination.mkdir()
    model_path = destination / "model.joblib"
    joblib.dump(predictor, model_path)
    restored = joblib.load(model_path)  # Only the artifact fitted by this command.
    if not np.array_equal(restored.predict(frame), predictor.predict(frame)):
        raise AssertionError("Restored own model differs from fitted predictions")
    metrics["model_artifact"] = {"path": model_path.name, "sha256": digest(model_path), "algorithm": "calibrated_score_fusion", "trusted_local_training_artifact": True}
    prediction_path = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted, "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(prediction_path, index=False)
    metrics["test_predictions_sha256"] = digest(prediction_path)
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Score-fusion test exact accuracy={metrics['accuracy']:.6f} ({sum(predicted==test['label'])}/{len(test)}); >=60%: {metrics['accuracy'] >= .6}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    evaluate() if args.evaluate else select()
