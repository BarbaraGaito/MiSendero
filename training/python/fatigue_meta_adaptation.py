"""Learn causal personal adaptation with a differentiable ridge classifier.

The network learns both a global delta forecast and a feature basis for
correcting it from actual earlier same-person reports. Training differentiates
through the ridge solve. Current/future responses never enter adaptation, and
all original 487/179 cases retain their native labels and participant split.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from torch import nn

from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_dynamics_experiment import plan as dynamics_plan
from fatigue_features import RESEARCH
from fatigue_online_calibration import temporal_metadata
from fatigue_probability import validate_calibration
from public_sources import RAW, digest

DIRECTORY = RESEARCH / "meta-adaptation-80-v1"


def context_keys(frame, metadata, scope):
    if scope not in ("task", "session") or len(frame) != len(metadata):
        raise ValueError("Explicit matching task/session metadata is required")
    result = {}
    for position, row in metadata.iterrows():
        mask = (metadata["group_key"].eq(row["group_key"]) & metadata["session_start"].eq(row["session_start"])
                & metadata["response_time"].le(row["response_time"] - pd.Timedelta(minutes=1)))
        if scope == "task":
            mask &= metadata["task_start"].eq(row["task_start"])
        previous = metadata[mask].sort_values("response_time")
        result[frame.iloc[position]["row_key"]] = [
            {"row_key": frame.iloc[i]["row_key"], "age_minutes": (row["response_time"] - old["response_time"]).total_seconds() / 60}
            for i, old in previous.iterrows()]
    return result


def native_targets(frame):
    values = pd.to_numeric(frame["label"].str.removeprefix("Borg ")).to_numpy(float)
    if not np.isfinite(values).all() or np.any(values != np.rint(values)) or np.any((values < 0) | (values > 10)):
        raise ValueError("Only original integer Borg outcomes 0-10 are supported")
    return values.astype(int)


class AdaptiveNetwork(nn.Module):
    def __init__(self, features, width, ridge):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(features, width), nn.Tanh())
        self.head = nn.Linear(width, 21)
        self.ridge = ridge
        self.width = width

    def basis(self, encoded):
        return torch.cat((torch.ones_like(encoded[..., :1]), encoded / math.sqrt(self.width)), dim=-1)

    def forward(self, query_x, support_x, support_delta, support_weight, prior):
        encoded_query = self.encoder(query_x)
        logits = self.head(encoded_query)
        if self.ridge is not None:
            encoded_support = self.encoder(support_x)
            phi_s, phi_q = self.basis(encoded_support), self.basis(encoded_query)
            residual = nn.functional.one_hot(support_delta, num_classes=21).to(query_x.dtype) - torch.softmax(self.head(encoded_support), dim=-1)
            weighted_phi = phi_s * support_weight[..., None]
            gram = phi_s.transpose(-2, -1) @ weighted_phi + self.ridge * torch.eye(self.width + 1, dtype=query_x.dtype)
            rhs = weighted_phi.transpose(-2, -1) @ residual
            coefficients = torch.linalg.solve(gram, rhs)
            logits = logits + 4. * (phi_q[:, None, :] @ coefficients).squeeze(1)
        scores = torch.softmax(logits, dim=1)
        destinations = (prior.long()[:, None] + torch.arange(-10, 11)[None, :]).clamp(0, 10)
        return torch.zeros((len(query_x), 11), dtype=scores.dtype).scatter_add(1, destinations, scores)


class MetaAdaptiveBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def transform(self, frame):
        values = self.scaler.transform(self.imputer.transform(frame[self.candidate["features"]]))
        return torch.tensor(values, dtype=torch.float32)

    def batch(self, queries, pool, histories):
        validate_calibration(queries)
        # A fixed fitting scaler transforms available observations; it never
        # learns statistics from this person's query/support/future rows.
        query_x, pool_x = self.transform(queries), self.transform(pool)
        positions = {key: i for i, key in enumerate(pool["row_key"])}
        records = [histories[key] if self.candidate["ridge_regularization"] is not None else [] for key in queries["row_key"]]
        maximum = max(1, max(map(len, records), default=0))
        support_x = torch.zeros((len(queries), maximum, query_x.shape[1]), dtype=torch.float32)
        support_delta = torch.zeros((len(queries), maximum), dtype=torch.int64)
        support_weight = torch.zeros((len(queries), maximum), dtype=torch.float32)
        for i, observations in enumerate(records):
            for j, observation in enumerate(observations):
                key, age = observation["row_key"], observation["age_minutes"]
                if key not in positions or not np.isfinite(age) or age < 1 or key == queries.iloc[i]["row_key"]:
                    raise ValueError("Missing/current/future support is not personal calibration")
                index = positions[key]
                if pool.iloc[index]["group_key"] != queries.iloc[i]["group_key"]:
                    raise ValueError("Personal calibration received another participant's outcome")
                old = pool.iloc[[index]]
                validate_calibration(old)
                delta = int(native_targets(old)[0]) - int(old.iloc[0]["prior_borg"])
                support_x[i, j] = pool_x[index]
                support_delta[i, j] = delta + 10
                support_weight[i, j] = math.exp(-age / 20.)
        prior = torch.tensor(queries["prior_borg"].to_numpy(), dtype=torch.float32)
        return query_x, support_x, support_delta, support_weight, prior

    def fit(self, frame, histories):
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(42)
        np.random.seed(42)
        validate_calibration(frame)
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True)
        self.scaler = StandardScaler().fit(self.imputer.fit_transform(frame[self.candidate["features"]]))
        inputs = self.batch(frame, frame, histories)
        targets = torch.tensor(native_targets(frame), dtype=torch.int64)
        self.model = AdaptiveNetwork(inputs[0].shape[1], self.candidate["width"], self.candidate["ridge_regularization"])
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=.01, weight_decay=.03)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.candidate["epochs"], eta_min=.001)
        self.model.train()
        for epoch in range(self.candidate["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            probability = self.model(*inputs)
            loss = -torch.log(probability[torch.arange(len(targets)), targets].clamp_min(1e-12)).mean()
            loss.backward()
            nn.utils.clip_grad_norm_(self.model.parameters(), 5.)
            optimizer.step()
            scheduler.step()
        self.final_training_loss = float(loss.detach())
        self.model.eval()
        return self

    def predict(self, frame, pool, histories):
        with torch.no_grad():
            scores = self.model(*self.batch(frame, pool, histories))
        return np.asarray([f"Borg {i}" for i in scores.argmax(dim=1).tolist()])


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    compact = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    candidates = []
    for name, features in (("prior_context", prior), ("compact_dynamics", compact)):
        for width in (8, 16):
            for ridge in (1., 10.):
                for epochs in (80, 200):
                    for scope in ("task", "session"):
                        candidates.append({"id": f"meta-{len(candidates):03d}", "feature_set": name, "features": features,
                                           "width": width, "ridge_regularization": ridge, "epochs": epochs, "scope": scope,
                                           "optimizer": "AdamW", "learning_rate": .01, "random_state": 42})
        candidates.append({"id": f"meta-{len(candidates):03d}", "feature_set": name, "features": features, "width": 16,
                           "ridge_regularization": None, "epochs": 200, "scope": "task",
                           "optimizer": "AdamW", "learning_rate": .01, "random_state": 42})
    return candidates


def select(smoke=False):
    frame, train, _, manifest, _ = load_inputs()
    metadata = temporal_metadata(frame, manifest)
    histories = {scope: context_keys(frame, metadata, scope) for scope in ("task", "session")}
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    candidates = plan(manifest)
    if smoke:
        fit, val = folds[0]
        started = time.monotonic()
        candidate = candidates[0]
        model = MetaAdaptiveBorg(candidate).fit(train.iloc[fit], histories[candidate["scope"]])
        predicted = model.predict(train.iloc[val[:8]], frame, histories[candidate["scope"]])
        if len(predicted) != 8 or not set(predicted) <= {f"Borg {i}" for i in range(11)}:
            raise ValueError("Differentiable adaptation runtime probe failed")
        print(f"Meta-adaptation CPU probe: {len(fit)} fit rows / 8 predictions / {time.monotonic()-started:.2f}s; no benchmark test used", flush=True)
        return
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"], "plan": candidates,
                 "dynamics_provenance_sha256": digest(RESEARCH / "dynamics-80-v1/provenance.json"),
                 "session_metadata_sha256": digest(RAW / "geofatigue/session_metadata.json"),
                 "context_index_sha256": hashlib.sha256(json.dumps(histories, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                 "history_metadata_code_sha256": digest(Path(__file__).with_name("fatigue_online_calibration.py")),
                 "dynamics_plan_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py")),
                 "train_row_keys": train["row_key"].tolist(), "torch_version": str(torch.__version__)}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True, "synthetic_rows": 0,
              "validation_person_outcomes_are_inputs_only_when_actually_recorded_earlier": True,
              "adaptation_policy": "Actual same-person same-session canonical reports at least one minute before the query. Current/future outcomes and other people never enter adaptation. The original 487 validation responses remain the denominator."}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the frozen adaptation study before changing its inputs")
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    folder = DIRECTORY / "folds"
    folder.mkdir(exist_ok=True)
    for candidate in candidates:
        if any(row["candidate"] == candidate for row in report["results"]):
            continue
        predicted = np.empty(len(train), dtype=object)
        losses = []
        for fold, (fit, val) in enumerate(folds):
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise ValueError("Meta-learning base fit leaked validation people")
            evidence = {"code_sha256": signature["code_sha256"], "dataset_sha256": manifest["dataset_sha256"], "candidate": candidate,
                        "fit_row_keys": train.iloc[fit]["row_key"].tolist(), "validation_row_keys": train.iloc[val]["row_key"].tolist()}
            fold_path = folder / f"{candidate['id']}-fold-{fold}.json"
            if fold_path.exists():
                saved = json.loads(fold_path.read_text(encoding="utf-8"))
                if any(saved.get(k) != v for k, v in evidence.items()):
                    raise ValueError("Frozen adaptation fold membership/inputs changed")
                values, loss = np.asarray(saved["predicted"]), saved["final_training_loss"]
            else:
                context = histories[candidate["scope"]]
                model = MetaAdaptiveBorg(candidate).fit(train.iloc[fit], context)
                values = model.predict(train.iloc[val], frame, context)
                loss = model.final_training_loss
                fold_path.write_text(json.dumps({**evidence, "predicted": values.tolist(), "final_training_loss": loss}, indent=2) + "\n", encoding="utf-8")
            predicted[val] = values
            losses.append(loss)
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(),
                                  "fold_training_losses": losses})
        best = max(report["results"], key=lambda row: row["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"Learned personal adaptation {len(report['results'])}/{len(candidates)}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    select(parser.parse_args().smoke)
