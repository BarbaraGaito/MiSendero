"""Train the deployment model on all 30 participants and export it with parity fixtures.

* the decision threshold comes from out-of-fold scores of GroupKFold(10) over all participants;
* the model file is plain JSON consumed by `services/fallDetection/model.ts` (no native runtime);
* `testing/fixtures/fall-detection/parity.json` holds small excerpts of the real UniMiB SHAR records
  (windows and short segments) plus the Python results the TypeScript pipeline must reproduce.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
from sklearn.model_selection import GroupKFold
from xgboost import XGBClassifier

from .candidates import candidate_peaks, extract_candidates
from .config import POST_SAMPLES, PRE_SAMPLES, WINDOW
from .dataset import ROOT, load_records, summarize
from .export_contract import TARGET as CONTRACT_PATH, contract
from .features import FEATURE_ORDER, magnitude, window_features
from .run_loso import OUT, SEED, best_threshold, make_model

MODEL_PATH = ROOT / "services/fallDetection/fallModel.json"
FIXTURE_PATH = ROOT / "testing/fixtures/fall-detection/parity.json"
MODEL_ID = "misendero-fall-xgboost-unimib-shar"
MODEL_VERSION = "2026.10.22-exp1"


def shortest32(value: float) -> float:
    return float(np.format_float_positional(np.float32(value), unique=True, trim="-"))


def export_xgboost(model: XGBClassifier) -> dict:
    document = json.loads(bytes(model.get_booster().save_raw(raw_format="json")))
    learner = document["learner"]
    base = learner["learner_model_param"]["base_score"]
    base = float(base.strip("[]")) if isinstance(base, str) else float(base)
    trees = []
    for tree in learner["gradient_booster"]["model"]["trees"]:
        left, right, split = tree["left_children"], tree["right_children"], tree["split_indices"]
        cond, default_left = tree["split_conditions"], tree["default_left"]
        if any(default_left[i] == 0 and left[i] != -1 and False for i in range(len(left))):
            raise AssertionError
        feature = [int(split[i]) if left[i] != -1 else -1 for i in range(len(left))]
        trees.append({"feature": feature,
                      "threshold": [shortest32(cond[i]) if left[i] != -1 else 0 for i in range(len(left))],
                      "yes": [int(x) if x != -1 else -1 for x in left], "no": [int(x) if x != -1 else -1 for x in right],
                      "leaf": [shortest32(cond[i]) if left[i] == -1 else 0 for i in range(len(left))]})
    return {"base_margin": float(np.log(base / (1 - base))), "trees": trees}


def evaluate_exported(exported: dict, X: np.ndarray) -> np.ndarray:
    """Reference evaluator mirroring model.ts (float32 comparison, float64 accumulation)."""
    out = np.zeros(len(X))
    for row, vector in enumerate(X):
        margin = exported["base_margin"]
        for tree in exported["trees"]:
            node = 0
            while tree["feature"][node] >= 0:
                node = tree["yes"][node] if np.float32(vector[tree["feature"][node]]) < np.float32(tree["threshold"][node]) else tree["no"][node]
            margin += tree["leaf"][node]
        out[row] = 1 / (1 + np.exp(-margin))
    return out


def main() -> None:
    records, audit = load_records()
    candidates, X = extract_candidates(records)
    kind = np.array([c.kind for c in candidates]); main_impact = np.array([c.main_impact for c in candidates])
    has_window = np.array([c.has_window for c in candidates]); participant = np.array([c.participant for c in candidates])
    activity = np.array([c.activity for c in candidates])
    labelled = has_window & ((kind == "adl") | main_impact)
    Xl, yl, gl = X[labelled], (kind[labelled] == "fall").astype(int), participant[labelled]

    oof = np.zeros(len(yl))
    for fit_idx, val_idx in GroupKFold(n_splits=10).split(Xl, yl, gl):
        inner = make_model("xgboost", int(yl[fit_idx].sum()), int((1 - yl[fit_idx]).sum()))
        inner.fit(Xl[fit_idx], yl[fit_idx])
        oof[val_idx] = inner.predict_proba(Xl[val_idx])[:, 1]
    threshold = best_threshold(yl, oof)
    model = make_model("xgboost", int(yl.sum()), int((1 - yl).sum()))
    model.fit(Xl, yl)
    exported = export_xgboost(model)
    reference = evaluate_exported(exported, Xl)
    native = model.predict_proba(Xl)[:, 1]
    max_diff = float(np.max(np.abs(reference - native)))
    if max_diff > 1e-5:
        raise AssertionError(f"exported trees differ from xgboost by {max_diff}")
    print(f"threshold={threshold} trees={len(exported['trees'])} export max |diff|={max_diff:.2e}", flush=True)

    loso = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))["models"]["xgboost"]
    summary = {key: loso["nested_threshold"][key] for key in ("precision", "recall", "specificity", "f1", "f1_macro", "pr_auc")}
    file = {
        "schema_version": 1, "id": MODEL_ID, "version": MODEL_VERSION, "algorithm": "xgboost",
        "status": "experimental", "deployment_approved": False,
        "trained_at": datetime.now(timezone.utc).isoformat(), "threshold": threshold,
        "feature_order": FEATURE_ORDER, "xgboost": exported,
        "provenance": {
            "dataset": "UniMiB SHAR (Micucci, Mobilio, Napoletano 2017)", "source": "https://www.sal.disco.unimib.it/technologies/unimib-shar/",
            "archive_sha256": summarize(records, audit)["archive_sha256"],
            "participants": 30, "training_candidates": int(len(yl)), "fall_positives": int(yl.sum()), "adl_negatives": int((1 - yl).sum()),
            "phone_position": "trouser pocket (right/left); no other position was trained or tested",
            "evidence": "leave-one-participant-out of this model family: see training/data/public/fall_detection/metrics.json",
            "loso_summary": summary,
            "limits": "Experimental falls performed by 30 volunteers (18-60 y, 24 F / 6 M); not real hiking accidents. No claim of safety performance."},
    }
    MODEL_PATH.write_text(json.dumps(file, separators=(",", ":")) + "\n", encoding="utf-8")
    print("wrote", MODEL_PATH, MODEL_PATH.stat().st_size, "bytes", flush=True)

    # ---- parity fixtures: real excerpts, 6-decimal values; expectations recomputed from the rounded values
    rng = np.random.default_rng(SEED)
    windows = []
    labelled_idx = np.where(labelled)[0]
    picks = []
    for act in ["FallingForw", "FallingBack", "FallingRight", "FallingLeft", "Syncope", "HittingObstacle",
                "Walking", "Running", "GoingUpS", "Jumping", "SittingDown", "LyingDownFS", "StandingUpFS", "StandingUpFL"]:
        pool = [i for i in labelled_idx if activity[i] == act]
        picks += list(rng.choice(pool, size=3, replace=False))
    for i in picks:
        c = candidates[i]
        record = records[c.record_index]
        raw = np.round(record.xyz_g[c.peak - PRE_SAMPLES:c.peak + POST_SAMPLES + 1], 6)
        features = window_features(raw)
        windows.append({"activity": c.activity, "label": c.kind, "xyz": raw.ravel().tolist(), "features": features.tolist(),
                        "probability": float(model.predict_proba(features.reshape(1, -1))[0, 1])})
    segments = []
    for act, count in (("FallingBack", 3), ("FallingForw", 2), ("Syncope", 1), ("Jumping", 2), ("SittingDown", 2), ("Running", 1)):
        pool = [k for k, r in enumerate(records) if r.activity == act and len(r.xyz_g) <= 400]
        if act in ("Jumping", "Running"):
            pool = [k for k, r in enumerate(records) if r.activity == act]
        for k in rng.choice(pool, size=count, replace=False):
            record = records[k]
            xyz = np.round(record.xyz_g[:400], 6)
            m = magnitude(xyz)
            expected = []
            for peak in candidate_peaks(m):
                if peak >= PRE_SAMPLES and peak + POST_SAMPLES < len(m):
                    f = window_features(xyz[peak - PRE_SAMPLES:peak + POST_SAMPLES + 1])
                    expected.append({"peak": int(peak), "peak_g": float(m[peak]),
                                     "probability": float(model.predict_proba(f.reshape(1, -1))[0, 1])})
            segments.append({"activity": record.activity, "samples": len(xyz), "xyz": xyz.ravel().tolist(), "expected_candidates": expected})
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps({
        "source": "Excerpts of the public UniMiB SHAR dataset (cite Micucci et al. 2017) kept only to verify Python/TypeScript equivalence.",
        "units": "g, gravity included, 50 Hz", "model_id": MODEL_ID, "model_version": MODEL_VERSION,
        "windows": windows, "segments": segments}, separators=(",", ":")) + "\n", encoding="utf-8")
    print("wrote", FIXTURE_PATH, FIXTURE_PATH.stat().st_size, "bytes; windows", len(windows), "segments", len(segments), flush=True)


if __name__ == "__main__":
    main()
