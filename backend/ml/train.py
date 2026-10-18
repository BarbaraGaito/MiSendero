"""Offline, reproducible training and holdout evaluation. Never called by the API."""
import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn

from ranking import (SPEC, ALGORITHM, SEED, baseline, estimator, evaluate, matrix,
                     read_examples, sha256, spec_sha256, split_examples, sufficiency)


def train(catalog: Path, prepared: Path, output: Path, *, synthetic_test=False) -> dict:
    if (output / "model.joblib").exists() or (output / "metadata.json").exists():
        raise ValueError("Use a new version directory; never overwrite deployed artifacts")
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    examples_file = prepared / "examples.jsonl"
    if (manifest.get("schemaVersion") != 1 or manifest.get("featureSchemaVersion") != SPEC["version"]
            or manifest.get("featureNames") != SPEC["names"] or manifest.get("synthetic") is not synthetic_test
            or manifest.get("completeCandidateJudgments") is not True
            or manifest.get("catalogSha256") != sha256(catalog)
            or manifest.get("examplesSha256") != sha256(examples_file)):
        raise ValueError("Prepared data checksum/schema mismatch; re-run the Node export")
    snapshot = json.loads(catalog.read_text(encoding="utf-8"))
    candidates = snapshot["candidates"]
    ids = {c["trailId"] for c in candidates}
    rows = read_examples(examples_file, synthetic_test=synthetic_test)
    if manifest.get("rowCount") != len(rows) or manifest.get("catalogSize") != len(ids) or any(r["trailId"] not in ids for r in rows):
        raise ValueError("Prepared data does not match the catalog snapshot")
    report = {"status": "insufficient_real_data", "synthetic": synthetic_test, "technicalTestOnly": synthetic_test, "trained": False,
              "algorithm": ALGORITHM, "data": sufficiency(rows), "metrics": None,
              "limitation": "Catalog features are not preference/relevance labels; no real accuracy can be claimed."}
    output.mkdir(parents=True, exist_ok=True)
    if report["data"]["sufficient"]:
        training, validation, test = split_examples(rows)
        # Per-query weighting: queries with many judged candidates must not dominate learning.
        from collections import Counter
        counts = Counter(r["queryId"] for r in training)
        model = estimator()
        model.fit(matrix([r["features"] for r in training]), [r["relevance"] for r in training],
                  sample_weight=[1 / counts[r["queryId"]] for r in training])
        metrics = {}
        for name, partition in (("validation", validation), ("test", test)):
            metrics[name] = {"supervised": evaluate(partition, model.predict(matrix([r["features"] for r in partition])).tolist(), len(ids)),
                             "baseline": evaluate(partition, [baseline(r["features"]) for r in partition], len(ids))}
        val_ml, val_baseline = metrics["validation"]["supervised"], metrics["validation"]["baseline"]
        # Predeclared engineering promotion rule on validation ONLY; test is held-out reporting.
        deployable = (not synthetic_test and val_ml["ndcg@1"] is not None and val_baseline["ndcg@1"] is not None
                      and val_ml["ndcg@1"] >= val_baseline["ndcg@1"] + 0.01
                      and val_ml["ndcg@3"] >= val_baseline["ndcg@3"]
                      and val_ml["precision@1"] >= val_baseline["precision@1"]
                      and val_ml["hard_constraint_match_rate"] == 1)
        report.update(status="synthetic_technical_test" if synthetic_test else "supervised_evaluated" if deployable else "baseline_retained", trained=True,
                      metrics=metrics, deployable=deployable,
                      partitions={name: {"rows": len(part), "queries": len({r["queryId"] for r in part}), "participants": len({r["splitGroupId"] for r in part})}
                                  for name, part in (("training", training), ("validation", validation), ("test", test))})
        model_file = output / "model.joblib"
        joblib.dump(model, model_file, compress=3)
        code_hash = hashlib.sha256((Path(__file__).read_bytes() + Path(__file__).with_name("ranking.py").read_bytes())).hexdigest()
        spec_hash = spec_sha256()
        version = hashlib.sha256((manifest["examplesSha256"] + code_hash + spec_hash).encode()).hexdigest()[:12]
        meta = {"modelVersion": "rf-v1-" + version, "algorithm": ALGORITHM,
                "featureSchemaVersion": SPEC["version"], "featureNames": SPEC["names"], "seed": SEED,
                "featureSpecSha256": spec_hash, "trainingCodeSha256": code_hash,
                "preparationCodeSha256": manifest.get("preparationCodeSha256"),
                "modelSha256": sha256(model_file), "catalogSha256": manifest["catalogSha256"],
                "datasetSha256": manifest["examplesSha256"], "sklearnVersion": sklearn.__version__,
                "numpyVersion": np.__version__, "pythonMinor": ".".join(platform.python_version_tuple()[:2]),
                "trainedAt": datetime.now(timezone.utc).isoformat(), "synthetic": synthetic_test, "technicalTestOnly": synthetic_test, "deployable": deployable,
                "evaluation": metrics, "minimumDataPolicy": report["data"],
                "promotionRule": "validation NDCG@1 >= baseline + .01; NDCG@3 and Precision@1 noninferior; hard constraints = 1",
                "splitPolicy": "60/20/20 connected participant + identical preferences; warm catalog, unseen preference groups",
                "hyperparameters": model.get_params()}
        (output / "metadata.json").write_text(json.dumps(meta, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "training-status.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--prepared", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = train(args.catalog, args.prepared, args.output)
    print(json.dumps({"status": report["status"], "trained": report["trained"], "data": report["data"]}, indent=2))
    return 0 if report["trained"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError):
        print("Training refused: invalid or inconsistent prepared data. See the dataset contract.")
        raise SystemExit(1)
