"""Local TabPFN v2 transfer on the unchanged exact native Borg task.

Built with PriorLabs-TabPFN. Public v2 weights are pinned by publisher SHA256.
No hosted inference, browser login, current/future Borg feature, target binning
or change to the original 487/179 participant split is permitted here.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from fatigue_body_context import BODY_FEATURES, load_inputs as body_inputs
from fatigue_dynamics import CONTEXT
from fatigue_dynamics_experiment import plan as dynamics_plan
from fatigue_features import RESEARCH
from fatigue_phone_experiment import load_inputs as phone_inputs, plan as phone_plan
from fatigue_probability import validate_calibration
from fetch_tabular_transfer import DIRECTORY as MODEL_DIRECTORY
from public_sources import ROOT, digest

DIRECTORY = RESEARCH / "tabular-transfer-80-v1"
WEIGHTS = MODEL_DIRECTORY / "tabpfn-v2-classifier-v2_default.ckpt"
WEIGHTS_SHA256 = "cf8c519c01eaf1613ee91239006d57b1c806ff5f23ac1aeb1315ba1015210e49"


def configure_local_runtime():
    cache = MODEL_DIRECTORY / "cache"
    cache.mkdir(exist_ok=True)
    for variable, suffix in (("TABPFN_MODEL_CACHE_DIR", "models"), ("HF_HUB_CACHE", "huggingface"),
                             ("MPLCONFIGDIR", "matplotlib"), ("SKB_DATA_DIRECTORY", "skrub")):
        path = cache / suffix
        path.mkdir(exist_ok=True)
        os.environ[variable] = str(path)
    os.environ.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", TABPFN_NO_BROWSER="1", DO_NOT_TRACK="1")
    import torch
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)


def verify_weights():
    metadata = json.loads((MODEL_DIRECTORY / "model.json").read_text(encoding="utf-8"))
    if metadata.get("gated") is not False or metadata.get("private") or digest(WEIGHTS) != WEIGHTS_SHA256:
        raise ValueError("Expected the pinned public ungated TabPFN v2 weights")
    import torch
    if torch.serialization.get_unsafe_globals_in_checkpoint(WEIGHTS):
        raise ValueError("Unexpected checkpoint globals; refuse unsafe loading")
    # Independently confirm the checkpoint is only tensors and primitive config.
    content = torch.load(WEIGHTS, map_location="cpu", weights_only=True)
    if set(content) != {"state_dict", "config"} or not isinstance(content["config"], dict):
        raise ValueError("Checkpoint differs from the inspected public v2 schema")


def load_inputs():
    frame, train, test, manifest, protocol = phone_inputs()
    body, _, _, body_manifest, _ = body_inputs()
    if frame["row_key"].tolist() != body["row_key"].tolist() or frame["label"].tolist() != body["label"].tolist():
        raise ValueError("Pre-task body and phone observations refer to different native cases")
    combined = pd.concat([frame, body[BODY_FEATURES]], axis=1)
    training = combined.loc[train.index].copy()
    testing = combined.loc[test.index].copy()
    sources = {"phone_dataset_sha256": manifest["dataset_sha256"], "body_dataset_sha256": body_manifest["dataset_sha256"]}
    return combined, training, testing, manifest, protocol, sources


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    compact = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    phone = next(c["features"] for c in phone_plan(manifest) if c["feature_set"] == "compact_phone")
    physiology = ["hr_last", "hr_delta_baseline", "hr_ratio_baseline", "hr_change_after_prior", "hr_recent_slope", "prior_history_mean", "prior_history_std"]
    sets = {"prior_context": prior, "compact_feedback": compact, "compact_phone": phone,
            "prior_physiology": list(dict.fromkeys(prior + physiology)), "pre_task_body": prior + BODY_FEATURES}
    return [{"id": f"TabPFN-v2-{i:03d}", "feature_set": name, "features": columns, "algorithm": "TabPFN-v2",
             "n_estimators": 4, "softmax_temperature": 1., "target_mode": mode, "random_state": 42}
            for i, (name, columns, mode) in enumerate((name, columns, mode) for name, columns in sets.items()
                                                     for mode in ("absolute_borg", "change_from_prior"))]


class TabPFNBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame):
        validate_calibration(frame)
        configure_local_runtime()
        from tabpfn import TabPFNClassifier
        from tabpfn.constants import ModelVersion
        import torch
        c = self.candidate
        self.model = TabPFNClassifier.create_default_for_version(ModelVersion.V2, model_path=str(WEIGHTS), device="cpu",
            n_estimators=c["n_estimators"], auto_scale_n_estimators=False, softmax_temperature=c["softmax_temperature"],
            balance_probabilities=False, random_state=c["random_state"], n_preprocessing_jobs=1,
            inference_precision=torch.float32, enable_torch_compile=False, fit_mode="fit_preprocessors", show_progress_bar=False)
        target = frame["label"].str.removeprefix("Borg ").astype(int)
        if c["target_mode"] == "change_from_prior":
            target = target - frame["prior_borg"].astype(int)
        self.model.fit(frame[c["features"]], target.astype(str))
        return self

    def predict(self, frame):
        validate_calibration(frame)
        values = self.model.predict(frame[self.candidate["features"]]).astype(int)
        if self.candidate["target_mode"] == "change_from_prior":
            values = np.clip(values + frame["prior_borg"].to_numpy(dtype=int), 0, 10)
        return np.asarray([f"Borg {i}" for i in values])


def select(smoke=False):
    configure_local_runtime()
    verify_weights()
    _, train, _, manifest, _, sources = load_inputs()
    candidates = plan(manifest)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    if smoke:
        fit, val = folds[0]
        started = time.monotonic()
        with threadpool_limits(limits=4):
            model = TabPFNBorg(candidates[1]).fit(train.iloc[fit])
            values = model.predict(train.iloc[val[:8]])
        if len(values) != 8 or any(v not in {f"Borg {i}" for i in range(11)} for v in values):
            raise ValueError("Runtime probe did not produce native Borg decisions")
        print(f"Local CPU runtime probe passed: {len(fit)} fit rows, 8 predictions, {time.monotonic()-started:.2f}s; no benchmark test used", flush=True)
        return
    versions = {name: importlib.metadata.version(name) for name in ("tabpfn", "torch", "numpy", "pandas", "scikit-learn", "scipy")}
    signature = {"code_sha256": digest(Path(__file__)), "sources": sources, "weights_sha256": WEIGHTS_SHA256,
                 "weights_metadata_sha256": digest(MODEL_DIRECTORY / "model.json"), "software_versions": versions,
                 "plan": candidates, "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "objective": "exact_native_Borg_accuracy_on_unchanged_cohort", "test_used_for_selection": False,
              "previous_benchmark_results_are_published": True, "attribution": "Built with PriorLabs-TabPFN"}
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if any(previous[k] != v for k, v in signature.items()):
            raise ValueError("Frozen TabPFN experiment changed; preserve previous run")
        report = previous
    done = {r["candidate"]["id"] for r in report["results"]}
    fold_directory = DIRECTORY / "folds"
    fold_directory.mkdir(exist_ok=True)
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        predicted = np.empty(len(train), dtype=object)
        scores = []
        for fold, (fit, val) in enumerate(folds):
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise AssertionError("Tabular transfer leaked participant groups")
            fold_path = fold_directory / f"{candidate['id']}-fold-{fold}.json"
            evidence = {"code_sha256": signature["code_sha256"], "sources": sources, "weights_sha256": WEIGHTS_SHA256,
                        "candidate": candidate, "fit_row_keys": train.iloc[fit]["row_key"].tolist(), "validation_row_keys": train.iloc[val]["row_key"].tolist()}
            if fold_path.exists():
                saved = json.loads(fold_path.read_text(encoding="utf-8"))
                if any(saved[k] != v for k, v in evidence.items()):
                    raise ValueError("Saved TabPFN fold differs from immutable inputs")
                values = np.asarray(saved["predicted"])
            else:
                started = time.monotonic()
                with threadpool_limits(limits=4):
                    model = TabPFNBorg(candidate).fit(train.iloc[fit])
                    values = model.predict(train.iloc[val])
                saved = {**evidence, "predicted": values.tolist(), "elapsed_seconds": time.monotonic() - started}
                fold_path.write_text(json.dumps(saved, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            predicted[val] = values
            score = float(accuracy_score(train.iloc[val]["label"], values))
            scores.append(score)
            print(f"{candidate['id']} fold {fold+1}/5 exact accuracy={score:.4f}", flush=True)
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                                  "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist()})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        content = json.dumps(report, indent=2, allow_nan=False) + "\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['target_mode']}: mean CV={np.mean(scores):.4f}, best={best['accuracy_mean']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    select(args.smoke)
