"""Nested participant-grouped correction of a frozen prior-Borg baseline.

Correction targets use inner out-of-participant predictions, never optimistic
in-sample base predictions. Sensors cannot perturb the baseline unless the
learned residual classifier prefers a different exact native Borg value.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from fatigue_phone_experiment import plan as phone_plan
from fatigue_spectral_experiment import load_inputs, plan as spectral_plan, fingerprint as spectral_fingerprint
from public_sources import digest

DIRECTORY = RESEARCH / "spectral-residual-80-v1"
GENERATED = ["base_predicted_borg", "base_change_from_prior", "base_max_probability", "base_entropy"]


def core_candidate(manifest):
    return next(c for c in phone_plan(manifest) if c["feature_set"] == "incumbent_control")


def base_context(model, frame):
    native = np.asarray([int(x.removeprefix("Borg ")) for x in model.predict(frame)])
    probabilities = model.model.predict_proba(frame[model.candidate["features"]])
    entropy = -(probabilities*np.log(probabilities.clip(1e-15))).sum(axis=1)/np.log(max(2, probabilities.shape[1]))
    return np.c_[native, native-frame["prior_borg"].to_numpy(float), probabilities.max(axis=1), entropy]


def inner_context(frame, candidate):
    context = np.empty((len(frame), len(GENERATED)))
    evidence = []
    for fit, val in GroupKFold(n_splits=3).split(frame, groups=frame["group_key"]):
        if set(frame.iloc[fit]["group_key"]) & set(frame.iloc[val]["group_key"]):
            raise ValueError("Inner residual baseline leaked participants")
        model = DynamicsClassifier(candidate).fit(frame.iloc[fit])
        context[val] = base_context(model, frame.iloc[val])
        evidence.append({"fit_row_keys": frame.iloc[fit]["row_key"].tolist(), "validation_row_keys": frame.iloc[val]["row_key"].tolist()})
    return context, evidence


def with_context(frame, context):
    if context.shape != (len(frame), len(GENERATED)) or not np.isfinite(context).all():
        raise ValueError("Incomplete cross-fitted residual context")
    return frame.assign(**{name: context[:, i] for i, name in enumerate(GENERATED)})


def corrected_predictions(base, probabilities, classes, zero_margin):
    classes = np.asarray(classes, dtype=int)
    base = np.asarray(base, dtype=int)
    if (probabilities.shape != (len(base), len(classes)) or not np.isfinite(probabilities).all()
            or (probabilities < 0).any() or not np.allclose(probabilities.sum(axis=1), 1.) or zero_margin < 0):
        raise ValueError("Valid native residual probabilities and nonnegative margin required")
    # An explicit zero option preserves the incumbent even in an unusual fold
    # with no observed zero residual. Ties favor leaving its decision unchanged.
    nonzero = classes != 0
    zero = probabilities[:, classes == 0].sum(axis=1)+zero_margin
    scores = np.c_[zero, probabilities[:, nonzero]]
    choices = np.r_[0, classes[nonzero]]
    native = np.clip(base+choices[scores.argmax(axis=1)], 0, 10)
    return np.asarray([f"Borg {i}" for i in native])


def plan(manifest):
    prior = core_candidate(manifest)["features"]
    compact = next(c["features"] for c in spectral_plan(manifest) if c["feature_set"] == "compact_spectra" and c["algorithm"] == "mlp")
    sets = {"compact_sensor_correction": compact+GENERATED+["hr_last", "hr_change_after_prior", "hr_recent_slope"],
            "all_sensor_correction": prior+manifest["spectral_features"]+GENERATED+["hr_last", "hr_change_after_prior", "hr_recent_slope"]}
    models = [("logistic", {"C": c, "max_iter": 3000}) for c in (.001, .01, .1)]
    models += [("random_forest", {"n_estimators": 200, "max_depth": 4, "min_samples_leaf": leaf}) for leaf in (10, 30)]
    candidates = [{"id": "spectral-residual-000", "algorithm": "control", "feature_set": "incumbent_control", "features": prior}]
    for name, features in sets.items():
        for algorithm, params in models:
            for margin in (0., .1, .25):
                candidates.append({"id": f"spectral-residual-{len(candidates):03d}", "algorithm": algorithm,
                                   "feature_set": name, "features": features, "params": params, "zero_margin": margin})
    return candidates


def fit_corrector(frame, target, candidate):
    if candidate["algorithm"] == "logistic":
        estimator = LogisticRegression(**candidate["params"], random_state=42)
        stages = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), estimator]
    else:
        estimator = RandomForestClassifier(**candidate["params"], random_state=42, n_jobs=1)
        stages = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), estimator]
    return make_pipeline(*stages).fit(frame[candidate["features"]], np.asarray(target, dtype=int))


def select():
    _, train, _, manifest, _ = load_inputs()
    candidates = plan(manifest)
    signature = {"code_sha256": digest(Path(__file__)), "parent_fingerprint": spectral_fingerprint(manifest),
                 "plan": candidates, "core_candidate": core_candidate(manifest), "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "synthetic_rows": 0, "nested_participant_cross_fitting": True, "evaluation_denominator": 487, "test_denominator": 179}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen nested residual correction inputs changed")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    packed, core_predictions, evidence = [], np.empty(len(train), dtype=object), []
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
        warnings.simplefilter("always", ConvergenceWarning)
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            if set(fitting["group_key"]) & set(validation["group_key"]):
                raise ValueError("Outer residual correction leaked participants")
            context_fit, inner = inner_context(fitting, signature["core_candidate"])
            base = DynamicsClassifier(signature["core_candidate"]).fit(fitting)
            context_val = base_context(base, validation)
            target = fitting["label"].str.removeprefix("Borg ").to_numpy(int)-context_fit[:, 0].astype(int)
            packed.append((with_context(fitting, context_fit), with_context(validation, context_val), target, context_val[:, 0].astype(int)))
            core_predictions[val] = [f"Borg {i}" for i in context_val[:, 0].astype(int)]
            evidence.append({"fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist(),
                             "inner_folds": inner, "fit_context": context_fit.tolist(), "validation_context": context_val.tolist()})
            print(f"Nested residual context {number+1}/5: inner fitting people excluded from their own base predictions", flush=True)
    expected = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in expected["results"] if r["candidate"]["id"] == "alternative-023")
    np.testing.assert_array_equal(core_predictions, expected)
    report["folds"] = evidence
    report["base_convergence_warnings"] = sum(issubclass(w.category, ConvergenceWarning) for w in caught)
    cached = {}
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        if candidate["algorithm"] == "control":
            predicted, convergence = core_predictions.copy(), 0
        else:
            key = json.dumps({k: v for k, v in candidate.items() if k not in ("id", "zero_margin")}, sort_keys=True)
            if key not in cached:
                fitted_scores, convergence = [], 0
                for fitting, validation, target, base_values in packed:
                    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                        warnings.simplefilter("always", ConvergenceWarning)
                        corrector = fit_corrector(fitting, target, candidate)
                        probability = corrector.predict_proba(validation[candidate["features"]])
                    convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
                    fitted_scores.append((base_values, probability, corrector.classes_))
                cached[key] = fitted_scores, convergence
            fitted_scores, convergence = cached[key]
            predicted = np.empty(len(train), dtype=object)
            for (_, val), (base_values, probability, classes) in zip(folds, fitted_scores):
                predicted[val] = corrected_predictions(base_values, probability, classes, candidate["zero_margin"])
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        changed = predicted != core_predictions
        truth = train["label"].to_numpy()
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(truth, predicted)), "oof_predictions": predicted.tolist(),
            "convergence_warnings": convergence, "changed_decisions": int(changed.sum()),
            "corrected_errors": int(((predicted == truth) & (core_predictions != truth)).sum()),
            "spoiled_correct_decisions": int(((predicted != truth) & (core_predictions == truth)).sum())})
        best = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Nested sensor correction {len(report['results'])}/{len(candidates)}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
