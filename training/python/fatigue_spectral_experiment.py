"""Frozen grouped comparison of observed phone spectra on native Borg targets."""
from __future__ import annotations

import importlib.metadata
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from fatigue_catboost import CatBoostBorg, TERRAINS
from fatigue_dynamics_experiment import DynamicsClassifier, plan as dynamics_plan
from fatigue_features import RESEARCH
from fatigue_phone_experiment import load_inputs as phone_inputs, plan as phone_plan
from fatigue_phone_spectral import DIRECTORY as SPECTRAL_DIRECTORY
from public_sources import digest

DIRECTORY = RESEARCH / "spectral-classification-80-v1"


def merge_spectra(parent, added, features):
    """Preserve every parent float, row and label; append feature-only columns."""
    if (not parent["row_key"].is_unique or not added["row_key"].is_unique
            or parent["row_key"].tolist() != added["row_key"].tolist()
            or added.columns.tolist() != ["row_key", *features]
            or len(set(features)) != len(features)
            or any(not c.startswith("spectral") or c in parent for c in features)):
        raise ValueError("Spectral join changed original cases or supplied non-spectral columns")
    stats = added[features].copy()
    stats.index = parent.index
    return pd.concat([parent.copy(), stats], axis=1)


def load_inputs():
    parent, train, test, manifest, protocol = phone_inputs()
    path = SPECTRAL_DIRECTORY / "dataset.csv"
    evidence = json.loads((SPECTRAL_DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if (digest(path) != evidence["dataset_sha256"]
            or evidence["feature_code_sha256"] != digest(Path(__file__).with_name("fatigue_phone_spectral.py"))
            or evidence["parent_dataset_sha256"] != manifest["dataset_sha256"]
            or evidence["parent_feature_code_sha256"] != manifest["feature_code_sha256"]
            or evidence["phone_receipt_sha256"] != manifest["phone_receipt_sha256"]
            or evidence["original_rows"] != 666 or evidence["synthetic_rows"] != 0
            or not evidence["no_gap_interpolation"]):
        raise ValueError("Frozen spectral data, feature preparation or parent source changed")
    added = pd.read_csv(path)
    frame = merge_spectra(parent, added, evidence["features"])
    terrain = frame[["terrain_"+t for t in TERRAINS]]
    if not terrain.isin([0, 1]).all().all() or not terrain.sum(axis=1).eq(1).all():
        raise ValueError("Unknown or ambiguous native terrain")
    frame = frame.assign(current_terrain=np.asarray(TERRAINS)[terrain.to_numpy().argmax(axis=1)])
    updated = {**manifest, "spectral_features": evidence["features"],
               "spectral_dataset_sha256": evidence["dataset_sha256"],
               "spectral_provenance_sha256": digest(SPECTRAL_DIRECTORY / "provenance.json")}
    return frame, frame.loc[train.index].copy(), frame.loc[test.index].copy(), updated, protocol


def plan(manifest):
    prior = next(c["features"] for c in phone_plan(manifest) if c["feature_set"] == "incumbent_control")
    history = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    compact = [f"spectral60_{channel}_{metric}" for channel in ("acc_mag", "gyro_mag", "vertical")
               for metric in ("std", "peak_hz", "entropy", "peak_normalized_power", "band_mid_share", "band_gait_share")]
    compact += ["spectral60_observed_bins", "spectral_prior_observed_bins", "spectral_initial_observed_bins"]
    sets = {"compact_spectra": prior+compact,
            "all_spectra": prior+manifest["spectral_features"],
            "spectra_history_physiology": history+manifest["spectral_features"]+["hr_last", "hr_change_after_prior", "hr_recent_slope"]}
    source = json.loads((RESEARCH / "catboost-80-v1/selection.json").read_text(encoding="utf-8"))
    if source["status"] != "complete":
        raise ValueError("The CatBoost control must already be frozen")
    cat = max(source["results"], key=lambda r: r["accuracy_mean"])["candidate"]
    candidates = [
        {"id": "spectra-000", "algorithm": "mlp", "feature_set": "incumbent_control", "features": prior,
         "params": {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}, "target_mode": "change_from_prior"},
        {**cat, "id": "spectra-001", "algorithm": "catboost", "feature_set": "catboost_control"},
    ]
    models = [
        *[("mlp", {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": alpha, "max_iter": 1000}) for alpha in (10., 100.)],
        *[("svm", {"C": c, "gamma": "scale"}) for c in (1., 10.)],
        ("logistic", {"C": .1, "max_iter": 3000}),
        ("random_forest", {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 5, "max_features": 1.}),
        ("hist_gradient_boosting", {"max_iter": 150, "max_leaf_nodes": 7, "learning_rate": .05, "l2_regularization": 10}),
        ("catboost", {}),
    ]
    for name, features in sets.items():
        for algorithm, params in models:
            for mode in ("absolute_borg", "change_from_prior"):
                columns = features
                if algorithm == "catboost":
                    columns = [f for f in columns if f not in {"terrain_"+t for t in TERRAINS}]+["current_terrain"]
                config = {"id": f"spectra-{len(candidates):03d}", "feature_set": name, "algorithm": algorithm,
                          "features": columns, "target_mode": mode}
                if algorithm == "catboost":
                    config.update(depth=3, l2_leaf_reg=30., iterations=900)
                else:
                    config["params"] = params
                candidates.append(config)
    return candidates


class SpectralBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame):
        cls = CatBoostBorg if self.candidate["algorithm"] == "catboost" else DynamicsClassifier
        self.model = cls(self.candidate).fit(frame)
        return self

    def predict(self, frame):
        return self.model.predict(frame)


def fingerprint(manifest):
    helpers = ("fatigue_phone_experiment.py", "fatigue_phone_spectral.py", "fatigue_dynamics_experiment.py", "fatigue_catboost.py")
    return {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
            "spectral_dataset_sha256": manifest["spectral_dataset_sha256"],
            "spectral_provenance_sha256": manifest["spectral_provenance_sha256"],
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "catboost_selection_sha256": digest(RESEARCH / "catboost-80-v1/selection.json"),
            "software_versions": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn", "catboost")}}


def select():
    _, train, _, manifest, _ = load_inputs()
    if len(train) != 487 or train["group_key"].nunique() != 28:
        raise ValueError("Spectral selection changed the original fitting cohort")
    candidates = plan(manifest)
    signature = {**fingerprint(manifest), "plan": candidates, "train_row_keys": train["row_key"].tolist()}
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "synthetic_rows": 0, "evaluation_denominator": 487, "test_denominator": 179,
              "policy": "Observed phone spectra only. All imputation/scaling/model fitting stays inside fitting participants. No current/future outcomes, no interpolation, no target exclusions."}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the frozen spectral search before changing its inputs")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    (DIRECTORY / "folds").mkdir(exist_ok=True)
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted = np.empty(len(train), dtype=object)
        convergence = 0
        for fold, (fit, val) in enumerate(folds):
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise ValueError("Spectral selection leaked validation participants")
            evidence = {"signature": signature, "candidate": candidate,
                        "fit_row_keys": train.iloc[fit]["row_key"].tolist(), "validation_row_keys": train.iloc[val]["row_key"].tolist()}
            fold_path = DIRECTORY / "folds" / f"{candidate['id']}-fold-{fold}.json"
            if fold_path.exists():
                saved = json.loads(fold_path.read_text(encoding="utf-8"))
                if any(saved.get(k) != v for k, v in evidence.items()):
                    raise ValueError("Frozen spectral fold evidence changed")
            else:
                with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                    warnings.simplefilter("always", ConvergenceWarning)
                    model = SpectralBorg(candidate).fit(train.iloc[fit])
                    values = model.predict(train.iloc[val])
                saved = {**evidence, "predicted": values.tolist(),
                         "convergence_warnings": sum(issubclass(w.category, ConvergenceWarning) for w in caught)}
                fold_path.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
            predicted[val] = saved["predicted"]
            convergence += saved["convergence_warnings"]
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)),
                                  "oof_predictions": predicted.tolist(), "convergence_warnings": convergence})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Spectra {len(report['results'])}/{len(candidates)}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)
    for number, source, source_id in ((0, "calibrated-alternatives-v1", "alternative-023"), (1, "catboost-80-v1", None)):
        original = json.loads((RESEARCH / source / "selection.json").read_text())
        expected = (next(r for r in original["results"] if r["candidate"]["id"] == source_id) if source_id
                    else max(original["results"], key=lambda r: r["accuracy_mean"]))
        actual = next(r for r in report["results"] if r["candidate"]["id"] == f"spectra-{number:03d}")
        np.testing.assert_array_equal(actual["oof_predictions"], expected["oof_predictions"])
    print("Both spectral-study controls reproduce all 487 original OOF decisions", flush=True)


if __name__ == "__main__":
    select()
