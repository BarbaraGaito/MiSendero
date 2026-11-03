"""Frozen participant-grouped CatBoost study for exact native Borg accuracy.

Ordered boosting, categorical terrain, fixed tree counts and CPU execution.
No early stopping on validation/test outcomes, synthetic reports, target
grouping, current/future self-report predictors or benchmark exclusions.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import time
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

from fatigue_dynamics_experiment import plan as dynamics_plan
from fatigue_features import RESEARCH
from fatigue_phone_experiment import load_inputs as phone_inputs, plan as phone_plan
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = RESEARCH / "catboost-80-v1"
TERRAINS = ("flat_trail", "stairs", "ramp")


def load_inputs():
    frame, train, test, manifest, protocol = phone_inputs()
    columns = ["terrain_" + name for name in TERRAINS]
    if not frame[columns].isin([0, 1]).all().all() or not frame[columns].sum(axis=1).eq(1).all():
        raise ValueError("Each task must have exactly one known terrain")
    frame = frame.copy().assign(current_terrain=np.asarray(TERRAINS)[frame[columns].to_numpy().argmax(axis=1)])
    return frame, frame.loc[train.index].copy(), frame.loc[test.index].copy(), manifest, protocol


def categorical_features(features):
    return [f for f in features if f == "current_terrain"]


class CatBoostBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame):
        validate_calibration(frame)
        c = self.candidate
        self.model = CatBoostClassifier(iterations=c["iterations"], depth=c["depth"], l2_leaf_reg=c["l2_leaf_reg"],
            learning_rate=.03, loss_function="MultiClass", boosting_type="Ordered", grow_policy="SymmetricTree",
            random_seed=42, thread_count=4, task_type="CPU", border_count=128, bootstrap_type="Bayesian",
            bagging_temperature=1., random_strength=1., nan_mode="Min", use_best_model=False, allow_writing_files=False, verbose=False)
        target = frame["label"].str.removeprefix("Borg ").astype(int).to_numpy()
        if c["target_mode"] == "change_from_prior":
            target = target - frame["prior_borg"].to_numpy(int)
        self.model.fit(frame[c["features"]], target, cat_features=categorical_features(c["features"]))
        return self

    def predict(self, frame):
        validate_calibration(frame)
        values = np.asarray(self.model.predict(frame[self.candidate["features"]])).reshape(-1).astype(int)
        if self.candidate["target_mode"] == "change_from_prior":
            values = np.clip(values + frame["prior_borg"].to_numpy(int), 0, 10)
        if not np.isin(values, np.arange(11)).all():
            raise ValueError("CatBoost output changed the native Borg scale")
        return np.asarray([f"Borg {i}" for i in values])

    def save(self, model_path, descriptor_path):
        self.model.save_model(str(model_path), format="cbm")
        descriptor = {"version": 1, "candidate": self.candidate, "model_sha256": digest(model_path),
                      "model_format": "catboost_native_cbm", "catboost_version": importlib.metadata.version("catboost"),
                      "deployment_approved": False, "native_labels": True, "recent_actual_prior_borg_required": True}
        descriptor_path.write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, model_path, descriptor_path):
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        if descriptor["model_sha256"] != digest(model_path) or descriptor["catboost_version"] != importlib.metadata.version("catboost"):
            raise ValueError("Saved native model/runtime differs from its descriptor")
        instance = cls(descriptor["candidate"])
        instance.model = CatBoostClassifier()
        instance.model.load_model(str(model_path), format="cbm")
        return instance


def plan(manifest):
    def native(features):
        return [f for f in features if f not in {"terrain_" + t for t in TERRAINS}] + ["current_terrain"]
    prior = next(c["features"] for c in phone_plan(manifest) if c["feature_set"] == "incumbent_control")
    dynamics = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    movement = next(c["features"] for c in phone_plan(manifest) if c["feature_set"] == "compact_phone")
    sets = {"prior_context": native(prior), "history_context": native(dynamics),
            "movement_physiology": native(movement) + ["hr_last", "hr_change_after_prior", "hr_recent_slope"]}
    configs = []
    for name, features in sets.items():
        for depth in (3, 5):
            for regularization in (3., 30.):
                for iterations in (300, 900):
                    for mode in ("absolute_borg", "change_from_prior"):
                        configs.append({"id": f"catboost-{len(configs):03d}", "feature_set": name, "features": features,
                                        "depth": depth, "l2_leaf_reg": regularization, "iterations": iterations, "target_mode": mode,
                                        "algorithm": "CatBoost_Ordered", "learning_rate": .03, "random_seed": 42})
    return configs


def select(smoke=False):
    _, train, _, manifest, _ = load_inputs()
    candidates = plan(manifest)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    if smoke:
        fit, val = folds[0]
        started = time.monotonic()
        model = CatBoostBorg(candidates[0]).fit(train.iloc[fit])
        result = model.predict(train.iloc[val[:8]])
        if len(result) != 8 or not set(result) <= {f"Borg {i}" for i in range(11)}:
            raise ValueError("CatBoost runtime probe failed")
        print(f"CPU probe passed: {len(fit)} fitting rows and 8 native predictions in {time.monotonic()-started:.2f}s; no benchmark test used", flush=True)
        return
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
                 "plan": candidates, "train_row_keys": train["row_key"].tolist(),
                 "software_versions": {name: importlib.metadata.version(name) for name in ("catboost", "numpy", "pandas", "scikit-learn")},
                 "phone_loader_code_sha256": digest(Path(__file__).with_name("fatigue_phone_experiment.py")),
                 "dynamics_plan_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py"))}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "synthetic_rows": 0, "early_stopping_with_validation_or_test": False}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the frozen CatBoost search before changing its inputs")
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    fold_directory = DIRECTORY / "folds"
    fold_directory.mkdir(exist_ok=True)
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted = np.empty(len(train), dtype=object)
        for fold, (fit, val) in enumerate(folds):
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise ValueError("CatBoost leaked validation participants")
            evidence = {"code_sha256": signature["code_sha256"], "dataset_sha256": manifest["dataset_sha256"], "candidate": candidate,
                        "fit_row_keys": train.iloc[fit]["row_key"].tolist(), "validation_row_keys": train.iloc[val]["row_key"].tolist()}
            fold_path = fold_directory / f"{candidate['id']}-fold-{fold}.json"
            if fold_path.exists():
                saved = json.loads(fold_path.read_text(encoding="utf-8"))
                if any(saved.get(k) != v for k, v in evidence.items()):
                    raise ValueError("Saved CatBoost fold differs from frozen data or configuration")
                values = np.asarray(saved["predicted"])
            else:
                model = CatBoostBorg(candidate).fit(train.iloc[fit])
                values = model.predict(train.iloc[val])
                fold_path.write_text(json.dumps({**evidence, "predicted": values.tolist()}, indent=2) + "\n", encoding="utf-8")
            predicted[val] = values
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist()})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"CatBoost {len(report['results'])}/{len(candidates)}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    select(parser.parse_args().smoke)
