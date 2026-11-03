"""Participant-disjoint GP classification of exact native Borg reports."""
from __future__ import annotations

import importlib.metadata
import json
import warnings
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, RBF, WhiteKernel
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

import fatigue_conditional_borg as parent
from fatigue_dynamics_experiment import plan as dynamics_plan
from public_sources import digest

DIRECTORY = parent.RESEARCH / "gaussian-process-80-v1"


def bounded_lml(objective, initial_theta, bounds):
    """Optimize fitting-only marginal likelihood with a fixed work budget."""
    result = minimize(objective, initial_theta, jac=True, bounds=bounds,
                      method="L-BFGS-B", options={"maxiter": 20, "maxfun": 60, "maxls": 10, "ftol": 1e-6})
    if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
        raise ValueError("Nonfinite GP marginal-likelihood optimization")
    return result.x, float(result.fun)


def fitting_reports(frame, extra, include_extra):
    """Filter by fitting people before parsing any additional target value."""
    selected = extra[extra["group_key"].isin(set(frame["group_key"]))].copy() if include_extra else extra.iloc[:0].copy()
    if (not frame["row_key"].is_unique or not selected["row_key"].is_unique
            or set(frame["row_key"]) & set(selected["row_key"])):
        raise ValueError("Only unique actually observed fitting reports are allowed")
    data = pd.concat([frame, selected], ignore_index=True)
    target = data["label"].str.removeprefix("Borg ").astype(float).to_numpy()
    if (not np.isfinite(target).all() or np.any(target != np.rint(target))
            or np.any((target < 0) | (target > 10))):
        raise ValueError("Native integer Borg outcomes are required; no rescaling or rounding")
    return data, target.astype(int), {
        "original_fitting_queries": len(frame), "additional_actual_reports": len(selected),
        "total_actual_reports": len(data), "fitting_people": frame["group_key"].nunique(),
        "alternative_input_views": 0, "synthetic_targets": 0,
    }


class GaussianBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame, extra):
        c = self.candidate
        self.features = list(c["features"])
        data, target, self.training_summary = fitting_reports(frame, extra, c["include_extra"])
        parent.validate_calibration(data)
        if c["target_mode"] == "change_from_prior":
            target = target - data["prior_borg"].to_numpy(int)
        elif c["target_mode"] != "absolute_borg":
            raise ValueError("Unknown native target parameterization")
        if len(np.unique(target)) < 2:
            raise ValueError("GP classification requires at least two fitting outcomes")
        self.preprocessing = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler())
        x = self.preprocessing.fit_transform(data[self.features])
        if c["kernel"] == "rbf":
            covariance = RBF(3., (.3, 30.))
        elif c["kernel"] == "matern_1.5":
            covariance = Matern(3., (.3, 30.), nu=1.5)
        else:
            raise ValueError("Unknown frozen GP kernel")
        kernel = ConstantKernel(1., (.1, 100.)) * covariance + WhiteKernel(.1, "fixed")
        self.model = GaussianProcessClassifier(kernel=kernel, optimizer=bounded_lml,
            n_restarts_optimizer=0, max_iter_predict=50, warm_start=False,
            copy_X_train=True, random_state=42, multi_class="one_vs_rest", n_jobs=1)
        with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
            warnings.simplefilter("always")
            self.model.fit(x, target)
        self.training_diagnostics = {"fitted_kernel": str(self.model.kernel_),
            "log_marginal_likelihood": float(self.model.log_marginal_likelihood_value_),
            "transformed_feature_count": x.shape[1],
            "warnings": sorted({f"{type(w.message).__name__}: {w.message}" for w in caught})}
        return self

    def predict(self, frame):
        parent.validate_calibration(frame)
        value = self.model.predict(self.preprocessing.transform(frame[self.features])).astype(int)
        if self.candidate["target_mode"] == "change_from_prior":
            value = value + frame["prior_borg"].to_numpy(int)
        value = np.clip(value, 0, 10)
        return np.asarray([f"Borg {i}" for i in value])


def plan(manifest, specifications):
    features = {"core": specifications["core"]["features"],
                "compact": next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")}
    result = [{"id": f"gp-{i:03d}", "algorithm": "historical_point_control", "initialization": name}
              for i, name in enumerate(("core", "view"))]
    for name, columns in features.items():
        for kernel in ("rbf", "matern_1.5"):
            for mode in ("absolute_borg", "change_from_prior"):
                for extra in (False, True):
                    result.append({"id": f"gp-{len(result):03d}", "algorithm": "gaussian_process",
                        "feature_set": name, "features": columns, "kernel": kernel,
                        "target_mode": mode, "include_extra": extra})
    return result


def fingerprint(inputs):
    return {**parent.fingerprint(inputs), "code_sha256": digest(Path(__file__)),
            "parent_code_sha256": digest(Path(parent.__file__)),
            "parent_selection_sha256": digest(parent.DIRECTORY / "selection.json"),
            "optimizer": {"method": "L-BFGS-B", "maxiter": 20, "maxfun": 60, "maxls": 10, "ftol": 1e-6},
            "software_versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pandas", "scikit-learn", "joblib")}}


def write_report(report):
    data = json.dumps(report, indent=2, allow_nan=False) + "\n"
    path = DIRECTORY / "selection.json"
    path.with_suffix(".tmp").write_text(data, encoding="utf-8")
    path.write_text(data, encoding="utf-8")


def select():
    _, train, test, manifest, _, _, extra, inputs, _ = parent.load_inputs()
    signature, candidates = fingerprint(inputs), plan(manifest, inputs["specifications"])
    DIRECTORY.mkdir(exist_ok=True)
    fold_folder = DIRECTORY / "folds"
    fold_folder.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "status": "running", "plan": candidates,
        "train_row_keys": train["row_key"].tolist(), "results": [], "target_accuracy": .8,
        "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
        "evaluation_denominator": len(train), "test_denominator": len(test),
        "minimum_cv_for_new_test_evaluation": .65, "extra_actual_report_pool": len(extra),
        "alternative_input_views": 0, "synthetic_borg_targets": 0,
        "policy": "Fit GP likelihood, imputation, scaling and kernel hyperparameters only on the original fitting people. Extra reports are actual native outcomes filtered by fitting people before parsing. No current/future label or identifier predictor. Original 487/179 queries and exact native targets stay unchanged. No repeated input views, source-state relabelling, test tuning or validation stopping."}
    if path.exists():
        old = json.loads(path.read_text())
        if (any(old.get(k) != v for k, v in signature.items()) or old["plan"] != candidates
                or old["train_row_keys"] != report["train_row_keys"]):
            raise ValueError("Frozen GP code, source, plan, software or cohort changed")
        report = old
    else:
        write_report(report)
    if report["status"] == "complete":
        return report
    done = {r["candidate"]["id"] for r in report["results"]}
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for c in candidates:
        if c["id"] in done:
            continue
        predictions, evidence = np.empty(len(train), dtype=object), []
        for number, (fit, val) in enumerate(folds):
            identity = {"signature": signature, "candidate": c, "fit_row_keys": train.iloc[fit]["row_key"].tolist(),
                        "validation_row_keys": train.iloc[val]["row_key"].tolist()}
            saved_path = fold_folder / f"{c['id']}-fold-{number}.json"
            if saved_path.exists():
                saved = json.loads(saved_path.read_text())
                if any(saved.get(k) != v for k, v in identity.items()):
                    raise ValueError("GP fold cache source or population changed")
            else:
                start = perf_counter()
                if c["algorithm"] == "historical_point_control":
                    source_path = parent.DIRECTORY / "sources" / f"{c['initialization']}-fold-{number}.joblib"
                    descriptor = json.loads(source_path.with_suffix(".json").read_text())
                    if (descriptor["model_sha256"] != digest(source_path) or descriptor["fit_row_keys"] != identity["fit_row_keys"]
                            or descriptor["signature"] != parent.fingerprint(inputs)):
                        raise ValueError("Historical warm control changed")
                    source = joblib.load(source_path)
                    values = source["classifier"].predict(source["preprocessor"].transform(train.iloc[val][source["features"]])).astype(int)
                    values = np.clip(values + train.iloc[val]["prior_borg"].to_numpy(int), 0, 10)
                    predicted = [f"Borg {v}" for v in values]
                    summary, diagnostics = {"original_fitting_queries": len(fit), "additional_actual_reports": 0}, {"source_model_sha256": descriptor["model_sha256"]}
                else:
                    model = GaussianBorg(c).fit(train.iloc[fit], extra)
                    predicted = model.predict(train.iloc[val]).tolist()
                    summary, diagnostics = model.training_summary, model.training_diagnostics
                saved = {**identity, "predicted": predicted, "training_summary": summary,
                         "training_diagnostics": diagnostics, "fit_and_prediction_seconds": perf_counter()-start}
                saved_path.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
            predictions[val] = saved["predicted"]
            evidence.append(saved)
            print(f"{c['id']} fold {number+1}/5 complete", flush=True)
        scores = [float(accuracy_score(train.iloc[val]["label"], predictions[val])) for _, val in folds]
        if c["algorithm"] == "historical_point_control":
            historical = json.loads((parent.DIRECTORY / "selection.json").read_text())
            reference = next(r["oof_predictions"] for r in historical["results"]
                             if r["candidate"]["initialization"] == c["initialization"] and r["candidate"]["mode"] == "point_control")
            np.testing.assert_array_equal(predictions, reference)
        report["results"].append({"candidate": c, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train["label"], predictions)), "oof_predictions": predictions.tolist(), "folds": evidence})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        write_report(report)
        print(f"{len(report['results'])}/{len(candidates)} {c['id']}: CV={scores}, mean={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)
    report["status"] = "complete"
    write_report(report)
    return report


if __name__ == "__main__":
    select()
