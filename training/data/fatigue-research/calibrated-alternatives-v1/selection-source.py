"""Kernel, linear and neural calibrated models on the unchanged Borg task."""
from __future__ import annotations

import argparse
import hashlib
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from common.evaluation import _summary_metrics, evaluate_training_run, holdout_details
from fatigue_calibrated_ensemble import load_inputs
from fatigue_features import RESEARCH
from fatigue_probability import validate_calibration
from public_sources import digest, verify_source_snapshot

DIRECTORY = RESEARCH / "calibrated-alternatives-v1"


def plan(manifest):
    prior = manifest["calibration_features"]
    context = ["elapsed_minutes", "cumulative_active_minutes", "task_order", "terrain_stairs", "terrain_ramp", "terrain_flat_trail"]
    sets = {"prior_context": prior + context,
            "prior_hr_history": prior + manifest["history_features"] + ["hr_last", "elapsed_minutes"]}
    algorithms = [
        *[("svm", {"C": c, "gamma": "scale"}) for c in (.1, 1., 10., 100.)],
        *[("logistic", {"C": c, "max_iter": 3000}) for c in (.01, .1, 1., 10.)],
        ("mlp", {"hidden_layer_sizes": [8], "solver": "lbfgs", "alpha": .1, "max_iter": 1000}),
        ("mlp", {"hidden_layer_sizes": [8], "solver": "lbfgs", "alpha": 1., "max_iter": 1000}),
        ("mlp", {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 1., "max_iter": 1000}),
        ("mlp", {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}),
        ("mlp", {"hidden_layer_sizes": [16, 8], "solver": "adam", "alpha": 1., "max_iter": 1000}),
        ("gaussian_nb", {"var_smoothing": .01}), ("gaussian_nb", {"var_smoothing": .1}),
    ]
    return [{"id": f"alternative-{i:03d}", "features": features, "feature_set": name,
             "algorithm": algorithm, "params": params, "target_mode": mode}
            for i, (name, features, algorithm, params, mode) in enumerate(
                (name, features, algorithm, params, mode) for name, features in sets.items()
                for algorithm, params in algorithms for mode in ("absolute_borg", "change_from_prior"))]


class CalibratedClassifier:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame):
        c = self.candidate
        if c["algorithm"] == "svm":
            classifier = SVC(**c["params"], random_state=42)
        elif c["algorithm"] == "logistic":
            classifier = LogisticRegression(**c["params"], random_state=42)
        elif c["algorithm"] == "mlp":
            classifier = MLPClassifier(**c["params"], random_state=42, early_stopping=False)
        elif c["algorithm"] == "gaussian_nb":
            classifier = GaussianNB(**c["params"])
        else:
            raise ValueError("Unknown calibrated alternative")
        self.model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), classifier)
        y = frame["label"].str.removeprefix("Borg ").astype(int)
        if c["target_mode"] == "change_from_prior":
            y = y - frame["prior_borg"].astype(int)
        self.model.fit(frame[c["features"]], y.astype(str))
        return self

    def predict(self, frame):
        validate_calibration(frame)
        values = self.model.predict(frame[self.candidate["features"]]).astype(int)
        if self.candidate["target_mode"] == "change_from_prior":
            values = np.clip(values + frame["prior_borg"].to_numpy(dtype=int), 0, 10)
        return np.asarray([f"Borg {i}" for i in values])


def select():
    _, train, _, manifest, _ = load_inputs()
    candidates = plan(manifest)
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {"version": 1, "objective": "exact_native_Borg_accuracy", "target_accuracy": .6,
              "dataset_sha256": manifest["dataset_sha256"], "code_sha256": digest(Path(__file__)),
              "plan": candidates, "plan_sha256": hashlib.sha256(json.dumps(candidates, sort_keys=True).encode()).hexdigest(),
              "train_row_keys": train["row_key"].tolist(), "test_used_for_selection": False,
              "previous_benchmark_results_are_published": True, "status": "running", "results": []}
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        for key in ("dataset_sha256", "code_sha256", "plan_sha256"):
            if old[key] != report[key]:
                raise ValueError("Alternative inputs changed; preserve previous results before a new version")
        report = old
    done = {r["candidate"]["id"] for r in report["results"]}
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        predictions = np.empty(len(train), dtype=object)
        scores, convergence = [], 0
        for fit, val in folds:
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise AssertionError("Alternative model fitting leaked participants")
            classifier = CalibratedClassifier(candidate)
            with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                warnings.simplefilter("always", ConvergenceWarning)
                classifier.fit(train.iloc[fit])
                values = classifier.predict(train.iloc[val])
            convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
            predictions[val] = values
            scores.append(float(accuracy_score(train.iloc[val]["label"], values)))
        result = {"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                  "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(train["label"], predictions)),
                  "oof_predictions": predictions.tolist(), "convergence_warnings": convergence}
        report["results"].append(result)
        best = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']} {candidate['target_mode']}: CV accuracy={result['accuracy_mean']:.4f}, best={report['best_cv_accuracy']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def evaluate():
    verify_source_snapshot("fatigue")
    frame, train, test, manifest, protocol = load_inputs()
    selection_path = DIRECTORY / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection["status"] != "complete" or selection["code_sha256"] != digest(Path(__file__)) or selection["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("Alternative search is incomplete or its inputs changed")
    best = max(selection["results"], key=lambda row: row["accuracy_mean"])
    if best["candidate"]["id"] != selection["winner_id"]:
        raise ValueError("Alternative winner differs from training CV selection")
    destination = DIRECTORY / "evaluation"
    if destination.exists():
        raise ValueError("Frozen alternative already evaluated; preserve the held-out evidence")
    candidate = best["candidate"]
    classifier = CalibratedClassifier(candidate)
    with threadpool_limits(limits=1):
        classifier.fit(train)
    labels = [f"Borg {i}" for i in range(11)]
    validity = {"real_public_ground_truth": True, "native_labels": True, "synthetic_rows": 0, "deployment_approved": False,
                "status": "participant_holdout_with_observed_Borg_feedback",
                "reason": "Requires a real previous Borg aged 1-15 minutes and observed prior feedback. Original published benchmark reused descriptively; not sensor-only, fresh external confirmation or clinical field approval."}
    metrics = evaluate_training_run(clf=classifier, dataset_name="Fatiga Borg con calibración previa", declared_source=manifest["source"]["source"],
        source_note=validity["reason"], feature_cols=candidate["features"], labels=labels,
        full_features=frame[candidate["features"]], full_labels=frame["label"], x_train=train[candidate["features"]], x_test=test[candidate["features"]], y_train=train["label"], y_test=test["label"])
    predicted = classifier.predict(test)
    cv_f1 = [float(f1_score(train.iloc[val]["label"], np.asarray(best["oof_predictions"])[val], labels=labels, average="macro", zero_division=0)) for _, val in GroupKFold(n_splits=5).split(train, groups=train["group_key"])]
    metrics.update(trained_at=datetime.now(timezone.utc).isoformat(), evaluation_validity=validity, input_contract=manifest["input_contract"],
        model_selection={"winner_id": selection["winner_id"], "candidate_count": len(selection["results"]), "test_used_for_selection": False})
    metrics["metrics"]["cross_validation"] = {"folds": 5, "accuracy_mean": best["accuracy_mean"], "accuracy_std": best["accuracy_std"], "f1_macro_mean": float(np.mean(cv_f1)), "f1_macro_std": float(np.std(cv_f1))}
    metrics["hyperparameters"] = {**candidate["params"], "algorithm": candidate["algorithm"], "target_mode": candidate["target_mode"], "selection_method": "cross_validated", "cv_folds": 5, "cv_f1_macro_mean": float(np.mean(cv_f1))}
    metrics["evaluation_protocol"] = {**protocol, "selection_sha256": digest(selection_path), "calibration_provenance_sha256": digest(RESEARCH / "calibrated-v2/provenance.json"), "test_used_for_selection": False, "previous_benchmark_results_are_published": True, "prior_observed_user_reports_are_inputs": True}
    metrics["evaluation_details"] = holdout_details(train["label"], test["label"], predicted, labels, train["group_key"], test["group_key"])
    metrics["previous_borg_baseline"] = {"strategy": "repeat_previous_observed_Borg", **_summary_metrics(test["label"], [f"Borg {i:g}" for i in test["prior_borg"]], labels)}
    metrics["guardrails"]["warnings"].insert(0, "Requiere Borg previa real de 1-15 minutos; el resultado no corresponde a sensores solos.")
    destination.mkdir()
    path = destination / "model.joblib"
    joblib.dump(classifier, path)
    restored = joblib.load(path)
    if not np.array_equal(restored.predict(frame), classifier.predict(frame)):
        raise AssertionError("Restored own artifact differs from fitted classifier")
    metrics["model_artifact"] = {"path": path.name, "sha256": digest(path), "algorithm": candidate["algorithm"], "trusted_local_training_artifact": True}
    prediction_path = destination / "test_predictions.csv"
    pd.DataFrame({"row_key": test["row_key"].to_numpy(), "observed": test["label"].to_numpy(), "predicted": predicted, "previous_borg": test["prior_borg"].to_numpy(), "prior_age_minutes": test["prior_age_minutes"].to_numpy()}).to_csv(prediction_path, index=False)
    metrics["test_predictions_sha256"] = digest(prediction_path)
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Frozen alternative {candidate}: exact test accuracy={metrics['accuracy']:.6f} ({sum(predicted==test['label'])}/{len(test)}), >=60%: {metrics['accuracy'] >= .6}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    # Persist classes under their stable importable module rather than __main__.
    import fatigue_calibrated_alternatives as module
    module.evaluate() if args.evaluate else module.select()
