"""Causal functional SGD starting from the verified L-BFGS Borg MLP.

The fitting split trains the original 13-feature MLP exactly. Double-precision
weights are copied to an equivalent ReLU network, retaining all native delta
options. Query-specific SGD may update its head or all layers, using only
actual earlier same-person outcomes. Population weights remain immutable.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits
from torch import nn
from torch.func import functional_call, grad

from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from fatigue_meta_adaptation import context_keys, native_targets
from fatigue_online_calibration import temporal_metadata
from fatigue_probability import validate_calibration
from public_sources import RAW, digest

DIRECTORY = RESEARCH / "warm-sgd-80-v1"


def core_candidate(manifest):
    return {"features": manifest["calibration_features"]+CONTEXT, "algorithm": "mlp", "target_mode": "change_from_prior",
            "params": {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}}


class WarmNetwork(nn.Module):
    def __init__(self, classifier):
        super().__init__()
        if classifier.activation != "relu" or len(classifier.coefs_) != 3:
            raise ValueError("Expected the frozen two-hidden-layer ReLU MLP")
        known = [int(value)+10 for value in classifier.classes_.astype(int)]
        self.priority = known+[i for i in range(21) if i not in known]
        layers = []
        for i, (weight, bias) in enumerate(zip(classifier.coefs_, classifier.intercepts_)):
            output = 21 if i == 2 else weight.shape[1]
            layer = nn.Linear(weight.shape[0], output, dtype=torch.float64)
            with torch.no_grad():
                if i == 2:
                    layer.weight.zero_()
                    layer.bias.fill_(-30.)
                    if weight.shape[1] == 1 and len(known) == 2:
                        # sklearn's binary sigmoid equals softmax([0, logit]).
                        layer.bias[known[0]] = 0.
                        layer.weight[known[1]].copy_(torch.tensor(weight[:, 0]))
                        layer.bias[known[1]] = float(bias[0])
                    else:
                        for position, value in enumerate(classifier.classes_.astype(int)):
                            layer.weight[value+10].copy_(torch.tensor(weight[:, position]))
                            layer.bias[value+10] = float(bias[position])
                else:
                    layer.weight.copy_(torch.tensor(weight.T))
                    layer.bias.copy_(torch.tensor(bias))
            layers.append(layer)
            if i < 2:
                layers.append(nn.ReLU())
        self.layers = nn.Sequential(*layers)

    def forward(self, x):
        return self.layers(x)


def episode_logits(network, params, candidate, query_x, support_x, support_delta, support_weight):
    def support_loss(current):
        logits = functional_call(network, current, (support_x,), strict=True)
        loss = nn.functional.cross_entropy(logits, support_delta, reduction="none")
        return (loss*support_weight).sum()/support_weight.sum().clamp_min(1.)

    adapted = params
    for _ in range(candidate["steps"]):
        gradients = grad(support_loss)(adapted)
        gradients = {name: (value if candidate["update_layers"] == "all" or name.startswith("layers.4.") else torch.zeros_like(value))
                     for name, value in gradients.items()}
        norm = torch.sqrt(sum((g*g).sum() for g in gradients.values())+1e-12)
        factor = (5./norm).clamp(max=1.)
        # Proximal SGD keeps the update close to its population starting point
        # without an unstable explicit weight-decay step at large lr*penalty.
        adapted = {name: params[name]+((value-params[name])-candidate["learning_rate"]*factor*gradients[name])/(1.+candidate["learning_rate"]*candidate["proximity"])
                   for name, value in adapted.items()}
    return functional_call(network, adapted, (query_x,), strict=True)


class WarmPersonalBorg:
    def __init__(self, candidate, core=None):
        self.candidate, self.core = candidate, core

    def fit(self, frame, core_specification):
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        validate_calibration(frame)
        if self.core is None:
            with threadpool_limits(limits=1):
                self.core = DynamicsClassifier(core_specification).fit(frame)
        self.features = core_specification["features"]
        self.model = WarmNetwork(self.core.model[-1])
        # Conversion must preserve the native fitting decisions before any
        # personal adaptation is considered.
        actual = self.global_predict(frame)
        np.testing.assert_array_equal(actual, self.core.predict(frame))
        return self

    def transform(self, frame):
        return torch.tensor(self.core.model[:-1].transform(frame[self.features]), dtype=torch.float64)

    def global_predict(self, frame):
        with torch.no_grad():
            order = torch.tensor(self.model.priority)
            delta = order[self.model(self.transform(frame))[:, order].argmax(dim=1)].numpy()-10
        return native_prediction(delta, frame["prior_borg"].to_numpy(int))

    def batch(self, queries, pool, histories):
        validate_calibration(queries)
        query_x = self.transform(queries)
        records = [histories[key] if self.candidate["steps"] else [] for key in queries["row_key"]]
        count = max(1, max(map(len, records), default=0))
        support_x = torch.zeros((len(queries), count, query_x.shape[1]), dtype=torch.float64)
        support_delta = torch.full((len(queries), count), 10, dtype=torch.int64)
        support_weight = torch.zeros((len(queries), count), dtype=torch.float64)
        positions = {key: i for i, key in enumerate(pool["row_key"])}
        groups, query_keys, query_groups = pool["group_key"].to_numpy(), queries["row_key"].to_numpy(), queries["group_key"].to_numpy()
        links = []
        for i, rows in enumerate(records):
            for j, row in enumerate(rows):
                key, age = row["row_key"], row["age_minutes"]
                if key not in positions or key == query_keys[i] or not np.isfinite(age) or age < 1:
                    raise ValueError("Only actual earlier reports may enter personal SGD")
                if groups[positions[key]] != query_groups[i]:
                    raise ValueError("Another person's Borg cannot enter personal SGD")
                links.append((i, j, positions[key], age))
        selected = sorted({p for _, _, p, _ in links})
        if selected:
            old = pool.iloc[selected]
            validate_calibration(old)
            transformed = self.transform(old)
            delta = native_targets(old)-old["prior_borg"].to_numpy(int)+10
            index = {p: i for i, p in enumerate(selected)}
            for i, j, p, age in links:
                support_x[i, j] = transformed[index[p]]
                support_delta[i, j] = int(delta[index[p]])
                support_weight[i, j] = math.exp(-age/20.)
        return query_x, support_x, support_delta, support_weight

    def predict(self, frame, pool, histories):
        inputs = self.batch(frame, pool, histories)
        with torch.no_grad():
            params = dict(self.model.named_parameters())
            logits = torch.vmap(lambda *args: episode_logits(self.model, params, self.candidate, *args))(*inputs)
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite warm-start SGD output")
            order = torch.tensor(self.model.priority)
            delta = order[logits[:, order].argmax(dim=1)].numpy()-10
        return native_prediction(delta, frame["prior_borg"].to_numpy(int))


def native_prediction(delta, prior):
    values = np.clip(np.asarray(delta, dtype=int)+np.asarray(prior, dtype=int), 0, 10)
    return np.asarray([f"Borg {i}" for i in values])


def plan():
    candidates = [{"id": "warm-sgd-000", "steps": 0, "learning_rate": 0., "proximity": 0., "scope": "task", "update_layers": "head"}]
    for scope in ("task", "session"):
        for layers in ("head", "all"):
            for lr in (.005, .05, .5):
                for steps in (1, 3):
                    for proximity in (1., 10.):
                        candidates.append({"id": f"warm-sgd-{len(candidates):03d}", "steps": steps, "learning_rate": lr,
                                           "proximity": proximity, "scope": scope, "update_layers": layers})
    return candidates


def load_contexts(frame, manifest):
    metadata = temporal_metadata(frame, manifest)
    return {scope: context_keys(frame, metadata, scope) for scope in ("task", "session")}


def fingerprint(manifest, contexts):
    helpers = ("fatigue_dynamics_experiment.py", "fatigue_meta_adaptation.py", "fatigue_online_calibration.py")
    return {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
            "core_candidate": core_candidate(manifest), "context_index_sha256": hashlib.sha256(json.dumps(contexts, sort_keys=True, allow_nan=False).encode()).hexdigest(),
            "session_metadata_sha256": digest(RAW / "geofatigue/session_metadata.json"),
            "dynamics_provenance_sha256": digest(RESEARCH / "dynamics-80-v1/provenance.json"),
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "software_versions": {name: importlib.metadata.version(name) for name in ("torch", "numpy", "pandas", "scikit-learn")}}


def select():
    frame, train, _, manifest, _ = load_inputs()
    contexts = load_contexts(frame, manifest)
    candidates = plan()
    signature = {**fingerprint(manifest, contexts), "plan": candidates, "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [], "test_used_for_selection": False,
              "previous_benchmark_results_are_published": True, "synthetic_rows": 0, "evaluation_denominator": 487, "test_denominator": 179,
              "support_optimizer": "proximal_SGD",
              "policy": "Original L-BFGS MLP copied in float64. Per-query functional proximal SGD sees only actual earlier canonical same-person same-session reports; exact task start when task-scoped. No query/future outcome, persistent population update or target exclusion. Unknown delta logits initialize at -30, not new observed examples."}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen warm-start SGD study changed")
    if not report["results"]:
        path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    packed = []
    evidence = []
    for fit, val in folds:
        fitting, validation = train.iloc[fit], train.iloc[val]
        if set(fitting["group_key"]) & set(validation["group_key"]):
            raise ValueError("Warm-start base includes validation participants")
        model = WarmPersonalBorg(candidates[0]).fit(fitting, signature["core_candidate"])
        np.testing.assert_array_equal(model.global_predict(validation), model.core.predict(validation))
        packed.append((model, validation))
        evidence.append({"fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist(),
                         "base_fitting_iterations": int(model.core.model[-1].n_iter_)})
    report["folds"] = evidence
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted = np.empty(len(train), dtype=object)
        for (_, val), (model, validation) in zip(folds, packed):
            model.candidate = candidate
            population = {name: value.detach().clone() for name, value in model.model.named_parameters()}
            predicted[val] = model.predict(validation, frame, contexts[candidate["scope"]])
            if any(not torch.equal(population[name], value) for name, value in model.model.named_parameters()):
                raise ValueError("Personal SGD changed population weights")
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist()})
        best = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Warm-start personal SGD {len(report['results'])}/{len(candidates)}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)
    expected = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in expected["results"] if r["candidate"]["id"] == "alternative-023")
    actual = next(r["oof_predictions"] for r in report["results"] if r["candidate"]["id"] == "warm-sgd-000")
    np.testing.assert_array_equal(actual, expected)
    print("Warm-start zero-step control reproduces all 487 original OOF decisions", flush=True)


if __name__ == "__main__":
    select()
