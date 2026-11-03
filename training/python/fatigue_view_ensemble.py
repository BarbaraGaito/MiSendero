"""Frozen fusion of native Borg probabilities from three grouped-fit models.

Members are the incumbent MLP, the previous CatBoost CV winner and the
observed-history-view MLP. Mixture rules are selected using original training
queries only. Original point decisions remain explicit reproducibility controls.
"""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_catboost as catboost
import fatigue_prior_view_training as view_training
from fatigue_dynamics import load_inputs as dynamics_inputs
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from fatigue_prior_views import DIRECTORY as VIEW_DIRECTORY, load as load_views
from fatigue_probability import native_scores, validate_calibration
from fatigue_warm_sgd import core_candidate
from public_sources import digest

DIRECTORY = RESEARCH / "view-probability-ensemble-80-v1"
MEMBERS = ("core", "cat", "view")


def probabilities(values):
    values = np.asarray(values, dtype=float)
    if (values.ndim != 2 or values.shape[1] != 11 or not np.isfinite(values).all()
            or np.any(values < 0) or not np.allclose(values.sum(axis=1), 1., rtol=0, atol=1e-10)):
        raise ValueError("Finite normalized probabilities for the eleven native Borg values required")
    return values


def fuse_scores(scores, recipe):
    weights = np.asarray(recipe["weights"], dtype=float)
    temperature = float(recipe["temperature"])
    if weights.shape != (3,) or not np.isfinite(weights).all() or np.any(weights < 0) or not np.isclose(weights.sum(), 1.) or not np.isfinite(temperature) or not temperature > 0:
        raise ValueError("Nonnegative simplex mixture weights and a positive temperature required")
    active = [(probabilities(scores[name]), weight) for name, weight in zip(MEMBERS, weights) if weight > 0]
    if len({len(values) for values, _ in active}) != 1:
        raise ValueError("Member score rows do not match")
    if recipe["kind"] == "arithmetic":
        result = np.zeros_like(active[0][0])
        for values, weight in active:
            scaled = values**(1./temperature)
            result += weight*scaled/scaled.sum(axis=1, keepdims=True)
    elif recipe["kind"] == "geometric":
        # A common temperature would not change a geometric mixture's argmax,
        # so only T=1 is part of the plan. A numerical floor keeps disjoint
        # learned supports finite; it does not create supervised observations.
        if temperature != 1.:
            raise ValueError("Geometric recipes use the single nonredundant common temperature")
        logits = sum(weight*np.log(values.clip(1e-15)) for values, weight in active)
        result = np.exp(logits-logits.max(axis=1, keepdims=True))
    else:
        raise ValueError("Unknown probability fusion rule")
    result /= result.sum(axis=1, keepdims=True)
    return probabilities(result)


def native_labels(scores):
    return np.asarray([f"Borg {i}" for i in probabilities(scores).argmax(axis=1)])


def prepare_frame(frame):
    validate_calibration(frame)
    columns = ["terrain_"+name for name in catboost.TERRAINS]
    terrain = frame[columns]
    if not terrain.isin([0, 1]).all().all() or not terrain.sum(axis=1).eq(1).all():
        raise ValueError("Exactly one known terrain is required")
    derived = np.asarray(catboost.TERRAINS)[terrain.to_numpy().argmax(axis=1)]
    if "current_terrain" in frame and not np.array_equal(derived, frame["current_terrain"]):
        raise ValueError("Categorical terrain contradicts the original task context")
    return frame.assign(current_terrain=derived)


class ViewProbabilityEnsemble:
    def __init__(self, candidate, specifications):
        self.candidate, self.specifications = candidate, specifications

    def fit(self, frame, pool):
        frame = prepare_frame(frame)
        with threadpool_limits(limits=1):
            self.core = DynamicsClassifier(self.specifications["core"]).fit(frame)
            self.cat = catboost.CatBoostBorg(self.specifications["cat"]).fit(frame)
            self.view = view_training.PriorViewBorg(self.specifications["view"]).fit(frame, pool, self.specifications["core"])
        return self

    def point_predictions(self, frame):
        frame = prepare_frame(frame)
        return {name: getattr(self, name).predict(frame) for name in MEMBERS}

    def member_scores(self, frame):
        frame = prepare_frame(frame)
        previous = frame["prior_borg"].to_numpy(float)
        core = native_scores(self.core.model, frame[self.specifications["core"]["features"]], previous if self.specifications["core"]["target_mode"] == "change_from_prior" else None)
        cat = native_scores(self.cat.model, frame[self.specifications["cat"]["features"]], previous if self.specifications["cat"]["target_mode"] == "change_from_prior" else None)
        features = self.view.scaler.transform(self.view.imputer.transform(frame[self.specifications["view"]["features"]]))
        view = native_scores(self.view.model, features, previous if self.specifications["view"]["target_mode"] == "change_from_prior" else None)
        return {name: probabilities(values) for name, values in zip(MEMBERS, (core, cat, view))}

    def predict_scores(self, frame):
        if self.candidate["kind"] == "point_control":
            frame = prepare_frame(frame)
            chosen = getattr(self, self.candidate["member"]).predict(frame)
            native = np.asarray([int(x.removeprefix("Borg ")) for x in chosen])
            return np.eye(11)[native]
        return fuse_scores(self.member_scores(frame), self.candidate)

    def predict(self, frame):
        return native_labels(self.predict_scores(frame))


def plan():
    candidates = [{"id": f"view-ensemble-{i:03d}", "kind": "point_control", "member": name} for i, name in enumerate(MEMBERS)]
    # Include single-member native-probability decisions separately from the
    # original delta-head point decisions: boundary aggregation may differ.
    for i in range(3):
        weights = [float(j == i) for j in range(3)]
        candidates.append({"id": f"view-ensemble-{len(candidates):03d}", "kind": "arithmetic", "temperature": 1., "weights": weights})
    for i in range(5):
        for j in range(5-i):
            weights = [i/4., j/4., (4-i-j)/4.]
            if sum(value > 0 for value in weights) < 2:
                continue
            for kind, temperature in [("arithmetic", t) for t in (.75, 1., 1.5)]+[("geometric", 1.)]:
                candidates.append({"id": f"view-ensemble-{len(candidates):03d}", "kind": kind,
                                   "temperature": temperature, "weights": weights})
    return candidates


def load_inputs():
    frame, train, test, manifest, protocol = catboost.load_inputs()
    native, native_train, native_test, native_manifest, _ = dynamics_inputs()
    if frame["row_key"].tolist() != native["row_key"].tolist() or train["row_key"].tolist() != native_train["row_key"].tolist() or test["row_key"].tolist() != native_test["row_key"].tolist():
        raise ValueError("Ensemble parents disagree on original query identities")
    pool, view_manifest = load_views()
    cat_path, view_path = catboost.DIRECTORY / "selection.json", view_training.DIRECTORY / "selection.json"
    reports = {"cat": json.loads(cat_path.read_text()), "view": json.loads(view_path.read_text())}
    for report in reports.values():
        if report["status"] != "complete" or report["test_used_for_selection"] or report["train_row_keys"] != train["row_key"].tolist():
            raise ValueError("A member was not selected on the original completed training CV")
    cat_report = reports["cat"]
    if cat_report["code_sha256"] != digest(Path(catboost.__file__)) or cat_report["dataset_sha256"] != manifest["dataset_sha256"] or cat_report["plan"] != catboost.plan(manifest):
        raise ValueError("Frozen CatBoost member inputs changed")
    signature = view_training.fingerprint(native_manifest, view_manifest)
    if any(reports["view"].get(k) != v for k, v in signature.items()) or reports["view"]["plan"] != view_training.plan(native_manifest):
        raise ValueError("Frozen observed-history-view member inputs changed")
    winners = {name: max(report["results"], key=lambda r: r["accuracy_mean"]) for name, report in reports.items()}
    for name, winner in winners.items():
        if winner["candidate"]["id"] != reports[name]["winner_id"]:
            raise ValueError("Member differs from its original grouped CV winner")
    specs = {"core": core_candidate(native_manifest), **{name: r["candidate"] for name, r in winners.items()}}
    common = list(dict.fromkeys([*specs["core"]["features"], *[c for c in specs["cat"]["features"] if c != "current_terrain"]]))
    np.testing.assert_array_equal(frame[common].to_numpy(float), native[common].to_numpy(float))
    evidence = {"phone_dataset_sha256": manifest["dataset_sha256"], "native_dataset_sha256": native_manifest["dataset_sha256"],
                "cat_selection_sha256": digest(cat_path), "view_selection_sha256": digest(view_path),
                "view_dataset_sha256": view_manifest["dataset_sha256"], "view_provenance_sha256": digest(VIEW_DIRECTORY / "provenance.json"),
                "member_specifications": specs, "runtime_features": common}
    return frame, train, test, manifest, protocol, pool, evidence, winners


def fingerprint(evidence):
    helpers = ("fatigue_catboost.py", "fatigue_prior_view_training.py", "fatigue_prior_views.py", "fatigue_probability.py",
               "fatigue_dynamics_experiment.py", "fatigue_phone_experiment.py", "fatigue_dynamics.py", "fatigue_warm_sgd.py")
    return {"code_sha256": digest(Path(__file__)), **evidence,
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "software_versions": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scikit-learn", "catboost", "joblib")}}


def select():
    _, train, _, _, _, pool, inputs, source_winners = load_inputs()
    signature = {**fingerprint(inputs), "plan": plan(), "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "status": "running", "results": [], "target_accuracy": .8,
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "minimum_cv_for_new_test_evaluation": .65, "evaluation_denominator": 487, "test_denominator": 179,
              "new_observed_targets": 0, "synthetic_borg_targets": 0, "native_scale_values": list(range(11)),
              "policy": "Fit all members only on each outer fold's people. Observed-history views are filtered by fitting query/person and keep total report weight one. Select fixed probability recipes only from all 487 original native training queries. The three historical point controls must reproduce their saved OOF decisions exactly. No current/future label predictor, identity routing, discarded query or easier test denominator."}
    if path.exists():
        report = json.loads(path.read_text())
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen ensemble recipe/data/model/runtime changed")
    else:
        path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    scores = {name: np.empty((len(train), 11)) for name in MEMBERS}
    point = {name: np.empty(len(train), dtype=object) for name in MEMBERS}
    fold_evidence = []
    directory = DIRECTORY / "folds"
    directory.mkdir(exist_ok=True)
    for number, (fit, val) in enumerate(folds):
        fitting, validation = train.iloc[fit], train.iloc[val]
        if set(fitting["group_key"]) & set(validation["group_key"]):
            raise ValueError("Ensemble member fit leaked validation people")
        identity = {"signature": fingerprint(inputs), "fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist()}
        data_path, meta_path = directory / f"fold-{number}.npz", directory / f"fold-{number}.json"
        if meta_path.exists():
            saved = json.loads(meta_path.read_text())
            if any(saved.get(k) != v for k, v in identity.items()) or saved["npz_sha256"] != digest(data_path):
                raise ValueError("Frozen ensemble fold score cache changed")
        else:
            with threadpool_limits(limits=1):
                model = ViewProbabilityEnsemble(plan()[0], inputs["member_specifications"]).fit(fitting, pool)
                score, prediction = model.member_scores(validation), model.point_predictions(validation)
            np.savez_compressed(data_path, **{name+"_scores": score[name] for name in MEMBERS},
                                **{name+"_point": prediction[name].astype(str) for name in MEMBERS})
            saved = {**identity, "npz_sha256": digest(data_path), "view_fitting_summary": model.view.fit_summary}
            meta_path.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        with np.load(data_path, allow_pickle=False) as cached:
            if set(cached.files) != {name+suffix for name in MEMBERS for suffix in ("_scores", "_point")}:
                raise ValueError("Unexpected target or identity channel in ensemble score cache")
            for name in MEMBERS:
                scores[name][val] = probabilities(cached[name+"_scores"])
                point[name][val] = cached[name+"_point"]
        fold_evidence.append(saved)
        print(f"Ensemble native probability folds {number+1}/5 verified", flush=True)
    expected = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in expected["results"] if r["candidate"]["id"] == "alternative-023")
    np.testing.assert_array_equal(point["core"], expected)
    for name in ("cat", "view"):
        np.testing.assert_array_equal(point[name], source_winners[name]["oof_predictions"])
    report["folds"] = fold_evidence
    truth = train["label"].to_numpy()
    report["point_member_disagreement_cases"] = int(np.any(np.stack(list(point.values())) != point["core"], axis=0).sum())
    report["diagnostic_point_member_oracle_correct"] = int(np.any(np.stack(list(point.values())) == truth, axis=0).sum())
    for recipe in signature["plan"]:
        if any(r["candidate"] == recipe for r in report["results"]):
            continue
        predicted = point[recipe["member"]] if recipe["kind"] == "point_control" else native_labels(fuse_scores(scores, recipe))
        accuracy = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": recipe, "accuracy_mean": float(np.mean(accuracy)), "fold_accuracy": accuracy,
                                  "pooled_oof_accuracy": float(accuracy_score(truth, predicted)), "oof_predictions": predicted.tolist()})
        winner = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"], best_cv_accuracy=winner["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(signature["plan"]) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Native probability fusion {len(report['results'])}/{len(signature['plan'])}: CV={np.mean(accuracy):.6f}, best={winner['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
