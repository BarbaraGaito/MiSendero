"""Light 1D-CNN under the same nested leave-one-participant-out protocol as run_loso.py.

Inputs are orientation-invariant like the tree models: the acceleration magnitude and the cosine
between each instantaneous acceleration vector and the mean pre-impact gravity vector.
Evaluation only: the CNN is deployed only if it is clearly better than the tree models (see docs).
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import torch
from torch import nn
from sklearn.model_selection import GroupKFold

from .candidates import candidate_peaks
from .config import PRE_SAMPLES, POST_SAMPLES, WINDOW
from .dataset import ROOT, load_records
from .evaluation import summarize
from .features import PRE_FAR, magnitude
from .run_loso import SEED, THRESHOLD_GRID, best_threshold, pooled_report, OUT

EPOCHS = 40
BATCH = 128


def channels(window: np.ndarray) -> np.ndarray:
    m = magnitude(window)
    ref = window[PRE_FAR[0]:PRE_FAR[1]].mean(axis=0)
    n = np.sqrt(np.sum(ref * ref))
    cosine = (window @ ref) / (np.maximum(m, 1e-9) * max(n, 1e-9))
    return np.stack([m, cosine]).astype(np.float32)


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv1d(2, 16, 5, padding=2), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(16, 32, 5, padding=2), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(32, 32, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool1d(1), nn.Flatten(), nn.Linear(32, 1))

    def forward(self, x):
        return self.body(x).squeeze(-1)


def fit_predict(Xtr, ytr, Xte_list, seed=SEED):
    torch.manual_seed(seed)
    net = Net()
    optimiser = torch.optim.Adam(net.parameters(), lr=2e-3)
    weight = torch.tensor(float((1 - ytr).sum() / max(ytr.sum(), 1)))
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=weight)
    x, y = torch.from_numpy(Xtr), torch.from_numpy(ytr.astype(np.float32))
    rng = np.random.default_rng(seed)
    for _ in range(EPOCHS):
        order = rng.permutation(len(x))
        for start in range(0, len(x), BATCH):
            index = torch.from_numpy(order[start:start + BATCH])
            optimiser.zero_grad()
            loss_fn(net(x[index]), y[index]).backward()
            optimiser.step()
    net.eval()
    with torch.no_grad():
        return [torch.sigmoid(net(torch.from_numpy(item))).numpy() for item in Xte_list]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(4)
    started = time.time()
    records, _ = load_records()
    rows, meta = [], []
    for index, record in enumerate(records):
        m = magnitude(record.xyz_g)
        top = int(np.argmax(m))
        for peak in candidate_peaks(m):
            if peak < PRE_SAMPLES or peak + POST_SAMPLES >= len(m):
                continue
            if record.kind == "fall" and peak != top:
                continue
            rows.append(channels(record.xyz_g[peak - PRE_SAMPLES:peak + POST_SAMPLES + 1]))
            meta.append((record.participant, record.activity, record.kind, record.pocket))
    X = np.stack(rows)
    participant = np.array([r[0] for r in meta]); activity = np.array([r[1] for r in meta])
    y = np.array([r[2] == "fall" for r in meta]).astype(int); pocket = np.array([r[3] for r in meta])
    people = list(range(30))[:3] if args.quick else list(range(30))
    score = np.full(len(y), np.nan); alarm = np.zeros(len(y), bool); taus = {}
    for person in people:
        train, test = participant != person, participant == person
        Xtr, ytr, gtr = X[train], y[train], participant[train]
        oof = np.zeros(len(ytr))
        for fit_idx, val_idx in GroupKFold(n_splits=5).split(Xtr, ytr, gtr):
            oof[val_idx] = fit_predict(Xtr[fit_idx], ytr[fit_idx], [Xtr[val_idx]])[0]
        tau = best_threshold(ytr, oof)
        p = fit_predict(Xtr, ytr, [X[test]])[0]
        score[test], alarm[test], taus[str(person)] = p, p >= tau, tau
        print(f"participant {person:2d} tau={tau:.2f} ({time.time() - started:.0f}s)", flush=True)
    mask = np.isin(participant, people)
    report = pooled_report("cnn_1d", y[mask], alarm[mask], score[mask], participant[mask], activity[mask], pocket[mask])
    report["selected_threshold_per_participant"] = taus
    report["architecture"] = {"input": "2 x 61 (magnitude, cosine to pre-impact gravity)", "parameters": int(sum(p.numel() for p in Net().parameters())),
                              "epochs": EPOCHS, "batch": BATCH, "optimizer": "Adam lr 2e-3", "loss": "BCE with class weight (no resampling)"}
    out = OUT / ("metrics_cnn.quick.json" if args.quick else "metrics_cnn.json")
    out.write_text(json.dumps({"cnn_1d": report, "elapsed_seconds": round(time.time() - started, 1)}, indent=2, default=float) + "\n", encoding="utf-8")
    s = report
    print(f"cnn_1d P={s['precision']:.3f} R={s['recall']:.3f} Spec={s['specificity']:.3f} F1={s['f1']:.3f} "
          f"F1macro={s['f1_macro']:.3f} PR-AUC={s['pr_auc']:.3f}", flush=True)


if __name__ == "__main__":
    main()
