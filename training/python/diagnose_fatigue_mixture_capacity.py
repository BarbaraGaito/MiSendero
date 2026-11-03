"""Label-dependent capacity diagnostic, never a predictor or a goal score.

For each original training OOF case, inspect whether any continuous convex
mixture of the frozen member scores could make the actual native value a
maximizer. The answer is deliberately optimistic about ties and numerical
tolerance. No oracle weights are retained, no test outcome is used, and no
result from this module is accepted as model accuracy or a runtime input.
"""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from sklearn.model_selection import GroupKFold

import fatigue_view_ensemble as ensemble
from public_sources import digest

TOLERANCE = 1e-7
CONDITIONS = (("arithmetic", .75), ("arithmetic", 1.), ("arithmetic", 1.5), ("geometric", 1.))


def maximum_true_margin(member_scores, actual_native_value, kind="arithmetic", temperature=1.):
    values = ensemble.probabilities(member_scores)
    if actual_native_value != int(actual_native_value) or not 0 <= actual_native_value <= 10:
        raise ValueError("An original native integer outcome is required for this diagnostic")
    actual_native_value = int(actual_native_value)
    if kind == "arithmetic":
        transformed = values**(1./temperature)
        transformed /= transformed.sum(axis=1, keepdims=True)
    elif kind == "geometric" and temperature == 1.:
        transformed = np.log(values.clip(1e-15))
    else:
        raise ValueError("Unsupported frozen score-space diagnostic")
    alternatives = [i for i in range(11) if i != actual_native_value]
    difference = (transformed[:, alternatives]-transformed[:, actual_native_value, None]).T
    members = len(values)
    result = linprog(np.r_[np.zeros(members), -1.],
                     A_ub=np.c_[difference, np.ones(10)], b_ub=np.zeros(10),
                     A_eq=np.asarray([[*np.ones(members), 0.]]), b_eq=[1.],
                     bounds=[(0., 1.)]*members+[(None, None)], method="highs",
                     options={"primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9})
    if not result.success or result.status != 0 or not np.isfinite(result.fun):
        return None, int(result.status)
    # Returning only the maximum margin prevents an oracle routing table from
    # being mistaken for an inference artifact.
    return float(-result.fun), int(result.status)


def run():
    _, train, _, _, _, _, evidence, _ = ensemble.load_inputs()
    path = ensemble.DIRECTORY / "selection.json"
    selection = json.loads(path.read_text())
    if selection["status"] != "complete" or selection["plan"] != ensemble.plan():
        raise ValueError("Freeze the original fusion selection before this post-hoc diagnostic")
    signature = {"code_sha256": digest(Path(__file__)), "selection_sha256": digest(path),
                 "source_signature": ensemble.fingerprint(evidence), "scipy_version": importlib.metadata.version("scipy"),
                 "conditions": [{"kind": k, "temperature": t} for k, t in CONDITIONS], "optimistic_margin_tolerance": TOLERANCE}
    destination = ensemble.DIRECTORY / "capacity-diagnostic.json"
    if destination.exists():
        saved = json.loads(destination.read_text())
        if any(saved.get(k) != v for k, v in signature.items()):
            raise ValueError("Preserve the completed capacity diagnostic before changing its inputs")
        print(f"Frozen diagnostic retained: {saved['optimistic_possible_cases']}/487 potentially reachable; NOT model accuracy", flush=True)
        return
    scores = np.empty((len(train), 3, 11))
    point = np.empty((len(train), 3), dtype=object)
    for number, (_, val) in enumerate(GroupKFold(n_splits=5).split(train, groups=train["group_key"])):
        metadata_path = ensemble.DIRECTORY / "folds" / f"fold-{number}.json"
        metadata = json.loads(metadata_path.read_text())
        source_path = metadata_path.with_suffix(".npz")
        if digest(source_path) != metadata["npz_sha256"] or metadata["validation_row_keys"] != train.iloc[val]["row_key"].tolist():
            raise ValueError("Frozen OOF source scores changed")
        with np.load(source_path, allow_pickle=False) as source:
            for member, name in enumerate(ensemble.MEMBERS):
                scores[val, member] = ensemble.probabilities(source[name+"_scores"])
                point[val, member] = source[name+"_point"]
    truth = train["label"].str.removeprefix("Borg ").to_numpy(int)
    point_possible = np.any(point == train["label"].to_numpy()[:, None], axis=1)
    grid_possible = np.any(np.stack([r["oof_predictions"] for r in selection["results"]]) == train["label"].to_numpy(), axis=0)
    records, possible_count, unknown = [], 0, 0
    for i, actual in enumerate(truth):
        margins, statuses = [], []
        for kind, temperature in CONDITIONS:
            margin, status = maximum_true_margin(scores[i], actual, kind, temperature)
            margins.append(margin)
            statuses.append(status)
            unknown += int(margin is None)
        # Any solver failure is optimistically counted as reachable; no hard
        # or uncertain case is removed from the 487-case denominator.
        possible = bool(point_possible[i] or any(m is None or m >= -TOLERANCE for m in margins))
        if grid_possible[i] and not possible:
            raise ValueError("The optimistic continuous diagnostic contradicts an actually correct frozen recipe")
        possible_count += possible
        records.append({"row_key": train.iloc[i]["row_key"], "maximum_margins": margins,
                        "solver_status": statuses, "potentially_reachable_optimistic": possible})
        if (i+1) % 100 == 0 or i+1 == len(train):
            print(f"Label-dependent capacity diagnostic {i+1}/487, not inference", flush=True)
    report = {**signature, "version": 1, "post_selection_diagnostic": True, "uses_actual_training_outcomes": True,
              "test_outcomes_used": False, "model_accuracy": None, "goal_score": False, "runtime_use_permitted": False,
              "oracle_weights_retained": False, "native_training_cases": 487, "point_member_oracle_cases": int(point_possible.sum()),
              "frozen_grid_oracle_cases": int(grid_possible.sum()), "optimistic_possible_cases": possible_count,
              "solver_failures_counted_optimistically": unknown, "case_diagnostics": records,
              "scope": "Only the frozen OOF score vectors of these three members, with any nonnegative per-case weights summing to one, arithmetic temperatures 0.75/1/1.5 or geometric T=1, plus their three original point controls. Actual outcomes are used to pose an oracle optimization; ties and near-zero margins are accepted optimistically. This is a numerical representational diagnostic, not a trained router, a rigorous data-wide ceiling, test accuracy, deployment approval or proof that other models cannot reach 80%."}
    destination.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Optimistic capacity of this frozen score family: {possible_count}/487; solver failures={unknown}. NOT model accuracy or goal achievement.", flush=True)


if __name__ == "__main__":
    run()
