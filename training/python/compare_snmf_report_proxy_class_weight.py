"""Compare class-weighted and unweighted logistic fire-report proxies.

Research only: keeps January 2026 as a temporal holdout and never selects a
model or threshold from the test metrics. The target is a SNMF report proxy,
not verified fire occurrence or ignition probability.
"""
from __future__ import annotations

import argparse
import json

from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from environmental_sources import ROOT, sha256
from train_snmf_report_proxy_gfs_model import (
    EVENT_AUDIT, PROXY_FILES, WEATHER_FILES, choose_validation_threshold,
    load_labels, load_weather_with_geography, summarize_split,
)

BASE = ROOT / "docs/environmental-models-2026-10-22"


def fit_candidate(train, validation, test, feature_columns, class_weight):
    transformer = ColumnTransformer([
        ("weather", StandardScaler(), feature_columns),
        ("region", OneHotEncoder(handle_unknown="ignore"), ["region"]),
    ])
    model = make_pipeline(transformer, LogisticRegression(
        class_weight=class_weight, C=1.0, max_iter=3000,
        solver="lbfgs", random_state=42,
    ))
    columns = feature_columns + ["region"]
    model.fit(train[columns], train["label"])
    validation_probability = model.predict_proba(validation[columns])[:, 1]
    test_probability = model.predict_proba(test[columns])[:, 1]
    return validation_probability, test_probability


def main(weather_model: str):
    weather_files = WEATHER_FILES[weather_model]
    if not all(path.is_file() for path in weather_files + PROXY_FILES + [EVENT_AUDIT]):
        raise FileNotFoundError("Required local weather/proxy inputs are missing.")

    daily = load_weather_with_geography(weather_files)
    frame = load_labels().merge(daily, on=["region", "date"], how="inner", validate="one_to_one")
    feature_columns = [c for c in frame.columns if c not in ("label", "date", "region")]
    train = frame[(frame.date >= "2024-01-20") & (frame.date < "2025-12-01")].copy()
    validation = frame[(frame.date >= "2025-12-01") & (frame.date < "2026-01-01")].copy()
    test = frame[(frame.date >= "2026-01-01") & (frame.date < "2026-02-01")].copy()
    if train.empty or validation.empty or test.empty:
        raise ValueError("Temporal split unexpectedly empty.")

    candidates = {}
    for name, weight in (("balanced", "balanced"), ("unweighted", None)):
        val_probability, test_probability = fit_candidate(
            train, validation, test, feature_columns, weight,
        )
        y_val = validation.label.to_numpy(dtype=int)
        candidates[name] = {
            "class_weight": weight,
            "validation_average_precision": float(average_precision_score(y_val, val_probability)),
            "validation_brier_score": float(brier_score_loss(y_val, val_probability)),
            "validation_threshold": choose_validation_threshold(y_val, val_probability),
            "test_probability": test_probability,
        }

    # Predeclared selection uses validation average precision only. Ties prefer
    # lower validation Brier score; January is held out from model selection.
    selected_name = max(
        candidates,
        key=lambda name: (
            candidates[name]["validation_average_precision"],
            -candidates[name]["validation_brier_score"],
        ),
    )
    selected = candidates[selected_name]
    test_prob = selected["test_probability"]
    y_test = test.label.to_numpy(dtype=int)
    baseline_prob = float(train.label.mean())
    baseline_brier = float(brier_score_loss(y_test, np.full(len(y_test), baseline_prob)))
    event_audit = json.loads(EVENT_AUDIT.read_text(encoding="utf-8"))

    result = {
        "experiment_id": f"{weather_model}-snmf-proxy-class-weight-comparison-2026-jan",
        "candidate_status": "not_reliable_for_fire_prediction",
        "target": "SNMF-reported incident proxy within 10 km; not physical fire absence or ignition probability.",
        "protocol": {
            "train_period": "2024-01-20 through 2025-11-30",
            "validation_period": "2025-12-01 through 2025-12-31",
            "test_period": "2026-01-01 through 2026-01-31",
            "selection_rule": "Choose class_weight by validation average precision; tie-break by lower validation Brier. Threshold selection uses validation only, >=80% proxy precision and >=5 alerts.",
            "diagnostic_test_threshold": 0.5,
            "test_used_for_selection": False,
        },
        "data": {
            "weather_model": weather_model,
            "train_route_days": int(len(train)),
            "train_positive_route_days": int(train.label.sum()),
            "validation_route_days": int(len(validation)),
            "validation_positive_route_days": int(validation.label.sum()),
            "test_route_days": int(len(test)),
            "test_positive_route_days": int(y_test.sum()),
            "test_independent_route_sector_start_days": int(event_audit["results"]["10"]["unique_route_sector_start_days"]),
        },
        "source_sha256": {
            **{path.name: sha256(path) for path in weather_files + PROXY_FILES},
            EVENT_AUDIT.name: sha256(EVENT_AUDIT),
        },
        "validation_candidates": {
            name: {k: v for k, v in candidate.items() if k != "test_probability"}
            for name, candidate in candidates.items()
        },
        "selected_candidate": selected_name,
        "test_selected_candidate_diagnostic": summarize_split(test, test_prob),
        "test_training_prevalence_baseline": {
            "predicted_probability": baseline_prob,
            "brier_score": baseline_brier,
        },
        "test_brier_vs_baseline": {
            "model": float(brier_score_loss(y_test, test_prob)),
            "constant_prevalence": baseline_brier,
            "model_better": bool(brier_score_loss(y_test, test_prob) < baseline_brier),
        },
        "limitations": [
            "Validation contains very few positives; model selection is unstable.",
            "January labels are reported-incident proxies and may omit physical fires.",
            "Route-days repeat incidents; the event-start sample is very small.",
            "The 0.5 test threshold is diagnostic only if no validation threshold qualifies.",
            "No application or production artifact is changed.",
        ],
        "synthetic_observations": 0,
        "deployment_approved": False,
    }
    out = BASE / f"fire-{weather_model}-snmf-class-weight-comparison-2026-jan.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("source_sha256", "limitations")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weather-model", choices=sorted(WEATHER_FILES), default="jma_gsm")
    main(parser.parse_args().weather_model)
