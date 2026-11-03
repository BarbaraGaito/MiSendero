"""Learn native Borg likelihood conditional on the actual prior value.

The same 21 possible delta heads represent eleven physically valid native
outputs for each query. Conditional cross-entropy uses exactly those eleven
logits, while matched controls learn unconstrained deltas and clip at inference.
No native target is rescaled, synthesized, grouped or dropped.
"""
from __future__ import annotations

import copy
import importlib.metadata
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits
from torch import nn

from fatigue_dynamics import load_inputs as dynamics_inputs
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_extra_feedback import DIRECTORY as EXTRA_DIRECTORY, load as load_extra
from fatigue_features import RESEARCH
from fatigue_prior_views import DIRECTORY as VIEW_DIRECTORY, load as load_views
import fatigue_prior_view_training as views
from fatigue_probability import validate_calibration
from fatigue_warm_sgd import WarmNetwork, core_candidate
from public_sources import digest

DIRECTORY = RESEARCH / "conditional-native-borg-80-v1"


def native_logits(delta_logits, prior):
    if delta_logits.ndim != 2 or delta_logits.shape[1] != 21 or prior.shape != (len(delta_logits),):
        raise ValueError("A 21-delta logit vector and actual prior per query are required")
    prior_value = prior.to(torch.float64)
    if (not torch.isfinite(delta_logits).all() or not torch.isfinite(prior_value).all()
            or torch.any(prior_value != prior_value.round()) or torch.any((prior_value < 0) | (prior_value > 10))):
        raise ValueError("Finite logits and an original integer prior in 0-10 required")
    positions = torch.arange(11, device=delta_logits.device)[None, :]-prior.long()[:, None]+10
    return delta_logits.gather(1, positions)


def training_data(frame, pool, extra, initialization, extra_weight):
    if not np.isfinite(extra_weight) or extra_weight < 0:
        raise ValueError("A finite nonnegative weight for real additional reports is required")
    if initialization == "view":
        data, weights, keys = views.fitting_views(frame, pool, "prefix", .6)
    elif initialization == "core":
        data, weights, keys = frame.copy(), np.ones(len(frame)), []
    else:
        raise ValueError("Unknown frozen source initialization")
    selected = extra[extra["group_key"].isin(set(frame["group_key"]))].copy() if extra_weight > 0 else extra.iloc[:0].copy()
    if selected["row_key"].duplicated().any() or set(selected["row_key"]) & set(frame["row_key"]):
        raise ValueError("Additional actual targets duplicated original fitting queries")
    combined = pd.concat([data, selected], ignore_index=True)
    weights = np.r_[weights, np.full(len(selected), extra_weight)]
    if abs(weights.sum()-len(frame)-extra_weight*len(selected)) > 1e-9:
        raise ValueError("View replication changed actual-report supervision weight")
    validate_calibration(combined)
    target = combined["label"].str.removeprefix("Borg ").to_numpy(float)
    if not np.isfinite(target).all() or not np.isin(target, np.arange(11)).all():
        raise ValueError("Current fitting targets must be actual unchanged native integer outcomes")
    summary = {"unique_original_targets": len(frame), "optimization_input_views": len(keys),
               "extra_actual_targets": len(selected), "extra_report_weight": float(extra_weight),
               "total_supervision_weight": float(weights.sum())}
    return combined, weights, target.astype(int), summary


def make_source(frame, pool, initialization, specifications):
    with threadpool_limits(limits=1):
        if initialization == "core":
            source = DynamicsClassifier(specifications["core"]).fit(frame)
            preprocessor, classifier = source.model[:-1], source.model[-1]
            source_views = 0
        elif initialization == "view":
            source = views.PriorViewBorg(specifications["view"]).fit(frame, pool, specifications["core"])
            preprocessor, classifier = make_pipeline(source.imputer, source.scaler), source.model
            source_views = source.fit_summary["alternative_input_views"]
        else:
            raise ValueError("Unknown source initialization")
    return {"initialization": initialization, "fit_row_keys": frame["row_key"].tolist(),
            "features": specifications[initialization]["features"], "preprocessor": preprocessor,
            "classifier": classifier, "regularization": float(classifier.alpha), "source_input_views": source_views}


class ConditionalBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def transform(self, frame):
        return torch.tensor(self.preprocessing.transform(frame[self.features]), dtype=torch.float64)

    def fit(self, frame, pool, extra, specifications, source=None):
        validate_calibration(frame)
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(42)
        c = self.candidate
        if source is None:
            source = make_source(frame, pool, c["initialization"], specifications)
        if source["initialization"] != c["initialization"] or source["fit_row_keys"] != frame["row_key"].tolist():
            raise ValueError("A warm source includes different original fitting people/queries")
        self.features = list(source["features"])
        self.preprocessing = copy.deepcopy(source["preprocessor"])
        self.model = WarmNetwork(source["classifier"])
        self.regularization = source["regularization"]
        self.loss_endpoints, self.iterations, self.initialized_new_deltas = [], 0, []
        with torch.no_grad():
            order = torch.tensor(self.model.priority)
            delta = order[self.model(self.transform(frame))[:, order].argmax(dim=1)].numpy()-10
        reference = np.clip(source["classifier"].predict(source["preprocessor"].transform(frame[self.features])).astype(int)+frame["prior_borg"].to_numpy(int), 0, 10)
        np.testing.assert_array_equal(np.clip(delta+frame["prior_borg"].to_numpy(int), 0, 10), reference)
        self.training_summary = {"unique_original_targets": len(frame), "source_input_views": source["source_input_views"],
                                 "optimization_input_views": 0, "extra_actual_targets": 0, "extra_report_weight": 0.,
                                 "total_supervision_weight": float(len(frame))}
        if c["mode"] == "fine_tune":
            data, weights, target, summary = training_data(frame, pool, extra, c["initialization"], c["extra_weight"])
            self.training_summary.update(summary)
            x = self.transform(data)
            prior = torch.tensor(data["prior_borg"].to_numpy(int), dtype=torch.long)
            y = torch.tensor(target, dtype=torch.long)
            weight = torch.tensor(weights, dtype=torch.float64)
            delta_target = y-prior+10
            known = set(source["classifier"].classes_.astype(int))
            actual = set((target-data["prior_borg"].to_numpy(int)).tolist())
            self.initialized_new_deltas = sorted(actual-known)
            with torch.no_grad():
                for value in self.initialized_new_deltas:
                    self.model.layers[-1].bias[value+10] = -4.

            def objective():
                logits = self.model(x)
                if c["objective"] == "conditional_native":
                    losses = nn.functional.cross_entropy(native_logits(logits, prior), y, reduction="none")
                elif c["objective"] == "delta":
                    losses = nn.functional.cross_entropy(logits, delta_target, reduction="none")
                else:
                    raise ValueError("Unknown supervised likelihood")
                penalty = sum(p.square().sum() for name, p in self.model.named_parameters() if name.endswith("weight"))
                loss = (losses*weight).sum()/weight.sum()+self.regularization*penalty/(2.*weight.sum())
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite native Borg training objective")
                return loss

            self.loss_endpoints.append(float(objective().detach()))
            if c["optimizer"] == "lbfgs":
                optimizer = torch.optim.LBFGS(self.model.parameters(), lr=1., max_iter=c["budget"], max_eval=2*c["budget"],
                                              tolerance_grad=1e-7, tolerance_change=1e-10, line_search_fn="strong_wolfe")
                def closure():
                    optimizer.zero_grad(set_to_none=True)
                    loss = objective()
                    loss.backward()
                    if any(p.grad is None or not torch.isfinite(p.grad).all() for p in self.model.parameters()):
                        raise ValueError("Nonfinite native likelihood gradient")
                    return loss
                optimizer.step(closure)
                self.iterations = int(optimizer.state[next(self.model.parameters())]["n_iter"])
            elif c["optimizer"] == "adam":
                optimizer = torch.optim.Adam(self.model.parameters(), lr=.001, weight_decay=0.)
                schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=c["budget"], eta_min=.0001)
                for _ in range(c["budget"]):
                    optimizer.zero_grad(set_to_none=True)
                    loss = objective()
                    loss.backward()
                    if any(p.grad is None or not torch.isfinite(p.grad).all() for p in self.model.parameters()):
                        raise ValueError("Nonfinite native likelihood gradient")
                    nn.utils.clip_grad_norm_(self.model.parameters(), 5.)
                    optimizer.step()
                    schedule.step()
                self.iterations = c["budget"]
            else:
                raise ValueError("Unknown fixed training optimizer")
            self.loss_endpoints.append(float(objective().detach()))
        elif c["mode"] not in ("point_control", "condition_only"):
            raise ValueError("Unknown conditional model recipe")
        self.model.requires_grad_(False).eval()
        for parameter in self.model.parameters():
            parameter.grad = None
        return self

    def predict(self, frame):
        validate_calibration(frame)
        prior = frame["prior_borg"].to_numpy(int)
        with torch.no_grad():
            logits = self.model(self.transform(frame))
            if self.candidate["mode"] == "condition_only" or self.candidate.get("objective") == "conditional_native":
                scores = native_logits(logits, torch.tensor(prior)).numpy()
                values = scores.argmax(axis=1)
                # An exact tie including the observed prior repeats that prior.
                tie = scores[np.arange(len(frame)), prior] == scores.max(axis=1)
                values[tie] = prior[tie]
            else:
                order = torch.tensor(self.model.priority)
                delta = order[logits[:, order].argmax(dim=1)].numpy()-10
                values = np.clip(prior+delta, 0, 10)
        return np.asarray([f"Borg {i}" for i in values])


def plan(specifications):
    candidates = []
    for initialization in ("core", "view"):
        for mode in ("point_control", "condition_only"):
            candidates.append({"id": f"conditional-borg-{len(candidates):03d}", "initialization": initialization,
                               "mode": mode, "features": specifications[initialization]["features"]})
        for objective in ("delta", "conditional_native"):
            for extra_weight in (0., .5):
                for optimizer, budget in (("lbfgs", 200), ("lbfgs", 600), ("adam", 100), ("adam", 300)):
                    candidates.append({"id": f"conditional-borg-{len(candidates):03d}", "initialization": initialization,
                        "mode": "fine_tune", "objective": objective, "extra_weight": extra_weight,
                        "optimizer": optimizer, "budget": budget, "features": specifications[initialization]["features"]})
    return candidates


def load_inputs():
    frame, train, test, manifest, protocol = dynamics_inputs()
    pool, view_manifest = load_views()
    extra, extra_manifest = load_extra()
    path = views.DIRECTORY / "selection.json"
    selection = json.loads(path.read_text())
    signature = views.fingerprint(manifest, view_manifest)
    if (selection["status"] != "complete" or selection["test_used_for_selection"]
            or selection["train_row_keys"] != train["row_key"].tolist()
            or any(selection.get(k) != v for k, v in signature.items()) or selection["plan"] != views.plan(manifest)):
        raise ValueError("Frozen observed-history initialization changed")
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    specs = {"core": core_candidate(manifest), "view": winner["candidate"]}
    if specs["core"]["features"] != specs["view"]["features"] or specs["view"]["view_policy"] != "prefix" or specs["view"]["view_mass"] != .6:
        raise ValueError("This study preserves the already selected 13-feature prefix-view initialization")
    if set(extra["group_key"]) & set(test["group_key"]) or not set(extra["group_key"]) <= set(train["group_key"]):
        raise ValueError("Extra actual reports include reserved original people")
    inputs = {"dataset_sha256": manifest["dataset_sha256"], "view_dataset_sha256": view_manifest["dataset_sha256"],
              "view_provenance_sha256": digest(VIEW_DIRECTORY / "provenance.json"), "view_selection_sha256": digest(path),
              "extra_dataset_sha256": extra_manifest["dataset_sha256"], "extra_provenance_sha256": digest(EXTRA_DIRECTORY / "provenance.json"),
              "specifications": specs}
    return frame, train, test, manifest, protocol, pool, extra, inputs, winner


def fingerprint(inputs):
    helpers = ("fatigue_warm_sgd.py", "fatigue_dynamics_experiment.py", "fatigue_probability.py", "fatigue_prior_view_training.py", "fatigue_prior_views.py", "fatigue_extra_feedback.py")
    return {"code_sha256": digest(Path(__file__)), **inputs,
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "software_versions": {name: importlib.metadata.version(name) for name in ("torch", "numpy", "pandas", "scipy", "scikit-learn", "joblib")}}


def select():
    _, train, _, _, _, pool, extra, inputs, source_winner = load_inputs()
    signature = {**fingerprint(inputs), "plan": plan(inputs["specifications"]), "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "status": "running", "results": [], "target_accuracy": .8,
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True,
              "evaluation_denominator": 487, "test_denominator": 179, "minimum_cv_for_new_test_evaluation": .65,
              "new_observed_targets": 0, "synthetic_borg_targets": 0, "extra_actual_report_pool": len(extra),
              "policy": "Copy each participant-disjoint source MLP and fixed preprocessing exactly. Conditional likelihood uses only native logits compatible with the observed prior; matched delta-CE recipes retain clipping. Real extra reports are fitting-only and filtered by people before reading their labels. History input views retain total weight one per original report. No current/future predictor, native-label rescaling, report interpolation, validation stopping or easier evaluation denominator."}
    if path.exists():
        report = json.loads(path.read_text())
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen conditional native likelihood study changed")
    else:
        path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    source_folder, fold_folder = DIRECTORY / "sources", DIRECTORY / "folds"
    source_folder.mkdir(exist_ok=True)
    fold_folder.mkdir(exist_ok=True)
    sources = {}
    for initialization in ("core", "view"):
        for number, (fit, val) in enumerate(folds):
            fitting = train.iloc[fit]
            if set(fitting["group_key"]) & set(train.iloc[val]["group_key"]):
                raise ValueError("Conditional study leaked outer validation people")
            model_path = source_folder / f"{initialization}-fold-{number}.joblib"
            metadata_path = model_path.with_suffix(".json")
            identity = {"signature": fingerprint(inputs), "initialization": initialization, "fit_row_keys": fitting["row_key"].tolist()}
            if metadata_path.exists():
                saved = json.loads(metadata_path.read_text())
                if any(saved.get(k) != v for k, v in identity.items()) or digest(model_path) != saved["model_sha256"]:
                    raise ValueError("Warm source fitting pool or own cached model changed")
                source = joblib.load(model_path)
            else:
                source = make_source(fitting, pool, initialization, inputs["specifications"])
                joblib.dump(source, model_path)
                metadata_path.write_text(json.dumps({**identity, "model_sha256": digest(model_path)}, indent=2)+"\n", encoding="utf-8")
            sources[initialization, number] = source
        print(f"Conditional source {initialization}: all five fitting-only initializations verified", flush=True)
    for candidate in signature["plan"]:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted, evidence = np.empty(len(train), dtype=object), []
        for number, (fit, val) in enumerate(folds):
            fold_path = fold_folder / f"{candidate['id']}-fold-{number}.json"
            identity = {"signature": fingerprint(inputs), "candidate": candidate,
                        "fit_row_keys": train.iloc[fit]["row_key"].tolist(), "validation_row_keys": train.iloc[val]["row_key"].tolist()}
            if fold_path.exists():
                saved = json.loads(fold_path.read_text())
                if any(saved.get(k) != v for k, v in identity.items()):
                    raise ValueError("Conditional model fold checkpoint changed")
            else:
                with threadpool_limits(limits=1):
                    model = ConditionalBorg(candidate).fit(train.iloc[fit], pool, extra, inputs["specifications"], sources[candidate["initialization"], number])
                    decision = model.predict(train.iloc[val])
                saved = {**identity, "predicted": decision.tolist(), "training_summary": model.training_summary,
                         "loss_endpoints": model.loss_endpoints, "iterations": model.iterations,
                         "initialized_new_deltas": model.initialized_new_deltas}
                fold_path.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
            predicted[val] = saved["predicted"]
            evidence.append(saved)
        if candidate["mode"] == "point_control":
            if candidate["initialization"] == "core":
                old = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
                expected = next(r["oof_predictions"] for r in old["results"] if r["candidate"]["id"] == "alternative-023")
            else:
                expected = source_winner["oof_predictions"]
            np.testing.assert_array_equal(predicted, expected)
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(), "folds": evidence})
        winner = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"], best_cv_accuracy=winner["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(signature["plan"]) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Conditional native Borg {len(report['results'])}/{len(signature['plan'])}: CV={np.mean(scores):.6f}, best={winner['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
