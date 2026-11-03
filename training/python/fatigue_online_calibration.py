"""Train-only selection of causal personal calibration of native Borg scores.

All base predictions for a person's validation rows come from a model fitted
without that person. Calibration for each row sees only actual earlier reports
from that session, never its current label or later labels. Native Borg remains
the target; zero predictions or difficult cases are never omitted.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import softmax
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from fatigue_dynamics import DIRECTORY as PARENT, load_inputs
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from fatigue_probability import native_scores
from public_sources import RAW, digest

DIRECTORY = RESEARCH / "online-calibration-80-v1"
SHIFTS = np.arange(-2, 3)


def shifted_scores(probabilities):
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 11 or not np.isfinite(probabilities).all() or np.any(probabilities < 0):
        raise ValueError("Finite native Borg score vectors required")
    if not np.allclose(probabilities.sum(axis=1), 1.):
        raise ValueError("Native Borg score vectors must sum to one")
    shifted = np.zeros((len(probabilities), len(SHIFTS), 11))
    for i, shift in enumerate(SHIFTS):
        for label in range(11):
            shifted[:, i, np.clip(label + shift, 0, 10)] += probabilities[:, label]
    return shifted


def adapt_one(current_scores, prior_scores, prior_observed, recipe):
    """The current label is deliberately absent from this function's inputs."""
    if recipe["kind"] == "unchanged" or len(prior_observed) == 0:
        return np.asarray(current_scores)
    observed = np.asarray(prior_observed, dtype=float)
    if not np.isfinite(observed).all() or np.any(observed != np.rint(observed)) or np.any((observed < 0) | (observed > 10)):
        raise ValueError("Only actual native earlier Borg reports may calibrate a model")
    translated = shifted_scores(prior_scores)
    likelihood = translated[np.arange(len(observed)), :, observed.astype(int)]
    weights = recipe["decay"] ** np.arange(len(observed) - 1, -1, -1)
    log_prior = -SHIFTS ** 2 / (2 * recipe["prior_std"] ** 2)
    log_likelihood = weights @ np.log(np.maximum(likelihood, .001))
    posterior = softmax(log_prior + recipe["strength"] * log_likelihood)
    return posterior @ shifted_scores(np.asarray(current_scores)[None, :])[0]


def temporal_metadata(frame, manifest):
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    by_key = {r["row_key"]: r for r in manifest["lineage"]}
    result = []
    for _, row in frame.iterrows():
        evidence = by_key[row["row_key"]]
        participant = "p" + re.search(r"/p(\d+)-", evidence["sensor_members"][0])[1]
        now = pd.Timestamp(evidence["response_time"])
        matched = [s for s in sessions[participant] if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"])]
        if len(matched) != 1:
            raise ValueError("Response has ambiguous session membership")
        result.append({"group_key": row["group_key"], "session_start": pd.Timestamp(matched[0]["start_time"]),
                       "task_start": pd.Timestamp(evidence["task_start"]), "response_time": now})
    return pd.DataFrame(result)


def history_indices(metadata, scope):
    if scope not in ("session", "task", "recent_two"):
        raise ValueError("Unknown online feedback scope")
    result = []
    for _, row in metadata.iterrows():
        mask = (metadata["group_key"].eq(row["group_key"]) & metadata["session_start"].eq(row["session_start"])
                & (metadata["response_time"] <= row["response_time"] - pd.Timedelta(minutes=1)))
        if scope == "task":
            mask &= metadata["task_start"].eq(row["task_start"])
        previous = metadata.loc[mask].sort_values("response_time").index.to_numpy()
        result.append(previous[-2:] if scope == "recent_two" else previous)
    return result


def recipes():
    choices = [{"id": "online-000", "kind": "unchanged", "scope": "session"}]
    for scope in ("session", "task", "recent_two"):
        for prior_std in (.3, .6, 1.):
            for strength in (.25, 1.):
                for decay in (.5, 1.):
                    choices.append({"id": f"online-{len(choices):03d}", "kind": "personal_bias_posterior", "scope": scope,
                                    "prior_std": prior_std, "strength": strength, "decay": decay})
    return choices


def member_pool(selection):
    if selection["status"] != "complete":
        raise ValueError("Wait for the existing dynamics search to finish before freezing its calibration pool")
    # Take the best validation member from each model family, then the top
    # three families. Held-out metrics/errors have no role in this decision.
    members, seen = [], set()
    for result in sorted(selection["results"], key=lambda r: r["accuracy_mean"], reverse=True):
        algorithm = result["candidate"]["algorithm"]
        if algorithm in seen:
            continue
        seen.add(algorithm)
        members.append(result["candidate"])
        if len(members) == 3:
            break
    return members


def select():
    _, train, _, manifest, _ = load_inputs()
    selection_path = PARENT / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection["dataset_sha256"] != manifest["dataset_sha256"] or selection["train_row_keys"] != train["row_key"].tolist():
        raise ValueError("Base member selection uses a different cohort")
    members = member_pool(selection)
    plan = recipes()
    signature = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
                 "base_selection_sha256": digest(selection_path), "base_members": members, "recipes": plan,
                 "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    descriptor_path = DIRECTORY / "inputs.json"
    if descriptor_path.exists() and json.loads(descriptor_path.read_text(encoding="utf-8")) != signature:
        raise ValueError("Frozen calibration experiment changed; preserve its previous results")
    descriptor_path.write_text(json.dumps(signature, indent=2) + "\n", encoding="utf-8")
    metadata = temporal_metadata(train, manifest)
    histories = {scope: history_indices(metadata, scope) for scope in ("session", "task", "recent_two")}
    truth = train["label"].str.removeprefix("Borg ").astype(int).to_numpy()
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    results, cached_scores = [], {}
    for index, candidate in enumerate(members):
        scores = np.zeros((len(train), 11))
        for fit, val in folds:
            if set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]):
                raise AssertionError("Online base fit leaked participants")
            with threadpool_limits(limits=1):
                model = DynamicsClassifier(candidate).fit(train.iloc[fit])
                prior = train.iloc[val]["prior_borg"].to_numpy(float) if candidate["target_mode"] == "change_from_prior" else None
                scores[val] = native_scores(model.model, train.iloc[val][candidate["features"]], prior)
        cached_scores[f"member_{index}"] = scores
        for recipe in plan:
            history = histories[recipe["scope"]]
            adapted = np.asarray([adapt_one(scores[i], scores[old], truth[old], recipe) for i, old in enumerate(history)])
            predicted = adapted.argmax(axis=1)
            fold_accuracy = [float(accuracy_score(truth[val], predicted[val])) for _, val in folds]
            results.append({"candidate": {"id": f"member-{index}-{recipe['id']}", "member": candidate, "recipe": recipe},
                            "accuracy_mean": float(np.mean(fold_accuracy)), "fold_accuracy": fold_accuracy,
                            "pooled_oof_accuracy": float(accuracy_score(truth, predicted)),
                            "oof_predictions": [f"Borg {i}" for i in predicted]})
        best = max(results, key=lambda r: r["accuracy_mean"])
        print(f"Online member {index+1}/{len(members)} {candidate['algorithm']}: unadjusted pooled CV={accuracy_score(truth,scores.argmax(axis=1)):.4f}, best online mean CV={best['accuracy_mean']:.4f}", flush=True)
    best = max(results, key=lambda r: r["accuracy_mean"])
    np.savez_compressed(DIRECTORY / "oof_scores.npz", **cached_scores)
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "complete",
              "objective": "exact_native_Borg_accuracy_on_unchanged_cohort", "test_used_for_selection": False,
              "previous_benchmark_results_are_published": True, "winner_id": best["candidate"]["id"],
              "best_cv_accuracy": best["accuracy_mean"], "results": results,
              "oof_scores_sha256": digest(DIRECTORY / "oof_scores.npz"),
              "score_semantics": "Uncalibrated native-class model scores with a personal shift posterior, not a clinical confidence estimate."}
    (DIRECTORY / "selection.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    select()
