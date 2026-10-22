"""Audit the sealed GeoFatigue holdout with ordinal, participant-aware metrics.

This reads existing predictions only. It does not retrain, relabel, or approve a
model for field use. Run from any directory with Python's standard library.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "training/data/public/fatigue"
OUTPUT = ROOT / "docs/fatigue-trekking-evaluation-2026-10-22/results.json"


def borg_number(label: str) -> int:
    if not label.startswith("Borg "):
        raise ValueError(f"Unexpected native label: {label}")
    value = int(label.removeprefix("Borg "))
    if not 0 <= value <= 10:
        raise ValueError(f"Out-of-range Borg value: {label}")
    return value


def scores(rows: list[dict], prediction_field: str) -> dict:
    observed = [borg_number(row["observed"]) for row in rows]
    predicted = [borg_number(row[prediction_field]) for row in rows]
    errors = [abs(a - b) for a, b in zip(observed, predicted)]
    n = len(rows)
    return {
        "n": n,
        "exact_accuracy": sum(e == 0 for e in errors) / n,
        "mae_borg_points": sum(errors) / n,
        "within_one_point": sum(e <= 1 for e in errors) / n,
        "errors_three_or_more_points": sum(e >= 3 for e in errors) / n,
    }


def participant_bootstrap(rows: list[dict], repetitions: int = 2000) -> dict:
    """Resample people, preserving all their observations in each draw."""
    by_person = defaultdict(list)
    for row in rows:
        by_person[row["group_key"]].append(row)
    groups = sorted(by_person)
    rng = random.Random(42)
    differences = []
    for _ in range(repetitions):
        sample = [row for key in rng.choices(groups, k=len(groups)) for row in by_person[key]]
        differences.append(scores(sample, "predicted")["mae_borg_points"] - scores(sample, "baseline")["mae_borg_points"])
    differences.sort()
    return {
        "unit": "participant",
        "repetitions": repetitions,
        "seed": 42,
        "mae_model_minus_baseline_95pct_percentile": [differences[int(.025 * repetitions)], differences[int(.975 * repetitions) - 1]],
    }


def main() -> None:
    metrics = json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))
    provenance_path = DATA / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    prediction_path = DATA / "test_predictions.csv"
    expected = metrics["test_predictions_sha256"]
    if hashlib.sha256(prediction_path.read_bytes()).hexdigest() != expected:
        raise ValueError("Sealed test predictions changed")
    if hashlib.sha256(provenance_path.read_bytes()).hexdigest() != metrics["evaluation_protocol"]["provenance_sha256"]:
        raise ValueError("Source provenance changed")
    if metrics["evaluation_validity"]["deployment_approved"] is not False:
        raise ValueError("Expected research-only model")
    lineage = {row["row_key"]: row["group_key"] for row in provenance["lineage"]}
    test_keys = metrics["evaluation_protocol"]["test_row_keys"]
    train_keys = metrics["evaluation_protocol"]["train_row_keys"]
    if len(lineage) != len(provenance["lineage"]) or set(test_keys) & set(train_keys):
        raise ValueError("Duplicate or overlapping data rows")
    if {lineage[key] for key in test_keys} & {lineage[key] for key in train_keys}:
        raise ValueError("Participant leakage")
    with prediction_path.open(newline="", encoding="utf-8") as source:
        predictions = list(csv.DictReader(source))
    if len(predictions) != len(test_keys) or {row["row_key"] for row in predictions} != set(test_keys):
        raise ValueError("Predictions do not match the sealed test")
    baseline = metrics["baseline"]["label"]
    rows = [{**row, "group_key": lineage[row["row_key"]], "baseline": baseline} for row in predictions]
    if len({row["group_key"] for row in rows}) != len(metrics["evaluation_protocol"]["test_groups"]):
        raise ValueError("Test participant count changed")
    for row in rows:
        borg_number(row["observed"])
        borg_number(row["predicted"])
    model_score = scores(rows, "predicted")
    baseline_score = scores(rows, "baseline")
    if abs(model_score["exact_accuracy"] - metrics["metrics"]["test"]["accuracy"]) > 1e-12:
        raise ValueError("Saved test accuracy disagrees with predictions")
    result = {
        "task": "GeoFatigue original modified Borg 0-10 ratings during 20-minute outdoor load carrying",
        "source": provenance["source"]["url"],
        "prediction_sha256": expected,
        "held_out_participants": len({row["group_key"] for row in rows}),
        "model": model_score,
        "training_majority_baseline": {"label": baseline, **baseline_score},
        "uncertainty": participant_bootstrap(rows),
        "scope": "In-source research evaluation only; no trekking fatigue ground truth or field performance estimate.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
