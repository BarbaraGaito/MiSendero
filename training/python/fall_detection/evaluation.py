"""Metrics shared by every detector (fall = positive class)."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score


def counts(y: np.ndarray, pred: np.ndarray) -> dict:
    y, pred = np.asarray(y).astype(bool), np.asarray(pred).astype(bool)
    return {"tp": int(np.sum(y & pred)), "fp": int(np.sum(~y & pred)),
            "fn": int(np.sum(y & ~pred)), "tn": int(np.sum(~y & ~pred))}


def from_counts(c: dict) -> dict:
    tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]
    div = lambda a, b: float(a / b) if b else 0.0
    precision, recall = div(tp, tp + fp), div(tp, tp + fn)
    specificity = div(tn, tn + fp)
    f1_fall = div(2 * precision * recall, precision + recall)
    precision_adl, f1_adl = div(tn, tn + fn), 0.0
    f1_adl = div(2 * precision_adl * specificity, precision_adl + specificity)
    beta2 = 4.0
    f2 = div((1 + beta2) * precision * recall, beta2 * precision + recall)
    return {"precision": precision, "recall": recall, "specificity": specificity, "f1": f1_fall, "f2": f2,
            "f1_macro": (f1_fall + f1_adl) / 2, "confusion_matrix": [[tn, fp], [fn, tp]],
            "confusion_matrix_labels": ["no_fall", "fall"], **c}


def f2_score(y: np.ndarray, pred: np.ndarray) -> float:
    return from_counts(counts(y, pred))["f2"]


def summarize(y, pred, score=None) -> dict:
    out = from_counts(counts(y, pred))
    if score is not None and len(set(np.asarray(y).tolist())) == 2:
        out["pr_auc"] = float(average_precision_score(y, score))
    return out


def bootstrap_by_participant(y, pred, participants, draws: int = 1000, seed: int = 20261022) -> dict:
    """95 % interval from resampling participants (the unit that must generalise), not windows."""
    y, pred, participants = np.asarray(y), np.asarray(pred), np.asarray(participants)
    ids = np.unique(participants)
    per = {p: counts(y[participants == p], pred[participants == p]) for p in ids}
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(draws):
        pick = rng.choice(ids, size=len(ids), replace=True)
        total = {k: sum(per[p][k] for p in pick) for k in ("tp", "fp", "fn", "tn")}
        rows.append(from_counts(total))
    interval = lambda key: [float(np.percentile([r[key] for r in rows], 2.5)),
                            float(np.percentile([r[key] for r in rows], 97.5))]
    return {key: interval(key) for key in ("precision", "recall", "specificity", "f1", "f1_macro")} | {"draws": draws}
