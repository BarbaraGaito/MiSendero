"""Predeclared equal-weight ensembles across native MLP initializations."""
from __future__ import annotations

import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_conditional_borg as parent
from fatigue_probability import native_scores
from public_sources import digest

DIRECTORY = parent.RESEARCH / "initialization-ensemble-80-v1"
SEEDS = [42, *range(32)]


def decide(scores, prior):
    scores, prior = np.asarray(scores, dtype=float), np.asarray(prior, dtype=float)
    if prior.ndim != 1 or not np.isfinite(prior).all() or not np.isin(prior, np.arange(11)).all():
        raise ValueError("Actual native prior values required")
    prior = prior.astype(int)
    if scores.shape != (len(prior), 11) or not np.isfinite(scores).all() or np.any(scores < 0):
        raise ValueError("Finite native score vectors required")
    maximum = scores.max(axis=1)
    result = scores.argmax(axis=1)
    repeat = scores[np.arange(len(prior)), prior] == maximum
    result[repeat] = prior[repeat]
    return np.asarray([f"Borg {v}" for v in result])


def ensemble_predict(probabilities, points, prior, method, count):
    p, points = np.asarray(probabilities, dtype=float), np.asarray(points)
    if (p.ndim != 3 or p.shape[2] != 11 or points.shape != p.shape[:2]
            or not 1 <= count <= len(p) or not np.isfinite(p).all() or np.any(p < 0)
            or not np.isin(points, np.arange(11)).all()):
        raise ValueError("Aligned member probabilities and native point decisions required")
    if not np.allclose(p.sum(axis=2), 1., rtol=0, atol=1e-10):
        raise ValueError("Each member must conserve native probability mass")
    points = points.astype(int)
    if method == "point_control":
        return np.asarray([f"Borg {v}" for v in points[0]])
    if method == "mean_probability":
        scores = p[:count].mean(axis=0)
    elif method == "majority_vote":
        scores = np.zeros_like(p[0])
        for values in points[:count]:
            scores[np.arange(len(values)), values] += 1.
    else:
        raise ValueError("Unknown frozen initialization aggregation")
    return decide(scores, prior)


class InitializationEnsemble:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame, pool, extra, specifications, template=None):
        family = self.candidate["family"]
        source = template if template is not None else parent.make_source(frame, pool, family, specifications)
        if source["initialization"] != family or source["fit_row_keys"] != frame["row_key"].tolist():
            raise ValueError("A source preprocessing state includes different fitting cases")
        self.features = list(source["features"])
        self.preprocessing = copy.deepcopy(source["preprocessor"])
        data, weights, target, self.training_summary = parent.training_data(frame, pool, extra, family, 0.)
        x = self.preprocessing.transform(data[self.features])
        target = (target-data["prior_borg"].to_numpy(int)).astype(str)
        self.models, self.training_diagnostics = [], []
        for seed in SEEDS[:self.candidate["members"]]:
            if seed == 42:
                model, warning_count = copy.deepcopy(source["classifier"]), 0
            else:
                model = clone(source["classifier"]).set_params(random_state=seed)
                with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
                    warnings.simplefilter("always")
                    if family == "core":
                        model.fit(x, target)
                    else:
                        model.fit(x, target, sample_weight=weights)
                warning_count = len(caught)
            self.models.append(model)
            self.training_diagnostics.append({"seed": seed, "iterations": int(model.n_iter_), "warnings": warning_count})
        return self

    def member_scores(self, frame):
        parent.validate_calibration(frame)
        x = self.preprocessing.transform(frame[self.features])
        prior = frame["prior_borg"].to_numpy(int)
        with threadpool_limits(limits=1):
            scores = np.stack([native_scores(model, x, prior) for model in self.models])
            points = np.stack([np.clip(model.predict(x).astype(int)+prior, 0, 10) for model in self.models])
        return scores, points

    def predict(self, frame):
        scores, points = self.member_scores(frame)
        return ensemble_predict(scores, points, frame["prior_borg"].to_numpy(int), self.candidate["method"], len(self.models))


def plan():
    result = []
    for family in ("core", "view"):
        result.append({"id": f"initialization-{len(result):03d}", "family": family, "method": "point_control", "members": 1})
        for count in (8, 16, 33):
            for method in ("mean_probability", "majority_vote"):
                result.append({"id": f"initialization-{len(result):03d}", "family": family, "method": method, "members": count})
    return result


def fingerprint(inputs):
    return {"code_sha256": digest(Path(__file__)), "parent_fingerprint": parent.fingerprint(inputs),
        "parent_selection_sha256": digest(parent.DIRECTORY / "selection.json"), "seeds": SEEDS,
        "native_score_code_sha256": digest(Path(__file__).with_name("fatigue_probability.py")), "worker_processes": 2}


def compute_fold(job):
    number, fit, val, signature = job
    _, train, _, _, _, pool, extra, inputs, _ = parent.load_inputs()
    if signature != fingerprint(inputs):
        raise ValueError("Frozen initialization experiment changed in a worker")
    fitting, validation = train.iloc[fit], train.iloc[val]
    if set(fitting["group_key"]) & set(validation["group_key"]):
        raise ValueError("Initialization fitting leaked validation people")
    arrays, details = {}, {}
    for family in ("core", "view"):
        path = parent.DIRECTORY / "sources" / f"{family}-fold-{number}.joblib"
        descriptor = json.loads(path.with_suffix(".json").read_text())
        if descriptor["signature"] != signature["parent_fingerprint"] or descriptor["model_sha256"] != digest(path):
            raise ValueError("Saved source template changed")
        template = joblib.load(path)
        c = {"family": family, "members": 33, "method": "mean_probability"}
        model = InitializationEnsemble(c).fit(fitting, pool, extra, inputs["specifications"], template)
        arrays[family+"_scores"], arrays[family+"_points"] = model.member_scores(validation)
        details[family] = {"source_model_sha256": descriptor["model_sha256"], "training_summary": model.training_summary,
                           "member_training": model.training_diagnostics}
    return {"signature": signature, "fold_number": number, "fit_row_keys": fitting["row_key"].tolist(),
            "validation_row_keys": validation["row_key"].tolist(), "details": details}, arrays


def save(report):
    path = DIRECTORY / "selection.json"
    text = json.dumps(report, indent=2, allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(text, encoding="utf-8")
    path.write_text(text, encoding="utf-8")


def select():
    _, train, test, _, _, _, _, inputs, _ = parent.load_inputs()
    signature, candidates = fingerprint(inputs), plan()
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY / "folds").mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "status": "running", "plan": candidates,
        "train_row_keys": train["row_key"].tolist(), "results": [], "target_accuracy": .8,
        "evaluation_denominator": len(train), "test_denominator": len(test), "test_used_for_selection": False,
        "previous_benchmark_results_are_published": True, "minimum_cv_for_new_test_evaluation": .65,
        "new_native_borg_targets": 0,
        "policy": "Equal-weight predeclared prefixes of 33 independent initializations, no favorable-seed selection. Core and observed-history-view source recipes stay fixed. Each original report retains total fitting weight one. All fitting/preprocessing excludes validation people; test cases and exact Borg targets stay unchanged. No current/future target predictor or test tuning."}
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k, v in signature.items()) or old["plan"] != candidates or old["train_row_keys"] != report["train_row_keys"]:
            raise ValueError("Frozen initialization source, code, plan or cases changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    jobs = []
    for number, (fit, val) in enumerate(folds):
        data_path = DIRECTORY / "folds" / f"fold-{number}.npz"
        metadata_path = data_path.with_suffix(".json")
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            if (metadata["signature"] != signature or metadata["npz_sha256"] != digest(data_path)
                    or metadata["fit_row_keys"] != train.iloc[fit]["row_key"].tolist()
                    or metadata["validation_row_keys"] != train.iloc[val]["row_key"].tolist()):
                raise ValueError("Saved initialization fold changed")
        else:
            jobs.append((number, fit, val, signature))
    if jobs:
        with ProcessPoolExecutor(max_workers=2) as executor:
            pending = [executor.submit(compute_fold, job) for job in jobs]
            for future in as_completed(pending):
                metadata, arrays = future.result()
                data_path = DIRECTORY / "folds" / f"fold-{metadata['fold_number']}.npz"
                np.savez_compressed(data_path, **arrays)
                metadata["npz_sha256"] = digest(data_path)
                data_path.with_suffix(".json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
                print(f"Initialization ensemble fitting-only fold {metadata['fold_number']+1}/5 complete: 66 member networks", flush=True)
    probabilities = {family: np.empty((33, len(train), 11)) for family in ("core", "view")}
    points = {family: np.empty((33, len(train)), dtype=int) for family in ("core", "view")}
    for number, (_, val) in enumerate(folds):
        with np.load(DIRECTORY / "folds" / f"fold-{number}.npz", allow_pickle=False) as data:
            if set(data.files) != {f+suffix for f in ("core", "view") for suffix in ("_scores", "_points")}:
                raise ValueError("Unexpected target/identity field in member score cache")
            for family in ("core", "view"):
                probabilities[family][:, val], points[family][:, val] = data[family+"_scores"], data[family+"_points"]
    previous = json.loads((parent.DIRECTORY / "selection.json").read_text())
    for c in candidates:
        if any(r["candidate"] == c for r in report["results"]):
            continue
        predicted = ensemble_predict(probabilities[c["family"]], points[c["family"]], train["prior_borg"].to_numpy(int), c["method"], c["members"])
        if c["method"] == "point_control":
            expected = next(r["oof_predictions"] for r in previous["results"] if r["candidate"]["initialization"] == c["family"] and r["candidate"]["mode"] == "point_control")
            np.testing.assert_array_equal(predicted, expected)
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": c, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist()})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        save(report)
        print(f"Initialization recipe {len(report['results'])}/14 {c['id']}: CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
