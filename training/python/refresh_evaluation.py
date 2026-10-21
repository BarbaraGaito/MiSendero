"""Extend audited evaluations using saved real observations; never fit or alter a model."""
import json
from datetime import datetime, timezone

import pandas as pd

from common.evaluation import holdout_details
from public_sources import ADAPTERS, OUTPUT, ROOT
from validate_public import validate


TARGETS = {"fatigue": "fatigueMetrics.json", "physio_risk": "riskMetrics.json",
           "route_difficulty": "routeDifficultyMetrics.json", "apn_route_difficulty": "apnRouteDifficultyMetrics.json"}


def extend_evaluation(metrics, rows, lineage, predictions):
    protocol = metrics["evaluation_protocol"]
    keyed = rows.assign(row_key=[item["row_key"] for item in lineage], group_key=[item["group_key"] for item in lineage])
    training = keyed[keyed["row_key"].isin(protocol["train_row_keys"])]
    group_by_key = dict(zip(keyed["row_key"], keyed["group_key"]))
    details = holdout_details(training["label"], predictions["observed"], predictions["predicted"], metrics["labels"],
                              training["group_key"], [group_by_key[key] for key in predictions["row_key"]])
    return {**metrics, "evaluation_details": details}


def main():
    # Verify all sources and existing results before changing any report.
    reports = {}
    for model in ADAPTERS:
        validate(model)
        directory = OUTPUT / model
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
        rows = pd.read_csv(directory / "dataset.csv", dtype={"label": str})
        predictions = pd.read_csv(directory / "test_predictions.csv", dtype=str)
        reports[model] = extend_evaluation(metrics, rows, provenance["lineage"], predictions)
    refreshed_at = datetime.now(timezone.utc).isoformat()
    for model, metrics in reports.items():
        metrics["evaluation_refreshed_at"] = refreshed_at
        text = json.dumps(metrics, indent=2, allow_nan=False) + "\n"
        (OUTPUT / model / "metrics.json").write_text(text, encoding="utf-8")
        (ROOT / "ai/models" / TARGETS[model]).write_text(text, encoding="utf-8")
        details = metrics["evaluation_details"]
        print(f"{model}: F1 macro={details['model']['f1_macro']:.4f}; baseline={details['baseline']['f1_macro']:.4f}; test groups={details['group_support']['test']}")


if __name__ == "__main__":
    main()
