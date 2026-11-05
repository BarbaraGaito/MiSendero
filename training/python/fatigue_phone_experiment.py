"""Frozen grouped search for causal phone movement plus previous native Borg."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from common.grouped_fatigue_search import grouped_search
from fatigue_dynamics import CONTEXT
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_phone_context import DIRECTORY, prepare
from public_sources import OUTPUT, digest, verify_source_snapshot


def load_inputs():
    verify_source_snapshot("fatigue")
    manifest = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if digest(DIRECTORY / "dataset.csv") != manifest["dataset_sha256"] or digest(Path(__file__).with_name("fatigue_phone_context.py")) != manifest["feature_code_sha256"]:
        raise ValueError("Phone features or preparation code changed after freezing")
    frame = pd.read_csv(DIRECTORY / "dataset.csv", dtype={"label": str})
    original = pd.read_csv(OUTPUT / "fatigue/dataset.csv", dtype={"label": str})
    if frame["label"].tolist() != original["label"].tolist():
        raise ValueError("Original native Borg labels changed")
    frame = pd.concat([frame, pd.DataFrame({"row_key": [r["row_key"] for r in manifest["lineage"]], "group_key": [r["group_key"] for r in manifest["lineage"]]})], axis=1)
    protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    train, test = [frame[frame["row_key"].isin(protocol[key])].copy() for key in ("train_row_keys", "test_row_keys")]
    if len(frame) != 666 or len(train) != 487 or len(test) != 179 or set(train["group_key"]) & set(test["group_key"]):
        raise ValueError("Original phone experiment cohort/participant holdout changed")
    return frame, train, test, manifest, protocol


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    compact = ["phone_recent30_acc_rms_mean", "phone_recent30_acc_rms_std", "phone_recent30_gyro_mean_mean",
               "phone_recent30_speed_native_mean", "phone_recent30_speed_native_std", "phone_recent30_stopped_fraction",
               "phone_task_acc_rms_mean", "phone_task_speed_native_mean", "phone_task_positive_height_change",
               "phone_recent120_height_p90_range", "phone_speed_native_change_after_prior",
               "phone_acc_rms_change_after_prior", "phone_recent30_observed_seconds", "phone_recent120_observed_seconds"]
    physiology = ["hr_last", "hr_delta_baseline", "hr_ratio_baseline", "hr_recent_slope", "hr_change_after_prior",
                  "hr_change_per_minute_after_prior", "eda_delta_baseline", "temperature_delta_baseline", "raw_pulse_rmssd_ms", "screening_sleep_hours"]
    sets = {"compact_phone": prior + compact, "all_phone": prior + manifest["phone_features"],
            "phone_physiology": prior + manifest["phone_features"] + physiology}
    configs = [
        *[("mlp", {"hidden_layer_sizes": shape, "solver": "lbfgs", "alpha": alpha, "max_iter": 1500}) for shape in ([8], [16, 8]) for alpha in (1., 10., 100.)],
        *[("svm", {"C": c, "gamma": "scale"}) for c in (1., 10.)],
        *[("logistic", {"C": c, "max_iter": 3000}) for c in (.1, 1.)],
        *[("random_forest", {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": leaf, "max_features": 1.}) for leaf in (3, 8)],
        *[("extra_trees", {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": leaf, "max_features": 1.}) for leaf in (3, 8)],
        *[("xgboost", {"n_estimators": 250, "max_depth": depth, "learning_rate": .05, "reg_lambda": 10, "min_child_weight": 5}) for depth in (2, 3)],
        *[("hist_gradient_boosting", {"max_iter": 150, "max_leaf_nodes": leaves, "learning_rate": .05, "l2_regularization": 10}) for leaves in (7, 15)],
    ]
    candidates = [{"id": "phone-000", "feature_set": "incumbent_control", "features": prior, "algorithm": "mlp",
                   "params": {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}, "target_mode": "change_from_prior"}]
    for name, features in sets.items():
        for algorithm, params in configs:
            for mode in ("absolute_borg", "change_from_prior"):
                candidates.append({"id": f"phone-{len(candidates):03d}", "feature_set": name, "features": features,
                                   "algorithm": algorithm, "params": params, "target_mode": mode})
    return candidates


def select():
    if not (DIRECTORY / "provenance.json").exists():
        prepare()  # Explicitly refuses a still-incomplete download receipt.
    _, train, _, manifest, _ = load_inputs()
    fingerprint = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
                   "grouped_search_code_sha256": digest(Path(__file__).parent / "common/grouped_fatigue_search.py"),
                   "classifier_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py"))}
    grouped_search(DIRECTORY, train, plan(manifest), fingerprint, DynamicsClassifier)


if __name__ == "__main__":
    select()
