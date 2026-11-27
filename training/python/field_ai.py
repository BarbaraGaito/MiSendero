"""Reproducible scoped prototype: prepare -> select -> evaluate once -> validate."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,
                             confusion_matrix, f1_score, fbeta_score, mean_absolute_error,
                             precision_recall_curve, recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from common.export_classifier import export_classifier, predict_proba_json
from common.selection import candidate_plan, make_estimator, fit_candidate
from field_sources import FEATURES, SCOPES, fatigue_dataset, load_boos
from public_sources import ROOT, digest

SEED = 42
BOOTSTRAPS = 2000
TASKS = ("fatigue", "ams")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def write_once(path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Frozen artifact differs: {path}; use a new run ID, never overwrite evidence")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def code_hashes():
    return {name: digest(Path(__file__).with_name(name)) for name in ("field_ai.py", "field_sources.py")}


def prepare(directory):
    for task, build in (("fatigue", fatigue_dataset), ("ams", load_boos)):
        frame, provenance = build()
        if task == "ams":
            train, test = next(GroupShuffleSplit(n_splits=1, test_size=.30, random_state=SEED)
                               .split(frame, groups=frame.split_group))
            frame["partition"] = "train"
            frame.loc[test, "partition"] = "test"
        train, test = frame[frame.partition == "train"], frame[frame.partition == "test"]
        if set(train.person) & set(test.person) or set(train.split_group) & set(test.split_group):
            raise ValueError("Participant/expedition leakage")
        if train.label.nunique() < 2 or test.label.nunique() < 2:
            raise ValueError("Frozen group split lacks both outcomes; do not search seeds")
        path = directory / task / "dataset.csv"
        content = frame.to_csv(index=False, lineterminator="\n")
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ValueError("Prepared observations changed; preserve the run and create a new version")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        write_once(path.with_name("provenance.json"), {**provenance, "dataset_sha256": digest(path),
                   "features": FEATURES[task], "scope": SCOPES[task], "code_sha256": code_hashes(),
                   "rows": len(frame), "train_rows": len(train), "test_rows": len(test),
                   "train_people": train.person.nunique(), "test_people": test.person.nunique(),
                   "train_split_groups": sorted(train.split_group.unique()),
                   "test_split_groups": sorted(test.split_group.unique()),
                   "test_row_keys": test.row_key.tolist()})
        print(f"{task}: prepared {len(frame)} observed rows, {train.person.nunique()}/{test.person.nunique()} people train/test", flush=True)
    write_once(directory / "protocol.json", {"version": 1, "seed": SEED, "candidate_plan": candidate_plan(),
               "bootstrap_replicates": BOOTSTRAPS, "selection_uses_test": False,
               "selection_objective": {"fatigue": "pooled grouped OOF MAE, native Borg median decision",
                                       "ams": "pooled grouped OOF average precision"},
               "threshold": "AMS maximum training OOF F2; highest threshold breaks ties",
               "eligibility": "paired participant bootstrap lower 95% improvement >0; fatigue large underestimation no worse; AMS Brier better than training prevalence and at least 10 held-out positive/negative observations",
               "scope": "academic informational prototype only; no clinical or general field approval",
               "code_sha256": code_hashes()})


def load_task(directory, task):
    path = directory / task
    provenance = json.loads((path / "provenance.json").read_text(encoding="utf-8"))
    if digest(path / "dataset.csv") != provenance["dataset_sha256"] or provenance["code_sha256"] != code_hashes():
        raise ValueError("Dataset or preparation source changed since freeze")
    frame = pd.read_csv(path / "dataset.csv", dtype={"label": str, "row_key": str})
    train, test = frame[frame.partition == "train"], frame[frame.partition == "test"]
    if frame.row_key.duplicated().any() or set(train.person) & set(test.person) or set(train.split_group) & set(test.split_group):
        raise ValueError("Duplicate identity or group leakage")
    return frame, train, test, provenance


def impute(values, medians):
    values = np.asarray(values, dtype=float)
    if np.isinf(values).any():
        raise ValueError("Infinite predictor")
    return np.column_stack((np.where(np.isnan(values), medians, values), np.isnan(values).astype(float)))


def fit(candidate, frame, task):
    values = frame[FEATURES[task]].to_numpy(float)
    medians = np.array([np.nanmedian(col) if np.isfinite(col).any() else 0 for col in values.T])
    estimator = make_estimator(candidate)
    fit_candidate(estimator, candidate, impute(values, medians), frame.label)
    return estimator, medians


def fatigue_values(classes, probabilities):
    values = np.array([float(label.removeprefix("Borg ")) for label in classes])
    order = np.argsort(values)
    positions = (np.cumsum(probabilities[:, order], axis=1) < .5).sum(axis=1)
    return values[order[np.minimum(positions, len(order)-1)]]


def result_values(estimator, medians, frame, task):
    probabilities = estimator.predict_proba(impute(frame[FEATURES[task]], medians))
    if task == "fatigue":
        return fatigue_values(estimator.classes_, probabilities)
    return probabilities[:, list(estimator.classes_).index("AMS+")]


def labels(frame, task):
    return frame.label.str.removeprefix("Borg ").astype(float).to_numpy() if task == "fatigue" else frame.label.eq("AMS+").astype(int).to_numpy()


def best_threshold(truth, probabilities):
    precision, recall, thresholds = precision_recall_curve(truth, probabilities)
    scores = 5 * precision[:-1] * recall[:-1] / np.maximum(4 * precision[:-1] + recall[:-1], 1e-15)
    return float(max(thresholds[np.isclose(scores, scores.max(), rtol=0, atol=1e-12)]))


def logits(probabilities):
    clipped = np.clip(probabilities, 1e-6, 1-1e-6)
    return np.log(clipped / (1-clipped)).reshape(-1, 1)


def calibrate(probabilities, calibration):
    score = logits(probabilities).ravel() * calibration["coef"] + calibration["intercept"]
    return 1 / (1 + np.exp(-np.clip(score, -700, 700)))


def select(directory):
    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    if protocol["code_sha256"] != code_hashes() or protocol["candidate_plan"] != candidate_plan():
        raise ValueError("Selection protocol changed")
    for task in TASKS:
        _, training, _, provenance = load_task(directory, task)
        path = directory / task / "selection.json"
        if path.exists():
            print(f"{task}: using frozen selection", flush=True)
            continue
        folds = list(GroupKFold(n_splits=min(5, training.split_group.nunique()))
                     .split(training, groups=training.split_group))
        truth = labels(training, task)
        results = []
        for candidate in protocol["candidate_plan"]:
            oof = np.empty(len(training))
            for fit_idx, val_idx in folds:
                fitted, medians = fit(candidate, training.iloc[fit_idx], task)
                oof[val_idx] = result_values(fitted, medians, training.iloc[val_idx], task)
            objective = float(mean_absolute_error(truth, oof) if task == "fatigue" else average_precision_score(truth, oof))
            results.append({"candidate": candidate, "objective": objective, "oof_predictions": oof.tolist()})
            print(f"{task}: {len(results)}/{len(protocol['candidate_plan'])} OOF={objective:.4f}", flush=True)
        winner = (min if task == "fatigue" else max)(results, key=lambda row: row["objective"])
        calibration, threshold = None, None
        if task == "ams":
            calibrator = LogisticRegression(C=1, random_state=SEED).fit(logits(winner["oof_predictions"]), truth)
            calibration = {"coef": float(calibrator.coef_[0, 0]), "intercept": float(calibrator.intercept_[0])}
            threshold = best_threshold(truth, calibrate(winner["oof_predictions"], calibration))
        write_once(path, {"dataset_sha256": provenance["dataset_sha256"], "code_sha256": code_hashes(),
                   "protocol_sha256": digest(directory / "protocol.json"), "test_used_for_selection": False,
                   "train_row_keys": training.row_key.tolist(), "winner_id": winner["candidate"]["id"],
                   "calibration": calibration, "threshold": threshold, "results": results,
                   "folds": [{"train_people": sorted(training.iloc[a].person.unique()),
                              "validation_people": sorted(training.iloc[b].person.unique())} for a, b in folds]})


def summary(truth, values, task, threshold=None):
    if task == "fatigue":
        vocabulary = list(range(11))
        return {"mae": float(mean_absolute_error(truth, values)), "accuracy": float(accuracy_score(truth, values)),
                "f1_macro": float(f1_score(truth, values, labels=vocabulary, average="macro", zero_division=0)),
                "underestimate_ge2": float(np.mean(truth-values >= 2)),
                "confusion_labels": vocabulary, "confusion_matrix": confusion_matrix(truth, values, labels=vocabulary).tolist()}
    decisions = values >= threshold
    return {"average_precision": float(average_precision_score(truth, values)), "roc_auc": float(roc_auc_score(truth, values)),
            "brier": float(brier_score_loss(truth, values)), "sensitivity": float(recall_score(truth, decisions, zero_division=0)),
            "specificity": float(recall_score(1-truth, 1-decisions.astype(int), zero_division=0)),
            "f2": float(fbeta_score(truth, decisions, beta=2, zero_division=0)),
            "confusion_labels": [0, 1], "confusion_matrix": confusion_matrix(truth, decisions, labels=[0, 1]).tolist(),
            "calibration_bins": [{"n": int(mask.sum()), "predicted": float(values[mask].mean()), "observed": float(truth[mask].mean())}
                                 for lo in np.arange(0, 1, .2)
                                 if (mask := (values >= lo) & (values < lo+.2+(1e-12 if lo >= .8 else 0))).any()]}


def paired_interval(truth, values, baseline, people, task):
    rng = np.random.default_rng(SEED)
    groups = sorted(set(people))
    members = {group: np.flatnonzero(people == group) for group in groups}
    differences = []
    for _ in range(BOOTSTRAPS):
        indices = np.concatenate([members[group] for group in rng.choice(groups, len(groups), replace=True)])
        y, p, b = truth[indices], values[indices], baseline[indices]
        if task == "ams" and len(set(y)) < 2:
            continue
        differences.append(float(np.mean(np.abs(y-b))-np.mean(np.abs(y-p))) if task == "fatigue"
                           else float(average_precision_score(y, p)-average_precision_score(y, b)))
    if len(differences) < BOOTSTRAPS // 2:
        return {"replicates": len(differences), "lower": None, "upper": None}
    lo, hi = np.quantile(differences, [.025, .975])
    return {"replicates": len(differences), "lower": float(lo), "upper": float(hi)}


def metrics_for(test, training, values, task, threshold):
    truth = labels(test, task)
    baseline = test.prior_borg.to_numpy() if task == "fatigue" else np.full(len(test), labels(training, task).mean())
    model = summary(truth, values, task, threshold)
    reference = summary(truth, baseline, task, .5 if task == "ams" else None)
    interval = paired_interval(truth, values, baseline, test.person.to_numpy(), task)
    improved = interval["lower"] is not None and interval["lower"] > 0
    if task == "fatigue":
        improved &= model["underestimate_ge2"] <= reference["underestimate_ge2"]
    else:
        improved &= model["brier"] < reference["brier"] and min(np.bincount(truth, minlength=2)) >= 10
    return {"model": model, "baseline": reference, "paired_improvement_95ci": interval,
            "observations": len(test), "people": int(test.person.nunique()),
            "runtime_eligible": bool(improved), "clinical_or_general_field_approved": False,
            "reason": "Supera la referencia en el alcance público evaluado; estimación orientativa del prototipo."
                      if improved else "El candidato no supera todos los criterios de mejora e incertidumbre del protocolo.",
            "coverage": {"fixed_test_rows": len(test), "scored_rows": len(values), "abstentions": 0}}


def evaluate(directory):
    for task in TASKS:
        _, training, test, provenance = load_task(directory, task)
        selection_path = directory / task / "selection.json"
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if selection["dataset_sha256"] != provenance["dataset_sha256"] or selection["code_sha256"] != code_hashes() or selection["protocol_sha256"] != digest(directory / "protocol.json"):
            raise ValueError("Frozen selection inputs changed")
        destination = directory / task / "evaluation"
        if destination.exists():
            print(f"{task}: evaluation already frozen; validate it instead", flush=True)
            continue
        winner = (min if task == "fatigue" else max)(selection["results"], key=lambda row: row["objective"])
        if winner["candidate"]["id"] != selection["winner_id"]:
            raise ValueError("Winner differs from training-only objective")
        estimator, medians = fit(winner["candidate"], training, task)
        values = result_values(estimator, medians, test, task)
        if task == "ams":
            values = calibrate(values, selection["calibration"])
        metrics = metrics_for(test, training, values, task, selection["threshold"])
        expanded = FEATURES[task] + [name+"_missing" for name in FEATURES[task]]
        payload = export_classifier(estimator, expanded, winner["candidate"]["algorithm"],
                                    {"real_public_ground_truth": True, "deployment_approved": False, "reason": SCOPES[task]})
        expected = estimator.predict_proba(impute(test[FEATURES[task]], medians))
        np.testing.assert_allclose(predict_proba_json(payload, impute(test[FEATURES[task]], medians)), expected, atol=1e-6, rtol=0)
        artifact = {"schema_version": 1, "id": f"{task}-{directory.name}", "task": task,
                    "scope": "fatigue_recent_borg" if task == "fatigue" else "ams_morning_next_ascent",
                    "scope_description": SCOPES[task], "input_features": FEATURES[task], "imputation": medians.tolist(),
                    "required_features": ["hr", "prior_borg", "prior_age_minutes"] if task == "fatigue" else FEATURES[task],
                    "input_ranges": {name: [float(training[name].min()), float(training[name].max())] for name in FEATURES[task]},
                    "runtime_eligible": metrics["runtime_eligible"], "eligibility_reason": metrics["reason"],
                    "clinical_or_general_field_approved": False, "historical_test_reused": provenance["historical_test_reused"],
                    "dataset_sha256": provenance["dataset_sha256"], "selection_sha256": digest(selection_path),
                    "protocol_sha256": digest(directory / "protocol.json"), "calibration": selection["calibration"],
                    "threshold": selection["threshold"], "classifier": payload}
        write_once(destination / "model.json", artifact)
        write_once(destination / "metrics.json", metrics)
        predictions = pd.DataFrame({"row_key": test.row_key, "person": test.person, "observed": labels(test, task), "predicted": values})
        predictions.to_csv(destination / "predictions.csv", index=False)
        fixtures = [{"inputs": {name: (None if pd.isna(row[name]) else float(row[name])) for name in FEATURES[task]},
                     "probabilities": probability.tolist(), "value": float(value)}
                    for (_, row), probability, value in zip(test.iterrows(), expected, values)]
        write_once(destination / "parity.json", fixtures)
        # Bundle an honest scoped candidate, including its failed eligibility.
        # Old experimental artifacts and their approval flags are untouched.
        bundle = ROOT / "ai/models/field"
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / f"{task}.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print(f"{task}: {metrics['model']}; scoped eligibility={metrics['runtime_eligible']}", flush=True)


def validate(directory):
    for task, rebuild in (("fatigue", fatigue_dataset), ("ams", load_boos)):
        frame, training, test, provenance = load_task(directory, task)
        original, _ = rebuild()
        pd.testing.assert_frame_equal(frame.drop(columns="partition").reset_index(drop=True),
                                      original.drop(columns="partition", errors="ignore").reset_index(drop=True), check_dtype=False)
        selection = json.loads((directory / task / "selection.json").read_text(encoding="utf-8"))
        protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
        if protocol["candidate_plan"] != candidate_plan() or protocol["code_sha256"] != code_hashes() or selection["protocol_sha256"] != digest(directory / "protocol.json") or selection["dataset_sha256"] != provenance["dataset_sha256"] or selection["train_row_keys"] != training.row_key.tolist():
            raise ValueError("Protocol/selection identity changed")
        if [r["candidate"] for r in selection["results"]] != protocol["candidate_plan"]:
            raise ValueError("Search candidates changed")
        truth = labels(training, task)
        for result in selection["results"]:
            values = np.asarray(result["oof_predictions"])
            expected = mean_absolute_error(truth, values) if task == "fatigue" else average_precision_score(truth, values)
            if len(values) != len(training) or not np.isclose(expected, result["objective"], atol=1e-12):
                raise ValueError("OOF objective/denominator changed")
        winner = (min if task == "fatigue" else max)(selection["results"], key=lambda r: r["objective"])
        if winner["candidate"]["id"] != selection["winner_id"]:
            raise ValueError("Winner modified")
        oof = np.empty(len(training))
        for a, b in GroupKFold(n_splits=min(5, training.split_group.nunique())).split(training, groups=training.split_group):
            model, medians = fit(winner["candidate"], training.iloc[a], task)
            oof[b] = result_values(model, medians, training.iloc[b], task)
        np.testing.assert_allclose(oof, winner["oof_predictions"], atol=1e-10, rtol=0)
        model, medians = fit(winner["candidate"], training, task)
        values = result_values(model, medians, test, task)
        if task == "ams":
            values = calibrate(values, selection["calibration"])
            if not np.isclose(best_threshold(truth, calibrate(winner["oof_predictions"], selection["calibration"])), selection["threshold"]):
                raise ValueError("Threshold changed")
        destination = directory / task / "evaluation"
        artifact = json.loads((destination / "model.json").read_text(encoding="utf-8"))
        probability = predict_proba_json(artifact["classifier"], impute(test[FEATURES[task]], artifact["imputation"]))
        np.testing.assert_allclose(probability, model.predict_proba(impute(test[FEATURES[task]], medians)), atol=1e-6, rtol=0)
        predictions = pd.read_csv(destination / "predictions.csv")
        if predictions.row_key.tolist() != test.row_key.tolist():
            raise ValueError("Prediction identities changed")
        np.testing.assert_allclose(values, predictions.predicted, atol=1e-12, rtol=0)
        stored = json.loads((destination / "metrics.json").read_text(encoding="utf-8"))
        actual = metrics_for(test, training, values, task, selection["threshold"])
        if fingerprint(stored) != fingerprint(actual) or artifact["runtime_eligible"] != actual["runtime_eligible"]:
            raise ValueError("Metrics or scoped eligibility changed")
        bundled = json.loads((ROOT / f"ai/models/field/{task}.json").read_text(encoding="utf-8"))
        if fingerprint(bundled) != fingerprint(artifact):
            raise ValueError("Mobile bundle differs from evaluated candidate")
        print(f"{task}: sources, selected folds, portable predictions, metrics and bundle verified", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "select", "evaluate", "validate"])
    parser.add_argument("--run", default="v1")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.run):
        parser.error("Run ID must be a simple directory name")
    directory = ROOT / "training/data/field-ai" / args.run
    {"prepare": prepare, "select": select, "evaluate": evaluate, "validate": validate}[args.stage](directory)


if __name__ == "__main__":
    main()
