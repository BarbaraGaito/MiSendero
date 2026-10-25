"""Paired, descriptive before/after comparison on the unchanged public holdout.

This command never fits or selects a model. Bootstrap units are independent
participants/regions/parks, never individual windows of the same participant.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common.evaluation import _summary_metrics
from public_sources import OUTPUT, ROOT, digest


def paired_group_bootstrap(observed, before, after, groups, labels, *, repetitions=2000):
    units = sorted(set(groups))
    if len(units) < 2:
        return {"independent_groups": len(units), "intervals": None,
                "reason": "One held-out group cannot estimate variation across independent groups."}
    label_index = {label: i for i, label in enumerate(labels)}
    group_index = {group: i for i, group in enumerate(units)}
    matrices = np.zeros((2, len(units), len(labels), len(labels)))
    for i, (truth, a, b, group) in enumerate(zip(observed, before, after, groups)):
        matrices[0, group_index[group], label_index[truth], label_index[a]] += 1
        matrices[1, group_index[group], label_index[truth], label_index[b]] += 1
    rng = np.random.default_rng(42)
    weights = rng.multinomial(len(units), np.full(len(units), 1 / len(units)), size=repetitions)
    samples = np.einsum("bg,mglk->mblk", weights, matrices)
    tp = np.diagonal(samples, axis1=2, axis2=3)
    denominator = samples.sum(axis=2) + samples.sum(axis=3)
    f1 = np.divide(2 * tp, denominator, out=np.zeros_like(tp), where=denominator > 0).mean(axis=2)
    accuracy = tp.sum(axis=2) / samples.sum(axis=(2, 3))
    return {"method": "paired_percentile_cluster_bootstrap", "seed": 42, "repetitions": repetitions,
            "independent_groups": len(units), "confidence_level": 0.95,
            "intervals": {key: np.quantile(values[1] - values[0], [0.025, 0.975]).tolist()
                          for key, values in {"accuracy_delta": accuracy, "f1_macro_delta": f1}.items()},
            "interpretation": "Descriptive uncertainty on the already published holdout; does not replace new external validation."}


def compare(baseline_path: Path, candidates_path: Path | None = None):
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidates = json.loads(candidates_path.read_text(encoding="utf-8")) if candidates_path else {}
    result = {"selection_used_test": False, "holdout_used_for_publication": False,
              "datasets_combined": False, "models": {}}
    for name, previous in baseline["models"].items():
        directory = ROOT / candidates[name]["candidate_directory"] if name in candidates else OUTPUT / name
        old = previous["metrics"]
        new = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        decision = candidates.get(name, new.get("publication_decision", {}))
        result["holdout_used_for_publication"] |= bool(decision.get("test_used_for_promotion"))
        before_path = baseline_path.parent / "baseline-predictions" / f"{name}.csv"
        if digest(before_path) != previous["files"]["test_predictions.csv"]:
            raise ValueError("Original prediction evidence changed")
        if any(digest(directory / field) != previous["files"][field] for field in ("dataset.csv", "provenance.json")):
            raise ValueError("Dataset or source lineage changed: direct paired comparison would be invalid")
        if any(old["evaluation_protocol"][key] != new["evaluation_protocol"][key]
               for key in ("train_row_keys", "test_row_keys", "train_groups", "test_groups")):
            raise ValueError("Original train/test partitions changed")
        before = pd.read_csv(before_path, dtype=str).set_index("row_key")
        after = pd.read_csv(directory / "test_predictions.csv", dtype=str).set_index("row_key")
        if set(before.index) != set(after.index) or not before["observed"].equals(after.loc[before.index, "observed"]):
            raise ValueError("Paired test observations changed")
        after = after.loc[before.index]
        for predictions, metrics in ((before, old), (after, new)):
            if _summary_metrics(predictions["observed"], predictions["predicted"], old["labels"]) != metrics["metrics"]["test"]:
                raise ValueError("Comparison metric differs from saved predictions")
        provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
        group_by_key = {row["row_key"]: row["group_key"] for row in provenance["lineage"]}
        groups = [group_by_key[key] for key in before.index]
        a, b = before["predicted"] == before["observed"], after["predicted"] == after["observed"]
        result["models"][name] = {
            "algorithm": new.get("model_artifact", {}).get("algorithm", "random_forest"), "rows": new["dataset"]["rows_total"],
            "publication_decision": candidates.get(name, {}).get("decision", "not_recorded"),
            "test_rows": len(before), "test_groups": len(set(groups)),
            "before": old["metrics"]["test"], "after": new["metrics"]["test"],
            "delta": {key: new["metrics"]["test"][key] - old["metrics"]["test"][key]
                      for key in ("accuracy", "precision_macro", "recall_macro", "f1_macro")},
            "cv_before": old["metrics"]["cross_validation"]["f1_macro_mean"],
            "cv_after": new["metrics"]["cross_validation"]["f1_macro_mean"],
            "corrected": int((~a & b).sum()), "regressed": int((a & ~b).sum()),
            "unchanged_holdout_verified": True,
            "uncertainty": paired_group_bootstrap(before["observed"], before["predicted"], after["predicted"], groups, old["labels"]),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, help="Manifest including retained/rejected candidate locations")
    args = parser.parse_args()
    result = compare(args.baseline, args.candidates)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    for name, row in result["models"].items():
        print(f"{name}: {row['algorithm']}; accuracy {row['before']['accuracy']:.4f} -> {row['after']['accuracy']:.4f}; F1 {row['before']['f1_macro']:.4f} -> {row['after']['f1_macro']:.4f}")


if __name__ == "__main__":
    main()
