"""Resumable exact-Borg CV; caller supplies only the original training people."""
import json
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits


def grouped_search(directory, train, candidates, fingerprint, estimator_type):
    if len(train) != 487 or train["group_key"].nunique() != 28 or not train["row_key"].is_unique:
        raise ValueError("Search must use the unchanged 487 responses of 28 original training people")
    directory.mkdir(exist_ok=True)
    path = directory / "selection.json"
    signature = {**fingerprint, "plan": candidates, "train_row_keys": train["row_key"].tolist()}
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "objective": "exact_native_Borg_accuracy_on_unchanged_cohort", "test_used_for_selection": False,
              "previous_benchmark_results_are_published": True}
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if any(previous.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen grouped experiment changed; preserve the previous version")
        report = previous
    done = {r["candidate"]["id"] for r in report["results"]}
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in candidates:
        if candidate["id"] in done:
            continue
        predictions = np.empty(len(train), dtype=object)
        scores, convergence = [], 0
        for fit, val in folds:
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise AssertionError("Grouped feedback search leaked participants")
            with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                warnings.simplefilter("always", ConvergenceWarning)
                fitted = estimator_type(candidate).fit(train.iloc[fit])
                values = fitted.predict(train.iloc[val])
            convergence += sum(issubclass(w.category, ConvergenceWarning) for w in caught)
            predictions[val] = values
            scores.append(float(accuracy_score(train.iloc[val]["label"], values)))
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                                  "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(train["label"], predictions)),
                                  "oof_predictions": predictions.tolist(), "convergence_warnings": convergence})
        winner = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"], best_cv_accuracy=winner["accuracy_mean"])
        content = json.dumps(report, indent=2, allow_nan=False) + "\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"{len(report['results'])}/{len(candidates)} {candidate['feature_set']} {candidate['algorithm']} {candidate['target_mode']}: CV={np.mean(scores):.4f}, best={winner['accuracy_mean']:.4f}", flush=True)
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
