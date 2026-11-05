"""Score real trekking observations against a locked, person-held-out test set.

The input is one row per *observed response*, not one row per sensor sample.
This script never trains a model or creates labels. It refuses to report a
fatigue result when the manifest and reference measure different outcomes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path


REQUIRED_COLUMNS = {
    "participant_id", "route_id", "terrain", "reference_at", "predicted_at",
    "observed", "predicted",
}
TERRAINS = {"uphill", "downhill", "level", "rest"}
OUTCOMES = {"rof_0_10", "borg_modified_0_10"}


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"Timestamp needs a timezone: {value}")
    return result


def integer(value: object, name: str) -> int:
    if isinstance(value, bool) or str(value).strip() not in {str(n) for n in range(11)}:
        raise ValueError(f"{name} must be an integer from 0 through 10: {value!r}")
    return int(value)


def validate_manifest(manifest: dict) -> None:
    reference = manifest["reference_outcome"]
    model = manifest["model_outcome"]
    if reference not in OUTCOMES or model != reference:
        raise ValueError("Reference and model outcomes must be the same supported scale")
    if not manifest.get("model_version"):
        raise ValueError("A locked model_version is required")
    train = set(manifest["development_participant_ids"])
    test = set(manifest["test_participant_ids"])
    if not train or not test or train & test:
        raise ValueError("Development and test participants must be nonempty and disjoint")
    if len(train) != len(manifest["development_participant_ids"]) or len(test) != len(manifest["test_participant_ids"]):
        raise ValueError("Duplicate participant IDs in manifest")
    integer(manifest["baseline_constant"], "baseline_constant")
    if "alert_threshold" in manifest:
        integer(manifest["alert_threshold"], "alert_threshold")
    if manifest.get("route_transfer_test"):
        development_routes = set(manifest["development_route_ids"])
        test_routes = set(manifest["test_route_ids"])
        if not development_routes or not test_routes or development_routes & test_routes:
            raise ValueError("Route-transfer test requires disjoint route IDs")


def read_rows(path: Path, manifest: dict) -> list[dict]:
    rows = []
    seen = set()
    test_people = set(manifest["test_participant_ids"])
    test_routes = set(manifest.get("test_route_ids", []))
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not REQUIRED_COLUMNS <= set(reader.fieldnames):
            raise ValueError(f"CSV requires columns: {', '.join(sorted(REQUIRED_COLUMNS))}")
        for line, row in enumerate(reader, 2):
            person = row["participant_id"].strip()
            route = row["route_id"].strip()
            if person not in test_people or not route:
                raise ValueError(f"Line {line}: participant is not in the sealed test or route is blank")
            if manifest.get("route_transfer_test") and route not in test_routes:
                raise ValueError(f"Line {line}: route is not in the sealed route-transfer test")
            terrain = row["terrain"].strip().lower()
            if terrain not in TERRAINS:
                raise ValueError(f"Line {line}: unknown terrain {terrain!r}")
            reference_at = timestamp(row["reference_at"].strip())
            predicted_at = timestamp(row["predicted_at"].strip())
            if predicted_at >= reference_at:
                raise ValueError(f"Line {line}: prediction must precede the reference response")
            key = (person, route, reference_at)
            if key in seen:
                raise ValueError(f"Line {line}: duplicate reference response")
            seen.add(key)
            observed = integer(row["observed"], f"line {line} observed")
            raw_prediction = row["predicted"].strip()
            prediction = integer(raw_prediction, f"line {line} predicted") if raw_prediction else None
            rows.append({"participant_id": person, "route_id": route, "terrain": terrain,
                         "observed": observed, "predicted": prediction})
    if not rows:
        raise ValueError("No observed responses")
    if {row["participant_id"] for row in rows} != test_people:
        raise ValueError("Some sealed test participants have no observations")
    return rows


def score(rows: list[dict], prediction_key: str, threshold: int | None) -> dict:
    evaluated = [row for row in rows if row[prediction_key] is not None]
    result = {"responses": len(rows), "predictions_available": len(evaluated),
              "coverage": len(evaluated) / len(rows) if rows else None}
    if not evaluated:
        return result
    errors = [abs(row["observed"] - row[prediction_key]) for row in evaluated]
    result.update({"exact_accuracy": sum(error == 0 for error in errors) / len(errors),
                   "within_one_accuracy": sum(error <= 1 for error in errors) / len(errors),
                   "mae_points": sum(errors) / len(errors),
                   "errors_three_or_more": sum(error >= 3 for error in errors)})
    if threshold is not None:
        tp = sum(row["observed"] >= threshold and row[prediction_key] >= threshold for row in evaluated)
        fp = sum(row["observed"] < threshold and row[prediction_key] >= threshold for row in evaluated)
        fn = sum(row["observed"] >= threshold and row[prediction_key] < threshold for row in evaluated)
        tn = len(evaluated) - tp - fp - fn
        result["alert"] = {"threshold": threshold, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                           "precision_ppv": tp / (tp + fp) if tp + fp else None,
                           "sensitivity": tp / (tp + fn) if tp + fn else None,
                           "specificity": tn / (tn + fp) if tn + fp else None}
    return result


def bootstrap(rows: list[dict], threshold: int | None, repetitions: int = 5000) -> dict:
    people = sorted({row["participant_id"] for row in rows})
    by_person = defaultdict(list)
    for row in rows:
        by_person[row["participant_id"]].append(row)
    rng = random.Random(42)
    exact, mae, mae_difference = [], [], []
    alert_values = {"precision_ppv": [], "sensitivity": [], "specificity": []}
    for _ in range(repetitions):
        sample = [row for person in rng.choices(people, k=len(people)) for row in by_person[person]]
        model = score(sample, "predicted", threshold)
        if model["predictions_available"] == 0:
            continue
        baseline = score([row for row in sample if row["predicted"] is not None], "baseline", None)
        exact.append(model["exact_accuracy"])
        mae.append(model["mae_points"])
        mae_difference.append(model["mae_points"] - baseline["mae_points"])
        if threshold is not None:
            for name, values in alert_values.items():
                if model["alert"][name] is not None:
                    values.append(model["alert"][name])

    def interval(values: list[float]) -> list[float] | None:
        if not values:
            return None
        values.sort()
        return [values[int(.025 * len(values))], values[min(len(values) - 1, int(.975 * len(values)))]]

    return {"unit": "participant", "seed": 42, "resamples": repetitions,
            "exact_accuracy_95pct": interval(exact), "mae_points_95pct": interval(mae),
            "model_minus_baseline_mae_95pct": interval(mae_difference),
            "alert_95pct": {name: {"interval": interval(values),
                                   "defined_resamples": len(values)}
                            for name, values in alert_values.items()} if threshold is not None else None}


def evaluate(rows: list[dict], manifest: dict) -> dict:
    threshold = manifest.get("alert_threshold")
    prepared = [{**row, "baseline": integer(manifest["baseline_constant"], "baseline_constant")}
                for row in rows]
    model = score(prepared, "predicted", threshold)
    baseline = score([row for row in prepared if row["predicted"] is not None], "baseline", threshold)
    baseline_all = score(prepared, "baseline", threshold)
    return {"reference_outcome": manifest["reference_outcome"],
            "model_version": manifest["model_version"],
            "participants": len({row["participant_id"] for row in rows}),
            "routes": len({row["route_id"] for row in rows}),
            "observed_label_counts": {str(n): sum(row["observed"] == n for row in rows)
                                      for n in range(11)},
            "model": model, "constant_baseline_same_coverage": baseline,
            "constant_baseline_all_responses": baseline_all,
            "by_terrain": {terrain: score([row for row in prepared if row["terrain"] == terrain],
                                          "predicted", threshold)
                           for terrain in sorted(TERRAINS) if any(row["terrain"] == terrain for row in rows)},
            "uncertainty": bootstrap(prepared, threshold)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.manifest.resolve(), args.observations.resolve()}:
        parser.error("Output path must differ from manifest and observations")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    result = evaluate(read_rows(args.observations, manifest), manifest)
    result["input_sha256"] = {
        "manifest": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "observations": hashlib.sha256(args.observations.read_bytes()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
