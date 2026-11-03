"""Participant-held-out GRU forecasts using only real earlier Borg reports.

Backpropagation and AdamW fit the query head and recurrent history encoder.
The current label is used only in fitting loss, never in a predictor token.
No synthetic examples, report interpolation or test-based early stopping.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence

from fatigue_dynamics import CONTEXT, load_inputs
from fatigue_features import RESEARCH
from fatigue_trajectory_bank import TERRAINS, build_queries, observed_source
from public_sources import digest

DIRECTORY = RESEARCH / "recurrent-feedback-80-v1"
TOKEN_FEATURES = ["observed_borg_div10", "elapsed_div30", "age_div60", "delta_borg_div10",
                  "interval_div15", *["terrain_" + t for t in TERRAINS], "same_current_terrain"]


def history_tokens(query):
    rows = query["history"]
    prior, age = query["prior_borg"], query["prior_age_minutes"]
    if not rows or not 1 <= age <= 15 or not np.isfinite(prior) or prior != round(prior) or not 0 <= prior <= 10:
        raise ValueError("Actual recent native previous Borg is mandatory")
    tokens = []
    previous = None
    for row in rows:
        borg, old_age = row["observed_borg"], row["age_minutes"]
        if not np.isfinite(borg) or borg != round(borg) or not 0 <= borg <= 10 or old_age < 1:
            raise ValueError("Current, future or non-native feedback cannot enter the encoder")
        if previous is not None and old_age >= previous["age_minutes"]:
            raise ValueError("Feedback must be strictly chronological")
        tokens.append([borg / 10., row["elapsed_minutes"] / 30., old_age / 60.,
                       0. if previous is None else (borg - previous["observed_borg"]) / 10.,
                       0. if previous is None else (previous["age_minutes"] - old_age) / 15.,
                       *[float(row["terrain"] == t) for t in TERRAINS], float(row["terrain"] == query["terrain"])])
        previous = row
    return np.asarray(tokens, dtype=np.float32)


def padded_histories(queries):
    tokens = [history_tokens(q) for q in queries]
    lengths = torch.tensor([len(t) for t in tokens], dtype=torch.int64)
    padded = torch.zeros((len(tokens), int(lengths.max()), len(TOKEN_FEATURES)), dtype=torch.float32)
    for i, values in enumerate(tokens):
        padded[i, :len(values)] = torch.from_numpy(values)
    return padded, lengths


class HistoryNetwork(nn.Module):
    def __init__(self, n_features, width, use_history=True):
        super().__init__()
        self.use_history = use_history
        self.encoder = nn.GRU(len(TOKEN_FEATURES), width, batch_first=True) if use_history else None
        self.head = nn.Sequential(nn.Linear(n_features + (width if use_history else 0), width), nn.Tanh(), nn.Dropout(.1), nn.Linear(width, 21))

    def forward(self, query, history, lengths, prior):
        if self.use_history:
            _, encoded = self.encoder(pack_padded_sequence(history, lengths.cpu(), batch_first=True, enforce_sorted=False))
            query = torch.cat((query, encoded[-1]), dim=1)
        scores = torch.softmax(self.head(query), dim=1)
        destinations = (prior.long()[:, None] + torch.arange(-10, 11)[None, :]).clamp(0, 10)
        # Edge deltas combine probability mass at the native scale boundary.
        return torch.zeros((len(query), 11), dtype=scores.dtype).scatter_add(1, destinations, scores)


class RecurrentBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def transform(self, frame):
        return torch.tensor(self.scaler.transform(self.imputer.transform(frame[self.candidate["features"]])), dtype=torch.float32)

    def fit(self, frame, queries):
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(42)
        np.random.seed(42)
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True)
        self.scaler = StandardScaler().fit(self.imputer.fit_transform(frame[self.candidate["features"]]))
        query = self.transform(frame)
        history, lengths = padded_histories(queries)
        prior = torch.tensor(frame["prior_borg"].to_numpy(), dtype=torch.float32)
        truth = torch.tensor(frame["label"].str.removeprefix("Borg ").astype(int).to_numpy(), dtype=torch.int64)
        self.model = HistoryNetwork(query.shape[1], self.candidate["width"], self.candidate["use_history"])
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=.01, weight_decay=self.candidate["weight_decay"])
        self.model.train()
        for epoch in range(self.candidate["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            probabilities = self.model(query, history, lengths, prior)
            loss = -torch.log(probabilities[torch.arange(len(truth)), truth].clamp_min(1e-12)).mean()
            loss.backward()
            nn.utils.clip_grad_norm_(self.model.parameters(), 5.)
            optimizer.step()
        self.model.eval()
        self.training_rows = len(frame)
        self.final_training_loss = float(loss.detach())
        return self

    def predict(self, frame, queries):
        with torch.no_grad():
            history, lengths = padded_histories(queries)
            scores = self.model(self.transform(frame), history, lengths, torch.tensor(frame["prior_borg"].to_numpy()))
        return np.asarray([f"Borg {i}" for i in scores.argmax(dim=1).tolist()])


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    physiology = ["hr_last", "hr_delta_baseline", "hr_change_after_prior", "hr_recent_slope", "prior_history_mean", "prior_history_std"]
    recipes = []
    for name, features in (("prior_context", prior), ("prior_physiology", prior + physiology)):
        for width in (8, 24):
            for decay in (.01, .1):
                for epochs in (80, 200):
                    recipes.append({"id": f"gru-{len(recipes):03d}", "features": features, "feature_set": name,
                                    "width": width, "weight_decay": decay, "epochs": epochs, "use_history": True,
                                    "optimizer": "AdamW", "learning_rate": .01, "random_state": 42})
        recipes.append({"id": f"gru-{len(recipes):03d}", "features": features, "feature_set": name,
                        "width": 24, "weight_decay": .1, "epochs": 200, "use_history": False,
                        "optimizer": "AdamW", "learning_rate": .01, "random_state": 42})
    return recipes


def select():
    frame, train, _, manifest, _ = load_inputs()
    reports, sessions = observed_source()
    queries = build_queries(frame, reports, sessions)
    training_queries = [queries[i] for i in train.index]
    recipes = plan(manifest)
    signature = {"code_sha256": digest(Path(__file__)), "query_source_code_sha256": digest(Path(__file__).with_name("fatigue_trajectory_bank.py")),
                 "dataset_sha256": manifest["dataset_sha256"], "plan": recipes, "train_row_keys": train["row_key"].tolist(),
                 "torch_version": str(torch.__version__), "token_features": TOKEN_FEATURES}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "synthetic_rows": 0, "interpolated_supervision_rows": 0}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the frozen recurrent study before changing inputs or code")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in recipes:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted = np.empty(len(train), dtype=object)
        losses = []
        for fit, val in folds:
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise ValueError("Recurrent fitting participants overlap validation")
            model = RecurrentBorg(candidate).fit(train.iloc[fit], [training_queries[i] for i in fit])
            predicted[val] = model.predict(train.iloc[val], [training_queries[i] for i in val])
            losses.append(model.final_training_loss)
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)),
                                  "oof_predictions": predicted.tolist(), "fold_final_training_loss": losses})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(recipes) else "running")
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"Recurrent {len(report['results'])}/{len(recipes)}: current CV={np.mean(scores):.6f}, best CV={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
