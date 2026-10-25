"""Train/evaluate native public labels with a sealed group-held-out test.

Outputs are research artifacts. Exporting a forest does not authorize using a
different label, time scale or population in the mobile app.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupShuffleSplit

from common.evaluation import evaluate_training_run, holdout_details
from common.audit_selection import audit_selection
from common.export_classifier import export_classifier, predict_json, predict_proba_json
from common.selection import cross_validate_candidate, fit_candidate, make_estimator, select_candidate
from public_sources import ADAPTERS, OUTPUT, ROOT, build_public_dataset, digest


def group_split(frame: pd.DataFrame, geographic_holdout: dict | None = None):
    groups = frame["group_key"]
    if groups.nunique() < 4:
        raise ValueError("At least four independent groups are required; do not fall back to row splitting")
    if geographic_holdout:
        test_units = set(geographic_holdout["test_units"])
        field = "park" if geographic_holdout["unit"] == "park" else "regions"
        units = frame["lineage"].map(lambda row: {row[field]} if field == "park" else set(row[field]))
        observed = set().union(*units)
        if not test_units <= observed:
            raise ValueError("Prespecified geographic test units are absent; do not silently change the holdout")
        if any(unit & test_units and unit - test_units for unit in units):
            raise ValueError("Connected network crosses the geographic test boundary")
        is_test = units.map(lambda unit: bool(unit & test_units)).to_numpy()
        train, test = np.flatnonzero(~is_test), np.flatnonzero(is_test)
        if not len(train) or not len(test):
            raise ValueError("Empty prespecified geographic partition")
    else:
        # One fixed split. Never search seeds or select a test partition for scores.
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=42)
        train, test = next(splitter.split(frame, groups=groups))
    if set(groups.iloc[train]) & set(groups.iloc[test]):
        raise AssertionError("Group leakage")
    return train, test


def grouped_cv(features, labels, groups, params):
    return cross_validate_candidate(features, labels, groups,
                                    {"algorithm": "random_forest", "params": {"class_weight": "balanced", **params}})


def baseline_for(y_train, y_test):
    counts = y_train.value_counts()
    majority = str(counts.index[0])
    tied = sorted(str(label) for label in counts[counts.eq(counts.max())].index)
    return {
        "strategy": "most_frequent_training_label", "label": majority,
        "test_accuracy": float(accuracy_score(y_test, [majority] * len(y_test))),
        "training_counts": {str(label): int(count) for label, count in counts.items()},
        "tie_breaker": "First occurrence in original training partition; never select using test results",
        # Report every equally frequent training label when tied. These are
        # counterfactual reference scores, not selection of the best test label.
        "tied_labels_test_accuracy": {label: float(accuracy_score(y_test, [label] * len(y_test))) for label in tied},
    }


def train(model: str, *, tune_only=False, use_selection=False) -> dict:
    frame, provenance = build_public_dataset(model)
    features = provenance["features"]
    geographic_holdout = provenance["source"].get("geographic_holdout")
    train_idx, test_idx = group_split(frame, geographic_holdout)
    x_train, x_test = frame.iloc[train_idx][features], frame.iloc[test_idx][features]
    y_train, y_test = frame.iloc[train_idx]["label"], frame.iloc[test_idx]["label"]
    groups = frame.iloc[train_idx]["group_key"]
    if y_train.nunique() < 2:
        raise ValueError("Fixed training partition has fewer than two observed labels; no test-seed search permitted")
    directory = OUTPUT / model
    selection_path = directory / "selection.json"
    inputs = {"dataset_sha256": provenance["dataset_sha256"],
              "provenance_sha256": digest(directory / "provenance.json"),
              "train_row_keys": frame.iloc[train_idx]["row_key"].tolist(), "features": features}
    if use_selection:
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        winner = audit_selection(selection, x_train, y_train, groups, inputs)
        candidate, cv = winner["candidate"], winner["cv"]
    else:
        candidate, cv, selection = select_candidate(x_train, y_train, groups,
            lambda done, total, score: print(f"{model}: train-only search {done}/{total}, best CV F1={score:.4f}", flush=True))
        selection["inputs"] = inputs
        selection_path.write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
    print(f"{model}: selected {candidate['algorithm']} CV F1={cv['f1_macro_mean']:.4f}, gain={selection['cv_gain_over_legacy']:.4f}", flush=True)
    if tune_only:
        return selection
    params = candidate["params"]
    clf = make_estimator(candidate)
    fit_warnings = fit_candidate(clf, candidate, x_train, y_train)
    labels = sorted(frame["label"].unique())
    # The audited grouped CV above is the only cross-validation result.
    metrics = evaluate_training_run(
        clf=clf, dataset_name={"fatigue": "Fatiga observada — Borg nativo", "physio_risk": "AMS observado — estudio nocturno", "route_difficulty": "Tramos argentinos — OSM + IGN", "apn_route_difficulty": "Recorridos argentinos — dificultad APN"}[model],
        declared_source=provenance["source"]["source"], source_note=provenance["source"]["scope"],
        feature_cols=features, labels=labels, full_features=frame[features], full_labels=frame["label"],
        x_train=x_train, x_test=x_test, y_train=y_train, y_test=y_test,
    )
    metrics["metrics"]["cross_validation"] = {k: v for k, v in cv.items() if k not in ("partitions", "oof_predictions")}
    warnings = [provenance["source"]["scope"], *metrics["guardrails"]["warnings"]]
    unseen = sorted(set(y_test) - set(y_train))
    if unseen:
        warnings.append("Etiquetas observadas solo en test, sin ejemplos de entrenamiento: " + ", ".join(unseen))
    warnings.append("Todas las filas de entrenamiento, validación y prueba son observaciones públicas; no se generan datos sintéticos.")
    if cv["convergence_warnings"] or fit_warnings:
        warnings.append("El optimizador alcanzó el límite de iteraciones en algún ajuste; revisar las advertencias de convergencia conservadas en el informe.")
    metrics["guardrails"]["status"] = "requires_more_real_data" if metrics["guardrails"]["insufficient_real_data"] or groups.nunique() < 10 else "review_recommended"
    metrics["guardrails"]["warnings"] = warnings
    metrics["guardrails"]["high_variance_risk"] = cv["f1_macro_std"] > 0.18
    metrics["trained_at"] = datetime.now(timezone.utc).isoformat()
    metrics["evaluation_validity"] = {
        "real_public_ground_truth": True, "status": "observed_public_labels_group_holdout",
        "reason": provenance["source"]["scope"], "deployment_approved": False,
        "native_labels": True, "synthetic_rows": 0,
    }
    metrics["baseline"] = baseline_for(y_train, y_test)
    metrics["hyperparameters"] = {**params, "algorithm": candidate["algorithm"], "random_state": 42,
                                  "selection_method": "cross_validated", "cv_folds": cv["folds"], "cv_f1_macro_mean": cv["f1_macro_mean"]}
    classifier = clf.named_steps["classifier"] if hasattr(clf, "named_steps") else clf
    metrics["hyperparameters"]["effective_parameters"] = classifier.get_params(deep=False)
    metrics["hyperparameters"]["standard_scaler"] = hasattr(clf, "named_steps")
    metrics["model_selection"] = {key: selection[key] for key in (
        "version", "objective", "candidate_count", "candidate_plan_sha256", "winner_id",
        "legacy_winner_id", "cv_gain_over_legacy", "test_used_for_selection", "interpretation")}
    metrics["model_selection"]["selection_sha256"] = digest(selection_path)
    metrics["model_selection"]["final_fit_convergence_warnings"] = fit_warnings
    import platform
    import sklearn
    metrics["reproducibility"] = {"python": platform.python_version(), "numpy": np.__version__,
                                  "sklearn": sklearn.__version__, "seed": 42,
                                  "code_sha256": {name: digest(ROOT / "training/python" / name) for name in (
                                      "train_public.py", "common/selection.py", "common/export_classifier.py")}}
    metrics["evaluation_protocol"] = {
        "seed": 42, "split": "geographic_holdout" if geographic_holdout else "group_holdout", "independent_group_count": int(frame["group_key"].nunique()),
        **({"geographic_holdout": geographic_holdout} if geographic_holdout else {}),
        "train_groups": sorted(set(groups)), "test_groups": sorted(set(frame.iloc[test_idx]["group_key"])),
        "train_row_keys": frame.iloc[train_idx]["row_key"].tolist(), "test_row_keys": frame.iloc[test_idx]["row_key"].tolist(),
        "cv_training_only": True, "cv_partitions": cv["partitions"],
        "provenance_sha256": digest(OUTPUT / model / "provenance.json"),
    }
    # Held-out predictions permit independent recomputation of every metric.
    test_prediction = clf.predict(x_test)
    metrics["evaluation_details"] = holdout_details(y_train, y_test, test_prediction, labels,
                                                   frame.iloc[train_idx]["group_key"], frame.iloc[test_idx]["group_key"])
    payload = export_classifier(clf, features, candidate["algorithm"], metrics["evaluation_validity"])
    if not np.allclose(predict_proba_json(payload, frame[features]), clf.predict_proba(frame[features]), atol=1e-10, rtol=1e-10):
        raise AssertionError("Exported classifier probabilities differ from fitted estimator")
    if not np.array_equal(predict_json(payload, x_test), test_prediction):
        raise AssertionError("Exported classifier differs from held-out predictions")
    pd.DataFrame({"row_key": frame.iloc[test_idx]["row_key"].to_numpy(), "observed": y_test.to_numpy(), "predicted": test_prediction}).to_csv(directory / "test_predictions.csv", index=False)
    metrics["test_predictions_sha256"] = digest(directory / "test_predictions.csv")
    artifact = "model.forest.json" if payload["type"] == "random_forest_json" else "model.classifier.json"
    (directory / artifact).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    stale = directory / ("model.classifier.json" if artifact == "model.forest.json" else "model.forest.json")
    if stale.exists():
        stale.unlink()
    metrics["model_artifact"] = {"path": artifact, "sha256": digest(directory / artifact), "algorithm": candidate["algorithm"]}
    (OUTPUT / model / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    target = {"fatigue": "fatigueMetrics.json", "physio_risk": "riskMetrics.json", "route_difficulty": "routeDifficultyMetrics.json", "apn_route_difficulty": "apnRouteDifficultyMetrics.json"}[model]
    (ROOT / "ai/models" / target).write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"{model}: real_rows={len(frame)} train={len(train_idx)} test={len(test_idx)} groups={frame['group_key'].nunique()} test_accuracy={metrics['accuracy']:.3f}", flush=True)
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=list(ADAPTERS), action="append")
    parser.add_argument("--tune-only", action="store_true", help="Save train-only selection without evaluating the holdout")
    parser.add_argument("--use-selection", action="store_true", help="Evaluate the previously frozen selection, without searching again")
    args = parser.parse_args()
    for model in args.model or list(ADAPTERS):
        train(model, tune_only=args.tune_only, use_selection=args.use_selection)


if __name__ == "__main__":
    main()
