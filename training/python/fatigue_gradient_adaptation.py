"""Causal MAML/FOMAML with SGD on actual earlier same-person Borg reports.

Population parameters are fitted without the validation people. Each query
gets its own functional SGD adaptation, using only earlier reports from that
person and session. No current/future target or persistent person identifier
is a network input, and inference never changes the population parameters.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.func import functional_call, grad

from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_dynamics_experiment import plan as dynamics_plan
from fatigue_features import RESEARCH
from fatigue_meta_adaptation import context_keys, native_targets
from fatigue_online_calibration import temporal_metadata
from fatigue_probability import validate_calibration
from public_sources import RAW, digest

DIRECTORY = RESEARCH / "gradient-adaptation-80-v1"


def native_probability(logits, prior):
    scores = torch.softmax(logits, dim=-1)
    destination = (prior.long()[..., None]+torch.arange(-10, 11)).clamp(0, 10)
    # Equality broadcasting avoids one_hot's data-dependent checks under vmap.
    mapping = (destination[..., None] == torch.arange(11)).to(scores.dtype)
    return (scores[..., None]*mapping).sum(dim=-2)


class GradientNetwork(nn.Module):
    def __init__(self, n_features):
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(n_features, 16), nn.Tanh(), nn.Linear(16, 8), nn.Tanh(), nn.Linear(8, 21))
        with torch.no_grad():
            self.layers[-1].weight.mul_(.1)
            self.layers[-1].bias.fill_(-2.)
            self.layers[-1].bias[10] = 2.

    def forward(self, x):
        return self.layers(x)


def episode_scores(network, candidate, params, query_x, query_prior, support_x, support_prior, support_target, support_weight):
    """Current outcome is absent; only support_target drives the inner SGD."""
    def support_loss(current):
        probability = native_probability(functional_call(network, current, (support_x,), strict=True), support_prior)
        loss = -torch.log(probability.gather(-1, support_target[:, None]).squeeze(-1).clamp_min(1e-8))
        return (loss*support_weight).sum()/support_weight.sum().clamp_min(1.)

    adapted = params
    for _ in range(candidate["inner_steps"]):
        gradients = grad(support_loss)(adapted)
        if candidate["first_order"]:
            gradients = {name: value.detach() for name, value in gradients.items()}
        norm = torch.sqrt(sum((value**2).sum() for value in gradients.values())+1e-12)
        factor = (5./norm).clamp(max=1.)
        adapted = {name: value-candidate["inner_learning_rate"]*(factor*gradients[name]+.03*(value-params[name]))
                   for name, value in adapted.items()}
    return native_probability(functional_call(network, adapted, (query_x,), strict=True), query_prior)


class GradientAdaptiveBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def transform(self, frame):
        return torch.tensor(self.scaler.transform(self.imputer.transform(frame[self.candidate["features"]])), dtype=torch.float32)

    def batch(self, queries, pool, histories):
        validate_calibration(queries)
        query_x = self.transform(queries)
        query_prior = torch.tensor(queries["prior_borg"].to_numpy(), dtype=torch.float32)
        positions = {key: i for i, key in enumerate(pool["row_key"])}
        records = [histories[key] if self.candidate["inner_steps"] else [] for key in queries["row_key"]]
        maximum = max(1, max(map(len, records), default=0))
        support_x = torch.zeros((len(queries), maximum, query_x.shape[1]), dtype=torch.float32)
        support_prior = torch.zeros((len(queries), maximum), dtype=torch.float32)
        support_target = torch.zeros((len(queries), maximum), dtype=torch.int64)
        support_weight = torch.zeros((len(queries), maximum), dtype=torch.float32)
        links = []
        pool_groups = pool["group_key"].to_numpy()
        query_keys, query_groups = queries["row_key"].to_numpy(), queries["group_key"].to_numpy()
        for i, observations in enumerate(records):
            for j, observation in enumerate(observations):
                key, age = observation["row_key"], observation["age_minutes"]
                if key not in positions or not np.isfinite(age) or age < 1 or key == query_keys[i]:
                    raise ValueError("Current, future or absent-context metadata is not personal support")
                if pool_groups[positions[key]] != query_groups[i]:
                    raise ValueError("Personal SGD received another person's outcome")
                links.append((i, j, positions[key], age))
        # Transform/validate each selected earlier report once, not every time
        # that report appears in someone's later support window. Future rows
        # and current targets are never transformed or parsed.
        selected = sorted({position for _, _, position, _ in links})
        if selected:
            old = pool.iloc[selected]
            validate_calibration(old)
            x = self.transform(old)
            priors, targets = old["prior_borg"].to_numpy(float), native_targets(old)
            index = {position: i for i, position in enumerate(selected)}
            for i, j, position, age in links:
                k = index[position]
                support_x[i, j], support_prior[i, j] = x[k], float(priors[k])
                support_target[i, j], support_weight[i, j] = int(targets[k]), math.exp(-age/20.)
        return query_x, query_prior, support_x, support_prior, support_target, support_weight

    def scores(self, inputs):
        params = dict(self.model.named_parameters())
        return torch.vmap(lambda *args: episode_scores(self.model, self.candidate, params, *args))(*inputs)

    def fit(self, frame, histories):
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(42)
        np.random.seed(42)
        validate_calibration(frame)
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True)
        self.scaler = StandardScaler().fit(self.imputer.fit_transform(frame[self.candidate["features"]]))
        inputs = self.batch(frame, frame, histories)
        target = torch.tensor(native_targets(frame), dtype=torch.int64)
        self.model = GradientNetwork(inputs[0].shape[1])
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=.01, weight_decay=.03)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.candidate["epochs"], eta_min=.001)
        losses = []
        for epoch in range(self.candidate["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            probability = self.scores(inputs)
            loss = -torch.log(probability.gather(1, target[:, None]).clamp_min(1e-8)).mean()
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite meta-training loss")
            loss.backward()
            if any(p.grad is None or not torch.isfinite(p.grad).all() for p in self.model.parameters()):
                raise ValueError("Nonfinite outer gradient through personal SGD")
            nn.utils.clip_grad_norm_(self.model.parameters(), 5.)
            optimizer.step()
            scheduler.step()
            if epoch == 0 or epoch == self.candidate["epochs"]-1:
                losses.append(float(loss.detach()))
        self.training_loss_endpoints = losses
        return self

    def predict_scores(self, frame, pool, histories):
        # torch.func.grad enables its own inner differentiation under no_grad;
        # inference does not retain an outer meta-learning graph.
        with torch.no_grad():
            values = self.scores(self.batch(frame, pool, histories)).numpy()
        if values.shape != (len(frame), 11) or not np.isfinite(values).all() or not np.allclose(values.sum(axis=1), 1., atol=1e-6):
            raise ValueError("Gradient adaptation changed native probability mass")
        return values

    def predict(self, frame, pool, histories):
        return np.asarray([f"Borg {i}" for i in self.predict_scores(frame, pool, histories).argmax(axis=1)])


def plan(manifest):
    prior = manifest["calibration_features"]+CONTEXT
    compact = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    candidates = []
    for name, features in (("prior_context", prior), ("compact_dynamics", compact)):
        recipes = [(lr, steps, scope, 80, False) for lr in (.05, .5) for steps in (1, 3) for scope in ("task", "session")]
        recipes += [(.5, 3, "session", 200, first) for first in (False, True)]
        recipes += [(0., 0, "task", epochs, False) for epochs in (80, 200)]
        for lr, steps, scope, epochs, first in recipes:
            candidates.append({"id": f"gradient-adapt-{len(candidates):03d}", "feature_set": name, "features": features,
                               "inner_learning_rate": lr, "inner_steps": steps, "scope": scope, "epochs": epochs,
                               "first_order": first, "inner_optimizer": "SGD", "outer_optimizer": "AdamW", "random_seed": 42})
    return candidates


def load_contexts(frame, manifest):
    metadata = temporal_metadata(frame, manifest)
    return {scope: context_keys(frame, metadata, scope) for scope in ("task", "session")}


def fingerprint(manifest, histories):
    helpers = ("fatigue_meta_adaptation.py", "fatigue_online_calibration.py", "fatigue_dynamics_experiment.py", "fatigue_probability.py")
    return {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
            "dynamics_provenance_sha256": digest(RESEARCH / "dynamics-80-v1/provenance.json"),
            "session_metadata_sha256": digest(RAW / "geofatigue/session_metadata.json"),
            "context_index_sha256": hashlib.sha256(json.dumps(histories, sort_keys=True, allow_nan=False).encode()).hexdigest(),
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "software_versions": {name: importlib.metadata.version(name) for name in ("torch", "numpy", "pandas", "scikit-learn")}}


def select(smoke=False):
    frame, train, _, manifest, _ = load_inputs()
    histories = load_contexts(frame, manifest)
    candidates = plan(manifest)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    if smoke:
        fit, val = folds[0]
        candidate = {**candidates[7], "epochs": 8}
        started = time.monotonic()
        model = GradientAdaptiveBorg(candidate).fit(train.iloc[fit], histories[candidate["scope"]])
        prediction = model.predict(train.iloc[val[:8]], frame, histories[candidate["scope"]])
        if len(prediction) != 8:
            raise ValueError("Gradient adaptation probe failed")
        print(f"MAML CPU probe: {len(fit)} fitting rows, 8 predictions, {time.monotonic()-started:.2f}s; no benchmark test used", flush=True)
        return
    signature = {**fingerprint(manifest, histories), "plan": candidates, "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "synthetic_rows": 0, "evaluation_denominator": 487, "test_denominator": 179,
              "population_parameters_exclude_validation_people": True,
              "policy": "Per-query functional SGD on actual canonical same-person same-session reports at least one minute earlier. Exact task boundaries when task-scoped. No current/future targets, persistent population updates, synthetic responses or benchmark exclusions."}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen gradient-adaptation inputs changed")
    (DIRECTORY / "folds").mkdir(exist_ok=True)
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted = np.empty(len(train), dtype=object)
        endpoints = []
        for number, (fit, val) in enumerate(folds):
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise ValueError("Meta-training population includes a validation participant")
            evidence = {"code_sha256": signature["code_sha256"], "dataset_sha256": manifest["dataset_sha256"], "candidate": candidate,
                        "context_index_sha256": signature["context_index_sha256"],
                        "fit_row_keys": train.iloc[fit]["row_key"].tolist(), "validation_row_keys": train.iloc[val]["row_key"].tolist()}
            fold_path = DIRECTORY / "folds" / f"{candidate['id']}-fold-{number}.json"
            if fold_path.exists():
                saved = json.loads(fold_path.read_text(encoding="utf-8"))
                if any(saved.get(k) != v for k, v in evidence.items()):
                    raise ValueError("Frozen MAML fold data/configuration changed")
            else:
                context = histories[candidate["scope"]]
                model = GradientAdaptiveBorg(candidate).fit(train.iloc[fit], context)
                values = model.predict(train.iloc[val], frame, context)
                saved = {**evidence, "predicted": values.tolist(), "training_loss_endpoints": model.training_loss_endpoints}
                fold_path.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
            predicted[val] = saved["predicted"]
            endpoints.append(saved["training_loss_endpoints"])
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)),
                                  "oof_predictions": predicted.tolist(), "fold_training_loss_endpoints": endpoints})
        best = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Personal gradient adaptation {len(report['results'])}/{len(candidates)}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    select(parser.parse_args().smoke)
