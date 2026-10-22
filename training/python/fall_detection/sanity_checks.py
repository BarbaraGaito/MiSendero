"""Sanity checks on the candidate-level result (GroupKFold by participant, Random Forest).

* permuted labels must collapse to chance (PR-AUC ~ prevalence);
* feature-group ablations show what the classifier depends on;
* a "no gate-like energy" ablation removes the peak magnitude features so the result cannot be a
  trivial threshold on the impact.
"""
from __future__ import annotations

import json

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict

from .candidates import extract_candidates
from .dataset import load_records
from .features import FEATURE_ORDER
from .run_loso import OUT, SEED

GROUPS = {
    "all_features": [],
    "without_orientation_change": ["angle_deg", "gravity_pre", "gravity_post"],
    "without_pre_impact_context": [n for n in FEATURE_ORDER if n.startswith(("pre_far", "pre_near", "energy_pre", "peaks_pre", "peak_over_pre"))] + ["gravity_pre", "angle_deg"],
    "without_post_impact": [n for n in FEATURE_ORDER if n.startswith(("post", "energy_post"))] + ["angle_deg", "gravity_post"],
    "without_peak_magnitude": ["m_max", "m_range", "impact_max", "impact_mean", "peak_over_pre_rms", "jerk_max", "jerk_impact"],
    "without_free_fall": ["freefall_min", "freefall_samples", "m_min", "impact_min", "pre_near_min"],
    "magnitude_peak_only": None,
}


def main() -> None:
    records, _ = load_records()
    candidates, X = extract_candidates(records)
    kind = np.array([c.kind for c in candidates]); main_impact = np.array([c.main_impact for c in candidates])
    has_window = np.array([c.has_window for c in candidates]); participant = np.array([c.participant for c in candidates])
    labelled = has_window & ((kind == "adl") | main_impact)
    X, y, g = X[labelled], (kind[labelled] == "fall").astype(int), participant[labelled]
    cv = GroupKFold(n_splits=6)
    out = {"protocol": "GroupKFold(6) by participant, Random Forest 200 trees; diagnostic only, not the reported result", "prevalence": float(y.mean())}
    for name, drop in GROUPS.items():
        keep = [i for i, n in enumerate(FEATURE_ORDER) if (n == "m_max" if drop is None else n not in drop)]
        p = cross_val_predict(RandomForestClassifier(200, min_samples_leaf=2, n_jobs=-1, random_state=SEED, class_weight="balanced_subsample"),
                              X[:, keep], y, groups=g, cv=cv, method="predict_proba")[:, 1]
        out[name] = {"features": len(keep), "pr_auc": float(average_precision_score(y, p)), "roc_auc": float(roc_auc_score(y, p))}
        print(name, out[name], flush=True)
    rng = np.random.default_rng(SEED)
    scores = []
    for _ in range(5):
        shuffled = rng.permutation(y)
        p = cross_val_predict(RandomForestClassifier(200, min_samples_leaf=2, n_jobs=-1, random_state=SEED, class_weight="balanced_subsample"),
                              X, shuffled, groups=g, cv=cv, method="predict_proba")[:, 1]
        scores.append(float(average_precision_score(shuffled, p)))
    out["permuted_labels_pr_auc"] = {"runs": scores, "mean": float(np.mean(scores))}
    print("permuted", out["permuted_labels_pr_auc"], flush=True)
    (OUT / "sanity_checks.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
