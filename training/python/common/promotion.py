"""A research publication gate, separate from train-only hyperparameter choice.

The holdout is used for this replacement decision. Published comparisons are
therefore descriptive and require a fresh external study for confirmation.
"""
from __future__ import annotations


def publication_decision(incumbent, candidate):
    result = {"test_used_for_promotion": incumbent is not None,
              "rule": "retain incumbent if fixed-holdout accuracy or macro F1 decreases",
              "interpretation": "A one-shot publication decision uses the already published holdout; resulting metrics are descriptive, not a fresh independent estimate."}
    if incumbent is None:
        return {**result, "decision": "published_new_evaluation"}
    same_rows = all(incumbent["evaluation_protocol"][key] == candidate["evaluation_protocol"][key]
                    for key in ("train_row_keys", "test_row_keys", "train_groups", "test_groups"))
    same_rows = same_rows and incumbent["evaluation_protocol"].get("provenance_sha256") == candidate["evaluation_protocol"].get("provenance_sha256")
    if not same_rows or incumbent["dataset"]["features"] != candidate["dataset"]["features"]:
        return {**result, "decision": "published_new_evaluation", "test_used_for_promotion": False,
                "reason": "Different data/features/partitions; no directly comparable incumbent score."}
    before, after = incumbent["metrics"]["test"], candidate["metrics"]["test"]
    delta = {key: after[key] - before[key] for key in ("accuracy", "f1_macro")}
    return {**result, "decision": "retained_incumbent" if any(v < -1e-12 for v in delta.values()) else "published_candidate",
            "before": {key: before[key] for key in delta}, "after": {key: after[key] for key in delta}, "delta": delta}
