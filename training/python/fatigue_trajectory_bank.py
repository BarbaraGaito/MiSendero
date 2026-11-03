"""Causal empirical trajectory forecasting of exact native Borg.

Each bank contains complete observed task trajectories of fitting people only.
An unseen person's actual earlier reports update a posterior over these
trajectories. Interpolation defines a prediction surface; it never creates
supervision rows or changes the original validation/test denominators.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr, softmax
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold

from fatigue_dynamics import load_inputs
from fatigue_features import RESEARCH
from public_sources import OUTPUT, RAW, digest, group_key, verify_source_snapshot

DIRECTORY = RESEARCH / "trajectory-bank-80-v1"
TERRAINS = ("flat_trail", "stairs", "ramp")


def observed_source():
    verify_source_snapshot("fatigue")
    reports = pd.read_csv(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
    reports["time"] = pd.to_datetime(reports["time"], utc=True)
    if reports.duplicated(["id", "time"]).any():
        raise ValueError("Ambiguous original questionnaire timestamp")
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    return reports, sessions


def query_for(reports, session, task, now, prior_borg, prior_age_minutes):
    old = reports[(reports["time"] >= pd.Timestamp(session["start_time"]))
                  & (reports["time"] <= now - pd.Timedelta(minutes=1))].sort_values("time")
    if old.empty or float(old.iloc[-1]["borg_scale"]) != prior_borg:
        raise ValueError("Recent observed Borg differs from the original chronological source")
    age = (now - old.iloc[-1]["time"]).total_seconds() / 60
    if not np.isclose(age, prior_age_minutes) or not 1 <= age <= 15 or not float(prior_borg).is_integer():
        raise ValueError("A real previous integer Borg aged 1-15 minutes is mandatory")
    history = []
    for _, report in old[old["task"].eq(1)].iterrows():
        matched = [t for t in session["tasks"] if t["label"] == report["task_label"]
                   and pd.Timestamp(t["start_time"]) <= report["time"] <= pd.Timestamp(t["end_time"])]
        if len(matched) != 1:
            raise ValueError("Earlier observed Borg is not linked to one published active task")
        history.append({"terrain": report["task_label"],
                        "elapsed_minutes": (report["time"] - pd.Timestamp(matched[0]["start_time"])).total_seconds() / 60,
                        "age_minutes": (now - report["time"]).total_seconds() / 60,
                        "observed_borg": float(report["borg_scale"])})
    if not history:
        raise ValueError("No actual past active-task feedback is available")
    return {"terrain": task["label"], "elapsed_minutes": (now - pd.Timestamp(task["start_time"])).total_seconds() / 60,
            "prior_borg": float(prior_borg), "prior_age_minutes": age, "history": history}


def build_queries(frame, reports, sessions):
    canonical = json.loads((OUTPUT / "fatigue/provenance.json").read_text(encoding="utf-8"))
    queries = []
    for index, evidence in enumerate(canonical["lineage"]):
        participant = "p" + re.search(r"/p(\d+)-", evidence["lineage"]["member"])[1]
        now = pd.Timestamp(evidence["lineage"]["label_time"])
        matched = [(s, t) for s in sessions[participant] for t in s["tasks"]
                   if pd.Timestamp(t["start_time"]) <= now <= pd.Timestamp(t["end_time"])]
        if len(matched) != 1:
            raise ValueError("Current query must belong to one original active task")
        session, task = matched[0]
        query = query_for(reports[reports["id"].eq(participant)], session, task, now,
                          float(frame.iloc[index]["prior_borg"]), float(frame.iloc[index]["prior_age_minutes"]))
        queries.append(query)
    return queries


def fit_bank(reports, sessions, allowed_groups):
    templates, all_rows = [], set()
    for participant, person_sessions in sessions.items():
        participant_group = group_key("GeoFatigue:" + participant)
        if participant_group not in allowed_groups:
            continue
        for session in person_sessions:
            curves = {}
            for task in session["tasks"]:
                start, end = pd.Timestamp(task["start_time"]), pd.Timestamp(task["end_time"])
                observed = reports[reports["id"].eq(participant) & reports["task"].eq(1)
                                   & reports["task_label"].eq(task["label"]) & reports["time"].between(start, end)].sort_values("time")
                if observed.empty:
                    continue
                values = observed["borg_scale"].to_numpy(float)
                if not np.isfinite(values).all() or np.any((values < 0) | (values > 10)):
                    raise ValueError("Template contains non-native or unobserved fatigue")
                all_rows.update(int(i) for i in observed.index)
                curves[task["label"]] = {"elapsed_minutes": ((observed["time"] - start).dt.total_seconds() / 60).tolist(),
                                         "observed_borg": values.tolist(), "original_response_rows": observed.index.tolist()}
            if curves:
                templates.append({"template_key": group_key("trajectory:" + participant + ":" + session["start_time"]),
                                  "group_key": participant_group, "prior_mass": 1. / len(person_sessions), "curves": curves})
    if not templates or set(t["group_key"] for t in templates) != set(allowed_groups):
        raise ValueError("Bank does not represent every fitting participant")
    return {"version": 1, "templates": templates, "fit_groups": sorted(allowed_groups),
            "actual_active_response_rows": sorted(all_rows), "interpolated_supervision_rows": 0,
            "note": "Includes actual published onset reports of fitting people, in addition to canonical active rows. Rest reports and unseen-person current/future reports never become fitting labels. Interpolation is for prediction only."}


def packed_query(bank, query, scope):
    prior, age = query["prior_borg"], query["prior_age_minutes"]
    if not np.isfinite(prior) or prior != round(prior) or not 0 <= prior <= 10 or not 1 <= age <= 15:
        raise ValueError("Missing, current, future or stale Borg is not a calibration input")
    history = [r for r in query["history"] if scope == "all_tasks" or r["terrain"] == query["terrain"]]
    if not history or any(r["age_minutes"] < 1 or not 0 <= r["observed_borg"] <= 10 for r in history):
        raise ValueError("Only actual earlier Borg reports may condition trajectories")
    templates = [t for t in bank["templates"] if query["terrain"] in t["curves"] and all(r["terrain"] in t["curves"] for r in history)]
    if not templates:
        raise ValueError("No learned trajectory covers this task context")
    def value(template, terrain, elapsed):
        curve = template["curves"][terrain]
        return float(np.interp(elapsed, curve["elapsed_minutes"], curve["observed_borg"]))
    current = np.asarray([value(t, query["terrain"], query["elapsed_minutes"]) for t in templates])
    earlier = np.asarray([[value(t, r["terrain"], r["elapsed_minutes"]) for t in templates] for r in history])
    return {"current": current, "earlier": earlier, "observed": np.asarray([r["observed_borg"] for r in history]),
            "ages": np.asarray([r["age_minutes"] for r in history]), "prior_mass": np.asarray([t["prior_mass"] for t in templates])}


def native_probabilities(means, sigma):
    upper = np.arange(11, dtype=float) + .5
    lower = upper - 1.
    lower[0], upper[-1] = -np.inf, np.inf
    return ndtr((upper - np.asarray(means)[..., None]) / sigma) - ndtr((lower - np.asarray(means)[..., None]) / sigma)


def predict_packed(packed, recipe):
    w = np.ones(len(packed["ages"])) if recipe["memory_minutes"] is None else np.exp(-packed["ages"] / recipe["memory_minutes"])
    errors = packed["observed"][:, None] - packed["earlier"]
    bias = np.clip((w[:, None] * errors).sum(axis=0) / (w.sum() + recipe["bias_shrinkage"]), -2., 2.)
    historical = native_probabilities(packed["earlier"] + bias, recipe["observation_sigma"])
    labels = packed["observed"].astype(int)
    likelihood = historical[np.arange(len(labels)), :, labels]
    posterior = softmax(np.log(packed["prior_mass"]) + (w[:, None] * np.log(np.maximum(likelihood, 1e-12))).sum(axis=0))
    return posterior @ native_probabilities(packed["current"] + bias, recipe["prediction_sigma"])


def predict_query(bank, query, recipe):
    return f"Borg {int(predict_packed(packed_query(bank, query, recipe['scope']), recipe).argmax())}"


def plan():
    return [{"id": f"trajectory-{i:03d}", "scope": scope, "observation_sigma": observation_sigma,
             "prediction_sigma": prediction_sigma, "bias_shrinkage": shrinkage, "memory_minutes": memory}
            for i, (scope, observation_sigma, prediction_sigma, shrinkage, memory) in enumerate(
                (s, o, p, b, m) for s in ("current_task", "all_tasks") for o in (.25, .5, 1.)
                for p in (.25, .5) for b in (0., 4., 16.) for m in (20., None))]


def select():
    reports, sessions = observed_source()
    frame, train, _, manifest, _ = load_inputs()
    queries = build_queries(frame, reports, sessions)
    recipes = plan()
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"], "plan": recipes,
                 "original_reports_sha256": digest(RAW / "geofatigue/self_reported_fatigue_level.original.tab"),
                 "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if any(saved[k] != v for k, v in signature.items()):
            raise ValueError("Frozen trajectory inputs changed; preserve previous run")
        if saved["status"] == "complete":
            print("Frozen trajectory search already complete", flush=True)
            return
    forecasts = {r["id"]: np.empty(len(train), dtype=object) for r in recipes}
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    evidence = []
    for fold, (fit, val) in enumerate(folds):
        fitting_groups, validation_groups = set(train.iloc[fit]["group_key"]), set(train.iloc[val]["group_key"])
        if fitting_groups & validation_groups:
            raise AssertionError("Trajectory bank leaked participant groups")
        bank = fit_bank(reports, sessions, fitting_groups)
        evidence.append({"fit_groups": sorted(fitting_groups), "validation_groups": sorted(validation_groups),
                         "actual_fitting_active_reports": len(bank["actual_active_response_rows"]), "templates": len(bank["templates"])})
        for position in val:
            query = queries[train.index[position]]
            packs = {scope: packed_query(bank, query, scope) for scope in ("current_task", "all_tasks")}
            for recipe in recipes:
                forecasts[recipe["id"]][position] = f"Borg {int(predict_packed(packs[recipe['scope']], recipe).argmax())}"
        print(f"Trajectory fold {fold+1}/5: {len(val)} unchanged validation rows, {len(bank['templates'])} fitting-session templates", flush=True)
    results = []
    for recipe in recipes:
        predicted = forecasts[recipe["id"]]
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        results.append({"candidate": recipe, "accuracy_mean": float(np.mean(scores)), "accuracy_std": float(np.std(scores)),
                        "fold_accuracy": scores, "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist()})
    best = max(results, key=lambda r: r["accuracy_mean"])
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "complete", "test_used_for_selection": False,
              "previous_benchmark_results_are_published": True, "folds": evidence, "results": results,
              "winner_id": best["candidate"]["id"], "best_cv_accuracy": best["accuracy_mean"], "interpolated_supervision_rows": 0}
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Frozen trajectory winner {best['candidate']}: exact native mean CV={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
