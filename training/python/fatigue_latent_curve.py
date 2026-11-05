"""Native Borg forecasting with quantized latent fatigue trajectories.

Only actual fitting-person reports estimate population curve priors. Actual
earlier current-task reports update the unseen person's intercept/rate posterior.
The latent grid is numerical integration, not fabricated supervision. Current
and future Borg labels never enter a query, and no benchmark row is discarded.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr, softmax
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from fatigue_dynamics import load_inputs
from fatigue_features import RESEARCH
from fatigue_trajectory_bank import TERRAINS, build_queries, observed_source, native_probabilities
from public_sources import RAW, digest, group_key

DIRECTORY = RESEARCH / "latent-curve-80-v1"
GRID = np.asarray([(a, v) for a in np.arange(-1., 7.001, .25) for v in np.arange(-1., 5.001, .1)])


def fit_prior(reports, sessions, allowed_groups, power):
    coefficients = {t: [] for t in TERRAINS}
    weights = {t: [] for t in TERRAINS}
    used, represented = set(), set()
    for person, person_sessions in sessions.items():
        group = group_key("GeoFatigue:" + person)
        if group not in allowed_groups:
            continue
        for session in person_sessions:
            for task in session["tasks"]:
                begin, end = pd.Timestamp(task["start_time"]), pd.Timestamp(task["end_time"])
                rows = reports[reports["id"].eq(person) & reports["task"].eq(1) & reports["task_label"].eq(task["label"])
                               & reports["time"].between(begin, end)].sort_values("time")
                if len(rows) < 2:
                    continue
                minutes = (rows["time"] - begin).dt.total_seconds().to_numpy() / 60
                values = rows["borg_scale"].to_numpy(float)
                if not np.isfinite(values).all() or np.any((values < 0) | (values > 10)):
                    raise ValueError("Population prior requires actual native Borg reports")
                design = np.column_stack((np.ones(len(rows)), (minutes / 5) ** power))
                beta = np.linalg.lstsq(design, values, rcond=None)[0]
                coefficients[task["label"]].append(beta)
                weights[task["label"]].append(1. / len(person_sessions))
                used.update(int(i) for i in rows.index)
                represented.add(group)
    if represented != set(allowed_groups):
        raise ValueError("Some fitting participants are not represented in the curve prior")
    priors = {}
    for terrain in TERRAINS:
        values, w = np.asarray(coefficients[terrain]), np.asarray(weights[terrain])
        if len(values) < 2:
            raise ValueError("Too few fitting task trajectories")
        mean = np.average(values, axis=0, weights=w)
        error = values - mean
        covariance = (error.T * w) @ error / w.sum() + np.diag([.1, .025])
        priors[terrain] = {"mean": mean.tolist(), "covariance": covariance.tolist(), "actual_task_trajectories": len(values)}
    return {"power": power, "priors": priors, "fit_groups": sorted(allowed_groups),
            "actual_active_report_rows": sorted(used), "interpolated_supervision_rows": 0}


def pack_query(query, prior):
    age, borg = query["prior_age_minutes"], query["prior_borg"]
    if not 1 <= age <= 15 or not np.isfinite(borg) or borg != round(borg) or not 0 <= borg <= 10:
        raise ValueError("A real previous Borg aged 1-15 minutes is required")
    for row in query["history"]:
        old, elapsed, value = row["age_minutes"], row["elapsed_minutes"], row["observed_borg"]
        if not np.isfinite([old, elapsed, value]).all() or old < 1 or elapsed < 0 or value != round(value) or not 0 <= value <= 10:
            raise ValueError("History contains future, missing or non-native feedback")
    if np.any(np.diff([row["age_minutes"] for row in query["history"]]) >= 0):
        raise ValueError("Session feedback must be strictly chronological")
    # A session can contain the same terrain more than once. Current-task
    # membership follows its start time, not the terrain name alone.
    history = [r for r in query["history"] if r["terrain"] == query["terrain"]
               and np.isclose(r["elapsed_minutes"] + r["age_minutes"], query["elapsed_minutes"], rtol=0, atol=1e-6)]
    if not history or history[-1]["observed_borg"] != borg or not np.isclose(history[-1]["age_minutes"], age):
        raise ValueError("Current-task earlier reports differ from the original previous Borg")
    ages = np.asarray([r["age_minutes"] for r in history])
    labels = np.asarray([r["observed_borg"] for r in history])
    if not np.isfinite(ages).all() or (ages < 1).any() or not np.isfinite(labels).all() or np.any(labels != np.rint(labels)):
        raise ValueError("Only actual earlier integer reports may condition a curve")
    past_time = np.asarray([r["elapsed_minutes"] for r in history])
    if np.any(past_time < 0) or np.any(np.diff(past_time) <= 0):
        raise ValueError("Earlier task reports must be chronological")
    terrain_prior = prior["priors"][query["terrain"]]
    mean = np.asarray(terrain_prior["mean"])
    covariance = np.asarray(terrain_prior["covariance"])
    difference = GRID - mean
    quadratic = np.einsum("ij,jk,ik->i", difference, np.linalg.inv(covariance), difference)
    earlier = GRID[:, 0][None, :] + (past_time[:, None] / 5) ** prior["power"] * GRID[:, 1][None, :]
    current = GRID[:, 0] + (query["elapsed_minutes"] / 5) ** prior["power"] * GRID[:, 1]
    return {"quadratic": quadratic, "earlier": earlier, "current": current, "labels": labels, "ages": ages}


def probabilities(packed, recipe):
    sigma = recipe["observation_sigma"]
    observed = packed["labels"][:, None]
    lower, upper = observed - .5, observed + .5
    lower = np.where(observed == 0, -np.inf, lower)
    upper = np.where(observed == 10, np.inf, upper)
    likelihood = ndtr((upper - packed["earlier"]) / sigma) - ndtr((lower - packed["earlier"]) / sigma)
    weights = np.ones(len(observed)) if recipe["memory_minutes"] is None else np.exp(-packed["ages"] / recipe["memory_minutes"])
    posterior = softmax(-.5 * packed["quadratic"] / recipe["prior_covariance_scale"] + weights @ np.log(likelihood.clip(1e-15)))
    return posterior @ native_probabilities(packed["current"], sigma)


def predict_query(prior, query, recipe):
    return f"Borg {int(probabilities(pack_query(query, prior), recipe).argmax())}"


def plan():
    return [{"id": f"latent-curve-{i:03d}", "power": power, "observation_sigma": sigma,
             "prior_covariance_scale": scale, "memory_minutes": memory}
            for i, (power, sigma, scale, memory) in enumerate((p, s, c, m) for p in (.5, 1., 1.5)
                for s in (.1, .3, .6) for c in (1., 4.) for m in (10., None))]


def select():
    frame, train, _, manifest, _ = load_inputs()
    reports, sessions = observed_source()
    queries = build_queries(frame, reports, sessions)
    recipes = plan()
    signature = {"code_sha256": digest(Path(__file__)), "query_source_code_sha256": digest(Path(__file__).with_name("fatigue_trajectory_bank.py")),
                 "dataset_sha256": manifest["dataset_sha256"], "original_reports_sha256": digest(RAW / "geofatigue/self_reported_fatigue_level.original.tab"),
                 "plan": recipes, "train_row_keys": train["row_key"].tolist(), "integration_grid_points": len(GRID)}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if any(saved.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the frozen latent-curve search before changing inputs")
        if saved["status"] == "complete":
            print("Frozen latent-curve search already complete", flush=True)
            return
    predicted = {c["id"]: np.empty(len(train), dtype=object) for c in recipes}
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    evidence = []
    with threadpool_limits(limits=1):
        for fold, (fit, val) in enumerate(folds):
            fit_groups, val_groups = set(train.iloc[fit]["group_key"]), set(train.iloc[val]["group_key"])
            if fit_groups & val_groups:
                raise ValueError("Latent population prior leaked unseen people")
            learned = {power: fit_prior(reports, sessions, fit_groups, power) for power in (.5, 1., 1.5)}
            evidence.append({"fit_groups": sorted(fit_groups), "validation_groups": sorted(val_groups),
                             "actual_fitting_active_reports": len(learned[1.]["actual_active_report_rows"])})
            for position in val:
                query = queries[train.index[position]]
                packed = {p: pack_query(query, prior) for p, prior in learned.items()}
                for recipe in recipes:
                    predicted[recipe["id"]][position] = f"Borg {int(probabilities(packed[recipe['power']], recipe).argmax())}"
            print(f"Latent-curve fold {fold+1}/5: all {len(val)} original validation responses predicted", flush=True)
    results = []
    for candidate in recipes:
        values = predicted[candidate["id"]]
        scores = [float(accuracy_score(train.iloc[val]["label"], values[val])) for _, val in folds]
        results.append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                        "pooled_oof_accuracy": float(accuracy_score(train["label"], values)), "oof_predictions": values.tolist()})
    best = max(results, key=lambda r: r["accuracy_mean"])
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "complete", "results": results, "folds": evidence,
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "winner_id": best["candidate"]["id"], "best_cv_accuracy": best["accuracy_mean"], "interpolated_supervision_rows": 0,
              "note": "Actual fitting people include original active onset reports. A numerical latent grid is a prediction integral, not extra observed training labels. Native validation/test denominators remain 487/179."}
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Frozen latent-curve winner {best['candidate']['id']}: exact CV={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
